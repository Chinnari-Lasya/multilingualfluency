"""Optional LLM FALLBACK for hosts that cannot run the local checkpoints (e.g. a free 512 MB instance, no PyTorch).

Used ONLY when a local model is unavailable AND an OpenAI-compatible endpoint is configured through the same
GEC_LLM_* settings the translation service uses (GEC_LLM_BASE_URL, GEC_LLM_MODEL, GEC_LLM_API_KEY).
GEC_LLM_FALLBACK=off disables it. When the local models load, nothing here is ever called.

Two stand-ins, each mimicking the interface of the local object it replaces:
* ``LLMGenerator``   ~ Seq2SeqModel: ``generate()`` returns up to N candidate corrections. LLMs expose no sequence
  log-probability, so ``has_scores`` is False and O2/O3 must not derive model-probability evidence from it.
* ``LLMMeaningJudge`` ~ SentenceEmbedder: ``similarity()`` is an LLM-RATED meaning-preservation score in [0, 1],
  NOT an embedding cosine. The O3 thresholds were set for E5 cosine and are uncalibrated for this judge.
Every result produced through this path is labelled ``engine="llm_fallback"`` with the model id in its trace.
"""
from __future__ import annotations

import json
import os
import threading
import time

import httpx
import regex

from .errors import ModelUnavailableError
from .langs import LANGUAGES

_TRANSPORT: httpx.BaseTransport | None = None  # tests inject an httpx.MockTransport here
_CACHE: dict[tuple, object] = {}
_LOCK = threading.Lock()
N_CANDIDATES = 3


class LLMUnavailableError(ModelUnavailableError):
    """The LLM fallback is not configured or its call failed (message says why; never contains the key)."""


def _clean(v: str | None) -> str:
    return (v or "").strip().strip("'\"").strip()


# Tried in order after GEC_LLM_MODEL when the endpoint is Google's and GEC_LLM_BACKUP_MODELS is unset: the free tier
# often answers 429 (quota) or 503 (high demand) for one model while a lighter one still has capacity.
GOOGLE_BACKUP_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")


def endpoint_settings() -> dict | None:
    """The GEC_LLM_* OpenAI-compatible endpoint (also used by translation), or None when not configured.
    ``models`` = GEC_LLM_MODEL (comma-separated allowed) + GEC_LLM_BACKUP_MODELS (or Google defaults)."""
    base = _clean(os.environ.get("GEC_LLM_BASE_URL")).rstrip("/")
    primary = [m for m in (_clean(x) for x in os.environ.get("GEC_LLM_MODEL", "").split(",")) if m]
    if not (base and primary):
        return None
    raw = os.environ.get("GEC_LLM_BACKUP_MODELS")
    if raw is None:
        backups = list(GOOGLE_BACKUP_MODELS) if "generativelanguage.googleapis.com" in base else []
    else:
        backups = [m for m in (_clean(x) for x in raw.split(",")) if m]
    models = list(dict.fromkeys(primary + backups))
    return {"base_url": base, "model": models[0], "models": models, "api_key": _clean(os.environ.get("GEC_LLM_API_KEY"))}


def llm_settings() -> dict | None:
    """Settings for the correction fallback, or None when disabled (GEC_LLM_FALLBACK=off) / not configured."""
    if _clean(os.environ.get("GEC_LLM_FALLBACK", "auto")).lower() in ("off", "0", "false", "no", "none"):
        return None
    return endpoint_settings()


def describe_http_error(e: Exception) -> str:
    """Status code + the provider's own error message (e.g. Google's 'API key not valid'), never the request."""
    if isinstance(e, httpx.HTTPStatusError):
        r = e.response
        msg = ""
        try:
            j = r.json()
            j = j[0] if isinstance(j, list) and j else j
            err = j.get("error", j) if isinstance(j, dict) else j
            msg = err.get("message", "") if isinstance(err, dict) else str(err)
        except Exception:  # noqa: BLE001 - non-JSON body
            msg = r.text
        msg = " ".join(str(msg).split())[:300]
        return f"HTTP {r.status_code} from {r.request.url.host}" + (f": {msg}" if msg else "")
    if isinstance(e, httpx.TimeoutException):
        return "the provider timed out"
    if isinstance(e, httpx.HTTPError):
        return f"cannot reach the provider ({type(e).__name__})"
    return type(e).__name__


_NEXT_MODEL = (404, 429, 500, 502, 503, 504)  # not found / quota / overloaded: another model may still answer


class _TryNext(Exception):
    pass


def _chat_one(s: dict, model: str, prompt: str, max_tokens: int, timeout: float, attempts: int,
              transport: httpx.BaseTransport | None) -> str:
    headers = {"Authorization": f"Bearer {s['api_key']}"} if s["api_key"] else {}
    body = {"model": model, "temperature": 0, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=timeout, transport=transport or _TRANSPORT) as c:
                r = c.post(f"{s['base_url']}/chat/completions", json=body, headers=headers)
            if r.status_code in _NEXT_MODEL and r.status_code != 404 and attempt < attempts - 1:
                wait = r.headers.get("retry-after", "")
                time.sleep(min(float(wait) if wait.replace(".", "", 1).isdigit() else 2.0 * (attempt + 1), 8.0))
                continue
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code in _NEXT_MODEL:
                raise _TryNext(describe_http_error(e)) from e
            raise LLMUnavailableError(f"LLM call failed ({model}): {describe_http_error(e)}", model=model) from e
        except (httpx.TimeoutException, httpx.TransportError) as e:
            if attempt < attempts - 1:
                continue
            raise _TryNext(describe_http_error(e)) from e
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise _TryNext(f"unexpected response shape ({type(e).__name__})") from e
        if not content or not str(content).strip():
            raise _TryNext("empty answer")
        return str(content).strip()
    raise _TryNext("no answer")  # pragma: no cover - loop always returns or raises


def chat_ex(prompt: str, *, settings: dict | None = None, max_tokens: int = 4096, timeout: float = 45.0,
            transport: httpx.BaseTransport | None = None) -> tuple[str, str]:
    """One deterministic chat completion -> (answer, model that answered). Tries GEC_LLM_MODEL first, then the
    backup models on 404/429/5xx; the last model gets retries with backoff. An auth/request error (400/401/403)
    stops at once: it would fail for every model. Raises LLMUnavailableError with every model's reason."""
    s = settings or llm_settings()
    if s is None:
        raise LLMUnavailableError("No LLM fallback is configured (GEC_LLM_BASE_URL / GEC_LLM_MODEL)")
    models = s.get("models") or [s["model"]]
    reasons = []
    for i, model in enumerate(models):
        try:
            return _chat_one(s, model, prompt, max_tokens, timeout, 3 if i == len(models) - 1 else 1, transport), model
        except _TryNext as e:
            reasons.append(f"{model}: {e}")
    raise LLMUnavailableError("LLM call failed for every model - " + " | ".join(reasons), model=models[0])


def chat(prompt: str, **kw) -> str:
    return chat_ex(prompt, **kw)[0]


def parse_json(text: str):
    """JSON from an LLM answer, tolerating ```json fences and prose around the object."""
    t = regex.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(t)
    except ValueError:
        m = regex.search(r"\{.*\}", t, flags=regex.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _cached(key: tuple, fn):
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    val = fn()
    with _LOCK:
        if len(_CACHE) > 2048:
            _CACHE.clear()
        _CACHE[key] = val
    return val


class _Cand:  # same shape as runtime.Candidate (not imported, to keep this module free of model code)
    def __init__(self, text: str, score: float = 0.0):
        self.text, self.score = text, score


class LLMGenerator:
    """Seq2SeqModel stand-in: minimal-edit GEC candidates for one language from the configured LLM."""

    is_llm = True
    has_scores = False  # no sequence log-probabilities: never turn ``score`` into confidence evidence
    max_input_tokens = 10_000

    def __init__(self, lang: str, settings: dict):
        self.lang, self.settings = lang, settings
        self.model = settings["model"]  # updated to the model that actually answered the last call
        self.local_failure: str | None = None  # why the local checkpoint could not be used (for the trace)

    @property
    def hf_id(self) -> str:
        return f"llm:{self.model}"

    def token_len(self, text: str) -> int:
        return len(text)

    def _ask(self, sentence: str) -> tuple[list[str], str]:
        name = LANGUAGES[self.lang].name
        prompt = (
            f"You are a grammatical error correction system for {name}.\n"
            f"Correct ONLY grammar, spelling, agreement, particles/postpositions and punctuation errors in the {name} "
            "sentence below, with the fewest possible edits. Keep the meaning, wording, register, names and numbers. "
            "Do not paraphrase or translate. If it is already correct, return it unchanged.\n"
            f"Return only JSON: {{\"candidates\": [\"<best correction>\", ...]}} with 1 to {N_CANDIDATES} distinct "
            "full-sentence candidates, best first.\n\n"
            f"Sentence: {sentence}")
        answer, model = chat_ex(prompt, settings=self.settings)
        try:
            data = parse_json(answer)
        except ValueError as e:  # malformed JSON
            raise LLMUnavailableError(f"LLM ({model}) answer was not valid JSON") from e
        cands = data.get("candidates") if isinstance(data, dict) else data
        out = [str(c).strip() for c in (cands or []) if isinstance(c, str) and c.strip()]
        if not out:
            raise LLMUnavailableError(f"LLM ({model}) returned no usable correction")
        return list(dict.fromkeys(out))[:N_CANDIDATES], model

    def generate(self, text: str, *, num_beams: int | None = None, num_return: int = 1, **_) -> list[_Cand]:
        texts, self.model = _cached(("gen", self.settings["model"], self.lang, text), lambda: self._ask(text))
        return [_Cand(t) for t in texts[:max(1, num_return)]]


class LLMMeaningJudge:
    """SentenceEmbedder stand-in for the meaning gate: LLM-rated meaning preservation in [0, 1] (not a cosine)."""

    is_llm = True

    def __init__(self, settings: dict):
        self.settings = settings
        self._ns = settings["model"]  # stable cache namespace
        self.model = settings["model"]  # updated to the model that actually answered the last call

    @property
    def name(self) -> str:
        return f"llm_judge:{self.model}"

    def _ask(self, pairs: list[tuple[str, str]]) -> list[float]:
        items = "\n".join(f"{i + 1}. A: {a}\n   B: {b}" for i, (a, b) in enumerate(pairs))
        prompt = (
            "For each numbered pair, rate how well sentence B preserves the MEANING of sentence A. Ignore grammar, "
            "spelling and punctuation fixes; judge only what is being said (facts, polarity, numbers, who does what, "
            "tense of the event). Scale: 1.0 = same meaning; 0.9 = tiny nuance change; 0.7 = noticeable change; "
            "0.3 or less = different meaning.\n"
            f"Return only JSON: {{\"scores\": [<number for pair 1>, ...]}} with exactly {len(pairs)} numbers.\n\n{items}")
        answer, self.model = chat_ex(prompt, settings=self.settings, max_tokens=2048)
        try:
            data = parse_json(answer)
            scores = [float(x) for x in (data.get("scores") if isinstance(data, dict) else data)]
        except (ValueError, TypeError) as e:
            raise LLMUnavailableError(f"LLM judge ({self.model}) answer was not valid JSON") from e
        if len(scores) != len(pairs):
            raise LLMUnavailableError(f"LLM judge ({self.model}) returned {len(scores)} scores for {len(pairs)} pairs")
        return [min(1.0, max(0.0, s)) for s in scores]

    def similarity_many(self, pairs: list[tuple[str, str]]) -> list[float]:
        out: dict[int, float] = {}
        todo = []
        for i, (a, b) in enumerate(pairs):
            if a == b:
                out[i] = 1.0
                continue
            with _LOCK:
                hit = _CACHE.get(("judge", self._ns, a, b))
            if hit is not None:
                out[i] = hit  # type: ignore[assignment]
            else:
                todo.append(i)
        uniq = list(dict.fromkeys(pairs[i] for i in todo))
        if uniq:
            fresh = dict(zip(uniq, self._ask(uniq)))
            with _LOCK:
                for p, s in fresh.items():
                    _CACHE[("judge", self._ns, *p)] = s
            for i in todo:
                out[i] = fresh[pairs[i]]
        return [round(float(out[i]), 4) for i in range(len(pairs))]

    def similarity(self, a: str, b: str) -> float:
        return self.similarity_many([(a, b)])[0]


def llm_generator(lang: str) -> LLMGenerator | None:
    s = llm_settings()
    return LLMGenerator(lang, s) if s else None


def llm_meaning_judge() -> LLMMeaningJudge | None:
    s = llm_settings()
    return LLMMeaningJudge(s) if s else None
