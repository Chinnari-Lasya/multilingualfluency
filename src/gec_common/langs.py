"""Language registry (te, or, hi, en, ja, ko) and script-based language identification.

Script identification is exact for Telugu/Odia/Hangul/kana, and only *script-level* for the rest:
Devanagari => 'hi' (Marathi/Nepali share it), Han-only => 'ja' (could be Chinese), Latin => 'en'
(any Latin-script language). These ambiguities are surfaced as warnings, never hidden.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import regex

from .errors import LanguageMismatchError, LanguageUndeterminedError, UnsupportedLanguageError
from .schemas import LangResolution


@dataclass(frozen=True)
class LanguageSpec:
    code: str
    name: str
    native_name: str
    script: str
    unit: Literal["word", "char"]  # alignment unit
    refine_chars: bool  # trim 1:1 word replacements to char-level (agglutinative particles)
    terminators: str


LANGUAGES: dict[str, LanguageSpec] = {
    "te": LanguageSpec("te", "Telugu", "తెలుగు", "Telugu", "word", False, ".!?"),
    "or": LanguageSpec("or", "Odia", "ଓଡ଼ିଆ", "Oriya", "word", False, ".!?।"),
    "hi": LanguageSpec("hi", "Hindi", "हिन्दी", "Devanagari", "word", False, ".!?।"),
    "en": LanguageSpec("en", "English", "English", "Latin", "word", False, ".!?"),
    "ja": LanguageSpec("ja", "Japanese", "日本語", "Han+Kana", "char", False, "。！？.!?"),
    "ko": LanguageSpec("ko", "Korean", "한국어", "Hangul", "word", True, ".!?"),
}
SUPPORTED = tuple(LANGUAGES)


def get_language(code: str) -> LanguageSpec:
    if code not in LANGUAGES:
        raise UnsupportedLanguageError(
            f"Language {code!r} is not supported. Supported: {', '.join(SUPPORTED)}",
            supported=list(SUPPORTED),
        )
    return LANGUAGES[code]


_SCRIPT_RX = {
    "te": regex.compile(r"\p{Script=Telugu}"),
    "or": regex.compile(r"\p{Script=Oriya}"),
    "hi": regex.compile(r"\p{Script=Devanagari}"),
    "ko": regex.compile(r"\p{Script=Hangul}"),
    "kana": regex.compile(r"[\p{Script=Hiragana}\p{Script=Katakana}]"),
    "han": regex.compile(r"\p{Script=Han}"),
    "en": regex.compile(r"\p{Script=Latin}"),
}
_EN_STOP = frozenset(
    "the is are a an of to in and i you he she it we they was were be have has for on with that this my your".split()
)


def _shares(text: str) -> dict[str, int]:
    return {k: len(rx.findall(text)) for k, rx in _SCRIPT_RX.items()}


def detect_language(text: str) -> LangResolution:
    counts = _shares(text)
    group = {
        "te": counts["te"], "or": counts["or"], "hi": counts["hi"], "ko": counts["ko"],
        "ja": counts["kana"] + counts["han"], "en": counts["en"],
    }
    total = sum(group.values())
    if total == 0:
        raise LanguageUndeterminedError("No letters in a supported script were found", counts=counts)
    lang = max(group, key=group.get)
    conf = group[lang] / total
    shares = {k: round(v / total, 3) for k, v in group.items() if v}
    mixed = sum(1 for k, v in group.items() if k != lang and v / total >= 0.2) > 0
    warnings: list[str] = []
    method = "script"
    if mixed:
        warnings.append("Mixed-script text: the dominant script decides the language.")
    if lang == "ja" and counts["kana"] == 0:
        conf *= 0.5
        method = "script-han-only"
        warnings.append("Han-only text: could be Chinese; treated as Japanese.")
    if lang == "hi":
        warnings.append("Devanagari is assumed to be Hindi; Marathi/Nepali/Sanskrit are not distinguished.")
    if lang == "en":
        toks = regex.findall(r"\p{L}+", text.lower())
        if len(toks) >= 4 and sum(t in _EN_STOP for t in toks) / len(toks) < 0.08:
            conf *= 0.6
            warnings.append("Latin-script text with few English function words: may not be English.")
    return LangResolution(language=lang, detected=lang, confidence=round(conf, 3), method=method,
                          mixed_script=mixed, warnings=warnings, script_shares=shares)


def resolve_language(text: str, declared: str | None = None) -> LangResolution:
    """Combine learner-declared language with detection. A strong conflict is an error, not a guess."""
    det = detect_language(text)
    if declared is None or declared == "auto":
        return det
    get_language(declared)
    if declared == det.detected:
        det.method = "declared+script"
        return det
    # Han-only text may legitimately be declared as Japanese only (already handled above).
    if det.confidence >= 0.8:
        raise LanguageMismatchError(
            f"Declared language {declared!r} conflicts with the script of the text (looks like {det.detected!r}).",
            declared=declared, detected=det.detected, confidence=det.confidence,
        )
    det.language = declared
    det.method = "declared-overrides-weak-detection"
    det.warnings.append(f"Declared {declared!r} but text looks like {det.detected!r} (low confidence).")
    return det
