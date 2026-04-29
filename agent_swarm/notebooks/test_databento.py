"""Smoke test: pull a few days of OHLCV via Databento.

Usage:
    python -m agent_swarm.notebooks.test_databento COIN
"""
from __future__ import annotations

import sys

from agent_swarm.data import databento_source


def main(ticker: str = "COIN", days: int = 30) -> None:
    print(f"Cost estimate for {ticker} ({days}d ohlcv-1d):")
    try:
        print(databento_source.cost_estimate(ticker, days=days))
    except Exception as exc:
        print(f"  (cost preview failed: {exc})")

    print(f"\nFetching {ticker} last {days} days...")
    df = databento_source.fetch_ohlcv(ticker, days=days)
    print(df.tail(10))
    print(f"\nrows: {len(df)}")


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "COIN"
    main(t.upper())
