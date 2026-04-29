"""Macro data — Treasury yield curve, VIX, dollar index, gold, oil.

yfinance is sufficient for daily macro proxies. For better quality / lower
latency, swap to FRED API (DGS3MO, DGS5, DGS10, DGS30) — same shape, just a
different fetcher.

Yield-curve tickers (yfinance):
    ^IRX   13-week T-bill (~3M proxy)
    ^FVX   5-year Treasury yield
    ^TNX   10-year Treasury yield
    ^TYX   30-year Treasury yield
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


YIELD_TICKERS = {
    "^IRX": "3M",
    "^FVX": "5Y",
    "^TNX": "10Y",
    "^TYX": "30Y",
}


def fetch_yield_curve(days: int = 90) -> pd.DataFrame:
    """Pull Treasury yield-curve tickers (3M, 5Y, 10Y, 30Y).

    Returns DataFrame with columns ['tenor', 'yield_pct', 'chg_5d_bps', 'chg_30d_bps']
    — one row per tenor, latest values.
    """
    end = datetime.today()
    start = end - timedelta(days=days)
    rows = []
    for ticker, tenor in YIELD_TICKERS.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
            if df.empty or len(df) < 6:
                continue
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            close = float(df["Close"].iloc[-1])
            chg_5d_bps = float(df["Close"].iloc[-1] - df["Close"].iloc[-6]) * 100  # yfinance shows yield * 100
            ref = df["Close"].iloc[0] if len(df) >= 21 else df["Close"].iloc[0]
            chg_30d_bps = float(df["Close"].iloc[-1] - ref) * 100
            rows.append({
                "tenor": tenor,
                "yield_pct": close,
                "chg_5d_bps": chg_5d_bps,
                "chg_30d_bps": chg_30d_bps,
            })
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("tenor")


def yield_curve_summary(curve: pd.DataFrame) -> dict:
    """Translate a yield curve into the key numbers an analyst cares about."""
    if curve.empty:
        return {}
    out = {tenor: float(curve.loc[tenor, "yield_pct"]) for tenor in curve.index}
    if "10Y" in curve.index and "3M" in curve.index:
        out["spread_3m10y_bps"] = (curve.loc["10Y", "yield_pct"] - curve.loc["3M", "yield_pct"]) * 100
    if "10Y" in curve.index and "5Y" in curve.index:
        out["spread_5y10y_bps"] = (curve.loc["10Y", "yield_pct"] - curve.loc["5Y", "yield_pct"]) * 100
    if "30Y" in curve.index and "10Y" in curve.index:
        out["spread_10y30y_bps"] = (curve.loc["30Y", "yield_pct"] - curve.loc["10Y", "yield_pct"]) * 100
    out["chg_10y_5d_bps"] = float(curve.loc["10Y", "chg_5d_bps"]) if "10Y" in curve.index else None
    out["chg_10y_30d_bps"] = float(curve.loc["10Y", "chg_30d_bps"]) if "10Y" in curve.index else None
    return out
