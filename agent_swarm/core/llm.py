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
import time
from functools import lru_cache

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


PROVIDER_DEFAULTS = {
    "anthropic": {"model": "claude-sonnet-4-6", "base_url": None, "key_env": "ANTHROPIC_API_KEY"},
    "deepseek": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com", "key_env": "DEEPSEEK_API_KEY"},
    "kimi": {"model": "moonshot-v1-auto", "base_url": "https://api.moonshot.ai/v1", "key_env": "MOONSHOT_API_KEY"},
    "openai": {"model": "gpt-4o-mini", "base_url": None, "key_env": "OPENAI_API_KEY"},
    "openrouter": {"model": "anthropic/claude-sonnet-4", "base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY"},
}

# Provider fallback chain: when an analyst prefers a provider whose key isn't set,
# fall back to the next available one. Lets you ship with optional providers.
FALLBACK_CHAIN = ["deepseek", "anthropic", "openai", "openrouter"]


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

    # SKIP_ANTHROPIC=1 (set by --no-anthropic) routes any Anthropic call to
    # DeepSeek before issuing the request. Useful when out of credits or to
    # save cost on a run.
    if provider == "anthropic" and os.environ.get("SKIP_ANTHROPIC"):
        provider = "deepseek"
        model = None

    cfg = PROVIDER_DEFAULTS[provider]

    # Graceful fallback: if the requested provider's key isn't loaded,
    # walk down FALLBACK_CHAIN until we find one that is. Reset `model` to the
    # fallback's default — the caller's model is provider-specific (e.g.
    # 'kimi-k2-0711-preview' is invalid on DeepSeek).
    if not os.environ.get(cfg["key_env"]):
        for fb in FALLBACK_CHAIN:
            if fb == provider:
                continue
            if os.environ.get(PROVIDER_DEFAULTS[fb]["key_env"]):
                provider = fb
                cfg = PROVIDER_DEFAULTS[fb]
                model = None  # force the use of fallback's default model
                break

    model = model or os.environ.get("LLM_MODEL") or cfg["model"]

    # Reasoning models burn tokens on internal chain-of-thought before output.
    # Auto-bump max_tokens so the answer isn't truncated.
    if "reasoner" in (model or "").lower() and max_tokens < 4000:
        max_tokens = 8000

    if not os.environ.get(cfg["key_env"]):
        raise RuntimeError(f"{cfg['key_env']} not set in environment / .env")

    # Retry on rate limit / overloaded with exponential backoff, then fall back
    # to next available provider if all retries fail.
    last_error = None
    for attempt in range(3):
        try:
            return _do_call(provider, model, system, prompt, max_tokens, temperature)
        except Exception as exc:
            err_str = str(exc).lower()
            is_transient = any(k in err_str for k in ("429", "overloaded", "rate", "timeout", "503"))
            if not is_transient or attempt == 2:
                last_error = exc
                break
            time.sleep(2 ** attempt)  # 1s, 2s

    # All retries failed → walk fallback chain
    for fb in FALLBACK_CHAIN:
        if fb == provider:
            continue
        if not os.environ.get(PROVIDER_DEFAULTS[fb]["key_env"]):
            continue
        try:
            print(f"[llm] {provider} failing → falling back to {fb}")
            return _do_call(fb, PROVIDER_DEFAULTS[fb]["model"], system, prompt, max_tokens, temperature)
        except Exception:
            continue

    raise last_error or RuntimeError("all providers failed")


def _do_call(provider: str, model: str, system, prompt, max_tokens, temperature) -> str:
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
