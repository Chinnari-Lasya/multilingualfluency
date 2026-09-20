"""O4 confidence. RAW confidence is an uncalibrated heuristic over model/verifier evidence; a Calibrator can be
fitted ONLY from labelled outcomes (gold references or independent educator verdicts). Until one is fitted, every
edit is reported with ``confidence_calibrated=False`` and the UI must say so.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from gec_common.schemas import CorrectionResult, Edit

ZERO_SHOT_CAP = 0.6  # zero-shot capability (Telugu): cap evidence, the model never saw the language in training


def raw_confidence(edit: Edit, capability: str) -> float:
    s = edit.scores
    if edit.source.startswith("rule:"):
        conf = 0.9
    else:
        parts = []
        if "seq_prob" in s:
            parts.append(float(s["seq_prob"]))
        if "support" in s:
            parts.append(float(s["support"]))
        if "edit_similarity" in s:
            parts.append(float(np.clip((s["edit_similarity"] - 0.8) / 0.2, 0.0, 1.0)))
        conf = float(np.mean(parts)) if parts else 0.3
    if capability == "seq2seq_gec_zero_shot" and not edit.source.startswith("rule:"):
        conf = min(conf, ZERO_SHOT_CAP)
    return round(float(np.clip(conf, 0.0, 1.0)), 3)


@dataclass
class Calibrator:
    """Histogram-binning calibrator: maps raw confidence -> empirical accuracy per bin."""

    edges: list[float]
    values: list[float]
    n_fit: int

    @classmethod
    def fit(cls, conf, correct, n_bins: int = 10) -> "Calibrator":
        c, y = np.asarray(conf, float), np.asarray(correct, float)
        if len(c) < 30:
            raise ValueError(f"Refusing to fit a calibrator on {len(c)} samples (<30): not meaningful")
        edges = np.linspace(0, 1, n_bins + 1)
        prior = float(y.mean())
        vals = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = (c >= lo) & ((c < hi) if hi < 1 else (c <= hi))
            vals.append(float(y[m].mean()) if m.sum() >= 5 else prior)
        return cls(edges.tolist(), vals, len(c))

    def predict(self, conf: float) -> float:
        i = int(np.clip(np.searchsorted(self.edges, conf, side="right") - 1, 0, len(self.values) - 1))
        return round(self.values[i], 3)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.__dict__), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Calibrator":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def apply_confidence(result: CorrectionResult, calibrator: Calibrator | None = None) -> CorrectionResult:
    cap = result.capability.level if result.capability else "none"
    for e in result.edits:
        raw = raw_confidence(e, cap)
        e.scores["confidence_raw"] = raw
        e.confidence = calibrator.predict(raw) if calibrator else raw
        e.confidence_calibrated = calibrator is not None
    return result
