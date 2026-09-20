"""Translation service (SEPARATE from grammatical error correction).

GEC:         input sentence  -> corrected sentence (same language)
Translation: source language -> target language

Providers are pluggable behind one small interface, selected by GEC_TRANSLATION_PROVIDER:
  hf_nllb            (default) local NLLB-200-distilled-600M via Hugging Face Transformers, CPU, no API key
  openai_compatible  any OpenAI-style chat endpoint (local Ollama/vLLM, or a hosted API added later) via GEC_LLM_* env
  none               translation disabled -> clear 503 error
"""
from __future__ import annotations

import os
from typing import Protocol

import httpx

from gec_common.config import model_spec
from gec_common.errors import (InvalidInputError, ModelUnavailableError, SameLanguageError,
                               TranslationUnavailableError, UnsupportedLanguageError)
from gec_common.langs import LANGUAGES, get_language
from gec_common.runtime import get_translator
from gec_common.text import normalize, split_sentences

NLLB_CODES = {"en": "eng_Latn", "te": "tel_Telu", "or": "ory_Orya", "hi": "hin_Deva", "ja": "jpn_Jpan", "ko": "kor_Hang"}
MAX_CHARS = 2000


class TranslationProvider(Protocol):
    name: str
    model: str | None

    def translate_sentence(self, text: str, src: str, tgt: str) -> str: ...


class NoneProvider:
    name, model = "none", None

    def translate_sentence(self, text: str, src: str, tgt: str) -> str:
        raise TranslationUnavailableError("No translation provider is configured (GEC_TRANSLATION_PROVIDER=none)")


class NllbProvider:
    name = "hf_nllb"

    def __init__(self) -> None:
        self.model = model_spec("translator")["hf_id"]

    def translate_sentence(self, text: str, src: str, tgt: str) -> str:
        try:
            tok, model, dev, torch = get_translator()
        except ModelUnavailableError as e:
            raise TranslationUnavailableError(
                "The translation model is not available. Download it with: python scripts/download_models.py translator",
                cause=e.message) from e
        tok.src_lang = NLLB_CODES[src]
        enc = tok(text, return_tensors="pt", truncation=True, max_length=256).to(dev)
        with torch.inference_mode():
            out = model.generate(**enc, forced_bos_token_id=tok.convert_tokens_to_ids(NLLB_CODES[tgt]), num_beams=4,
                                 max_new_tokens=min(256, int(enc["input_ids"].shape[1] * 2.5) + 16))
        return tok.batch_decode(out, skip_special_tokens=True)[0].strip()


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self.base = os.environ.get("GEC_LLM_BASE_URL", "").rstrip("/")
        self.model = os.environ.get("GEC_LLM_MODEL", "")
        self.key = os.environ.get("GEC_LLM_API_KEY", "")
        self._transport = transport
        if not (self.base and self.model):
            raise TranslationUnavailableError("openai_compatible provider needs GEC_LLM_BASE_URL and GEC_LLM_MODEL")

    def translate_sentence(self, text: str, src: str, tgt: str) -> str:
        prompt = (f"Translate the following {LANGUAGES[src].name} text into {LANGUAGES[tgt].name}. "
                  f"Output only the translation.\n\n{text}")
        try:
            with httpx.Client(timeout=30, transport=self._transport) as c:
                r = c.post(f"{self.base}/chat/completions", headers={"Authorization": f"Bearer {self.key}"} if self.key else {},
                           json={"model": self.model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise TranslationUnavailableError(f"Translation provider call failed: {type(e).__name__}") from e


def get_provider() -> TranslationProvider:
    kind = os.environ.get("GEC_TRANSLATION_PROVIDER", "hf_nllb")
    if kind == "none":
        return NoneProvider()
    if kind == "openai_compatible":
        return OpenAICompatibleProvider()
    return NllbProvider()


def provider_info() -> dict:
    p = get_provider()
    lic = model_spec("translator").get("license") if p.name == "hf_nllb" else None
    return {"provider": p.name, "model": p.model, "languages": list(LANGUAGES), "license": lic,
            "note": "Translation is separate from grammar correction. Machine translation can contain errors; low-resource "
                    "pairs (Odia, Telugu) are less reliable."}


def translate(text: str, source: str, target: str, provider: TranslationProvider | None = None) -> dict:
    if source not in LANGUAGES:
        raise UnsupportedLanguageError(f"Unsupported source language {source!r}", supported=list(LANGUAGES))
    if target not in LANGUAGES:
        raise UnsupportedLanguageError(f"Unsupported target language {target!r}", supported=list(LANGUAGES))
    if source == target:
        raise SameLanguageError("Source and target language must differ")
    get_language(source), get_language(target)
    text = normalize(text, max_chars=MAX_CHARS)
    provider = provider or get_provider()
    parts = [text[a:b] for a, b in split_sentences(text)] or [text]
    if len(parts) > 30:
        raise InvalidInputError("Too many sentences (max 30)")
    out = [provider.translate_sentence(p, source, target) for p in parts]
    joiner = "" if target == "ja" else " "
    return {"translation": joiner.join(out), "source_language": source, "target_language": target,
            "provider": provider.name, "model": provider.model, "sentences": len(parts)}
