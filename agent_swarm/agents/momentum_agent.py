"""Momentum agent.

Looks at trend, MA structure, RSI, breakouts, and 52-week positioning to
form a momentum thesis.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MomentumView:
    ticker: str
    stance: str        # "bullish" | "bearish" | "neutral"
    confidence: float  # 0.0 - 1.0
    summary: str
    reasoning: str


class MomentumAgent:
    name = "Momentum Agent"
    role = "analyst"

    def analyze(self, ticker: str, context: dict) -> MomentumView:
        raise NotImplementedError("wire up to core.signals (RSI, MAs) + LLM reasoning")
