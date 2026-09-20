"""Masked-LM error DETECTION for all six languages (O2: multilingual error detection).

For each sub-word we mask it and read p(original | context). A span is flagged when the original is very
unlikely while the MLM's top prediction is confident. Output is DETECTION ONLY: flags carry a suggestion but are
never auto-applied. Thresholds in configs/models.yaml are UNCALIBRATED heuristics: false-positive/negative rates
are unknown until measured on gold data.
"""
from __future__ import annotations

import regex

from gec_common.config import thresholds
from gec_common.runtime import get_mlm
from gec_common.schemas import Flag

MAX_SUBWORDS = 96


def detect_flags(sentence: str, offset: int = 0) -> list[Flag]:
    th = thresholds("detector")
    tok, model, dev, torch = get_mlm()
    enc = tok(sentence, return_offsets_mapping=True, truncation=True, max_length=MAX_SUBWORDS + 2)
    ids: list[int] = enc["input_ids"]
    offs = enc["offset_mapping"]
    special = set(tok.all_special_ids)
    pos = [i for i, (s, e) in enumerate(offs) if e > s and ids[i] not in special]
    if len(pos) < 3:
        return []
    flags: list[Flag] = []
    for b in range(0, len(pos), 24):
        chunk = pos[b:b + 24]
        batch = []
        for p in chunk:
            row = list(ids)
            row[p] = tok.mask_token_id
            batch.append(row)
        inp = torch.tensor(batch, device=dev)
        with torch.inference_mode():
            logits = model(input_ids=inp, attention_mask=torch.ones_like(inp)).logits
        for k, p in enumerate(chunk):
            probs = torch.softmax(logits[k, p], dim=-1)
            orig = ids[p]
            p_orig = float(probs[orig])
            top_p, top_id = probs.max(dim=-1)
            if top_id.item() == orig or p_orig >= th["min_orig_prob"] or float(top_p) < th["min_top_prob"]:
                continue
            s, e = offs[p]
            sugg = tok.convert_ids_to_tokens(int(top_id)).replace("▁", "").strip()
            if not regex.search(r"\p{L}", sugg):
                sugg = ""  # punctuation/junk pieces are not useful suggestions
            flags.append(Flag(start=s + offset, end=e + offset, text=sentence[s:e], score=round(1.0 - p_orig, 4),
                              reason=f"MLM: p(original)={p_orig:.5f}; top prediction p={float(top_p):.2f} (uncalibrated)",
                              suggestion=sugg or None))
    flags.sort(key=lambda f: -f.score)
    return flags[: th["max_flags"]]
