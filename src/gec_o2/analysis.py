"""Language-specific error analysis plugins (O2). They refine the coarse generic edit type using small,
hand-written function-word / suffix inventories. These inventories are HEURISTIC and have not been reviewed
by native-speaker linguists; unmatched edits keep their generic type.
"""
from __future__ import annotations

from gec_common.schemas import Edit

_EN_DET = {"a", "an", "the"}
_EN_PREP = {"in", "on", "at", "to", "for", "of", "with", "by", "from", "about", "into", "over"}
_EN_PRON = {"i", "me", "my", "he", "him", "his", "she", "her", "they", "them", "their", "we", "us", "our"}
_EN_BE = {"is", "are", "was", "were", "am", "be", "been", "being", "has", "have", "had", "do", "does", "did"}
_HI_POST = {"ने", "को", "से", "में", "पर", "का", "की", "के", "तक", "लिए"}
_HI_AUX = {"है", "हैं", "हूँ", "हो", "था", "थी", "थे", "थीं", "हूं"}
_JA_PARTICLES = set("はがをにでとへもの") | {"から", "まで", "より"}
_KO_JOSA = {"은", "는", "이", "가", "을", "를", "에", "에서", "의", "로", "으로", "과", "와", "도", "만", "에게", "께"}
_OR_POST = {"କୁ", "ରେ", "ର", "ଠାରୁ", "ଙ୍କୁ", "ଙ୍କର", "ଠାରେ"}


def _words(s: str) -> list[str]:
    return s.strip().split()


def refine_type(edit: Edit) -> Edit:
    lang, o, r = edit.language, edit.original.strip(), edit.replacement.strip()
    t = edit.error_type
    lo, lr = o.lower(), r.lower()
    if lang == "en":
        infl = ("s", "es", "ed", "d", "ing", "ly")
        if lo and lr and lo != lr and ((lo.startswith(lr) and lo[len(lr):] in infl) or (lr.startswith(lo) and lr[len(lo):] in infl)
                                       or (lo.endswith("ing") and lr == lo[:-3])):
            t = "VERB_OR_NOUN_FORM"
        elif {lo, lr} - {""} and (lo in _EN_DET or not lo) and (lr in _EN_DET or not lr):
            t = "DET"
        elif (lo in _EN_PREP or not lo) and (lr in _EN_PREP or not lr) and (lo or lr):
            t = "PREP"
        elif (lo in _EN_BE or lr in _EN_BE) and lo and lr:
            t = "VERB_FORM"
        elif t == "MORPHOLOGY" and (lo.rstrip("s") == lr.rstrip("s") or lo.endswith(("ing", "ed")) or lr.endswith(("ing", "ed"))):
            t = "VERB_OR_NOUN_FORM"
    elif lang == "hi":
        if (o in _HI_POST or not o) and (r in _HI_POST or not r) and (o or r):
            t = "POSTPOSITION"
        elif o in _HI_AUX and r in _HI_AUX or (t == "MORPHOLOGY" and o.endswith(("ता", "ती", "ते")) != r.endswith(("ता", "ती", "ते"))):
            t = "AGREEMENT"
        elif t == "MORPHOLOGY":
            t = "AGREEMENT"
    elif lang == "ja":
        if o in _JA_PARTICLES and r in _JA_PARTICLES:
            t = "PARTICLE"
        elif (o in _JA_PARTICLES and not r) or (r in _JA_PARTICLES and not o):
            t = "PARTICLE_MISSING_OR_EXTRA"
    elif lang == "ko":
        if o in _KO_JOSA and r in _KO_JOSA:
            t = "JOSA"
        elif (o in _KO_JOSA and not r) or (r in _KO_JOSA and not o):
            t = "JOSA_MISSING_OR_EXTRA"
    elif lang == "or":
        if o in _OR_POST or r in _OR_POST or t == "MORPHOLOGY":
            t = "SUFFIX_OR_POSTPOSITION"
    elif lang == "te":
        if t == "MORPHOLOGY":
            t = "SUFFIX_AGREEMENT"
    if t != edit.error_type:
        edit = edit.model_copy(update={"error_type": t})
    if edit.rule_id is None:
        edit = edit.model_copy(update={"rule_id": f"{lang}.{edit.error_type}"})
    return edit
