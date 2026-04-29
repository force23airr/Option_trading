"""Shared scaffolding for analyst agents.

Every analyst follows the same shape: take a packaged context (price df,
indicator snapshot, optional peer-views in round 2), call an LLM, return a
structured AnalystView. Provider/model is chosen per analyst so the swarm can
mix Claude + DeepSeek + others.

Conditional spawning: each analyst declares `should_spawn(ctx)`. The swarm
only instantiates analysts whose data dependencies are present in the
DataContext.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from ..core import llm

if TYPE_CHECKING:
    from ..core.context import DataContext


@dataclass
class AnalystView:
    analyst: str
    ticker: str
    stance: str            # "bullish" | "bearish" | "neutral"
    confidence: float      # 0.0 - 1.0
    summary: str           # one-sentence headline
    observations: list[str] = field(default_factory=list)
    pattern: str = ""      # named pattern if found, else ""
    horizon: str = ""      # "intraday" | "1-5d" | "1-4w" | "longer"
    raw: str = ""
    provider: str = ""
    model: str = ""

    def short(self) -> str:
        return f"[{self.analyst}] {self.stance} ({self.confidence:.0%}) — {self.summary}"


def _bars_table(df: pd.DataFrame, n: int = 30) -> str:
    cols = [c for c in ("Open", "High", "Low", "Close", "Volume", "RSI", "MA20", "MA50") if c in df.columns]
    tail = df[cols].tail(n).copy()
    tail.index = [str(i.date()) if hasattr(i, "date") else str(i) for i in tail.index]
    return tail.to_string(float_format=lambda x: f"{x:,.2f}")


_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _parse_json_reply(raw: str) -> dict:
    m = _JSON_RE.search(raw)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


class BaseAnalyst:
    name: str = "Base Analyst"
    focus: str = "general"  # what this analyst specializes in
    system_prompt: str = "You are a careful, evidence-driven equity analyst."
    provider: str | None = None  # None = use env default
    model: str | None = None

    @classmethod
    def should_spawn(cls, ctx: "DataContext") -> bool:
        """Whether this analyst should be instantiated given available data.
        Default: spawn unconditionally (chart analysts only need OHLCV).
        Override in subclasses that need optional data (options, news, macro).
        """
        return True

    def _build_prompt(self, ticker: str, df: pd.DataFrame, snap: dict, peer_views: list[AnalystView] | None) -> str:
        peers_block = ""
        if peer_views:
            peers_block = "\n\nPEER ANALYSTS' INITIAL TAKES (you may agree, disagree, or refine):\n"
            for v in peer_views:
                peers_block += f"- {v.short()}\n"

        return f"""Ticker: {ticker}
Your specialty: {self.focus}

Indicator snapshot:
{json.dumps(snap, indent=2, default=str)}

Recent price/volume bars (most recent last):
{_bars_table(df, 30)}
{peers_block}
Analyze ONLY through your specialty lens. Identify any patterns or signals you see in the data.

Reply with a single JSON object — no prose outside the JSON:
{{
  "stance": "bullish" | "bearish" | "neutral",
  "confidence": <float 0.0-1.0>,
  "summary": "<one sentence headline>",
  "pattern": "<named pattern if found, else empty string>",
  "horizon": "intraday" | "1-5d" | "1-4w" | "longer",
  "observations": ["<concrete observation 1>", "<observation 2>", "..."]
}}"""

    def analyze(
        self,
        ticker: str,
        df: pd.DataFrame,
        snap: dict,
        peer_views: list[AnalystView] | None = None,
    ) -> AnalystView:
        prompt = self._build_prompt(ticker, df, snap, peer_views)
        raw = llm.chat(
            prompt,
            system=self.system_prompt,
            provider=self.provider,
            model=self.model,
            max_tokens=900,
            temperature=0.4,
        )
        parsed = _parse_json_reply(raw)
        return AnalystView(
            analyst=self.name,
            ticker=ticker,
            stance=str(parsed.get("stance", "neutral")).lower(),
            confidence=float(parsed.get("confidence", 0.0) or 0.0),
            summary=str(parsed.get("summary", "")).strip(),
            observations=[str(o) for o in parsed.get("observations", [])][:8],
            pattern=str(parsed.get("pattern", "")).strip(),
            horizon=str(parsed.get("horizon", "")).strip(),
            raw=raw,
            provider=self.provider or "default",
            model=self.model or "default",
        )
