"""Negative / recovery tests. Model doubles here are FAULT INJECTORS used only inside the test suite to force
bad model behaviour; the application never ships canned corrections."""
import httpx
import pytest

from gec_common.errors import ModelUnavailableError
from gec_common.runtime import Candidate, clear_models, register_override
from gec_o2.corrector import O2Reference
from gec_o3.controlled import O3Controlled
from gec_o4.confidence import apply_confidence
from gec_o4.explain import explain
from gec_o4.llm import NoneProvider, OpenAICompatibleProvider

pytestmark = pytest.mark.negative


class FakeModel:
    """Stands in for a Seq2SeqModel and returns scripted n-best candidates."""
    hf_id = "fake/model"
    max_input_tokens = 128

    def __init__(self, candidates, raises=None):
        self.candidates, self.raises = candidates, raises

    def token_len(self, text):
        return len(text.split())

    def generate(self, text, **kw):
        if self.raises:
            raise self.raises
        return [Candidate(t, s) for t, s in self.candidates]


class FakeEmb:
    """Similarity 0.99 unless the strings differ a lot (then 0.5)."""
    def __init__(self, sim=0.99):
        self.sim = sim

    def similarity(self, a, b):
        return 1.0 if a == b else self.sim


@pytest.fixture(autouse=True)
def _clean():
    clear_models()
    yield
    clear_models()


def use(candidates=None, raises=None, key="en_t5_gec"):
    register_override(f"s2s:{key}", FakeModel(candidates or [], raises))


# ------------------------------------------------------------------ meaning-changing rewrite
def test_o3_blocks_number_change_and_abstains():
    src = "I bought 5 apples."
    use([("I bought 6 apples.", -0.05)] * 4)
    r = O3Controlled(FakeEmb()).correct(src, "en", "minimal")
    assert r.corrected == src
    assert r.edits and all(e.gate_status == "rejected" for e in r.edits)
    assert r.edits[0].gate_reason.startswith("meaning:number_changed")
    assert r.abstained and "Meaning preservation" in r.abstain_reason


def test_o3_blocks_negation_removal():
    src = "She did not go to school."
    use([("She did go to school.", -0.05)] * 4)
    r = O3Controlled(FakeEmb()).correct(src, "en", "fluency")  # even in the looser mode
    assert r.corrected == src and r.abstained
    assert "negation_changed" in r.edits[0].gate_reason


def test_o3_blocks_low_sentence_similarity_rewrite():
    src = "The cat sat on the mat."
    use([("The cat sat on the sofa.", -0.05)] * 4)
    r = O3Controlled(FakeEmb(sim=0.5)).correct(src, "en", "minimal")
    assert r.corrected == src and r.abstained
    assert r.edits[0].gate_reason.startswith("meaning:")


# ------------------------------------------------------------------ over-correction
def test_o3_minimal_blocks_lexical_rewrite_of_correct_sentence():
    src = "The car is big."
    use([("The vehicle is large.", -0.05), ("The car is big.", -0.06), ("The vehicle is large.", -0.3), ("The car is big.", -0.4)])
    r = O3Controlled(FakeEmb()).correct(src, "en", "minimal")
    assert r.corrected == src  # nothing applied to an already-correct sentence
    assert not [e for e in r.edits if e.gate_status != "rejected"]


def test_o3_no_change_margin_rejects_edit_when_model_is_nearly_indifferent():
    src = "Today is a nice day."
    use([("Today is a very nice day.", -0.30), ("Today is a nice day.", -0.33)])  # gap 0.03 < 0.10
    r = O3Controlled(FakeEmb()).correct(src, "en", "minimal")
    assert r.corrected == src
    assert any("no_change_margin" in (e.gate_reason or "") for e in r.edits)


def test_o3_edit_budget_limits_number_of_edits():
    src = "a b c d e f g h i j."
    use([("A B C D E F G H I J.", -0.05)] * 4)
    r = O3Controlled(FakeEmb()).correct(src, "en", "minimal")
    assert len([e for e in r.edits if e.gate_status != "rejected"]) <= 4  # 35% of ~11 tokens


# ------------------------------------------------------------------ inappropriate correction
def test_script_switch_output_is_rejected_by_both_pipelines():
    src = "मैं स्कूल जाती है।"
    use([("আমি স্কুলে যাবে।", -0.01)] * 4, key="hi_indicbart_gec")
    r2 = O2Reference(use_detector=False).correct(src, "hi")
    r3 = O3Controlled(FakeEmb()).correct(src, "hi", "minimal")
    assert r2.corrected == src and any("safety guard" in w for w in r2.warnings)
    assert r3.corrected == src and not r3.edits


def test_runaway_length_output_is_rejected():
    src = "I like tea."
    use([("I like tea. " * 20, -0.01)] * 4)
    r = O2Reference(use_detector=False).correct(src, "en")
    assert r.corrected == src


# ------------------------------------------------------------------ uncertain / low confidence
def test_low_evidence_edit_gets_low_confidence_and_zero_shot_cap():
    use([("I like to swim.", -1.6)])  # seq_prob ~ 0.2
    r = O2Reference(use_detector=False).correct("I likes to swim.", "en")
    apply_confidence(r)
    e = r.edits[0]
    assert e.confidence is not None and e.confidence < 0.3 and e.confidence_calibrated is False


# ------------------------------------------------------------------ failure / degraded mode
def test_o2_degrades_to_rules_when_model_unavailable():
    use(raises=ModelUnavailableError("weights missing"))
    r = O2Reference(use_detector=False).correct("the the pool  is  nice .", "en")
    assert r.degraded and any("unavailable" in w for w in r.warnings)
    assert r.corrected != r.source  # deterministic rules still fixed spacing / duplicate word
    assert all(e.source.startswith("rule:") for e in r.edits)


def test_o3_fails_closed_when_generator_unavailable():
    use(raises=ModelUnavailableError("weights missing"))
    r = O3Controlled(FakeEmb()).correct("I likes tea.", "en", "minimal")
    assert r.degraded and r.abstained and r.corrected == r.source and not r.edits


def test_o3_fails_closed_when_meaning_gate_unavailable():
    class BrokenEmb:
        def similarity(self, a, b):
            raise ModelUnavailableError("embedder down")
    use([("I like tea.", -0.05)] * 4)
    r = O3Controlled(BrokenEmb()).correct("I likes tea.", "en", "minimal")
    assert r.degraded and r.abstained and r.corrected == r.source


def test_ja_or_te_have_no_generator_and_o3_says_so():
    for lang, txt in [("ja", "私は学校を行きます。"), ("te", "నేను ఇంటికి వెళ్తాను."), ("or", "ମୁଁ ଘରକୁ ଯାଏ ।")]:
        r = O3Controlled(FakeEmb()).correct(txt, lang, "minimal")
        assert r.corrected == txt and any("cannot correct" in w for w in r.warnings)


# ------------------------------------------------------------------ LLM explanation failures
def _edit():
    r = O2Reference(use_detector=False).correct("I has  a pen.", "en") if False else None
    from gec_common.schemas import Edit
    return Edit(start=2, end=5, original="has", replacement="have", op="replace", language="en", error_type="VERB_FORM")


def test_explanation_falls_back_when_llm_errors():
    p = OpenAICompatibleProvider("http://x", "m", transport=httpx.MockTransport(lambda req: httpx.Response(500)))
    x = explain(_edit(), p)
    assert x.source == "template" and x.fallback_reason.startswith("llm_error")


def test_explanation_falls_back_when_llm_output_is_not_grounded():
    ok = lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "Use the right verb form."}}]})
    x = explain(_edit(), OpenAICompatibleProvider("http://x", "m", transport=httpx.MockTransport(ok)))
    assert x.source == "template" and x.fallback_reason.startswith("verification_failed")


def test_explanation_accepts_grounded_llm_output_and_none_provider_is_default():
    ok = lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "Change 'has' to 'have' because the subject is 'I'."}}]})
    x = explain(_edit(), OpenAICompatibleProvider("http://x", "m", transport=httpx.MockTransport(ok)))
    assert x.source == "llm"
    assert explain(_edit(), NoneProvider()).source == "template"
