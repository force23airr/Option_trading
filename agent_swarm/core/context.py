"""DataContext — what data is available for a given run.

Each analyst checks `should_spawn(ctx)` to decide whether its dependencies
(options chain, news, macro frame, etc.) are present. Keeps the swarm
flexible — the same `Swarm.run()` works for an equity-only run or a full
options + macro run without code changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass
class DataContext:
    ticker: str
    df: pd.DataFrame                         # OHLCV + indicators
    snap: dict                               # latest indicator snapshot
    chain_df: pd.DataFrame | None = None     # full option chain w/ IV + greeks
    chain_summary: object | None = None      # ChainSummary (avoid circular import)
    spot: float | None = None
    rv30: float | None = None
    rv60: float | None = None
    risk_free_rate: float = 0.045
    macro_df: pd.DataFrame | None = None
    yield_curve: pd.DataFrame | None = None
    yield_summary: dict | None = None
    news: list[dict] = field(default_factory=list)
    earnings_date: date | None = None

    @property
    def has_options(self) -> bool:
        return self.chain_summary is not None and self.chain_df is not None and not self.chain_df.empty

    @property
    def has_macro(self) -> bool:
        return self.macro_df is not None and not self.macro_df.empty

    @property
    def has_rates(self) -> bool:
        return self.yield_curve is not None and not self.yield_curve.empty

    @property
    def has_news(self) -> bool:
        return bool(self.news)

    @property
    def has_long_history(self) -> bool:
        """True if we have enough bars for MA200 + 52-week extremes."""
        return self.df is not None and len(self.df) >= 252
