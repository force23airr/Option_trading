"""Agent swarm entry point.

Run end-to-end on a single ticker:
    python -m agent_swarm.main AAPL
"""
from __future__ import annotations

import sys

from .agents.momentum_agent import MomentumAgent
from .agents.order_book_agent import OrderBookAgent
from .agents.risk_agent import RiskAgent
from .core import data, signals
from .core.portfolio import Portfolio


def run(ticker: str) -> None:
    df = signals.add_indicators(data.fetch_ohlcv(ticker))
    snap = signals.snapshot(df)
    headlines = data.fetch_news(ticker)
    macro = data.macro_snapshot()

    context = {
        "snapshot": snap,
        "headlines": headlines,
        "macro": macro,
    }

    momentum = MomentumAgent()
    order_book = OrderBookAgent()
    risk = RiskAgent()

    print(f"=== {ticker} ===")
    print(f"price: {snap.get('close')}  rsi: {snap.get('rsi'):.1f}")

    analyst_views = []
    for agent in (momentum, order_book):
        try:
            view = agent.analyze(ticker, context)
            analyst_views.append(view)
            print(f"[{agent.name}] {view.stance} ({view.confidence:.0%}) — {view.summary}")
        except NotImplementedError:
            print(f"[{agent.name}] not yet wired up")

    try:
        verdict = risk.review(ticker, analyst_views, context)
        print(f"[{risk.name}] {verdict.decision} — {verdict.summary}")
    except NotImplementedError:
        print(f"[{risk.name}] not yet wired up")

    portfolio = Portfolio()
    print(f"portfolio cash: ${portfolio.cash:,.0f}")


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    run(ticker.upper())
