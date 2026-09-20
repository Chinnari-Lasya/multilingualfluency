"""Systems under test. The evaluator talks to a system only through this tiny interface (HTTP or callable),
so it never imports model code and can score any GEC system that returns API-shaped JSON."""
from __future__ import annotations

import time
from typing import Callable, Protocol

import httpx

from .io import Example, PredEdit, Prediction


class SystemUnderTest(Protocol):
    name: str

    def correct(self, text: str, lang: str) -> dict: ...


class CallableSUT:
    def __init__(self, fn: Callable[[str, str], dict], name: str = "callable"):
        self.fn, self.name = fn, name

    def correct(self, text: str, lang: str) -> dict:
        return self.fn(text, lang)


class HttpSUT:
    """POST {base}/api/v1/corrections. Works against this project's API or anything returning the same shape."""

    def __init__(self, base_url: str, pipeline: str = "o2", mode: str = "reference", token: str | None = None,
                 timeout: float = 300.0):
        self.base, self.pipeline, self.mode, self.timeout = base_url.rstrip("/"), pipeline, mode, timeout
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.name = f"http:{pipeline}/{mode}"

    def correct(self, text: str, lang: str) -> dict:
        r = httpx.post(f"{self.base}/api/v1/corrections", headers=self.headers, timeout=self.timeout,
                       json={"text": text, "language": lang, "pipeline": self.pipeline, "mode": self.mode,
                             "persist": False, "explain": False})
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        return r.json()


def to_prediction(ex: Example, out: dict, latency_ms: float) -> Prediction:
    edits = [PredEdit(start=e["start"], end=e["end"], original=e.get("original", ""),
                      replacement=e.get("replacement", ""), confidence=e.get("confidence"),
                      confidence_calibrated=bool(e.get("confidence_calibrated")),
                      gate_status=e.get("gate_status", "not_applicable"))
             for e in out.get("edits", []) if e.get("gate_status") != "rejected"]
    return Prediction(id=ex.id, lang=ex.lang, output=out.get("corrected"), latency_ms=latency_ms,
                      degraded=bool(out.get("degraded")), edits=edits)


def collect_predictions(sut: SystemUnderTest, examples: list[Example], progress: Callable[[int, int], None] | None = None
                        ) -> list[Prediction]:
    preds = []
    for i, ex in enumerate(examples, 1):
        t0 = time.perf_counter()
        try:
            out = sut.correct(ex.source, ex.lang)
            preds.append(to_prediction(ex, out, (time.perf_counter() - t0) * 1000))
        except Exception as e:  # noqa: BLE001 - a crash is a RESULT, recorded and counted, never hidden
            preds.append(Prediction(id=ex.id, lang=ex.lang, output=None, error=f"{type(e).__name__}: {e}"[:300],
                                    latency_ms=(time.perf_counter() - t0) * 1000))
        if progress:
            progress(i, len(examples))
    return preds
