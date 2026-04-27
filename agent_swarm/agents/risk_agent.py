"""Risk agent.

Takes the analyst theses and challenges them: bear case, sizing, drawdown,
correlation, tail risk. Can approve, modify, or reject.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskVerdict:
    ticker: str
    decision: str      # "approve" | "modify" | "reject"
    confidence: float
    summary: str
    reasoning: str
    max_position_pct: float = 0.0


class RiskAgent:
    name = "Risk Agent"
    role = "risk"

    def review(self, ticker: str, analyst_views: list, context: dict) -> RiskVerdict:
        raise NotImplementedError("wire up to core.portfolio + LLM reasoning")
