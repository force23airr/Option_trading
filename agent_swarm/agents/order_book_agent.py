"""Order book / price-action agent.

Reads recent OHLCV + microstructure cues (volume profile, range, gaps) and
forms a tape-reading thesis on the ticker.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderBookView:
    ticker: str
    stance: str        # "bullish" | "bearish" | "neutral"
    confidence: float  # 0.0 - 1.0
    summary: str
    reasoning: str


class OrderBookAgent:
    name = "Order Book Agent"
    role = "analyst"

    def analyze(self, ticker: str, context: dict) -> OrderBookView:
        raise NotImplementedError("wire up to core.data + core.signals + LLM reasoning")
