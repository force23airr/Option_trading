"""Trade executor.

Translates an approved thesis + risk verdict into a concrete options
structure (strikes / expiry / sizing) and routes the order. Paper-trades
into the in-memory Portfolio for now; swap in a broker SDK (IBKR,
Tradier, Alpaca) later.
"""
from __future__ import annotations

from dataclasses import dataclass

from .portfolio import Portfolio, Position


@dataclass
class TradeTicket:
    ticker: str
    structure: str         # "long_calls" | "long_puts" | "call_spread" | "put_spread" | ...
    strikes: list[float]
    expiry: str            # ISO date
    qty: int
    est_debit: float
    rationale: str


def execute(ticket: TradeTicket, portfolio: Portfolio) -> Position:
    """Paper-execute a ticket into the portfolio. Returns the opened Position."""
    pos = Position(
        ticker=ticket.ticker,
        strategy=ticket.structure,
        qty=ticket.qty,
        entry_price=ticket.est_debit,
        notional=ticket.est_debit * ticket.qty * 100,
        expiry=ticket.expiry,
    )
    portfolio.open(pos)
    return pos
