"""O3 deterministic verifiers: hard meaning checks. These are VERIFIERS, not LLM opinions.

Negation lexicons are small hand-written HEURISTICS (not linguist-reviewed); they catch obvious polarity flips
and are not exhaustive. Numbers are compared across digit systems (Telugu/Odia/Devanagari digits -> ASCII).
"""
from __future__ import annotations

import unicodedata
from collections import Counter

import regex

_NUM = regex.compile(r"\p{Nd}+(?:[.,]\p{Nd}+)*")
_LATIN = regex.compile(r"[A-Za-z]{2,}")
_NEG = {
    "en": regex.compile(r"\b(?:not|no|never|none|nothing|nobody|cannot|without)\b|n['’]t\b", regex.I),
    "hi": regex.compile(r"(?<![\p{L}\p{M}])(?:नहीं|नही|मत|न)(?![\p{L}\p{M}])"),
    "te": regex.compile(r"(?:లేదు|లేరు|లేవు|కాదు|వద్దు|కాను|లేను)"),
    "or": regex.compile(r"(?:ନାହିଁ|ନୁହେଁ|ନୁହଁ|ନାହାନ୍ତି|ନଥିଲା)|(?<![\p{L}\p{M}])ନ(?![\p{L}\p{M}])"),
    "ja": regex.compile(r"(?:ない|ません|なかっ|ぬ)"),
    "ko": regex.compile(r"(?:않|없|아니|못)|(?<![\p{L}])안(?![\p{L}])"),
}


def _numbers(s: str) -> Counter:
    out = Counter()
    for m in _NUM.findall(s):
        out["".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in m)] += 1
    return out


_EN_CLAUSE = regex.compile(r"\b(?:not|no|never|cannot|without)\b|n['’]t\b", regex.I)
_EN_INDEF = regex.compile(r"\b(?:none|nothing|nobody|nowhere)\b", regex.I)


def _neg_count(text: str, lang: str) -> int:
    if lang == "en":  # negative indefinites only count when no clause negator is present (double negation)
        c = len(_EN_CLAUSE.findall(text))
        return c if c else len(_EN_INDEF.findall(text))
    return len(_NEG[lang].findall(text))


def hard_violations(original: str, replacement: str, lang: str) -> list[str]:
    """Reasons a change must not be applied. Pass SENTENCE-level before/after text so negation context is visible."""
    v: list[str] = []
    if _numbers(original) != _numbers(replacement):
        v.append("number_changed")
    if _neg_count(original, lang) != _neg_count(replacement, lang):
        v.append("negation_changed")
    if lang != "en" and Counter(t.lower() for t in _LATIN.findall(original)) != Counter(
            t.lower() for t in _LATIN.findall(replacement)):
        v.append("latin_token_changed")  # names/brands/loanwords in a non-Latin sentence
    return v
