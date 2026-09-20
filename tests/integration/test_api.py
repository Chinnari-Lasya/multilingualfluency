"""API tests on an isolated SQLite DB. Pipelines run with the deterministic-rule path (no model downloads);
real-model end-to-end tests are in test_models_e2e.py (pytest -m models)."""
import pytest
from fastapi.testclient import TestClient

import gec_api.main as main
from gec_api import db as dbm
from gec_api.pipeline import Coach
from gec_common.runtime import clear_models


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GEC_DATABASE_URL", f"sqlite:///{tmp_path/'t.db'}")
    clear_models()
    c = Coach()
    c.o2.use_detector = False
    c.o2.use_model = False  # rules only: no model download in API tests
    monkeypatch.setattr(main, "_coach", c)
    with TestClient(main.app) as tc:
        yield tc


def login(c, user):
    r = c.post("/api/v1/auth/login", json={"username": user, "password": "demo"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_languages_and_capability_honesty(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    langs = {l["code"]: l for l in client.get("/api/v1/languages").json()}
    assert set(langs) == {"te", "or", "hi", "en", "ja", "ko"}
    for code in ("te", "or", "ja"):  # no working GEC checkpoint: must NOT claim neural GEC
        assert langs[code]["capability"]["level"] == "rules_and_detection"
        assert langs[code]["capability"]["limitations"]
    for code in ("en", "hi", "ko"):
        assert langs[code]["capability"]["level"] == "seq2seq_gec"


def test_auth_required_and_roles_enforced(client):
    assert client.post("/api/v1/corrections", json={"text": "hello world"}).status_code == 401
    L = login(client, "learner")
    assert client.get("/api/v1/review/queue", headers=L).status_code == 403
    assert client.post("/api/v1/evaluations/run", headers=L, json={}).status_code == 403
    assert client.post("/api/v1/auth/login", json={"username": "learner", "password": "wrong"}).status_code == 401


@pytest.mark.parametrize("payload,status,code", [
    ({"text": ""}, 422, "invalid_input"),
    ({"text": "   \n "}, 422, "invalid_input"),
    ({"text": "a\x00b"}, 422, "invalid_input"),
    ({"text": "x" * 6000, "language": "en"}, 413, "input_too_long"),
    ({"text": "hello", "language": "fr"}, 422, "unsupported_language"),
    ({"text": "This is plainly English text here.", "language": "hi"}, 422, "language_mismatch"),
    ({"text": "12345 !!!"}, 422, "language_undetermined"),
])
def test_input_validation_returns_structured_errors(client, payload, status, code):
    L = login(client, "learner")
    r = client.post("/api/v1/corrections", headers=L, json={**payload, "pipeline": "o2"})
    assert r.status_code == status and r.json()["error"] == code


def test_correct_persist_decide_adjudicate_progress_roundtrip(client):
    L, E = login(client, "learner"), login(client, "educator")
    r = client.post("/api/v1/corrections", headers=L, json={"text": "He is the the man .  Really", "language": "en", "pipeline": "o2"})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["run_id"] and run["pipeline"] == "o2" and run["edits"]
    # offsets/edits reproduce the output exactly
    from gec_common.align import apply_edits
    from gec_common.schemas import Edit
    edits = [Edit(**{k: e[k] for k in Edit.model_fields if k in e}) for e in run["edits"]]
    assert apply_edits(run["source"], edits) == run["corrected"]
    assert all(e["explanation"]["text"] for e in run["edits"])
    assert all(e["confidence_calibrated"] is False for e in run["edits"])
    eid = run["edits"][0]["id"]
    assert client.post(f"/api/v1/edits/{eid}/decision", headers=L, json={"decision": "accept"}).json()["learner_decision"] == "accept"
    assert client.get(f"/api/v1/edits/{eid}/explanation", headers=L).status_code == 200
    # educator: queue -> Modify requires a replacement -> accept
    assert any(q["id"] == eid for q in client.get("/api/v1/review/queue", headers=E).json())
    assert client.post(f"/api/v1/edits/{eid}/adjudications", headers=E, json={"verdict": "revise"}).status_code == 422
    a = client.post(f"/api/v1/edits/{eid}/adjudications", headers=E, json={"verdict": "revise", "revised_replacement": "X"})
    assert a.status_code == 200 and a.json()["adjudications"][0]["reviewer_independent"] is False
    # demo reviewer must NOT produce an acceptance number
    s = client.get("/api/v1/review/summary", headers=E).json()
    assert s["status"] == "not_performed_yet" and s["n_total_adjudications_incl_demo"] == 1
    prog = client.get("/api/v1/learners/me/progress", headers=L).json()
    assert "en" in prog["languages"] and prog["languages"]["en"]["submissions"] == 1
    assert client.get("/api/v1/learners/me/history", headers=L).json()[0]["language"] == "en"
    # learner_progress snapshot persisted
    with dbm.SessionLocal() as s_:
        assert s_.query(dbm.LearnerProgress).count() > 0


def test_learner_cannot_read_another_learners_run(client):
    L = login(client, "learner")
    run = client.post("/api/v1/corrections", headers=L, json={"text": "the the cat", "language": "en", "pipeline": "o2"}).json()
    with dbm.SessionLocal() as s:
        s.add(dbm.User(username="other", password_hash=main.hash_pw("demo"), role="learner"))
        s.commit()
    O = login(client, "other")
    assert client.get(f"/api/v1/corrections/{run['run_id']}", headers=O).status_code == 404


def test_stateless_mode_for_evaluator_needs_no_auth_and_writes_nothing(client):
    r = client.post("/api/v1/corrections", json={"text": "the the cat", "language": "en", "pipeline": "o2", "persist": False, "explain": False})
    assert r.status_code == 200 and r.json()["run_id"] is None
    with dbm.SessionLocal() as s:
        assert s.query(dbm.Submission).count() == 0


def test_evaluation_dashboard_says_not_evaluated_before_any_run(client):
    A = login(client, "admin")
    assert client.get("/api/v1/evaluations", headers=A).json() == []
