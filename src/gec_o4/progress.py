"""O4 learner-progress tracking: pure functions over recorded outcomes (rebuildable from the database).

Counting rule (documented, so progress numbers are explainable): an edit counts as a learner ERROR unless an
educator rejected it. A learner rejecting a suggestion does NOT remove it (the learner may be wrong), unless an
educator accepted it (then it counts regardless). No mastery claim is made from fewer than 3 submissions.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class EditOutcome:
    submission_id: int
    submitted_at: float  # epoch seconds, orders submissions
    language: str
    tokens: int
    error_type: str
    educator_verdict: str | None = None  # accept | reject | revise | None


def counts_as_error(o: EditOutcome) -> bool:
    return o.educator_verdict != "reject"


def progress_report(outcomes: list[EditOutcome], submissions: list[tuple[int, float, str, int]],
                    recent_n: int = 3) -> dict:
    """submissions: (id, submitted_at, language, tokens) for ALL of the learner's submissions (incl. error-free)."""
    report: dict = {"languages": {}, "min_submissions_for_trend": recent_n}
    by_lang: dict[str, list[tuple[int, float, int]]] = defaultdict(list)
    for sid, ts, lang, toks in submissions:
        by_lang[lang].append((sid, ts, toks))
    for lang, subs in by_lang.items():
        subs.sort(key=lambda x: x[1])
        recent_ids = {s[0] for s in subs[-recent_n:]}
        earlier_ids = {s[0] for s in subs[:-recent_n]}
        tok_recent = sum(t for sid, _, t in subs if sid in recent_ids) or 1
        tok_earlier = sum(t for sid, _, t in subs if sid in earlier_ids)
        types: dict[str, dict] = {}
        for o in outcomes:
            if o.language != lang or not counts_as_error(o):
                continue
            d = types.setdefault(o.error_type, {"recent": 0, "earlier": 0, "total": 0})
            d["total"] += 1
            d["recent" if o.submission_id in recent_ids else "earlier"] += 1
        rows = []
        for et, d in types.items():
            rr = 100 * d["recent"] / tok_recent
            er = 100 * d["earlier"] / tok_earlier if tok_earlier else None
            if len(subs) < recent_n + 1 or er is None:
                trend = "insufficient_data"
            elif rr < er * 0.8:
                trend = "improving"
            elif rr > er * 1.2:
                trend = "worsening"
            else:
                trend = "stable"
            rows.append({"error_type": et, "total": d["total"], "recent_per_100_tokens": round(rr, 2),
                         "earlier_per_100_tokens": None if er is None else round(er, 2), "trend": trend})
        rows.sort(key=lambda r: (-r["recent_per_100_tokens"], -r["total"]))
        report["languages"][lang] = {
            "submissions": len(subs),
            "error_types": rows,
            "focus": [r["error_type"] for r in rows[:3] if r["recent_per_100_tokens"] > 0],
            "note": None if len(subs) >= recent_n + 1 else
            f"Fewer than {recent_n + 1} submissions in this language: trends are not reported yet.",
        }
    return report
