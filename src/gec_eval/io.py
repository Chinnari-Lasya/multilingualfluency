"""Dataset / prediction file formats (JSONL). The evaluator sees ONLY these files: never model code.

Dataset:     first line {"_meta": {"name","kind","license","description",...}} then one example per line:
             {"id","lang","source","references":[...],"tags":[...]}   references==[source] means 'already correct'
Predictions: {"id","lang","output","latency_ms","degraded","error","edits":[{start,end,original,replacement,
             confidence,confidence_calibrated,gate_status}]}
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

DATASET_KINDS = ("smoke_fixture", "public_dev", "held_out", "stress")


class Example(BaseModel):
    id: str
    lang: str
    source: str
    references: list[str]
    tags: list[str] = Field(default_factory=list)

    @property
    def is_correct(self) -> bool:
        return all(r == self.source for r in self.references)


class PredEdit(BaseModel):
    start: int
    end: int
    original: str = ""
    replacement: str = ""
    confidence: float | None = None
    confidence_calibrated: bool = False
    gate_status: str = "not_applicable"


class Prediction(BaseModel):
    id: str
    lang: str
    output: str | None = None
    latency_ms: float | None = None
    degraded: bool = False
    error: str | None = None
    edits: list[PredEdit] = Field(default_factory=list)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_dataset(path: str | Path) -> tuple[dict, list[Example]]:
    meta, items = {}, []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "_meta" in obj:
                meta = obj["_meta"]
                continue
            ex = Example(**obj)
            if not ex.references:
                raise ValueError(f"{path}:{ln} example {ex.id} has no references")
            items.append(ex)
    if meta.get("kind") not in DATASET_KINDS:
        raise ValueError(f"dataset _meta.kind must be one of {DATASET_KINDS}, got {meta.get('kind')!r}")
    return meta, items


def load_predictions(path: str | Path) -> list[Prediction]:
    with open(path, encoding="utf-8") as f:
        return [Prediction(**json.loads(line)) for line in f if line.strip()]


def write_jsonl(path: str | Path, rows: list[dict | BaseModel]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r.model_dump() if isinstance(r, BaseModel) else r, ensure_ascii=False) + "\n")
