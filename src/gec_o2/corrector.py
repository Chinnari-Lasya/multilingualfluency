"""O2 reproducible reference corrector: detect -> minimal correct -> align -> language analysis.

Deterministic: beam search, no sampling, fixed rules. Never imports O3. Produces raw model evidence in
``Edit.scores`` (seq_prob); turning that into a user-facing confidence is O4's job.
"""
from __future__ import annotations

import math
import time
from contextlib import contextmanager

from gec_common.align import apply_edits, extract_edits, spans_overlap
from gec_common.config import language_capability, load_models_config
from gec_common.errors import ModelUnavailableError
from gec_common.langs import get_language, resolve_language
from gec_common.runtime import get_seq2seq, script_consistent
from gec_common.schemas import CapabilityInfo, CorrectionResult, Edit, Flag, Mode, StageTrace
from gec_common.text import normalize, split_sentences

from .analysis import refine_type
from .detector import detect_flags
from .rules import apply_rules

MAX_SENTENCES = 40


class O2Reference:
    name = "o2"

    def __init__(self, *, use_detector: bool = True, use_model: bool = True):
        self.use_detector = use_detector
        self.use_model = use_model

    def capability(self, lang: str) -> CapabilityInfo:
        return language_capability(get_language(lang).code)

    @contextmanager
    def _stage(self, trace: list[StageTrace], name: str):
        t0 = time.perf_counter()
        rec = StageTrace(stage=name, status="ok")
        try:
            yield rec
        except Exception as e:  # noqa: BLE001 - a failing stage degrades, it never crashes the request
            rec.status, rec.detail = "failed", f"{type(e).__name__}: {e}"[:300]
        finally:
            rec.ms = round((time.perf_counter() - t0) * 1000, 1)
            trace.append(rec)

    def correct(self, text: str, lang: str | None = None, mode: Mode = "reference") -> CorrectionResult:
        t_all = time.perf_counter()
        text = normalize(text)
        res_lang = resolve_language(text, lang)
        lang = res_lang.language
        cap = self.capability(lang)
        gen_key = load_models_config()["languages"][lang].get("generator")
        trace: list[StageTrace] = []
        warnings: list[str] = list(res_lang.warnings)
        edits: list[Edit] = []
        flags: list[Flag] = []
        model_ids: dict[str, str] = {}
        degraded = False
        if mode != "reference":
            warnings.append(f"O2 has a single reference mode; requested mode {mode!r} ignored.")

        spans = split_sentences(text)
        if len(spans) > MAX_SENTENCES:
            warnings.append(f"Only the first {MAX_SENTENCES} sentences were processed.")
            spans = spans[:MAX_SENTENCES]

        model_ok = self.use_model and gen_key is not None
        model_failed = False
        n_skipped = 0
        t_model = t_rules = 0.0
        for a, b in spans:
            sent = text[a:b]
            model_edits: list[Edit] = []
            if model_ok and not model_failed:
                t0 = time.perf_counter()
                try:
                    m = get_seq2seq(gen_key)
                    model_ids["generator"] = m.hf_id
                    if m.token_len(sent) > m.max_input_tokens:
                        n_skipped += 1
                    else:
                        cand = m.generate(sent)[0]
                        out = cand.text
                        ratio = len(out) / max(1, len(sent))
                        if not out or not (0.5 <= ratio <= 2.0) or not script_consistent(sent, out):
                            warnings.append("Model output rejected by safety guard (length/script); sentence left unchanged.")
                        elif out != sent:
                            for e in extract_edits(sent, out, lang, offset=a):
                                e.source = f"model:{gen_key}"
                                e.scores = {"seq_prob": round(math.exp(cand.score), 4)}
                                model_edits.append(e)
                except ModelUnavailableError as e:
                    model_failed, degraded = True, True
                    warnings.append(f"Neural model unavailable ({e.message}); using rules only.")
                    trace.append(StageTrace(stage="generator", status="failed", detail=e.message[:200]))
                t_model += time.perf_counter() - t0
            t0 = time.perf_counter()
            rule_edits = [r for r in apply_rules(sent, lang, offset=a)
                          if not any(spans_overlap(r, m_) for m_ in model_edits)]
            t_rules += time.perf_counter() - t0
            edits.extend(model_edits + rule_edits)

        if gen_key is None:
            trace.append(StageTrace(stage="generator", status="skipped",
                                    detail=f"no GEC checkpoint for {lang} (capability={cap.level})"))
        elif not model_failed:
            trace.append(StageTrace(stage="generator", status="degraded" if n_skipped else "ok", ms=round(t_model * 1000, 1),
                                    detail=f"{n_skipped} over-long sentence(s) skipped" if n_skipped else None))
        if n_skipped:
            warnings.append(f"{n_skipped} sentence(s) exceeded the model input limit and were not model-corrected.")
        trace.append(StageTrace(stage="rules", status="ok", ms=round(t_rules * 1000, 1)))

        with self._stage(trace, "analysis"):
            edits = [refine_type(e) for e in edits]

        if self.use_detector:
            with self._stage(trace, "detector") as rec:
                for a, b in spans:
                    flags.extend(detect_flags(text[a:b], offset=a))
                edits_spans = [(e.start, e.end) for e in edits]
                flags = [f for f in flags if not any(s < f.end and f.start < e_ for s, e_ in edits_spans)]
                model_ids["detector"] = load_models_config()["models"]["mlm_detector"]["hf_id"]
            if rec.status == "failed":
                degraded = True
                warnings.append("Error detector unavailable; no detection flags produced.")

        edits.sort(key=lambda e: (e.start, e.end))
        corrected = apply_edits(text, edits)
        return CorrectionResult(
            pipeline="o2", mode="reference", language=lang, language_detection=res_lang, source=text,
            corrected=corrected, edits=edits, flags=flags, capability=cap, degraded=degraded,
            warnings=warnings, trace=trace, model_ids=model_ids,
            latency_ms=round((time.perf_counter() - t_all) * 1000, 1),
        )
