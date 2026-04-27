"""Portfolio state.

Tracks open positions, cash, and exposure. The risk agent reads from this
to size new trades and check correlation/concentration limits.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    ticker: str
    strategy: str          # e.g. "long_calls", "call_spread"
    qty: int               # contracts
    entry_price: float
    notional: float        # net debit/credit at entry
    expiry: str = ""       # ISO date


@dataclass
class Portfolio:
    cash: float = 100_000.0
    positions: list[Position] = field(default_factory=list)

    def gross_exposure(self) -> float:
        return sum(abs(p.notional) for p in self.positions)

    def position_for(self, ticker: str) -> Position | None:
        return next((p for p in self.positions if p.ticker == ticker), None)

    def open(self, position: Position) -> None:
        self.cash -= position.notional
        self.positions.append(position)

    def close(self, ticker: str, exit_price: float) -> float:
        """Close all positions in `ticker` at `exit_price`. Returns realized P&L."""
        pnl = 0.0
        keep = []
        for p in self.positions:
            if p.ticker == ticker:
                realized = (exit_price - p.entry_price) * p.qty * 100  # options multiplier
                self.cash += abs(p.notional) + realized
                pnl += realized
            else:
                keep.append(p)
        self.positions = keep
        return pnl
