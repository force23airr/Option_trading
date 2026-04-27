"""Market data fetchers.

Pulls OHLCV + headlines + macro context used by every agent. Wraps yfinance
for now; swap in a paid feed (Polygon, Tiingo) later by keeping this the
single source of price/news data.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


def fetch_ohlcv(ticker: str, days: int = 365) -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=days)
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        return df
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df[["Open", "High", "Low", "Close", "Volume"]].copy()


def fetch_news(ticker: str, limit: int = 10) -> list[dict]:
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        return []
    out = []
    for item in items[:limit]:
        content = item.get("content", item)
        provider = content.get("provider")
        publisher = (
            provider.get("displayName") if isinstance(provider, dict) else content.get("publisher", "")
        )
        out.append({
            "title": content.get("title", ""),
            "publisher": publisher,
            "date": str(content.get("pubDate") or content.get("providerPublishTime", "")),
        })
    return out


MACRO_TICKERS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "DXY": "Dollar Index",
    "TLT": "20Y Treasury",
    "GLD": "Gold",
    "USO": "Oil",
    "^VIX": "VIX",
}


def macro_snapshot(days: int = 30) -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=days + 5)
    rows = []
    for tkr, label in MACRO_TICKERS.items():
        try:
            df = yf.download(tkr, start=start, end=end, progress=False, auto_adjust=True)
            if df.empty or len(df) < 2:
                continue
            close = float(df["Close"].iloc[-1])
            chg_1d = float(df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1) * 100
            chg_30d = float(df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100
            rows.append({"ticker": tkr, "label": label, "close": close, "chg_1d_pct": chg_1d, "chg_30d_pct": chg_30d})
        except Exception:
            continue
    return pd.DataFrame(rows)
