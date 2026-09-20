"""Composition root: normalise -> (O2 | O3) -> assessment -> O4 confidence -> O4 explanations.
The only place that wires the independent packages together."""
from __future__ import annotations

import threading

from gec_common.align import tokenize
from gec_common.config import thresholds
from gec_common.errors import ModelUnavailableError
from gec_common.runtime import get_embedder
from gec_common.schemas import CorrectionResult
from gec_o2.corrector import O2Reference
from gec_o3.controlled import O3Controlled
from gec_o3.gates import hard_violations
from gec_o4.confidence import Calibrator, apply_confidence
from gec_o4.explain import explain
from gec_o4.llm import provider_from_env


def assess(res: CorrectionResult, embedder=None) -> dict:
    """Post-hoc, pipeline-independent status of the FINAL output: meaning preservation + over-correction risk.
    Heuristic and uncalibrated; it reports evidence, it does not certify correctness."""
    tau = thresholds("o3")["minimal"]["min_sentence_similarity"]
    src, out, lang = res.source, res.corrected, res.language
    if src == out:
        mp = {"status": "preserved", "similarity": 1.0, "note": "text unchanged"}
    else:
        try:
            sim = round((embedder or get_embedder()).similarity(src, out), 4)
            viol = hard_violations(src, out, lang)
            status = "violated" if viol else ("preserved" if sim >= tau else "uncertain")
            mp = {"status": status, "similarity": sim, "threshold": tau, "hard_check_failures": viol}
        except ModelUnavailableError:
            mp = {"status": "not_checked", "note": "embedder unavailable"}
    applied = [e for e in res.edits if e.gate_status != "rejected"]
    rejected = [e for e in res.edits if e.gate_status == "rejected"]
    n_tok = max(1, len(tokenize(src, lang)))
    changed = sum(max(1, len(tokenize(e.original, lang)), len(tokenize(e.replacement, lang))) for e in applied)
    ratio = round(changed / n_tok, 3)
    import regex
    g = lambda x: len(regex.findall(r"\X", x.strip()))  # noqa: E731
    rewrites = sum(e.error_type == "WORD_CHOICE" and g(e.original) >= 4 and g(e.replacement) >= 4 for e in applied)
    level = "high" if ratio > 0.5 else "medium" if (ratio > 0.3 or rewrites) else "low"
    oc = {"risk": level, "edit_ratio": ratio, "applied_edits": len(applied), "lexical_rewrites_applied": rewrites,
          "edits_blocked_by_gates": [{"original": e.original, "replacement": e.replacement, "reason": e.gate_reason}
                                     for e in rejected if (e.gate_reason or "").startswith("overcorrection")],
          "note": "Heuristic. O3 actively blocks over-correction; O2 does not gate."}
    return {"meaning_preservation": mp, "over_correction": oc}


class Coach:
    def __init__(self, calibrator: Calibrator | None = None, max_concurrent: int = 2):
        self.o2, self.o3 = O2Reference(), O3Controlled()
        self.calibrator = calibrator
        self.llm = provider_from_env()
        self._sem = threading.Semaphore(max_concurrent)

    def run(self, text: str, language: str | None, pipeline: str = "o2", mode: str = "reference",
            with_explanations: bool = True) -> tuple[CorrectionResult, list[dict | None]]:
        with self._sem:
            if pipeline == "o3":
                res = self.o3.correct(text, language, mode if mode in ("minimal", "fluency") else "minimal")
            else:
                res = self.o2.correct(text, language, "reference")
        apply_confidence(res, self.calibrator)
        try:
            res.assessment = assess(res)
        except Exception as err:  # noqa: BLE001 - assessment failure must not fail the correction
            res.assessment = {"error": f"{type(err).__name__}"}
            res.warnings.append("Assessment unavailable.")
        exps: list[dict | None] = []
        for e in res.edits:
            if not with_explanations:
                exps.append(None)
                continue
            try:
                exps.append(explain(e, self.llm).model_dump())
            except Exception as err:  # noqa: BLE001
                exps.append({"text": "Explanation unavailable.", "rule_id": "none", "source": "template",
                             "verified": False, "fallback_reason": type(err).__name__})
        return res, exps
