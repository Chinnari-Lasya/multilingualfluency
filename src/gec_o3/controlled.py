"""O3 controlled corrector: n-best candidate generation -> edit decomposition -> per-edit gates -> recompose.

Separate from O2 by construction (import-linter enforces it): O3 owns its generation strategy, edit-level gates
(meaning preservation, over-correction control, edit budget) and its two modes:

* ``minimal``  - strict budget, no lexical rewrites, needs n-best agreement.
* ``fluency``  - looser budget, lexical replacements allowed, still meaning-gated.

HONEST LIMITATION: in this build both modes drive the SAME open GEC checkpoints (no fluency-trained model exists
for these languages on the Hub), so 'fluency' differs by gating thresholds and candidate acceptance, not by a
different model. Thresholds are uncalibrated defaults (configs/models.yaml).
"""
from __future__ import annotations

import math
import time
from collections import Counter

import regex

from gec_common.align import apply_edits, extract_edits, tokenize
from gec_common.config import language_capability, load_models_config, thresholds
from gec_common.errors import ModelUnavailableError
from gec_common.langs import get_language, resolve_language
from gec_common.runtime import get_embedder, get_seq2seq, script_consistent
from gec_common.schemas import CapabilityInfo, CorrectionResult, Edit, Mode, StageTrace
from gec_common.text import normalize, split_sentences

from .gates import hard_violations

MAX_SENTENCES = 40


def _graphemes(s: str) -> int:
    return len(regex.findall(r"\X", s.strip()))


def _is_lexical_rewrite(e: Edit) -> bool:
    """A content-word swap (both sides >=4 graphemes, different word). Short function-morpheme swaps such as a
    particle or verb ending are NOT rewrites: they are exactly what minimal correction is for."""
    return _graphemes(e.original) >= 4 and _graphemes(e.replacement) >= 4


class O3Controlled:
    name = "o3"

    def __init__(self, embedder=None):
        self._embedder = embedder  # injectable (tests / fault injection); default = shared e5 embedder

    def capability(self, lang: str) -> CapabilityInfo:
        return language_capability(get_language(lang).code)

    def _emb(self):
        return self._embedder or get_embedder()

    # ---- per-sentence -------------------------------------------------------------------------------
    def _process_sentence(self, sent: str, offset: int, lang: str, gen_key: str, mode: str,
                          warnings: list[str]) -> list[Edit]:
        th = thresholds("o3")[mode]
        n_best = int(thresholds("o3")["nbest"])
        m = get_seq2seq(gen_key)
        if m.token_len(sent) > m.max_input_tokens:
            warnings.append("A sentence exceeded the model input limit and was left unchanged.")
            return []
        cands = m.generate(sent, num_beams=max(n_best, 4), num_return=n_best)
        valid = []
        for c in cands:
            ratio = len(c.text) / max(1, len(sent))
            if c.text and 0.5 <= ratio <= 2.0 and script_consistent(sent, c.text):
                valid.append(c)
        if not valid or valid[0].text == sent:
            return []
        best = valid[0]
        # No-change margin: how much more does the MODEL prefer its edit over leaving the sentence alone?
        # (None = the unchanged sentence is not among the n-best, i.e. clearly worse than the edit.)
        unchanged = next((c for c in valid if c.text == sent), None)
        gap = None if unchanged is None else best.score - unchanged.score
        proposals = extract_edits(sent, best.text, lang)
        if not proposals:
            return []
        keys = Counter()
        for c in valid:
            for e in extract_edits(sent, c.text, lang):
                keys[(e.start, e.end, e.replacement)] += 1
        emb = self._emb()
        tokens_total = max(1, len(tokenize(sent, lang)))
        scored: list[Edit] = []
        for e in proposals:
            e.source = f"model:{gen_key}"
            support = keys[(e.start, e.end, e.replacement)] / len(valid)
            edited = apply_edits(sent, [e])
            sim = emb.similarity(sent, edited)
            e.scores = {"support": round(support, 3), "edit_similarity": round(sim, 4),
                        "seq_prob": round(math.exp(best.score), 4)}
            if gap is not None:
                e.scores["no_change_gap"] = round(gap, 4)
            reason = None
            hv = hard_violations(sent, edited, lang)
            if hv:
                reason = f"meaning:{hv[0]}"
            elif gap is not None and gap < th["min_no_change_margin"]:
                reason = f"overcorrection:no_change_margin(gap={gap:.3f}<{th['min_no_change_margin']})"
            elif not th["allow_word_choice"] and e.error_type == "WORD_CHOICE" and _is_lexical_rewrite(e):
                reason = "overcorrection:lexical_rewrite_in_minimal_mode"
            elif support < th["min_support"]:
                reason = f"overcorrection:low_nbest_support({support:.2f}<{th['min_support']})"
            elif sim < th["min_edit_similarity"]:
                reason = f"meaning:edit_similarity({sim:.3f}<{th['min_edit_similarity']})"
            e.gate_status = "rejected" if reason else "accepted"
            e.gate_reason = reason
            scored.append(e)

        # edit budget: keep the best-supported edits until the changed-token ratio is exhausted
        budget = th["max_edit_ratio"] * tokens_total
        used = 0.0
        for e in sorted((x for x in scored if x.gate_status == "accepted"),
                        key=lambda x: (-x.scores["support"], -x.scores["edit_similarity"])):
            cost = max(1, len(tokenize(e.original, lang)), len(tokenize(e.replacement, lang)))
            if used + cost > max(budget, 1.0):
                e.gate_status, e.gate_reason = "rejected", f"overcorrection:edit_budget(max_ratio={th['max_edit_ratio']})"
            else:
                used += cost

        # whole-sentence meaning check on what would actually be output
        accepted = [x for x in scored if x.gate_status == "accepted"]
        if accepted:
            out = apply_edits(sent, accepted)
            ssim = emb.similarity(sent, out)
            if ssim < th["min_sentence_similarity"]:
                for x in accepted:
                    x.gate_status = "rejected"
                    x.gate_reason = f"meaning:sentence_similarity({ssim:.3f}<{th['min_sentence_similarity']})"
        for x in scored:
            x.start += offset
            x.end += offset
        return scored

    # ---- public -------------------------------------------------------------------------------------
    def correct(self, text: str, lang: str | None = None, mode: Mode = "minimal") -> CorrectionResult:
        t_all = time.perf_counter()
        if mode not in ("minimal", "fluency"):
            mode = "minimal"
        text = normalize(text)
        res_lang = resolve_language(text, lang)
        lang = res_lang.language
        cap = self.capability(lang)
        gen_key = load_models_config()["languages"][lang].get("generator")
        trace: list[StageTrace] = []
        warnings: list[str] = list(res_lang.warnings)
        edits: list[Edit] = []
        degraded = False
        model_ids: dict[str, str] = {}

        if gen_key is None:
            trace.append(StageTrace(stage="generator", status="skipped",
                                    detail=f"O3 has no generator for {lang}; text returned unchanged"))
            warnings.append(f"O3 cannot correct {lang}: no GEC checkpoint exists. Output is the unchanged source.")
        else:
            t0 = time.perf_counter()
            spans = split_sentences(text)[:MAX_SENTENCES]
            try:
                for a, b in spans:
                    edits.extend(self._process_sentence(text[a:b], a, lang, gen_key, mode, warnings))
                model_ids["generator"] = load_models_config()["models"][gen_key]["hf_id"]
                model_ids["meaning_embedder"] = load_models_config()["models"]["embedder"]["hf_id"]
                trace.append(StageTrace(stage="generate+gate", status="ok", ms=round((time.perf_counter() - t0) * 1000, 1)))
            except ModelUnavailableError as e:
                # FAIL CLOSED: if the generator or the meaning gate cannot run, apply nothing.
                degraded, edits = True, []
                warnings.append(f"O3 model component unavailable ({e.message}); no edits applied (fail-closed).")
                trace.append(StageTrace(stage="generate+gate", status="failed", detail=e.message[:200]))

        edits.sort(key=lambda e: (e.start, e.end))
        applied = [e for e in edits if e.gate_status != "rejected"]
        abstained, why = False, None
        if degraded:
            abstained, why = True, "A component needed to verify meaning preservation was unavailable; no edit applied (fail-closed)."
        elif edits and not applied and any((e.gate_reason or "").startswith("meaning:") for e in edits):
            abstained, why = True, "Meaning preservation could not be established for the proposed edits; text left unchanged."
        return CorrectionResult(abstained=abstained, abstain_reason=why,
            pipeline="o3", mode=mode, language=lang, language_detection=res_lang, source=text,
            corrected=apply_edits(text, applied), edits=edits, capability=cap, degraded=degraded,
            warnings=warnings, trace=trace, model_ids=model_ids,
            latency_ms=round((time.perf_counter() - t_all) * 1000, 1),
        )
