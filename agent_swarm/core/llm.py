"""LLM provider abstraction.

One entry point — `chat(prompt, system=...)` — that routes to Anthropic or any
OpenAI-compatible endpoint (DeepSeek, OpenRouter, Together, Groq, etc.).
Provider/model are picked per call or from env so analysts can mix models.

Required env vars (only the ones you use):
    ANTHROPIC_API_KEY   — for Anthropic
    DEEPSEEK_API_KEY    — for DeepSeek
    OPENAI_API_KEY      — for OpenAI
    OPENROUTER_API_KEY  — for OpenRouter

Optional defaults:
    LLM_PROVIDER  (default: "anthropic")
    LLM_MODEL     (default: provider-specific)
"""
from __future__ import annotations

import os
from functools import lru_cache

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


PROVIDER_DEFAULTS = {
    "anthropic": {"model": "claude-sonnet-4-6", "base_url": None, "key_env": "ANTHROPIC_API_KEY"},
    "deepseek": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com", "key_env": "DEEPSEEK_API_KEY"},
    "openai": {"model": "gpt-4o-mini", "base_url": None, "key_env": "OPENAI_API_KEY"},
    "openrouter": {"model": "anthropic/claude-sonnet-4", "base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY"},
}


@lru_cache(maxsize=8)
def _anthropic_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


@lru_cache(maxsize=8)
def _openai_compat_client(provider: str):
    from openai import OpenAI
    cfg = PROVIDER_DEFAULTS[provider]
    return OpenAI(api_key=os.environ[cfg["key_env"]], base_url=cfg["base_url"])


def chat(
    prompt: str,
    system: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.4,
) -> str:
    """Send one user-prompt-style request and return the assistant's text reply."""
    provider = provider or os.environ.get("LLM_PROVIDER", "anthropic")
    if provider not in PROVIDER_DEFAULTS:
        raise ValueError(f"unknown provider: {provider}")

    cfg = PROVIDER_DEFAULTS[provider]
    model = model or os.environ.get("LLM_MODEL") or cfg["model"]

    if not os.environ.get(cfg["key_env"]):
        raise RuntimeError(f"{cfg['key_env']} not set in environment / .env")

    if provider == "anthropic":
        msg = _anthropic_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    client = _openai_compat_client(provider)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def available_providers() -> list[str]:
    """Return providers whose API key is present."""
    out = []
    for p, cfg in PROVIDER_DEFAULTS.items():
        if os.environ.get(cfg["key_env"]):
            out.append(p)
    return out
