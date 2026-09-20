"""Metric sanity tests: properties any correct GLEU / F0.5 / over-correction implementation must satisfy."""
import numpy as np
import pytest

from gec_eval import metrics as M
from gec_eval.io import Example, PredEdit, Prediction
from gec_eval.report import evaluate


def ex(i, src, *refs, lang="en"):
    return Example(id=i, lang=lang, source=src, references=list(refs) or [src])


DATA = [
    ex("a", "He go to school .", "He goes to school ."),
    ex("b", "I has a apple .", "I have an apple ."),
    ex("c", "This is fine .", "This is fine ."),
    ex("d", "She like cats .", "She likes cats ."),
]


def outputs(kind):
    if kind == "identity":
        return [e.source for e in DATA]
    if kind == "oracle":
        return [e.references[0] for e in DATA]
    if kind == "overcorrect":  # fixes the errors but also rewrites the correct sentence
        return [e.references[0] if not e.is_correct else "This is very fine ." for e in DATA]


def test_gleu_oracle_is_one_and_identity_is_lower():
    o, i = M.gleu_score(M.gleu_matrix(DATA, outputs("oracle"))), M.gleu_score(M.gleu_matrix(DATA, outputs("identity")))
    assert o == pytest.approx(1.0) and i < o


def test_f05_oracle_identity_and_overcorrection():
    def tot(kind):
        c = [M.edit_counts(e, o) for e, o in zip(DATA, outputs(kind))]
        return M.prf(*(sum(x[k] for x in c) for k in ("tp", "fp", "fn")))
    assert tot("oracle")["f0.5"] == pytest.approx(1.0)
    ident = tot("identity")
    assert ident["recall"] == 0.0 and ident["f0.5"] == 0.0
    oc = tot("overcorrect")
    assert oc["recall"] == 1.0 and oc["precision"] < 1.0


def test_over_correction_flags_edit_in_unprotected_region():
    c = M.edit_counts(DATA[2], "This is very fine .")  # reference == source, so any edit is unprotected
    assert c["n_hyp"] == 1 and c["n_over"] == 1
    c = M.edit_counts(DATA[0], "He goes to school .")
    assert c["n_over"] == 0 and c["tp"] == 1


def test_best_reference_is_chosen():
    e = ex("x", "I likes swimming .", "I like swimming .", "I enjoy swimming .")
    assert M.edit_counts(e, "I enjoy swimming .")["tp"] == 1


def test_mp_checks_numbers_and_negation_across_scripts():
    assert M.mp_checks("She did not go with 5 friends", "She did go with 5 friends", "en") == ["negation_changed"]
    assert M.mp_checks("我 5", "我 6", "en") == ["number_changed"]
    assert M.mp_checks("నాకు ౫ పుస్తకాలు", "నాకు 5 పుస్తకాలు", "te") == []  # Telugu digit == ASCII digit
    assert M.mp_checks("私は行きません", "私は行きます", "ja") == ["negation_changed"]


def test_calibration_perfect_and_miscalibrated_and_small_n():
    rng = np.random.default_rng(0)
    conf = rng.uniform(0, 1, 2000)
    good = M.calibration(conf, rng.uniform(0, 1, 2000) < conf)
    bad = M.calibration(np.full(2000, 0.95), rng.uniform(0, 1, 2000) < 0.5)
    assert good["ece"] < 0.05 < bad["ece"] and good["status"] == "ok"
    assert M.calibration([0.9] * 10, [True] * 10)["status"] == "insufficient_samples"
    assert M.calibration([], [])["status"] == "not_evaluated"


def test_educator_acceptance_never_counts_non_independent_reviewers():
    demo = [{"verdict": "accept", "reviewer_independent": False, "reviewer_id": 1}] * 50
    assert M.educator_acceptance(demo)["status"] == "not_performed_yet"
    assert M.educator_acceptance([])["status"] == "not_performed_yet"
    real = [{"verdict": "accept", "reviewer_independent": True, "reviewer_id": 2}] * 3 + \
           [{"verdict": "reject", "reviewer_independent": True, "reviewer_id": 2}]
    r = M.educator_acceptance(real)
    assert r["acceptance_rate"] == 0.75 and r["status"] == "insufficient_samples"


class FakeEmb:
    def encode(self, texts):
        v = np.array([[1.0, 0.0] if "very" not in t else [0.6, 0.8] for t in texts])
        return v


def test_evaluate_report_structure_and_honest_placeholders():
    preds = [Prediction(id=e.id, lang=e.lang, output=o, latency_ms=10.0) for e, o in zip(DATA, outputs("overcorrect"))]
    rep = evaluate({"kind": "smoke_fixture", "name": "t"}, DATA, preds, system="unit", embedder=FakeEmb())
    en = rep["metrics"]["per_language"]["en"]
    assert en["over_correction"]["sentence_level"]["rate"] == 1.0
    assert en["meaning_preservation"]["n_changed"] == 4
    assert rep["not_measured"]["educator_acceptance"]["status"] == "not_performed_yet"
    assert rep["not_measured"]["held_out_evaluation"]["status"] == "not_performed_yet"
    assert any("SMOKE" in w for w in rep["warnings"])
    assert en["calibration"]["status"] == "not_evaluated"  # predictions carried no confidences
