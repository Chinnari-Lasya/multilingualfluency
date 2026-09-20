"""Shared data contracts. Offsets are Unicode CODE POINTS into the NFC-normalized source text
(NOT UTF-16 units: the frontend must convert)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["reference", "minimal", "fluency"]
Op = Literal["insert", "delete", "replace"]
GateStatus = Literal["accepted", "rejected", "not_applicable"]
StageStatus = Literal["ok", "skipped", "failed", "degraded"]


class Edit(BaseModel):
    start: int
    end: int
    original: str
    replacement: str
    op: Op
    language: str
    error_type: str = "OTHER"
    rule_id: str | None = None
    source: str = "unknown"  # "model:<key>" | "rule:<id>" | "mlm:<key>"
    confidence: float | None = None
    confidence_calibrated: bool = False
    gate_status: GateStatus = "not_applicable"
    gate_reason: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)


class Flag(BaseModel):
    """A suspicious span with NO applied correction (detection-only output)."""

    start: int
    end: int
    text: str
    score: float
    reason: str
    suggestion: str | None = None
    source: str = "mlm"


class StageTrace(BaseModel):
    stage: str
    status: StageStatus
    ms: float = 0.0
    detail: str | None = None


class LangResolution(BaseModel):
    language: str
    detected: str
    confidence: float
    method: str
    mixed_script: bool = False
    warnings: list[str] = Field(default_factory=list)
    script_shares: dict[str, float] = Field(default_factory=dict)


class CapabilityInfo(BaseModel):
    language: str
    level: Literal["seq2seq_gec", "seq2seq_gec_zero_shot", "rules_and_detection", "none"]
    model_id: str | None = None
    summary: str
    limitations: list[str] = Field(default_factory=list)
    license_note: str | None = None


class CorrectionResult(BaseModel):
    pipeline: str  # "o2" | "o3"
    mode: Mode
    language: str
    language_detection: LangResolution | None = None
    source: str
    corrected: str
    edits: list[Edit] = Field(default_factory=list)  # includes gate-rejected edits (gate_status)
    flags: list[Flag] = Field(default_factory=list)
    capability: CapabilityInfo | None = None
    degraded: bool = False
    abstained: bool = False  # O3: meaning preservation uncertain -> no edit applied
    abstain_reason: str | None = None
    assessment: dict = Field(default_factory=dict)  # meaning-preservation + over-correction status (composition root)
    warnings: list[str] = Field(default_factory=list)
    trace: list[StageTrace] = Field(default_factory=list)
    model_ids: dict[str, str] = Field(default_factory=dict)
    latency_ms: float = 0.0

    @property
    def applied_edits(self) -> list[Edit]:
        return [e for e in self.edits if e.gate_status != "rejected"]
