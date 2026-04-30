"""News Analyst — reads recent headlines + earnings proximity.

Routed to Claude because narrative/text reasoning is its strongest lens, and
because it gives the swarm a 4th distinct brain in the round-2 debate
(Claude / DeepSeek-V3 / Kimi / DeepSeek-R1).

Spawns only when ctx.news has items.
"""
from __future__ import annotations

import json
from datetime import date

from .base import AnalystView, BaseAnalyst, _parse_json_reply
from ..core import llm
from ..data import news_source


class NewsAnalyst(BaseAnalyst):
    name = "News Analyst"
    focus = "headline sentiment, catalysts, earnings proximity, narrative shifts"
    system_prompt = (
        "You are a news-driven equity analyst. You read recent headlines AND SEC EDGAR "
        "filings (8-K, 10-Q, 10-K, Form 4 insider trades) and translate narrative into "
        "directional pressure. SEC filings are primary-source and outrank syndicated "
        "headlines: an 8-K signals a material event the company itself disclosed; a "
        "cluster of Form 4 sells signals insider distribution; a 10-Q/10-K is the actual "
        "financials. You weigh source quality, recency, and proximity to scheduled "
        "catalysts (earnings, Fed meetings, regulatory deadlines). You are skeptical of "
        "hype and clickbait. You explicitly flag when the news flow contradicts the "
        "chart, and you say so."
    )
    provider = "anthropic"
    model = None  # use env default Claude model

    @classmethod
    def should_spawn(cls, ctx) -> bool:
        return ctx.has_news

    def analyze(self, ticker, df, snap, peer_views=None):
        raise NotImplementedError("call analyze_with_news(ctx, ...) instead")

    def analyze_with_news(self, ctx, peer_views: list[AnalystView] | None = None) -> AnalystView:
        peers_block = ""
        if peer_views:
            peers_block = "\n\nPEER ANALYSTS' VIEWS (for context):\n"
            for v in peer_views:
                peers_block += f"- {v.short()}\n"

        earnings_line = ""
        if isinstance(ctx.earnings_date, date):
            days_to = (ctx.earnings_date - date.today()).days
            earnings_line = f"\nUpcoming earnings: {ctx.earnings_date.isoformat()} ({days_to:+d} days from today)\n"

        headlines = news_source.headlines_block(ctx.news, n=15)

        prompt = f"""Ticker: {ctx.ticker}

Underlying snapshot:
{json.dumps(ctx.snap, indent=2, default=str)}
{earnings_line}
RECENT HEADLINES (most recent first):
{headlines}
{peers_block}
Read the news flow through your lens. Do the headlines confirm, contradict, or
have no bearing on the technical picture? Are there imminent catalysts the chart
doesn't yet price in? Reply with one JSON object:
{{
  "stance": "bullish" | "bearish" | "neutral",
  "confidence": <float 0.0-1.0>,
  "summary": "<one sentence>",
  "sentiment": "positive" | "negative" | "mixed" | "quiet",
  "catalyst_proximity": "imminent" | "within_2w" | "none_visible",
  "chart_news_alignment": "aligned" | "divergent" | "neutral",
  "horizon": "intraday" | "1-5d" | "1-4w" | "longer",
  "observations": ["<concrete observation referencing a specific headline>", "..."]
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
            pattern=str(parsed.get("sentiment", "")).strip(),
            horizon=str(parsed.get("horizon", "")).strip(),
            raw=raw,
            provider=self.provider or "",
            model=self.model or "",
        )
