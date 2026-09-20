"""Real end-to-end tests against a RUNNING API (real HF models, PostgreSQL if the API is configured for it).
Run: pytest -m models   (skipped automatically when the API is not reachable)."""
import os

import httpx
import pytest

from gec_common.align import apply_edits
from gec_common.schemas import Edit

pytestmark = pytest.mark.models
API = os.environ.get("GEC_TEST_API", "http://127.0.0.1:8000")

CASES = {  # language -> (input text, capability level, substrings that MUST appear in the O2 output)
    "en": ("I likes to swimming in the pool.", "seq2seq_gec", ["I like"]),
    "hi": ("मैं स्कूल जाती है। राम ने ने खाना खाया|", "seq2seq_gec", ["जाती हूं", "राम ने खाना", "।"]),
    "ko": ("나는 학교을 갑니다. 한국어는어렵다.", "seq2seq_gec", ["학교에", "한국어는 어렵다"]),
    "ja": ("私は学校を行きます,  昨日友達をを会いました.", "rules_and_detection", ["、", "友達を会いました。"]),
    "te": ("నేను  ఇంటికి వెళ్తాను.", "rules_and_detection", ["నేను ఇంటికి"]),
    "or": ("ମୁଁ ଘରକୁ ଯାଉଛି |", "rules_and_detection", ["ଯାଉଛି ।"]),
}


@pytest.fixture(scope="module")
def client():
    try:
        httpx.get(f"{API}/api/v1/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip(f"API not reachable at {API}")
    c = httpx.Client(base_url=API, timeout=900)
    tok = c.post("/api/v1/auth/login", json={"username": "learner", "password": "demo"}).json()["token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    return c


def _consistent(run):
    edits = [Edit(**{k: e[k] for k in Edit.model_fields if k in e}) for e in run["edits"] if e["gate_status"] != "rejected"]
    return apply_edits(run["source"], edits) == run["corrected"]


@pytest.mark.parametrize("lang", list(CASES))
def test_language_end_to_end(client, lang):
    text, level, must = CASES[lang]
    r = client.post("/api/v1/corrections/compare", json={"text": text, "language": lang, "o3_mode": "minimal"})
    assert r.status_code == 200, r.text
    d = r.json()
    o2, o3 = d["o2"], d["o3"]
    assert o2["pipeline"] == "o2" and o3["pipeline"] == "o3"           # distinct modules
    assert o2["capability"]["level"] == level                           # capability reported truthfully
    for frag in must:
        assert frag in o2["corrected"], (frag, o2["corrected"])
    assert _consistent(o2) and _consistent(o3)                          # edits reproduce the output exactly
    assert o2["assessment"]["meaning_preservation"]["status"] in ("preserved", "uncertain", "violated", "not_checked")
    assert all(e["explanation"] and e["explanation"]["text"] for e in o2["edits"])
    if level == "rules_and_detection":                                  # never claim neural correction
        assert all(e["source"].startswith("rule:") for e in o2["edits"])
        assert o3["corrected"] == o3["source"]
    else:
        assert any(e["source"].startswith("model:") for e in o2["edits"])


def test_o3_leaves_already_correct_sentences_unchanged(client):
    for lang, s in [("en", "The weather is nice today."), ("ko", "오늘 날씨가 좋습니다."), ("hi", "आज मौसम अच्छा है।")]:
        d = client.post("/api/v1/corrections/compare", json={"text": s, "language": lang, "o3_mode": "minimal"}).json()
        assert d["o3"]["corrected"] == s, (lang, d["o3"]["corrected"])


def test_o3_blocks_meaning_change_on_real_model(client):
    d = client.post("/api/v1/corrections/compare", json={"text": "She did not go to the party with 5 friends.", "language": "en"}).json()
    assert d["o3"]["corrected"] == d["source"]
    assert d["o3"]["assessment"]["meaning_preservation"]["status"] == "preserved"
