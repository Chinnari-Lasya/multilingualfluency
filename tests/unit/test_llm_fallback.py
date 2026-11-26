"""LLM fallback (local models unavailable) and the rules-only English grammar heuristics.

The HTTP server here is a FAULT/STUB INJECTOR (httpx.MockTransport) standing in for an OpenAI-compatible
endpoint; it is used only inside the test suite. No test calls a real provider."""
import json

import httpx
import pytest

import gec_common.llm_fallback as fb
from gec_common.errors import ModelUnavailableError, TranslationUnavailableError
from gec_common.runtime import clear_models, register_override
from gec_o2.corrector import O2Reference
from gec_o2.rules import apply_rules
from gec_o3.controlled import O3Controlled
from gec_translate.service import OpenAICompatibleProvider, translate

SRC = "I likes to swimming in the pool. She don't know nothing."


class Broken:
    """A local checkpoint that cannot load (e.g. PyTorch missing)."""
    hf_id = "broken"
    max_input_tokens = 128

    def token_len(self, t):
        raise ModelUnavailableError("PyTorch is not installed")

    def generate(self, *a, **k):
        raise ModelUnavailableError("PyTorch is not installed")


def _server(fixes: dict, judge: float = 1.0, status: int = 200):
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        if status != 200:
            return httpx.Response(status, json={"error": {"code": status, "message": "API key not valid. Please pass a valid API key."}})
        prompt = json.loads(req.content)["messages"][0]["content"]
        if "Return only JSON: {\"scores\"" in prompt:
            n = prompt.count("\n   B: ")
            content = json.dumps({"scores": [judge] * n})
        else:
            sent = prompt.rsplit("Sentence: ", 1)[1]
            content = "```json\n" + json.dumps({"candidates": [fixes.get(sent, sent)]}) + "\n```"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return httpx.MockTransport(handler), calls


FIXES = {"I likes to swimming in the pool.": "I like to swim in the pool.",
         "She don't know nothing.": "She doesn't know anything."}


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setenv("GEC_LLM_BASE_URL", "https://llm.test/v1beta/openai/")
    monkeypatch.setenv("GEC_LLM_MODEL", " gemini-test ")
    monkeypatch.setenv("GEC_LLM_API_KEY", " secret-key ")
    monkeypatch.delenv("GEC_LLM_FALLBACK", raising=False)
    fb._CACHE.clear()
    clear_models()
    register_override("s2s:en_t5_gec", None)
    yield monkeypatch
    fb._TRANSPORT = None
    fb._CACHE.clear()
    clear_models()


def _broken_local(monkeypatch):
    import gec_common.runtime as rt
    monkeypatch.setattr(rt, "get_seq2seq", lambda key: (_ for _ in ()).throw(ModelUnavailableError("PyTorch is not installed")))
    monkeypatch.setattr(rt, "get_embedder", lambda key="embedder": (_ for _ in ()).throw(ModelUnavailableError("PyTorch is not installed")))


def test_o2_uses_llm_fallback_and_labels_it(llm):
    _broken_local(llm)
    fb._TRANSPORT, calls = _server(FIXES)
    r = O2Reference().correct(SRC, "en")
    assert r.corrected == "I like to swim in the pool. She doesn't know anything."
    assert r.engine == "llm_fallback" and not r.degraded
    assert r.model_ids["generator"] == "llm:gemini-test"
    assert all(e.source in ("llm:gemini-test",) or e.source.startswith("rule:") for e in r.edits)
    assert all("seq_prob" not in e.scores for e in r.edits if e.source.startswith("llm:"))  # no fake probability
    assert any("LLM fallback used" in w for w in r.warnings)
    gen = next(t for t in r.trace if t.stage == "generator")
    assert gen.status == "ok" and "LLM fallback" in gen.detail and "PyTorch" in gen.detail
    det = next(t for t in r.trace if t.stage == "detector")
    assert det.status == "skipped"
    # settings are cleaned: no stray spaces in the URL/model, key sent as a bearer token, never echoed
    assert str(calls[0].url) == "https://llm.test/v1beta/openai/chat/completions"
    assert calls[0].headers["authorization"] == "Bearer secret-key"


def test_o3_applies_safe_llm_edits_with_llm_meaning_gate(llm):
    _broken_local(llm)
    fb._TRANSPORT, _ = _server(FIXES, judge=0.98)
    r = O3Controlled().correct(SRC, "en", "minimal")
    assert not r.abstained and not r.degraded and r.engine == "llm_fallback"
    # minimal mode keeps its existing over-correction gates (edit budget / lexical rewrite) for the second sentence
    assert r.corrected == "I like to swim in the pool. She doesn't know nothing."
    blocked = [e for e in r.edits if e.gate_status == "rejected"]
    assert [e.original for e in blocked] == ["nothing"]
    assert blocked[0].gate_reason.startswith("overcorrection:")
    f = O3Controlled().correct(SRC, "en", "fluency")
    assert f.corrected == "I like to swim in the pool. She doesn't know anything."
    assert all(e.gate_status == "accepted" for e in f.edits)
    assert r.model_ids["meaning_embedder"] == "llm_judge:gemini-test"
    assert any("LLM judge" in w for w in r.warnings)
    assert "LLM fallback" in next(t for t in r.trace if t.stage == "generate+gate").detail


def test_o3_llm_judge_low_score_blocks_edits(llm):
    _broken_local(llm)
    fb._TRANSPORT, _ = _server(FIXES, judge=0.4)
    r = O3Controlled().correct("I likes to swimming in the pool.", "en", "minimal")
    assert r.corrected == r.source and r.abstained
    assert all((e.gate_reason or "").startswith("meaning:") for e in r.edits)


def test_o3_hard_checks_still_apply_to_llm_candidates(llm):
    _broken_local(llm)
    fb._TRANSPORT, _ = _server({"I bought 5 apples.": "I bought 6 apples."})
    r = O3Controlled().correct("I bought 5 apples.", "en", "minimal")
    assert r.corrected == "I bought 5 apples."
    assert any((e.gate_reason or "") == "meaning:number_changed" for e in r.edits)


def test_llm_http_error_is_reported_with_status_and_reason_then_rules_take_over(llm):
    _broken_local(llm)
    fb._TRANSPORT, _ = _server({}, status=400)
    r = O2Reference(use_detector=False).correct(SRC, "en")
    assert r.degraded and r.engine == "rules_only"
    w = " ".join(r.warnings)
    assert "HTTP 400" in w and "API key not valid" in w and "secret-key" not in w
    assert r.corrected == "I like to swim in the pool. She doesn't know anything."  # grammar rules fallback
    o3 = O3Controlled().correct(SRC, "en", "minimal")
    assert o3.abstained and o3.corrected == o3.source and "HTTP 400" in o3.trace[-1].detail


def test_fallback_off_or_unconfigured_keeps_previous_behaviour(llm):
    _broken_local(llm)
    llm.setenv("GEC_LLM_FALLBACK", "off")
    r = O3Controlled().correct(SRC, "en", "minimal")
    assert r.degraded and r.abstained and r.engine == "none"
    llm.delenv("GEC_LLM_FALLBACK")
    llm.delenv("GEC_LLM_BASE_URL")
    r2 = O2Reference(use_detector=False).correct("the the pool  is  nice .", "en")
    assert r2.degraded and r2.engine == "rules_only"


def test_translation_error_shows_provider_reason(llm):
    fb._TRANSPORT, _ = _server({}, status=400)
    p = OpenAICompatibleProvider(transport=fb._TRANSPORT)
    with pytest.raises(TranslationUnavailableError) as ei:
        translate("I go to school.", "en", "hi", provider=p)
    msg = ei.value.message
    assert "HTTP 400" in msg and "API key not valid" in msg and "gemini-test" in msg and "secret" not in msg


def _per_model(statuses: dict):
    """Server answering each model with its own status (200 = a valid translation/correction)."""
    seen = []

    def handler(req: httpx.Request):
        model = json.loads(req.content)["model"]
        seen.append(model)
        st = statuses.get(model, 200)
        if st != 200:
            return httpx.Response(st, json={"error": {"code": st, "message": f"{model} says {st}"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "मैं स्कूल जाता हूँ।"}}]})

    return httpx.MockTransport(handler), seen


def test_quota_or_overload_moves_to_backup_model_and_reports_it(llm, monkeypatch):
    monkeypatch.setattr(fb.time, "sleep", lambda s: None)
    llm.setenv("GEC_LLM_BACKUP_MODELS", "backup-a, backup-b")
    t, seen = _per_model({"gemini-test": 429, "backup-a": 503})
    out = translate("I go to school.", "en", "hi", provider=OpenAICompatibleProvider(transport=t))
    assert out["translation"] == "मैं स्कूल जाता हूँ।" and out["model"] == "backup-b"
    assert seen[:2] == ["gemini-test", "backup-a"] and seen[-1] == "backup-b"


def test_every_model_failing_lists_each_reason(llm, monkeypatch):
    monkeypatch.setattr(fb.time, "sleep", lambda s: None)
    llm.setenv("GEC_LLM_BACKUP_MODELS", "backup-a")
    t, _ = _per_model({"gemini-test": 429, "backup-a": 503})
    with pytest.raises(TranslationUnavailableError) as ei:
        translate("I go to school.", "en", "hi", provider=OpenAICompatibleProvider(transport=t))
    msg = ei.value.message
    assert "gemini-test: HTTP 429" in msg and "backup-a: HTTP 503" in msg


def test_auth_error_does_not_try_other_models(llm):
    llm.setenv("GEC_LLM_BACKUP_MODELS", "backup-a")
    t, seen = _per_model({"gemini-test": 401})
    with pytest.raises(TranslationUnavailableError):
        translate("I go to school.", "en", "hi", provider=OpenAICompatibleProvider(transport=t))
    assert seen == ["gemini-test"]


def test_google_endpoint_gets_default_backup_models(llm):
    llm.setenv("GEC_LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
    s = fb.endpoint_settings()
    assert s["models"][0] == "gemini-test" and list(s["models"][1:]) == list(fb.GOOGLE_BACKUP_MODELS)
    llm.setenv("GEC_LLM_BACKUP_MODELS", "")
    assert fb.endpoint_settings()["models"] == ["gemini-test"]


@pytest.mark.parametrize("src,out", [
    ("I likes to swimming in the pool.", "I like to swim in the pool."),
    ("She don't know nothing.", "She doesn't know anything."),
    ("They doesn't like it.", "They don't like it."),
    ("We was happy.", "We were happy."),
    ("He like tea.", "He likes tea."),
    ("She have a car.", "She has a car."),
    ("I is ready.", "I am ready."),
    ("He didn't see nobody there.", "He didn't see anybody there."),
])
def test_rules_only_grammar_heuristics(src, out):
    from gec_common.align import apply_edits
    assert apply_edits(src, apply_rules(src, "en", grammar=True)) == out


@pytest.mark.parametrize("ok", [
    "Let it go.", "Does he know the answer?", "I want to make it work.", "He go to school yesterday.",
    "I look forward to swimming.", "She doesn't know anything.", "They like reading.", "If I were you.",
])
def test_rules_only_grammar_heuristics_leave_these_alone(ok):
    from gec_common.align import apply_edits
    assert apply_edits(ok, apply_rules(ok, "en", grammar=True)) == ok


def test_grammar_heuristics_are_off_by_default():
    assert apply_rules("I likes tea.", "en") == []
