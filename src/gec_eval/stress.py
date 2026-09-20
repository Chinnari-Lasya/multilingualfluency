"""Stress evaluation: perturb inputs, call the system, check INVARIANTS (not accuracy):
no crash; edit offsets consistent with the returned source; applying the edits reproduces the output;
already-correct text is not damaged by harmless noise; latency stays bounded."""
from __future__ import annotations

import time
from typing import Callable

import numpy as np

from gec_common.align import apply_edits
from gec_common.schemas import Edit

from .io import Example
from .sut import SystemUnderTest

PERTURBATIONS: dict[str, Callable[[str], str]] = {
    "extra_spaces": lambda s: s.replace(" ", "   "),
    "emoji_suffix": lambda s: s + " 😀🎉",
    "url_suffix": lambda s: s + " https://example.com/a?b=1&c=2",
    "code_switch_suffix": lambda s: s + " OK meeting 3pm",
    "native_and_ascii_digits": lambda s: s + " 123 ५६७ ౧౨౩",
    "rtl_mark_prefix": lambda s: "‏" + s,
    "zero_width_space_inside": lambda s: s.replace(" ", " ​", 1),
    "newline_split": lambda s: s.replace(" ", "\n", 1),
    "very_long_token": lambda s: s + " " + "a" * 400,
    "repeated_30x": lambda s: " ".join([s] * 30),
}
# perturbations that only APPEND/prepend noise: the original text must survive unchanged if it was correct
_PRESERVE = {"emoji_suffix", "url_suffix", "code_switch_suffix", "native_and_ascii_digits", "rtl_mark_prefix"}


def _consistent(out: dict) -> bool:
    try:
        src = out["source"]
        edits = [Edit(**{**e, "language": e.get("language", "en")}) for e in out.get("edits", [])
                 if e.get("gate_status") != "rejected"]
        return apply_edits(src, edits) == out["corrected"]  # also validates every span against the source
    except Exception:  # noqa: BLE001
        return False


def run_stress(sut: SystemUnderTest, examples: list[Example], per_language: int = 3,
               perturbations: dict[str, Callable[[str], str]] | None = None) -> dict:
    perturbations = perturbations or PERTURBATIONS
    picked: list[Example] = []
    seen: dict[str, int] = {}
    for e in examples:
        if e.is_correct and seen.get(e.lang, 0) < per_language:
            picked.append(e)
            seen[e.lang] = seen.get(e.lang, 0) + 1
    report: dict = {"n_base_examples": len(picked), "perturbations": {}, "system": sut.name}
    for name, fn in perturbations.items():
        crashes = structured = inconsistent = preserved = n_pres = 0
        lat: list[float] = []
        for ex in picked:
            text = fn(ex.source)
            t0 = time.perf_counter()
            try:
                out = sut.correct(text, ex.lang)
            except Exception as err:  # noqa: BLE001
                msg = str(err)
                # 4xx-style structured rejections are ACCEPTABLE behaviour; anything else is a crash
                if "HTTP 4" in msg or "InvalidInput" in msg or "InputTooLong" in msg or "LanguageMismatch" in msg:
                    structured += 1
                else:
                    crashes += 1
                continue
            lat.append((time.perf_counter() - t0) * 1000)
            if not _consistent(out):
                inconsistent += 1
            if name in _PRESERVE:
                n_pres += 1
                core = ex.source.strip()
                if core in out.get("corrected", ""):
                    preserved += 1
        n = len(picked)
        report["perturbations"][name] = {
            "n": n, "crash_rate": round(crashes / n, 4), "structured_rejection_rate": round(structured / n, 4),
            "inconsistent_edit_rate": round(inconsistent / max(1, n - crashes - structured), 4),
            "correct_text_preserved_rate": round(preserved / n_pres, 4) if n_pres else None,
            "latency_ms_p95": round(float(np.percentile(lat, 95)), 1) if lat else None,
        }
    return report
