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


def apply_rules(sentence: str, lang: str, offset: int = 0) -> list[Edit]:
    out: list[Edit] = []
    for rule in _RULES:
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
