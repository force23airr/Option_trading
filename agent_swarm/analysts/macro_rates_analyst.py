"""Macro Rates Analyst — reads the Treasury yield curve.

Reasons about: rate regime (rising/falling/stable), curve shape (normal /
flat / inverted), and what either implies for the underlying ticker. Banks
benefit from steepening; long-duration growth names hurt by rising rates;
gold/utilities reactive to real-rate moves.

Spawns only when a yield curve has been pulled.
"""
from __future__ import annotations

import json

from .base import AnalystView, BaseAnalyst, _parse_json_reply
from ..core import llm


class MacroRatesAnalyst(BaseAnalyst):
    name = "Macro Rates Analyst"
    focus = "treasury yield curve, rate regime, curve shape, duration sensitivity for the underlying"
    system_prompt = (
        "You are a rates strategist. You read the Treasury yield curve (3M / 5Y / 10Y / 30Y) "
        "and recent changes in basis points. You then translate this into what it MEANS for "
        "the specific ticker under analysis. Banks/insurers benefit from steepening. "
        "Long-duration growth and high-multiple tech are sensitive to 10Y moves. Gold and "
        "utilities respond to real-rate direction. REITs are duration-sensitive. Crypto "
        "proxies (COIN, MSTR) are risk-on plays — they fall on hawkish surprises and rally "
        "on dovish ones. Be explicit about your linkage from rates to the ticker."
    )
    provider = "deepseek"
    model = "deepseek-chat"

    @classmethod
    def should_spawn(cls, ctx) -> bool:
        return ctx.has_rates

    def analyze(self, ticker: str, df, snap: dict, peer_views=None) -> AnalystView:
        # We need access to ctx.yield_summary; signature compat means we pass via base.
        # Use the convenience entry point below.
        raise NotImplementedError("call analyze_with_rates(ctx, ...) instead")

    def analyze_with_rates(self, ctx, peer_views: list[AnalystView] | None = None) -> AnalystView:
        peers_block = ""
        if peer_views:
            peers_block = "\n\nPEER ANALYSTS' VIEWS (for context):\n"
            for v in peer_views:
                peers_block += f"- {v.short()}\n"

        rates_block = json.dumps(ctx.yield_summary or {}, indent=2)

        prompt = f"""Ticker: {ctx.ticker}
Underlying snapshot:
{json.dumps(ctx.snap, indent=2, default=str)}

TREASURY YIELD CURVE (latest):
{rates_block}

{peers_block}
Translate the rate regime into directional pressure on this specific ticker.
Reply with one JSON object:
{{
  "stance": "bullish" | "bearish" | "neutral",
  "confidence": <float 0.0-1.0>,
  "summary": "<one sentence linking rates to the ticker>",
  "rate_regime": "rising" | "falling" | "stable",
  "curve_shape": "normal" | "flat" | "inverted",
  "duration_sensitivity": "high" | "medium" | "low",
  "horizon": "1-5d" | "1-4w" | "longer",
  "observations": ["<concrete observation>", "..."]
}}"""
        raw = llm.chat(
            prompt, system=self.system_prompt,
            provider=self.provider, model=self.model,
            max_tokens=1800, temperature=0.3,
        )
        parsed = _parse_json_reply(raw)
        return AnalystView(
            analyst=self.name, ticker=ctx.ticker,
            stance=str(parsed.get("stance", "neutral")).lower(),
            confidence=float(parsed.get("confidence", 0.0) or 0.0),
            summary=str(parsed.get("summary", "")).strip(),
            observations=[str(o) for o in parsed.get("observations", [])][:8],
            pattern=str(parsed.get("rate_regime", "")).strip(),
            horizon=str(parsed.get("horizon", "")).strip(),
            raw=raw,
            provider=self.provider or "",
            model=self.model or "",
        )
