"""Run an evaluation and produce a provenance-stamped report. Numbers exist ONLY if computed here from a
dataset + predictions; anything not measured is reported as 'not_evaluated' / 'not_performed_yet'."""
from __future__ import annotations

import datetime as dt
import platform
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from gec_common.runtime import get_embedder

from . import metrics as M
from .io import Example, Prediction, sha256_file

MP_TAU_DEFAULT = 0.90  # UNCALIBRATED default: see docs/evaluation.md


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
                              cwd=Path(__file__).resolve().parents[2]).stdout.strip() or "no-commit"
    except Exception:  # noqa: BLE001
        return "unknown"


def _bootstrap(fn, n: int, k: int = 400, seed: int = 13) -> list[float] | None:
    if n < 8:
        return None
    rng = np.random.default_rng(seed)
    vals = sorted(fn(rng.integers(0, n, n)) for _ in range(k))
    return [round(vals[int(0.025 * k)], 4), round(vals[int(0.975 * k) - 1], 4)]


def _lang_metrics(exs: list[Example], preds: dict[str, Prediction], embedder, tau: float) -> dict:
    ok = [(e, preds[e.id]) for e in exs if e.id in preds and preds[e.id].output is not None]
    failed = len(exs) - len(ok)
    out: dict = {"n_examples": len(exs), "n_scored": len(ok), "n_failed_or_missing": failed}
    if not ok:
        return out
    E = [e for e, _ in ok]
    O = [p.output for _, p in ok]
    # GLEU
    G = M.gleu_matrix(E, O)
    out["gleu"] = {"value": round(M.gleu_score(G), 4),
                   "ci95": _bootstrap(lambda idx: M.gleu_score(G[idx]), len(E)),
                   "baseline_identity": round(M.gleu_score(M.gleu_matrix(E, [e.source for e in E])), 4)}
    # F0.5 + over-correction (edit level)
    C = [M.edit_counts(e, o) for e, o in zip(E, O)]
    tp, fp, fn = (sum(c[k] for c in C) for k in ("tp", "fp", "fn"))
    arr = np.array([[c["tp"], c["fp"], c["fn"]] for c in C], float)
    f = M.prf(tp, fp, fn)
    out["edit_f0.5"] = {**{k: round(v, 4) for k, v in f.items()}, "tp": tp, "fp": fp, "fn": fn,
                        "ci95": _bootstrap(lambda idx: M.prf(*arr[idx].sum(0))["f0.5"], len(E))}
    n_hyp, n_over = sum(c["n_hyp"] for c in C), sum(c["n_over"] for c in C)
    correct = [i for i, e in enumerate(E) if e.is_correct]
    changed_correct = sum(O[i] != E[i].source for i in correct)
    out["over_correction"] = {
        "sentence_level": {"n_already_correct": len(correct), "changed": changed_correct,
                           "rate": round(changed_correct / len(correct), 4) if correct else None},
        "edit_level": {"n_hyp_edits": n_hyp, "in_unprotected_regions": n_over,
                       "rate": round(n_over / n_hyp, 4) if n_hyp else None,
                       "definition": "hypothesis edits touching a region that NO reference edits"},
    }
    # meaning preservation (changed outputs only; unchanged trivially preserves meaning)
    chg = [i for i in range(len(E)) if O[i] != E[i].source]
    if chg:
        sims = embedder.encode([E[i].source for i in chg]), embedder.encode([O[i] for i in chg])
        cos = (sims[0] * sims[1]).sum(1)
        passed = [bool(cos[k] >= tau and not M.mp_checks(E[i].source, O[i], E[i].lang)) for k, i in enumerate(chg)]
        # diagnostic: do the GOLD references themselves pass this MP test? (guards against a too-strict tau)
        refs = [(E[i].source, E[i].references[0]) for i in chg if E[i].references[0] != E[i].source]
        rp = None
        if refs:
            a, b = embedder.encode([s for s, _ in refs]), embedder.encode([r for _, r in refs])
            rc = (a * b).sum(1)
            rp = round(float(np.mean([rc[k] >= tau and not M.mp_checks(s, r, E[0].lang) for k, (s, r) in enumerate(refs)])), 4)
        out["meaning_preservation"] = {"rate_over_changed_outputs": round(float(np.mean(passed)), 4), "n_changed": len(chg),
                                       "threshold_cosine": tau, "threshold_status": "uncalibrated_default",
                                       "gold_reference_pass_rate_diagnostic": rp,
                                       "checks": "embedding cosine + numbers + negation lexicon (heuristic)"}
    else:
        out["meaning_preservation"] = {"rate_over_changed_outputs": None, "n_changed": 0,
                                       "note": "system changed nothing; meaning trivially preserved"}
    # calibration (per-edit confidence vs edit correctness)
    conf, ok_flags = [], []
    for (e, p), c in zip(ok, C):
        by_key = {(pe.start, pe.end, pe.replacement): pe for pe in p.edits}
        for he, good in zip(c["hyp"], c["hyp_correct"]):
            pe = by_key.get((he.start, he.end, he.replacement))
            if pe is not None and pe.confidence is not None:
                conf.append(pe.confidence)
                ok_flags.append(good)
    out["calibration"] = M.calibration(conf, ok_flags)
    out["calibration"]["confidence_calibrated_flag"] = any(pe.confidence_calibrated for _, p in ok for pe in p.edits)
    out["resource_cost"] = M.resource_summary([p for _, p in ok])
    out["crash_rate"] = round(failed / len(exs), 4)
    out["degraded_rate"] = round(sum(p.degraded for _, p in ok) / len(ok), 4)
    return out


def evaluate(meta: dict, examples: list[Example], preds: list[Prediction], *, system: str, dataset_path: str | Path | None = None,
             preds_path: str | Path | None = None, tau: float = MP_TAU_DEFAULT, adjudications: list[dict] | None = None,
             embedder=None, rss_mb: float | None = None) -> dict:
    embedder = embedder or get_embedder()
    pmap = {p.id: p for p in preds}
    by_lang: dict[str, list[Example]] = defaultdict(list)
    for e in examples:
        by_lang[e.lang].append(e)
    per_lang = {lang: _lang_metrics(exs, pmap, embedder, tau) for lang, exs in sorted(by_lang.items())}
    scored = [l for l in per_lang.values() if "gleu" in l]
    macro = {}
    if scored:
        macro = {"gleu": round(float(np.mean([l["gleu"]["value"] for l in scored])), 4),
                 "edit_f0.5": round(float(np.mean([l["edit_f0.5"]["f0.5"] for l in scored])), 4),
                 "note": "unweighted mean over languages"}
    warnings = []
    kind = meta.get("kind")
    if kind == "smoke_fixture":
        warnings.append("SMOKE FIXTURE: developer-authored, tiny, not native-validated. These numbers exercise the harness; they are NOT a validation of the system.")
    if any(len(v) < 30 for v in by_lang.values()):
        warnings.append("Fewer than 30 examples per language: confidence intervals are wide and metrics are unstable.")
    return {
        "system": system,
        "dataset": {"meta": meta, "n": len(examples), "path": str(dataset_path) if dataset_path else None,
                    "sha256": sha256_file(dataset_path) if dataset_path else None},
        "manifest": {"created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "git_sha": _git_sha(),
                     "python": sys.version.split()[0], "platform": platform.platform(),
                     "predictions_sha256": sha256_file(preds_path) if preds_path else None,
                     "mp_threshold": tau, "bootstrap": {"resamples": 400, "seed": 13}},
        "metrics": {"per_language": per_lang, "macro": macro},
        "not_measured": {
            "educator_acceptance": M.educator_acceptance(adjudications or []),
            "held_out_evaluation": {"status": "not_performed_yet", "note": "No locked held-out split exists yet."},
            "human_meaning_preservation_audit": {"status": "not_performed_yet"},
        },
        "warnings": warnings,
    }
