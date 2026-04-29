"""Build & view an option chain with IV + greeks.

    python -m agent_swarm.tools.option_chain COIN
    python -m agent_swarm.tools.option_chain COIN --days 1 --rate 0.045

Pulls the latest cbbo-1m quotes for the past `days` (default 1), takes the most
recent quote per contract, inverts mid through Black-Scholes for IV, and prints
the near-ATM slice for each expiry.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from agent_swarm.core import black_scholes as bs
from agent_swarm.core import data, options
from agent_swarm.data import opra_source

CACHE_DIR = Path(__file__).resolve().parents[2] / "data_cache"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--days", type=int, default=1, help="how many days of quotes to pull")
    ap.add_argument("--rate", type=float, default=0.045)
    ap.add_argument("--n-strikes", type=int, default=12, help="strikes near ATM to display")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    ticker = args.ticker.upper()

    print(f"📡 fetching {ticker} OHLCV for spot...")
    eq = data.fetch_ohlcv(ticker, days=60)
    spot = float(eq["Close"].iloc[-1])
    rv30 = bs.realized_vol(eq["Close"], window=30)
    print(f"   spot=${spot:,.2f}   realized vol 30d={rv30 * 100:.1f}%")

    cost = opra_source.cost_estimate(ticker, days=args.days)
    print(f"\n💰 OPRA quote pull will cost ~${cost:.4f}")

    print(f"📡 fetching {args.days}d of cbbo-1m quotes for {ticker}.OPT ...")
    quotes = opra_source.fetch_quotes(ticker, days=args.days)
    print(f"   {len(quotes):,} quote messages, {quotes['symbol'].nunique() if 'symbol' in quotes.columns else 0} unique contracts")

    chain = options.build_chain(quotes, spot=spot, rate=args.rate)
    if chain.empty:
        print("   chain is empty — likely off-hours quotes; try a weekday or a longer window")
        return

    print(f"\n✅ chain: {len(chain)} contracts, {chain['expiry'].nunique()} expiries\n")
    print(f"   expiries: {[str(e) for e in sorted(chain['expiry'].unique())][:8]}{' ...' if chain['expiry'].nunique() > 8 else ''}\n")

    pd.set_option("display.float_format", lambda x: f"{x:,.3f}")

    for expiry in sorted(chain["expiry"].unique())[:3]:
        slice_ = options.near_atm(chain, spot, expiry=expiry, n=args.n_strikes)
        print(f"--- {expiry}  ({slice_['dte'].iloc[0]} DTE) ---")
        cols = ["right", "strike", "bid", "ask", "mid", "iv", "delta", "gamma", "vega", "theta"]
        print(slice_[cols].to_string(index=False))
        print()

    print(f"chain ATM IV summary:")
    atm = options.near_atm(chain, spot, n=8)
    if not atm["iv"].isna().all():
        print(f"   ATM IV (median across nearest expiry):  {atm['iv'].median() * 100:.1f}%")
        print(f"   Realized vol 30d (for comparison):     {rv30 * 100:.1f}%")
        spread = atm["iv"].median() - rv30
        verdict = "RICH (IV > RV)" if spread > 0.02 else "CHEAP (IV < RV)" if spread < -0.02 else "FAIR"
        print(f"   IV-RV spread: {spread * 100:+.1f}pts  →  {verdict}")

    if args.save:
        CACHE_DIR.mkdir(exist_ok=True)
        out = CACHE_DIR / f"{ticker}_chain.csv"
        chain.to_csv(out, index=False)
        print(f"\n💾 saved → {out}")


if __name__ == "__main__":
    main()
