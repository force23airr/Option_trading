"""Events Analyst — reads scheduled catalyst/calendar risk.

This analyst is deliberately narrower than News Analyst. It does not scan raw
headlines; it reads structured upcoming events and translates them into trade
permission, sizing, and volatility-risk context.
"""
from __future__ import annotations

import json

from .base import AnalystView, BaseAnalyst, _parse_json_reply
from ..core import llm
from ..data import events_source


class EventsAnalyst(BaseAnalyst):
    name = "Events Analyst"
    focus = "scheduled catalysts, macro calendar risk, earnings proximity, event-driven volatility"
    system_prompt = (
        "You are an event-risk analyst for an options trading desk. You read only "
        "structured scheduled events: earnings, macro releases, Fed events, regulatory "
        "dates, sector events, and other calendar catalysts. Your job is to say whether "
        "the event calendar supports taking risk, requires smaller size, or argues for "
        "staying flat. You are conservative around gap risk and implied-volatility "
        "repricing. Do not invent events. Use only the event list and snapshot provided."
    )
    provider = "deepseek"
    model = "deepseek-chat"

    @classmethod
    def should_spawn(cls, ctx) -> bool:
        return ctx.has_events

    def analyze(self, ticker, df, snap, peer_views=None):
        raise NotImplementedError("call analyze_with_events(ctx, ...) instead")

    def analyze_with_events(self, ctx, peer_views: list[AnalystView] | None = None) -> AnalystView:
        peers_block = ""
        if peer_views:
            peers_block = "\n\nPEER ANALYSTS' VIEWS (for context):\n"
            for v in peer_views:
                peers_block += f"- {v.short()}\n"

        prompt = f"""Ticker: {ctx.ticker}

Underlying snapshot:
{json.dumps(ctx.snap, indent=2, default=str)}

EVENT SUMMARY:
{json.dumps(ctx.event_summary or {}, indent=2, default=str)}

UPCOMING STRUCTURED EVENTS:
{events_source.events_block(ctx.events)}
{peers_block}

Translate the event calendar into trade permission and volatility risk. Reply
with one JSON object:
{{
  "stance": "bullish" | "bearish" | "neutral",
  "confidence": <float 0.0-1.0>,
  "summary": "<one sentence naming the key event risk>",
  "event_risk": "low" | "medium" | "high" | "extreme",
  "trade_permission": "approve" | "reduce_size" | "watchlist_only" | "reject",
  "volatility_effect": "iv_expansion_likely" | "iv_crush_risk" | "gap_risk" | "none_visible",
  "horizon": "intraday" | "1-5d" | "1-4w" | "longer",
  "observations": ["<concrete observation referencing date/days/importance>", "..."]
}}"""
        raw = llm.chat(
            prompt,
            system=self.system_prompt,
            provider=self.provider,
            model=self.model,
            max_tokens=1800,
            temperature=0.25,
        )
        parsed = _parse_json_reply(raw)
        return AnalystView(
            analyst=self.name,
            ticker=ctx.ticker,
            stance=str(parsed.get("stance", "neutral")).lower(),
            confidence=float(parsed.get("confidence", 0.0) or 0.0),
            summary=str(parsed.get("summary", "")).strip(),
            observations=[str(o) for o in parsed.get("observations", [])][:8],
            pattern=str(parsed.get("trade_permission", "")).strip(),
            horizon=str(parsed.get("horizon", "")).strip(),
            raw=raw,
            provider=self.provider or "",
            model=self.model or "",
        )
