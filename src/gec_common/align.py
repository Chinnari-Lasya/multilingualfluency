"""Deterministic, language-aware edit extraction (charter O2: edit alignment).

Design
------
* Tokenisation is per language unit: word tokens for te/or/hi/en/ko (Unicode letters + combining marks +
  ZWJ/ZWNJ so Indic conjuncts are never split), character tokens for Japanese (no spaces).
* Tokens are aligned with difflib.SequenceMatcher (deterministic; no learned component).
* An edit's source span INCLUDES the surrounding inter-token whitespace, then common leading/trailing
  whitespace is trimmed. This makes ``apply_edits(source, extract_edits(source, target)) == target`` exact
  (property-tested) while still reporting tight spans like ``insert "the "``.
* Korean 1:1 word replacements are refined to syllable level so a particle change is a 1-char edit.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

import regex

from .langs import get_language
from .schemas import Edit

_WORD = regex.compile(r"[\p{L}\p{M}\p{N}‌‍]+(?:['’\-][\p{L}\p{M}\p{N}]+)*|[^\s]")
_CHAR = regex.compile(r"[A-Za-z\p{Nd}]+|[^\s]")
_PUNCT = regex.compile(r"[\p{P}\p{S}]+")


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int


def tokenize(text: str, lang: str) -> list[Token]:
    rx = _CHAR if get_language(lang).unit == "char" else _WORD
    return [Token(m.group(), m.start(), m.end()) for m in rx.finditer(text)]


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def classify_generic(original: str, replacement: str) -> str:
    """Language-agnostic coarse type. Language plugins (gec_o2.analysis) may refine this."""
    o, r = original.strip(), replacement.strip()
    if o == r:
        return "SPACING"
    if (not o or _PUNCT.fullmatch(o)) and (not r or _PUNCT.fullmatch(r)):
        return "PUNCT"
    if not o:
        return "MISSING"
    if not r:
        return "UNNECESSARY"
    if o.casefold() == r.casefold():
        return "ORTH"
    if regex.sub(r"[\p{P}\p{S}]", "", o) == regex.sub(r"[\p{P}\p{S}]", "", r):
        return "PUNCT"
    d, m = levenshtein(o, r), max(len(o), len(r))
    ratio = 1 - d / m
    if d <= 2 and ratio >= 0.5:
        return "SPELLING"
    if ratio >= 0.4:
        return "MORPHOLOGY"
    return "WORD_CHOICE"


def _make(source: str, s0: int, s1: int, repl: str, lang: str) -> Edit | None:
    a = source[s0:s1]
    # trim common surrounding whitespace so spans are tight
    while a and repl and a[0] == repl[0] and a[0].isspace():
        a, repl, s0 = a[1:], repl[1:], s0 + 1
    while a and repl and a[-1] == repl[-1] and a[-1].isspace():
        a, repl, s1 = a[:-1], repl[:-1], s1 - 1
    if a == repl:
        return None
    op = "insert" if not a else "delete" if not repl else "replace"
    return Edit(start=s0, end=s1, original=a, replacement=repl, op=op, language=lang,
                error_type=classify_generic(a, repl))


def _refine_chars(source: str, e: Edit) -> Edit:
    a, b, s0, s1 = e.original, e.replacement, e.start, e.end
    if not a.strip() or not b.strip() or " " in a.strip() or " " in b.strip():
        return e
    p = 0
    while p < min(len(a), len(b)) and a[p] == b[p]:
        p += 1
    q = 0
    while q < min(len(a), len(b)) - p and a[len(a) - 1 - q] == b[len(b) - 1 - q]:
        q += 1
    if p == 0 and q == 0:
        return e
    a2, b2 = a[p:len(a) - q], b[p:len(b) - q]
    op = "insert" if not a2 else "delete" if not b2 else "replace"
    return Edit(start=s0 + p, end=s1 - q, original=a2, replacement=b2, op=op, language=e.language,
                error_type=classify_generic(a2, b2))


def extract_edits(source: str, target: str, lang: str, *, offset: int = 0) -> list[Edit]:
    """Edits transforming ``source`` into ``target``; ``offset`` shifts spans (for sentence-level calls)."""
    spec = get_language(lang)
    S, T = tokenize(source, lang), tokenize(target, lang)
    sm = SequenceMatcher(None, [t.text for t in S], [t.text for t in T], autojunk=False)
    out: list[Edit] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1 - 1):  # whitespace-only differences between equal tokens
                a, b = i1 + k, j1 + k
                gs = source[S[a].end:S[a + 1].start]
                gt = target[T[b].end:T[b + 1].start]
                if gs != gt:
                    e = _make(source, S[a].end, S[a + 1].start, gt, lang)
                    if e:
                        out.append(e)
            continue
        n = i2 - i1
        if tag == "replace" and n > 1 and n == j2 - j1:
            # Equal-length replacement: emit one edit per word so a correct fix and an unnecessary change
            # in the same phrase can be accepted/rejected independently (O3 edit-level gating).
            for k in range(n):
                a, b = i1 + k, j1 + k
                s0 = (S[i1 - 1].end if i1 > 0 else 0) if k == 0 else S[a].start
                t0 = (T[j1 - 1].end if j1 > 0 else 0) if k == 0 else T[b].start
                s1 = (S[i2].start if i2 < len(S) else len(source)) if k == n - 1 else S[a].end
                t1 = (T[j2].start if j2 < len(T) else len(target)) if k == n - 1 else T[b].end
                pe = _make(source, s0, s1, target[t0:t1], lang)
                if pe is not None:
                    if spec.refine_chars:
                        pe = _refine_chars(source, pe)
                    out.append(pe)
                if k < n - 1:  # whitespace between paired words
                    gs, gt = source[S[a].end:S[a + 1].start], target[T[b].end:T[b + 1].start]
                    if gs != gt:
                        ge = _make(source, S[a].end, S[a + 1].start, gt, lang)
                        if ge:
                            out.append(ge)
            continue
        s0 = S[i1 - 1].end if i1 > 0 else 0
        s1 = S[i2].start if i2 < len(S) else len(source)
        t0 = T[j1 - 1].end if j1 > 0 else 0
        t1 = T[j2].start if j2 < len(T) else len(target)
        e = _make(source, s0, s1, target[t0:t1], lang)
        if e is None:
            continue
        if spec.refine_chars and tag == "replace" and (i2 - i1) == 1 and (j2 - j1) == 1:
            e = _refine_chars(source, e)
        out.append(e)
    out.sort(key=lambda e: (e.start, e.end))
    if offset:
        for e in out:
            e.start += offset
            e.end += offset
    return out


def apply_edits(source: str, edits: list[Edit]) -> str:
    """Apply non-overlapping edits. Raises ValueError on overlap or span/text mismatch."""
    ordered = sorted(edits, key=lambda e: (e.start, e.end))
    prev_end, last_insert = -1, -1
    for e in ordered:
        if e.start < prev_end or e.start > e.end or e.end > len(source):
            raise ValueError(f"overlapping or out-of-range edit at {e.start}-{e.end}")
        if source[e.start:e.end] != e.original:
            raise ValueError(f"edit original {e.original!r} does not match source span {source[e.start:e.end]!r}")
        if e.start == e.end:  # an insertion may touch a neighbouring span, but not another insertion
            if e.start == last_insert:
                raise ValueError(f"two insertions at position {e.start}")
            last_insert = e.start
        prev_end = max(prev_end, e.end)
    out, pos = [], 0
    for e in ordered:
        out.append(source[pos:e.start])
        out.append(e.replacement)
        pos = e.end
    out.append(source[pos:])
    return "".join(out)


def spans_overlap(a: Edit, b: Edit) -> bool:
    """Overlap incl. touching insertions at the same point."""
    if a.start == a.end and b.start == b.end:
        return a.start == b.start
    if a.start == a.end:
        return b.start < a.start < b.end
    if b.start == b.end:
        return a.start < b.start < a.end
    return a.start < b.end and b.start < a.end
