"""O5 metrics. Own implementations (NOT cross-validated against official scripts: see docs/evaluation.md).

* GLEU  - Napoles et al. 2015/2016 corpus-level, n=1..4, source-penalised; multiple references handled by a
          deterministic sweep over reference indices (official script samples references randomly).
* F0.5  - edit-level P/R with best-reference selection (ERRANT-style tie-breaks), edits from gec_common.align.
* Over-correction - sentence level (already-correct inputs changed) and edit level (edits touching regions that
          NO reference edits).
* Meaning preservation - embedding similarity + numbers + negation, with THIS package's own lexicon.
* Calibration - ECE / Brier / reliability bins on per-edit confidence vs edit correctness.
"""
from __future__ import annotations

import math
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import regex

from gec_common.align import extract_edits, tokenize

from .io import Example, Prediction

# ------------------------------------------------------------------------------------------------- GLEU


def _ngrams(toks: list[str], n: int) -> Counter:
    return Counter(tuple(toks[i:i + n]) for i in range(len(toks) - n + 1))


def gleu_sentence_stats(src: list[str], hyp: list[str], ref: list[str]) -> np.ndarray:
    """[hlen, rlen, (matches_n, total_n) for n=1..4]."""
    out = [len(hyp), len(ref)]
    for n in range(1, 5):
        h, s, r = _ngrams(hyp, n), _ngrams(src, n), _ngrams(ref, n)
        m = sum((h & r).values()) - sum(((h & s) - r).values())
        out += [max(m, 0), max(len(hyp) + 1 - n, 0)]
    return np.array(out, dtype=float)


def gleu_from_stats(stats: np.ndarray) -> float:
    if stats[0] <= 0 or np.any(stats[2::2] <= 0) or np.any(stats[3::2] <= 0):
        return 0.0
    log_prec = np.mean(np.log(stats[2::2] / stats[3::2]))
    return float(math.exp(min(0.0, 1 - stats[1] / stats[0]) + log_prec))


def gleu_matrix(examples: list[Example], outputs: list[str]) -> np.ndarray:
    """(n_examples, K, 10) stats; K = max #references (references cycled for shorter lists)."""
    K = max(len(e.references) for e in examples)
    M = np.zeros((len(examples), K, 10))
    for i, (e, o) in enumerate(zip(examples, outputs)):
        s, h = [t.text for t in tokenize(e.source, e.lang)], [t.text for t in tokenize(o, e.lang)]
        for k in range(K):
            r = [t.text for t in tokenize(e.references[k % len(e.references)], e.lang)]
            M[i, k] = gleu_sentence_stats(s, h, r)
    return M


def gleu_score(M: np.ndarray) -> float:
    return float(np.mean([gleu_from_stats(M[:, k].sum(axis=0)) for k in range(M.shape[1])]))


# ------------------------------------------------------------------------------------------------- F0.5


def _key(e) -> tuple[int, int, str]:
    return (e.start, e.end, e.replacement)


def _touch(a, b) -> bool:
    return a.start <= b.end and b.start <= a.end


def edit_counts(ex: Example, output: str) -> dict:
    """TP/FP/FN vs best reference, plus over-correction edit counts, and per-hyp-edit correctness."""
    hyp = extract_edits(ex.source, output, ex.lang)
    hkeys = {_key(e) for e in hyp}
    best = None
    ref_edit_lists = []
    for r in ex.references:
        red = extract_edits(ex.source, r, ex.lang)
        ref_edit_lists.append(red)
        rk = {_key(e) for e in red}
        tp, fp, fn = len(hkeys & rk), len(hkeys - rk), len(rk - hkeys)
        cand = (-tp, fp, fn, tp, rk)
        if best is None or cand[:3] < best[:3]:
            best = cand
    _, _, _, tp, rk = best
    all_ref = [e for lst in ref_edit_lists for e in lst]
    unprotected = [e for e in hyp if not any(_touch(e, r) for r in all_ref)]
    return {"tp": tp, "fp": len(hkeys) - tp, "fn": len(rk) - tp, "n_hyp": len(hyp), "n_over": len(unprotected),
            "hyp_correct": [(_key(e) in rk) for e in hyp], "hyp": hyp}


def prf(tp: float, fp: float, fn: float, beta: float = 0.5) -> dict:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = (1 + beta**2) * p * r / (beta**2 * p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f0.5": f}


# ------------------------------------------------------------------------------- meaning preservation
_NUM = regex.compile(r"\p{Nd}+(?:[.,]\p{Nd}+)*")
_NEG = {
    "en": r"\b(?:not|no|never|none|nothing|nobody|cannot|without)\b|n['’]t\b",
    "hi": r"(?<![\p{L}\p{M}])(?:नहीं|नही|मत|न)(?![\p{L}\p{M}])",
    "te": r"(?:లేదు|లేరు|లేవు|కాదు|వద్దు)",
    "or": r"(?:ନାହିଁ|ନୁହେଁ|ନୁହଁ|ନାହାନ୍ତି|ନଥିଲା)",
    "ja": r"(?:ない|ません|なかっ)",
    "ko": r"(?:않|없|아니|못)|(?<![\p{L}])안(?![\p{L}])",
}
_NEG_RX = {k: regex.compile(v, regex.I) for k, v in _NEG.items()}


def _nums(s: str) -> Counter:
    return Counter("".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in m) for m in _NUM.findall(s))


_EN_CL = regex.compile(r"\b(?:not|no|never|cannot|without)\b|n['’]t\b", regex.I)
_EN_IN = regex.compile(r"\b(?:none|nothing|nobody|nowhere)\b", regex.I)


def _neg_n(text: str, lang: str) -> int:
    if lang == "en":
        c = len(_EN_CL.findall(text))
        return c if c else len(_EN_IN.findall(text))
    return len(_NEG_RX[lang].findall(text))


def mp_checks(source: str, output: str, lang: str) -> list[str]:
    bad = []
    if _nums(source) != _nums(output):
        bad.append("number_changed")
    if _neg_n(source, lang) != _neg_n(output, lang):
        bad.append("negation_changed")
    return bad


# ------------------------------------------------------------------------------------- calibration


def calibration(conf: list[float], correct: list[bool], n_bins: int = 10) -> dict:
    c, y = np.asarray(conf, float), np.asarray(correct, float)
    n = len(c)
    if n == 0:
        return {"status": "not_evaluated", "reason": "no edit confidences in predictions"}
    edges = np.linspace(0, 1, n_bins + 1)
    bins, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (c >= lo) & ((c < hi) if hi < 1 else (c <= hi))
        if m.sum():
            gap = abs(float(y[m].mean()) - float(c[m].mean()))
            ece += m.sum() / n * gap
            bins.append({"lo": round(lo, 2), "hi": round(hi, 2), "n": int(m.sum()),
                         "mean_confidence": round(float(c[m].mean()), 3), "accuracy": round(float(y[m].mean()), 3)})
    return {"status": "ok" if n >= 100 else "insufficient_samples", "n": n, "ece": round(ece, 4),
            "brier": round(float(np.mean((c - y) ** 2)), 4), "bins": bins,
            "warning": None if n >= 100 else f"only {n} edits: ECE is not statistically meaningful (<100)"}


# ------------------------------------------------------------------------------- educator acceptance


def educator_acceptance(adjudications: list[dict]) -> dict:
    """Only INDEPENDENT educators count. Developer/demo adjudications never produce an acceptance number."""
    indep = [a for a in adjudications if a.get("reviewer_independent")]
    if not indep:
        return {"status": "not_performed_yet", "n_independent_reviews": 0,
                "note": "No independent educator has reviewed any output. No acceptance figure exists."}
    acc = sum(a["verdict"] in ("accept", "revise") and a["verdict"] == "accept" for a in indep)
    n = len(indep)
    p = acc / n
    z = 1.96
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return {"status": "ok" if n >= 30 else "insufficient_samples", "n_independent_reviews": n,
            "n_reviewers": len({a.get("reviewer_id") for a in indep}), "acceptance_rate": round(p, 4),
            "wilson_95": [round(centre - half, 4), round(centre + half, 4)]}


# ---------------------------------------------------------------------------------------- resources


def resource_summary(preds: list[Prediction], rss_mb: float | None = None) -> dict:
    lat = [p.latency_ms for p in preds if p.latency_ms is not None]
    if not lat:
        return {"status": "not_evaluated"}
    a = np.asarray(lat)
    return {"status": "ok", "n": len(lat), "latency_ms_p50": round(float(np.percentile(a, 50)), 1),
            "latency_ms_p95": round(float(np.percentile(a, 95)), 1), "latency_ms_mean": round(float(a.mean()), 1),
            "throughput_per_s": round(1000.0 / float(a.mean()), 3) if a.mean() > 0 else None,
            "peak_rss_mb": rss_mb, "llm_tokens": 0, "llm_cost_usd": 0.0,
            "note": "Latency measured on this machine (CPU); not comparable to other hardware."}


@dataclass
class LangAgg:
    examples: list[Example] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
