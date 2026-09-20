"""Optional LLM provider abstraction. DEFAULT is 'none': the system needs no LLM and no paid API.

``openai_compatible`` talks to any OpenAI-style /chat/completions endpoint (e.g. a local Ollama / vLLM /
llama.cpp server, or a hosted API added later purely through env config). It is never used unless configured.
"""
from __future__ import annotations

import os
from typing import Protocol

import httpx


class LLMError(Exception):
    pass


class LLMProvider(Protocol):
    name: str

    def complete(self, prompt: str, *, max_tokens: int = 200) -> str: ...


class NoneProvider:
    name = "none"

    def complete(self, prompt: str, *, max_tokens: int = 200) -> str:
        raise LLMError("no LLM provider configured")


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 20.0,
                 transport: httpx.BaseTransport | None = None):
        self.base_url, self.model, self.api_key, self.timeout = base_url.rstrip("/"), model, api_key, timeout
        self._transport = transport

    def complete(self, prompt: str, *, max_tokens: int = 200) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": 0,
                "messages": [{"role": "user", "content": prompt}]}
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as c:
                r = c.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMError(f"LLM call failed: {type(e).__name__}: {e}") from e


def provider_from_env() -> LLMProvider:
    kind = os.environ.get("GEC_LLM_PROVIDER", "none")
    if kind == "openai_compatible" and os.environ.get("GEC_LLM_BASE_URL") and os.environ.get("GEC_LLM_MODEL"):
        return OpenAICompatibleProvider(os.environ["GEC_LLM_BASE_URL"], os.environ["GEC_LLM_MODEL"],
                                        os.environ.get("GEC_LLM_API_KEY", ""))
    return NoneProvider()
