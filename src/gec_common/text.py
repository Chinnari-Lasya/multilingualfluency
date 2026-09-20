"""Input normalisation and sentence segmentation. All offsets are code points in the NFC text.

We deliberately do NOT strip ZWJ/ZWNJ (U+200D/U+200C): they are meaningful in Telugu/Odia/Hindi conjuncts.
"""
from __future__ import annotations

import os
import unicodedata

from .errors import InputTooLongError, InvalidInputError

MAX_CHARS = int(os.environ.get("GEC_MAX_INPUT_CHARS", "5000"))
_BAD_CONTROL = {chr(c) for c in range(32)} - {"\n", "\t"}


def normalize(text: str, max_chars: int | None = None) -> str:
    if not isinstance(text, str):
        raise InvalidInputError("text must be a string")
    limit = max_chars or MAX_CHARS
    if len(text) > limit * 4:  # cheap pre-check before NFC work
        raise InputTooLongError(f"Input exceeds {limit} characters", limit=limit, length=len(text))
    if any(c in _BAD_CONTROL for c in text[:100000]):
        raise InvalidInputError("Input contains disallowed control characters")
    t = unicodedata.normalize("NFC", text.lstrip("﻿")).replace("\r\n", "\n").replace("\r", "\n")
    if not t.strip():
        raise InvalidInputError("Input is empty or whitespace only")
    if len(t) > limit:
        raise InputTooLongError(f"Input exceeds {limit} characters", limit=limit, length=len(t))
    return t


_STRONG = set("。！？")
_WEAK = set(".!?।॥…")
_CLOSERS = set("\"'”’)]）」』】》")


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Sentence spans (start, end) excluding surrounding whitespace. Newline always splits."""
    spans: list[tuple[int, int]] = []
    n, i, start = len(text), 0, 0

    def emit(a: int, b: int) -> None:
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if b > a:
            spans.append((a, b))

    while i < n:
        c = text[i]
        if c == "\n":
            emit(start, i)
            start = i + 1
            i += 1
            continue
        if c in _STRONG or c in _WEAK:
            j = i + 1
            while j < n and (text[j] in _STRONG or text[j] in _WEAK):
                j += 1
            while j < n and text[j] in _CLOSERS:
                j += 1
            if c in _STRONG or c in "।॥" or j >= n or text[j].isspace():
                emit(start, j)
                start = j
                i = j
                continue
        i += 1
    emit(start, n)
    return spans
