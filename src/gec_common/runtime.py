"""CPU-first model runtime shared by O2/O3/eval: device resolution, LRU model cache, HF wrappers.

Nothing here requires a GPU. ``GEC_DEVICE=auto`` uses CUDA only if present and otherwise falls back to CPU.
Model objects can be replaced with ``register_override`` (used by tests and fault-injection).
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .config import load_models_config, model_spec
from .errors import ModelUnavailableError


def resolve_device(pref: str | None = None) -> str:
    pref = pref or os.environ.get("GEC_DEVICE") or load_models_config()["runtime"]["device"]
    if pref in ("auto", "cuda"):
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:  # torch missing/broken -> CPU path will raise a clear ModelUnavailableError later
            return "cpu"
    return "cpu"


class _Registry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: OrderedDict[str, Any] = OrderedDict()
        self._overrides: dict[str, Any] = {}

    def get(self, key: str, factory: Callable[[], Any], max_items: int) -> Any:
        with self._lock:
            if key in self._overrides:
                return self._overrides[key]
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
            obj = factory()
            self._items[key] = obj
            while len(self._items) > max_items:
                self._items.popitem(last=False)
            return obj

    def override(self, key: str, obj: Any | None) -> None:
        with self._lock:
            if obj is None:
                self._overrides.pop(key, None)
            else:
                self._overrides[key] = obj

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._overrides.clear()


_REG = _Registry()
register_override = _REG.override
clear_models = _REG.clear


def _max_loaded() -> int:
    return int(load_models_config()["runtime"].get("max_loaded_models", 3))


def _torch():
    try:
        import torch
    except Exception as e:  # pragma: no cover
        raise ModelUnavailableError("PyTorch is not installed", cause=str(e)) from e
    n = int(os.environ.get("GEC_NUM_THREADS", load_models_config()["runtime"].get("num_threads", 0)) or 0)
    if n > 0:
        torch.set_num_threads(n)
    return torch


@dataclass
class Candidate:
    text: str
    score: float  # length-normalised sequence log-probability (higher = more confident)


class Seq2SeqModel:
    """One HF seq2seq checkpoint, loaded on CPU/GPU. Sentence-at-a-time (no padding tricks)."""

    def __init__(self, key: str):
        self.spec = model_spec(key)
        self.key = key
        self.hf_id: str = self.spec["hf_id"]
        self.prefix: str = self.spec.get("input_prefix", "")
        self.max_input_tokens = int(self.spec.get("max_input_tokens", 128))
        torch = _torch()
        self.device = resolve_device()
        try:
            if self.spec["arch"] == "seq2seq_indicbart":
                from transformers import AlbertTokenizer, MBartForConditionalGeneration

                self.tok = AlbertTokenizer.from_pretrained(self.hf_id, keep_accents=True, do_lower_case=False)
                self.model = MBartForConditionalGeneration.from_pretrained(self.hf_id)
                self.lang_tag: str = self.spec["lang_tag"]
                self.tag_id: int = self.tok.convert_tokens_to_ids(self.lang_tag)
            elif self.spec["arch"] == "seq2seq_kobart":
                from transformers import BartForConditionalGeneration, PreTrainedTokenizerFast

                self.tok = PreTrainedTokenizerFast.from_pretrained(self.hf_id)
                self.model = BartForConditionalGeneration.from_pretrained(self.hf_id)
            else:
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, T5Tokenizer

                try:
                    self.tok = AutoTokenizer.from_pretrained(self.hf_id)
                except ValueError:
                    # transformers 5.x cannot auto-convert some mT5 sentencepiece-only repos; the slow
                    # sentencepiece tokenizer is exact for them.
                    self.tok = T5Tokenizer.from_pretrained(self.hf_id)
                self.model = AutoModelForSeq2SeqLM.from_pretrained(self.hf_id)
        except Exception as e:
            raise ModelUnavailableError(f"Could not load model {self.hf_id}", model=self.hf_id, cause=str(e)) from e
        self.model.eval().to(self.device)
        self._torch = torch

    def _encode(self, text: str) -> list[int]:
        if self.spec["arch"] == "seq2seq_indicbart":
            return self.tok(f"{text} </s> {self.lang_tag}", add_special_tokens=False).input_ids
        if self.spec["arch"] == "seq2seq_kobart":
            return [self.tok.bos_token_id] + self.tok.encode(text) + [self.tok.eos_token_id]
        return self.tok(self.prefix + text, truncation=False).input_ids

    def token_len(self, text: str) -> int:
        return len(self._encode(text))

    def generate(self, text: str, *, num_beams: int | None = None, num_return: int = 1,
                 max_new_tokens: int | None = None) -> list[Candidate]:
        torch = self._torch
        ids = self._encode(text)
        gen = dict(self.spec.get("generate", {}))
        beams = num_beams or gen.pop("num_beams", 4)
        gen.pop("num_beams", None)
        n_ret = min(num_return, beams)
        max_new = max_new_tokens or min(192, max(16, int(len(ids) * 1.6) + 8))
        input_ids = torch.tensor([ids], device=self.device)
        kw: dict[str, Any] = dict(gen, num_beams=beams, num_return_sequences=n_ret, max_new_tokens=max_new,
                                  do_sample=False, return_dict_in_generate=True, output_scores=True)
        if self.spec["arch"] == "seq2seq_kobart":
            kw["eos_token_id"] = 1
        elif self.spec["arch"] == "seq2seq_indicbart":
            kw.update(decoder_start_token_id=self.tag_id, pad_token_id=self.tok.pad_token_id,
                      eos_token_id=self.tok.eos_token_id, attention_mask=torch.ones_like(input_ids))
        else:
            kw["attention_mask"] = torch.ones_like(input_ids)
        with torch.inference_mode():
            out = self.model.generate(input_ids, **kw)
        # transformers 5 renamed sequence_scores -> sequences_scores. Never fall back to a fake 0.0 score:
        # a silent default here would report every output as 100% confident.
        raw = getattr(out, "sequences_scores", None)
        if raw is None:
            raw = getattr(out, "sequence_scores", None)
        if raw is None:
            raise ModelUnavailableError("generation output has no sequence scores", model=self.hf_id)
        scores = raw.tolist()
        texts = self.tok.batch_decode(out.sequences, skip_special_tokens=True,
                                      clean_up_tokenization_spaces=bool(self.spec.get("decode_cleanup", True)))
        return [Candidate(t.strip(), float(s)) for t, s in zip(texts, scores)]


def get_seq2seq(key: str) -> Seq2SeqModel:
    return _REG.get(f"s2s:{key}", lambda: Seq2SeqModel(key), _max_loaded())


class SentenceEmbedder:
    """Mean-pooled, L2-normalised sentence embeddings (multilingual-e5 style, with 'query: ' prefix)."""

    def __init__(self, key: str = "embedder"):
        self.spec = model_spec(key)
        self.prefix = self.spec.get("input_prefix", "")
        torch = _torch()
        self.device = resolve_device()
        try:
            from transformers import AutoModel, AutoTokenizer

            self.tok = AutoTokenizer.from_pretrained(self.spec["hf_id"])
            self.model = AutoModel.from_pretrained(self.spec["hf_id"]).eval().to(self.device)
        except Exception as e:
            raise ModelUnavailableError(f"Could not load embedder {self.spec['hf_id']}", cause=str(e)) from e
        self._torch = torch
        self._cache: dict[str, np.ndarray] = {}

    def encode(self, texts: list[str]) -> np.ndarray:
        torch = self._torch
        todo = [t for t in dict.fromkeys(texts) if t not in self._cache]
        for i in range(0, len(todo), 16):
            batch = todo[i:i + 16]
            enc = self.tok([self.prefix + t for t in batch], padding=True, truncation=True, max_length=256,
                           return_tensors="pt").to(self.device)
            with torch.inference_mode():
                h = self.model(**enc).last_hidden_state
            m = enc["attention_mask"].unsqueeze(-1).to(h.dtype)
            v = (h * m).sum(1) / m.sum(1).clamp(min=1)
            v = torch.nn.functional.normalize(v, dim=-1).cpu().numpy()
            for t, vec in zip(batch, v):
                self._cache[t] = vec
        if len(self._cache) > 4096:
            self._cache.clear()
        return np.stack([self._cache[t] if t in self._cache else self.encode([t])[0] for t in texts])

    def similarity(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        va, vb = self.encode([a, b])
        return float(np.clip(va @ vb, -1.0, 1.0))


def get_embedder(key: str = "embedder") -> SentenceEmbedder:
    return _REG.get(f"emb:{key}", lambda: SentenceEmbedder(key), _max_loaded() + 1)


def get_mlm(key: str = "mlm_detector"):
    """Returns (tokenizer, model, device) for a masked-LM."""

    def _load():
        torch = _torch()
        spec = model_spec(key)
        try:
            from transformers import AutoModelForMaskedLM, AutoTokenizer

            tok = AutoTokenizer.from_pretrained(spec["hf_id"])
            dev = resolve_device()
            model = AutoModelForMaskedLM.from_pretrained(spec["hf_id"]).eval().to(dev)
        except Exception as e:
            raise ModelUnavailableError(f"Could not load MLM {spec['hf_id']}", cause=str(e)) from e
        return tok, model, dev, torch

    return _REG.get(f"mlm:{key}", _load, _max_loaded() + 1)


def script_consistent(src: str, out: str) -> bool:
    """Guard: a corrector must not switch script (e.g. Devanagari input answered in Bengali or Telugu).
    Passes only if at least half of the output's letters/marks are in the SOURCE's dominant script."""
    import regex

    groups = {
        "Telugu": r"\p{Script=Telugu}", "Oriya": r"\p{Script=Oriya}", "Devanagari": r"\p{Script=Devanagari}",
        "Hangul": r"\p{Script=Hangul}", "Latin": r"\p{Script=Latin}",
        "Cjk": r"[\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Han}]",
    }
    counts = {g: len(regex.findall(rx, src)) for g, rx in groups.items()}
    dom = max(counts, key=counts.get)
    if counts[dom] == 0:
        return True  # source has no letters in a known script: nothing to compare against
    total_out = len(regex.findall(r"[\p{L}\p{M}]", out))
    if total_out == 0:
        return False
    return len(regex.findall(groups[dom], out)) / total_out >= 0.5


def get_translator(key: str = "translator"):
    """Returns (tokenizer, model, device, torch) for the translation model, loaded lazily in bfloat16 (CPU-friendly)."""

    def _load():
        torch = _torch()
        spec = model_spec(key)
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            tok = AutoTokenizer.from_pretrained(spec["hf_id"])
            dev = resolve_device()
            model = AutoModelForSeq2SeqLM.from_pretrained(spec["hf_id"], dtype=torch.bfloat16).eval().to(dev)
        except Exception as e:
            raise ModelUnavailableError(f"Could not load translator {spec['hf_id']}", cause=str(e)) from e
        return tok, model, dev, torch

    return _REG.get(f"mt:{key}", _load, 2)
