"""View / export the OHLCV data the swarm is collecting.

    python -m agent_swarm.tools.view_data COIN
    python -m agent_swarm.tools.view_data COIN --days 90
    python -m agent_swarm.tools.view_data COIN --csv      # also save CSV

CSV lands in ./data_cache/{TICKER}_{days}d.csv.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from agent_swarm.core import data, signals


CACHE_DIR = Path(__file__).resolve().parents[2] / "data_cache"


def _ascii_chart(closes: pd.Series, height: int = 12, width: int = 60) -> str:
    s = closes.dropna().tail(width)
    if s.empty:
        return "(no data)"
    lo, hi = s.min(), s.max()
    if hi == lo:
        return "(flat)"
    rows = [[" "] * len(s) for _ in range(height)]
    for x, v in enumerate(s):
        y = int((v - lo) / (hi - lo) * (height - 1))
        rows[height - 1 - y][x] = "█"
    chart = "\n".join("".join(r) for r in rows)
    return f"{hi:>8.2f} ┤\n{chart}\n{lo:>8.2f} ┤"


def view(ticker: str, days: int = 90, save_csv: bool = False) -> pd.DataFrame:
    df = data.fetch_ohlcv(ticker, days=days)
    if df.empty:
        print(f"No data for {ticker}")
        return df

    df = signals.add_indicators(df)
    snap = signals.snapshot(df)

    print(f"\n{'=' * 60}")
    print(f"  {ticker}   {len(df)} bars   {df.index[0].date()} → {df.index[-1].date()}")
    print("=" * 60)

    print("\nLatest snapshot:")
    for k, v in snap.items():
        if isinstance(v, float):
            print(f"  {k:<14} {v:>14,.2f}")
        else:
            print(f"  {k:<14} {v!s:>14}")

    print("\nLast 10 bars:")
    print(df.tail(10).to_string(float_format=lambda x: f"{x:,.2f}"))

    print("\nClose price (ASCII):")
    print(_ascii_chart(df["Close"]))

    if save_csv:
        CACHE_DIR.mkdir(exist_ok=True)
        out = CACHE_DIR / f"{ticker.upper()}_{days}d.csv"
        df.to_csv(out)
        print(f"\nSaved → {out}")

    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--csv", action="store_true", help="also save CSV to data_cache/")
    args = ap.parse_args()
    view(args.ticker.upper(), days=args.days, save_csv=args.csv)


if __name__ == "__main__":
    main()
