"""Technical signals.

Indicator computations and structured "feature snapshots" handed to agents
as part of their prompt context. Keep this purely numerical — no LLM calls.
"""
from __future__ import annotations

import pandas as pd


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()
    df["RSI"] = rsi(df["Close"])
    df["52W_High"] = df["High"].rolling(252).max()
    df["52W_Low"] = df["Low"].rolling(252).min()
    df["Vol_avg20"] = df["Volume"].rolling(20).mean()
    return df


def snapshot(df: pd.DataFrame) -> dict:
    """Return a flat dict of latest indicator values — agent-friendly."""
    if df.empty:
        return {}
    last = df.iloc[-1]
    out = {
        "close": float(last["Close"]),
        "rsi": float(last.get("RSI", float("nan"))),
        "ma20": float(last.get("MA20", float("nan"))),
        "ma50": float(last.get("MA50", float("nan"))),
        "ma200": float(last.get("MA200", float("nan"))),
        "high_52w": float(last.get("52W_High", float("nan"))),
        "low_52w": float(last.get("52W_Low", float("nan"))),
        "volume": float(last["Volume"]),
        "vol_avg20": float(last.get("Vol_avg20", float("nan"))),
    }
    if len(df) > 20:
        out["chg_1d_pct"] = float(df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1) * 100
        out["chg_5d_pct"] = float(df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1) * 100
        out["chg_20d_pct"] = float(df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1) * 100
    return out
