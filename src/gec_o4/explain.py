"""O4 pedagogical explanations: rule-grounded templates first; an LLM may only REPHRASE, and only if a
verifier confirms the rephrasing still cites the actual edit. Any failure falls back to the template.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from gec_common.config import config_dir
from gec_common.langs import LANGUAGES
from gec_common.schemas import Edit

from .llm import LLMError, LLMProvider, NoneProvider

PROMPT_VERSION = "explain_rephrase_v1"
_PROMPT = (
    "You are a language tutor. Rewrite the explanation below for a {level} learner of {language} in at most "
    "three sentences. Keep every quoted form exactly as written. Do not add rules that are not in the text.\n\n"
    "Explanation:\n{text}"
)


class Explanation(BaseModel):
    text: str
    rule_id: str
    source: str  # "template" | "llm"
    verified: bool = True
    fallback_reason: str | None = None
    prompt_version: str | None = None
    native_educator_reviewed: bool = False  # honest flag: templates are developer-authored v0


@lru_cache(maxsize=1)
def _templates() -> dict:
    return yaml.safe_load(Path(config_dir() / "explanations.yaml").read_text(encoding="utf-8"))["templates"]


def change_phrase(e: Edit) -> str:
    if e.op == "insert":
        return f"add '{e.replacement.strip()}'"
    if e.op == "delete":
        return f"remove '{e.original.strip()}'"
    return f"'{e.original.strip()}' → '{e.replacement.strip()}'"


def template_explanation(e: Edit) -> Explanation:
    t = _templates()
    keys = [e.rule_id or "", f"{e.language}.{e.error_type}", f"*.{e.error_type}", "*.OTHER"]
    key = next(k for k in keys if k in t)
    entry = t[key]
    change = change_phrase(e)
    text = entry["why"].format(change=change, original=e.original.strip(), replacement=e.replacement.strip())
    if entry.get("tip"):
        text += " " + entry["tip"]
    return Explanation(text=text, rule_id=key, source="template")


def _verify(rephrased: str, e: Edit) -> str | None:
    """Return a failure reason, or None if the rephrasing is acceptable."""
    if not rephrased or len(rephrased) > 700:
        return "empty_or_too_long"
    for form in (e.original.strip(), e.replacement.strip()):
        if form and form not in rephrased:
            return f"missing_quoted_form:{form}"
    return None


def explain(e: Edit, provider: LLMProvider | None = None, level: str = "intermediate") -> Explanation:
    base = template_explanation(e)
    provider = provider or NoneProvider()
    if provider.name == "none":
        return base
    try:
        out = provider.complete(_PROMPT.format(level=level, language=LANGUAGES[e.language].name, text=base.text))
    except LLMError as err:
        return base.model_copy(update={"fallback_reason": f"llm_error:{err}"[:200]})
    bad = _verify(out, e)
    if bad:
        return base.model_copy(update={"fallback_reason": f"verification_failed:{bad}"[:200]})
    return Explanation(text=out, rule_id=base.rule_id, source="llm", verified=True, prompt_version=PROMPT_VERSION)
