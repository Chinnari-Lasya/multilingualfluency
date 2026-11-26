"""Deterministic, language-specific normalisation rules (O2). High precision, deliberately low recall.

Each rule returns edits with ``source='rule:<id>'``. Rules are the ONLY correction mechanism for Japanese and
Odia (no GEC checkpoint exists for them), so their scope is intentionally narrow and documented.
"""
from __future__ import annotations

import regex

from gec_common.align import classify_generic
from gec_common.schemas import Edit

_EN_FUNC_DUP = {"the", "a", "an", "of", "to", "in", "on", "is", "are", "was", "and", "for", "with", "at"}
_HI_FUNC_DUP = {"ने", "को", "से", "में", "पर", "का", "की", "के", "है", "हैं", "और", "तक"}


def _edit(src: str, s: int, e: int, repl: str, lang: str, rule: str, etype: str | None = None) -> Edit | None:
    orig = src[s:e]
    if orig == repl:
        return None
    op = "insert" if not orig else "delete" if not repl else "replace"
    return Edit(start=s, end=e, original=orig, replacement=repl, op=op, language=lang,
                error_type=etype or classify_generic(orig, repl), rule_id=rule, source=f"rule:{rule}",
                scores={"rule": 1.0})


def _dup_space(s: str, lang: str):
    for m in regex.finditer(r"(?<=\S)[ \t]{2,}(?=\S)", s):
        yield _edit(s, m.start(), m.end(), " ", lang, "dup_space", "SPACING")


def _dup_function_word(s: str, lang: str):
    funcs = _EN_FUNC_DUP if lang == "en" else _HI_FUNC_DUP if lang == "hi" else None
    if funcs is None:
        return
    for m in regex.finditer(r"(?<![\p{L}\p{M}])([\p{L}\p{M}]+)([ \t]+)\1(?![\p{L}\p{M}])", s, flags=regex.IGNORECASE):
        if m.group(1).lower() in funcs:
            yield _edit(s, m.start() + len(m.group(1)), m.end(), "", lang, "dup_word", "UNNECESSARY")


def _space_before_punct(s: str, lang: str):
    if lang != "en":
        return
    for m in regex.finditer(r"(?<=[\p{L}\p{N}]) +(?=[.,;:!?](?:\s|$))", s):
        yield _edit(s, m.start(), m.end(), "", lang, "space_before_punct", "PUNCT")


def _space_after_comma(s: str, lang: str):
    if lang != "en":
        return
    for m in regex.finditer(r"(?<=[A-Za-z]),(?=[A-Za-z])", s):
        yield _edit(s, m.start(), m.end(), ", ", lang, "space_after_comma", "PUNCT")


def _en_pronoun_i(s: str, lang: str):
    if lang != "en":
        return
    for m in regex.finditer(r"(?<![\p{L}\p{N}'’.])i(?![\p{L}\p{N}'’.])", s):
        yield _edit(s, m.start(), m.end(), "I", lang, "pronoun_i", "ORTH")


def _danda_pipe(s: str, lang: str):
    """ASCII '|' used as sentence-final danda in Hindi/Odia."""
    if lang not in ("hi", "or"):
        return
    for m in regex.finditer(r"\|(?=\s*$)", s):
        yield _edit(s, m.start(), m.end(), "।", lang, "danda_pipe", "PUNCT")


def _ja_ascii_punct(s: str, lang: str):
    if lang != "ja":
        return
    for m in regex.finditer(r"(?<=[\p{Hiragana}\p{Katakana}\p{Han}])([,.])(?=\s|$|[\p{Hiragana}\p{Katakana}\p{Han}])", s):
        yield _edit(s, m.start(), m.end(), "、" if m.group() == "," else "。", lang, "ja_ascii_punct", "PUNCT")


def _ja_dup_wo(s: str, lang: str):
    if lang != "ja":
        return
    for m in regex.finditer(r"を(?=を)", s):  # 'をを' is never a valid sequence
        yield _edit(s, m.start(), m.end(), "", lang, "ja_dup_wo", "PARTICLE")


_RULES = [_dup_space, _dup_function_word, _space_before_punct, _space_after_comma, _en_pronoun_i,
          _danda_pipe, _ja_ascii_punct, _ja_dup_wo]


# ---- English grammar heuristics (RULES-ONLY fallback) ------------------------------------------------------
# Applied ONLY when no generator (local checkpoint or LLM fallback) corrected the sentence, so model runs are
# unchanged. Closed verb lexicon + adjacency patterns: high precision on common learner errors, low recall.
_EN_BASE = (
    "like want need love hate eat play work live know make take see say get come think read write speak walk run "
    "swim drink sleep study watch try cry fly wash teach finish miss buy cook drive sing dance learn help start open "
    "close call use feel look seem go do have understand remember forget believe agree enjoy travel shop sit stop "
    "plan begin listen talk wait stay visit move carry win fix sell tell give leave meet pay send spend").split()
_EN_DOUBLE = {"swim", "run", "sit", "get", "shop", "stop", "plan", "begin", "win", "put", "cut"}


def _third(v: str) -> str:
    if v in ("have", "do", "go"):
        return {"have": "has", "do": "does", "go": "goes"}[v]
    if regex.search(r"(?:s|sh|ch|x|z)$", v):
        return v + "es"
    if regex.search(r"[^aeiou]y$", v):
        return v[:-1] + "ies"
    return v + "s"


def _ing(v: str) -> list[str]:
    if v in _EN_DOUBLE:
        return [v + v[-1] + "ing"]
    if v == "travel":
        return ["travelling", "traveling"]
    if v.endswith("e") and not v.endswith(("ee", "ye")):
        return [v[:-1] + "ing"]
    return [v + "ing"]


_EN_3SG_TO_BASE = {_third(v): v for v in _EN_BASE}
_EN_BASE_TO_3SG = {v: _third(v) for v in _EN_BASE}
_EN_ING_TO_BASE = {g: v for v in _EN_BASE for g in _ing(v)}
# words after which "he/she/it + base verb" is correct ("let it go", "does he know", "to make it work")
_EN_BASE_OK_BEFORE = {"let", "lets", "make", "makes", "made", "help", "helps", "helped", "see", "saw", "watch",
                      "watched", "hear", "heard", "will", "would", "can", "could", "should", "shall", "may", "might",
                      "must", "do", "does", "did", "to", "and", "or", "if"}
_EN_PAST_MARKERS = regex.compile(r"\b(?:yesterday|ago|last|earlier|previously|once)\b", regex.I)
_EN_TO_ING_HEADS = regex.compile(
    r"\b(?:like|likes|liked|love|loves|loved|want|wants|wanted|need|needs|needed|hate|hates|hated|try|tries|tried|"
    r"prefer|prefers|preferred|decide|decides|decided|plan|plans|planned|hope|hopes|hoped|learn|learns|learned|"
    r"start|starts|started|begin|begins|began|would like)\s+to\s+(\p{L}+ing)\b", regex.I)


def _case(like: str, word: str) -> str:
    return word[:1].upper() + word[1:] if like[:1].isupper() else word


def _en_sva(s: str, lang: str):
    """I/you/we/they + 3sg verb -> base ('I likes' -> 'I like'); he/she/it + base -> 3sg ('she go' -> 'she goes')."""
    if lang != "en":
        return
    for m in regex.finditer(r"\b(I|you|we|they)\s+(\p{L}+)\b", s, flags=regex.I):
        subj, verb = m.group(1), m.group(2)
        low = verb.lower()
        if low == "is":
            repl = "am" if subj.lower() == "i" else "are"
        elif low == "are" and subj.lower() == "i":
            repl = "am"
        elif low in _EN_3SG_TO_BASE:
            repl = _EN_3SG_TO_BASE[low]
        else:
            continue
        yield _edit(s, m.start(2), m.end(2), _case(verb, repl), lang, "en_sva", "AGREEMENT")
    if _EN_PAST_MARKERS.search(s):  # "He go ... yesterday": the fix is a tense change, not agreement
        return
    for m in regex.finditer(r"(?:(\p{L}+)\s+)?\b(he|she|it)\s+(\p{L}+)\b", s, flags=regex.I):
        prev, verb = (m.group(1) or "").lower(), m.group(3)
        low = verb.lower()
        if prev in _EN_BASE_OK_BEFORE:
            continue
        if low == "are":
            repl = "is"
        elif low in _EN_BASE_TO_3SG:
            repl = _EN_BASE_TO_3SG[low]
        else:
            continue
        yield _edit(s, m.start(3), m.end(3), _case(verb, repl), lang, "en_sva", "AGREEMENT")


def _en_do_agreement(s: str, lang: str):
    """'she don't' -> 'she doesn't', 'they doesn't' -> 'they don't' (also 'do not' / 'does not')."""
    if lang != "en":
        return
    for m in regex.finditer(r"\b(he|she|it)\s+(don['’]t|do(?=\s+not\b))", s, flags=regex.I):
        aux = m.group(2)
        repl = "doesn" + aux[3:] if aux.lower().startswith("don") else "does"
        yield _edit(s, m.start(2), m.end(2), _case(aux, repl), lang, "en_do_agreement", "AGREEMENT")
    for m in regex.finditer(r"\b(I|you|we|they)\s+(doesn['’]t|does(?=\s+not\b))", s, flags=regex.I):
        aux = m.group(2)
        repl = "don" + aux[5:] if aux.lower().startswith("doesn") else "do"
        yield _edit(s, m.start(2), m.end(2), _case(aux, repl), lang, "en_do_agreement", "AGREEMENT")


def _en_was_were(s: str, lang: str):
    if lang != "en":
        return
    for m in regex.finditer(r"\b(we|you|they)\s+(was)\b", s, flags=regex.I):
        yield _edit(s, m.start(2), m.end(2), _case(m.group(2), "were"), lang, "en_was_were", "AGREEMENT")


def _en_double_negative(s: str, lang: str):
    """'don't know nothing' -> 'don't know anything' (the clause negator is kept, so polarity is unchanged)."""
    if lang != "en":
        return
    swap = {"nothing": "anything", "nobody": "anybody", "nowhere": "anywhere", "no one": "anyone", "no-one": "anyone"}
    for m in regex.finditer(r"\b(?:\p{L}+n['’]t|not|never)\b(?:\s+\p{L}+){0,3}?\s+(nothing|nobody|nowhere|no[ -]one)\b",
                            s, flags=regex.I):
        w = m.group(1)
        yield _edit(s, m.start(1), m.end(1), _case(w, swap[w.lower()]), lang, "en_double_negative", "NEGATION")


def _en_to_ing(s: str, lang: str):
    """'likes to swimming' -> 'likes to swim' (to + -ing after verbs that take an infinitive)."""
    if lang != "en":
        return
    for m in _EN_TO_ING_HEADS.finditer(s):
        g = m.group(1)
        base = _EN_ING_TO_BASE.get(g.lower())
        if base:
            yield _edit(s, m.start(1), m.end(1), _case(g, base), lang, "en_to_infinitive", "VERB_FORM")


_GRAMMAR_RULES = [_en_sva, _en_do_agreement, _en_was_were, _en_double_negative, _en_to_ing]


def apply_rules(sentence: str, lang: str, offset: int = 0, grammar: bool = False) -> list[Edit]:
    """Normalisation rules always; ``grammar=True`` adds the English grammar heuristics (rules-only fallback)."""
    out: list[Edit] = []
    for rule in _RULES + (_GRAMMAR_RULES if grammar else []):
        for e in rule(sentence, lang):
            if e is not None:
                e.start += offset
                e.end += offset
                out.append(e)
    out.sort(key=lambda e: (e.start, e.end))
    # drop overlaps among rules (keep first)
    kept: list[Edit] = []
    for e in out:
        if kept and e.start < kept[-1].end:
            continue
        kept.append(e)
    return kept
