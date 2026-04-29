"""WTI oil end-to-end demo: pull historical, compute realized vol, price a hypothetical option.

    python -m agent_swarm.tools.wti_demo            # USO ETF (always works, equities feed)
    python -m agent_swarm.tools.wti_demo --futures  # CL futures via Databento GLBX.MDP3

The futures path needs GLBX.MDP3 access on your Databento plan; if you don't
have it the call will 403 and we fall back to USO automatically.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from agent_swarm.core import black_scholes as bs
from agent_swarm.core import data, signals
from agent_swarm.data import databento_source

CACHE_DIR = Path(__file__).resolve().parents[2] / "data_cache"


def fetch_wti(use_futures: bool, days: int) -> tuple[str, pd.DataFrame]:
    if use_futures:
        try:
            df = databento_source.fetch_futures("CL.c.0", days=days)
            if not df.empty:
                return "WTI (CL.c.0 continuous front-month)", df
            print("[wti] futures returned empty; falling back to USO")
        except Exception as exc:
            print(f"[wti] futures fetch failed: {exc}")
            print("[wti] falling back to USO ETF")
    return "USO (United States Oil Fund ETF)", data.fetch_ohlcv("USO", days=days)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--futures", action="store_true", help="use CL futures (needs GLBX.MDP3 access)")
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--strike-pct", type=float, default=1.0,
                    help="strike as a multiple of spot (1.0 = ATM, 0.95 = 5% OTM put / 5% ITM call)")
    ap.add_argument("--dte", type=int, default=30, help="days to expiry for the demo option")
    ap.add_argument("--rate", type=float, default=0.045, help="risk-free rate")
    args = ap.parse_args()

    label, df = fetch_wti(args.futures, args.days)
    if df.empty:
        print("No data returned — check Databento dataset access or your network.")
        return

    df = signals.add_indicators(df)
    spot = float(df["Close"].iloc[-1])
    rv30 = bs.realized_vol(df["Close"], window=30)
    rv60 = bs.realized_vol(df["Close"], window=60)

    print(f"\n{'=' * 64}")
    print(f"  {label}")
    print(f"  {len(df)} bars   {df.index[0].date()} → {df.index[-1].date()}")
    print("=" * 64)
    print(f"  spot:                ${spot:,.2f}")
    print(f"  realized vol 30d:    {rv30 * 100:.1f}%")
    print(f"  realized vol 60d:    {rv60 * 100:.1f}%")
    print(f"  RSI:                 {df['RSI'].iloc[-1]:.1f}")
    print(f"  20d MA:              ${df['MA20'].iloc[-1]:,.2f}")

    print(f"\nLast 5 bars:")
    print(df[["Open", "High", "Low", "Close", "Volume"]].tail(5).to_string(float_format=lambda x: f"{x:,.2f}"))

    K = spot * args.strike_pct
    T = args.dte / 365.0
    sigma = rv30 if not math.isnan(rv30) else 0.40

    print(f"\n--- BLACK-SCHOLES ({args.dte}d to expiry, σ = realized 30d = {sigma * 100:.1f}%) ---")
    print(f"  spot S:    ${spot:,.2f}")
    print(f"  strike K:  ${K:,.2f}  ({args.strike_pct * 100:.0f}% of spot)")
    print(f"  T:         {T:.4f} yrs")
    print(f"  r:         {args.rate * 100:.2f}%")

    for kind in ("call", "put"):
        g = bs.greeks(spot, K, T, args.rate, sigma, kind=kind)
        print(f"\n  {kind.upper():5s}  price={g.price:>7.3f}  Δ={g.delta:+.3f}  "
              f"Γ={g.gamma:.4f}  vega={g.vega/100:.3f}/1%vol  "
              f"θ={g.theta/365:.3f}/day  ρ={g.rho/100:.3f}/1%r")

    # save data
    CACHE_DIR.mkdir(exist_ok=True)
    out = CACHE_DIR / ("WTI_CL_continuous.csv" if args.futures and "CL" in label else "WTI_USO.csv")
    df.to_csv(out)
    print(f"\n💾 saved → {out}")


if __name__ == "__main__":
    main()
