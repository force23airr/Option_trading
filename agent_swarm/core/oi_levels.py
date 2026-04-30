"""Compute dealer-positioning levels from a chain DataFrame with OI.

Pure computation — no I/O, no LLMs. Consumed by `summarize_chain` (and downstream
by OptionsAnalyst + QuantStrategist prompts).

Definitions:
- call wall  = strike with the largest call OI in a given expiry
- put wall   = strike with the largest put OI in a given expiry
- max pain   = strike that minimizes total ITM dollar value across all OI at expiry
              i.e. the strike where the most option holders lose the most
- top OI strikes = top 5 strikes ranked by combined call+put OI
"""
from __future__ import annotations

from datetime import date

import pandas as pd


def compute_max_pain(chain_slice: pd.DataFrame) -> float | None:
    """For each candidate strike K in the slice, sum option-holder pain at expiry:
        pain(K) = Σ max(K - strike_call, 0) * call_oi
                + Σ max(strike_put - K, 0) * put_oi
    Max-pain is the K minimizing total pain. Returns None if no OI.
    """
    if chain_slice.empty or "open_interest" not in chain_slice.columns:
        return None
    if chain_slice["open_interest"].sum() == 0:
        return None

    strikes = sorted(chain_slice["strike"].unique())
    if not strikes:
        return None

    calls = chain_slice[chain_slice["right"] == "C"][["strike", "open_interest"]]
    puts = chain_slice[chain_slice["right"] == "P"][["strike", "open_interest"]]

    best_K, best_pain = None, None
    for K in strikes:
        call_pain = ((K - calls["strike"]).clip(lower=0) * calls["open_interest"]).sum()
        put_pain = ((puts["strike"] - K).clip(lower=0) * puts["open_interest"]).sum()
        total = float(call_pain + put_pain)
        if best_pain is None or total < best_pain:
            best_pain, best_K = total, float(K)
    return best_K


def compute_oi_levels(chain: pd.DataFrame, expiry: date) -> dict | None:
    """One expiry → dealer-positioning levels. Returns None if no OI for this expiry."""
    if chain.empty or "open_interest" not in chain.columns:
        return None

    slice_ = chain[chain["expiry"] == expiry].copy()
    if slice_.empty or slice_["open_interest"].sum() == 0:
        return None

    calls = slice_[slice_["right"] == "C"]
    puts = slice_[slice_["right"] == "P"]

    call_wall = None
    if not calls.empty and calls["open_interest"].sum() > 0:
        call_wall = float(calls.loc[calls["open_interest"].idxmax(), "strike"])

    put_wall = None
    if not puts.empty and puts["open_interest"].sum() > 0:
        put_wall = float(puts.loc[puts["open_interest"].idxmax(), "strike"])

    max_pain = compute_max_pain(slice_)

    by_strike = slice_.pivot_table(
        index="strike", columns="right", values="open_interest", aggfunc="sum", fill_value=0
    )
    if "C" not in by_strike.columns:
        by_strike["C"] = 0
    if "P" not in by_strike.columns:
        by_strike["P"] = 0
    by_strike["total"] = by_strike["C"] + by_strike["P"]
    top = by_strike.nlargest(5, "total")
    top_oi_strikes = [
        {
            "strike": float(strike),
            "call_oi": int(row["C"]),
            "put_oi": int(row["P"]),
            "total_oi": int(row["total"]),
        }
        for strike, row in top.iterrows()
    ]

    total_oi = int(by_strike["total"].sum())
    top5_oi = int(top["total"].sum())
    concentration = round(top5_oi / total_oi * 100, 1) if total_oi else 0.0

    total_call_oi = int(calls["open_interest"].sum())
    total_put_oi = int(puts["open_interest"].sum())
    pc_ratio = round(total_put_oi / total_call_oi, 2) if total_call_oi else None

    dte = int(slice_["dte"].iloc[0])

    return {
        "expiry": str(expiry),
        "dte": dte,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "max_pain": max_pain,
        "top_oi_strikes": top_oi_strikes,
        "total_oi": total_oi,
        "oi_concentration_pct": concentration,
        "put_call_oi_ratio": pc_ratio,
    }


def pick_top_expiries(chain: pd.DataFrame, n: int = 2, max_dte: int = 120) -> list[date]:
    """The n expiries with the largest total OI within a tradable horizon.

    `max_dte=120` filters out LEAPs whose post-split orphan strikes ($0.50,
    $2.50, etc.) carry massive but non-actionable OI and distort max-pain.
    """
    if chain.empty or "open_interest" not in chain.columns:
        return []
    valid = chain[(chain["dte"] > 0) & (chain["dte"] <= max_dte)]
    if valid.empty:
        return []
    totals = valid.groupby("expiry")["open_interest"].sum().sort_values(ascending=False)
    return [exp for exp in totals.head(n).index.tolist()]
