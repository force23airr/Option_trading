"""Databento-backed market data.

Pulls historical OHLCV bars from Databento's Historical API. Drop-in for the
yfinance fetcher in `core/data.py` so analysts can switch sources without
caring where bytes come from.

Set DATABENTO_API_KEY in the environment (or .env at the project root).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import databento as db


DEFAULT_DATASET = "XNAS.ITCH"  # Nasdaq TotalView-ITCH; covers most US equities
DEFAULT_SCHEMA = "ohlcv-1d"


@lru_cache(maxsize=1)
def _client() -> db.Historical:
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError(
            "DATABENTO_API_KEY not set. Add it to your environment or to a .env "
            "file at the project root."
        )
    return db.Historical(key)


def fetch_ohlcv(
    ticker: str,
    days: int = 365,
    dataset: str = DEFAULT_DATASET,
    schema: str = DEFAULT_SCHEMA,
    stype_in: str = "raw_symbol",
) -> pd.DataFrame:
    """Return a DataFrame indexed by date with Open/High/Low/Close/Volume columns."""
    # Clamp end to *yesterday* UTC midnight. After midnight UTC, "today UTC"
    # is past Databento's daily-bar publication, which 422s. -1 day is safe.
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    start = end - timedelta(days=days)

    data = _client().timeseries.get_range(
        dataset=dataset,
        symbols=[ticker.upper()],
        schema=schema,
        start=start,
        end=end,
        stype_in=stype_in,
    )

    df = data.to_df()
    if df.empty:
        return df

    rename = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    df = df.rename(columns=rename)
    cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    df = df[cols].copy()

    # Consolidated datasets (e.g. DBEQ.BASIC) return one row per venue per day.
    # Aggregate to a single bar per timestamp.
    if df.index.has_duplicates:
        df = df.groupby(df.index).agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        })
    return df


def fetch_futures(
    symbol: str = "CL.c.0",
    days: int = 365,
    dataset: str = "GLBX.MDP3",
    schema: str = "ohlcv-1d",
) -> pd.DataFrame:
    """Pull a CME futures continuous contract.

    Common symbols (continuous front-month):
        CL.c.0   WTI crude oil
        NG.c.0   natural gas
        GC.c.0   gold
        ES.c.0   E-mini S&P 500
        NQ.c.0   E-mini Nasdaq

    Requires GLBX.MDP3 dataset access on your Databento plan.
    """
    return fetch_ohlcv(symbol, days=days, dataset=dataset, schema=schema, stype_in="continuous")


def cost_estimate(
    ticker: str,
    days: int = 365,
    dataset: str = DEFAULT_DATASET,
    schema: str = DEFAULT_SCHEMA,
) -> dict:
    """Preview Databento billing before issuing a paid query."""
    # Clamp end to *yesterday* UTC midnight. After midnight UTC, "today UTC"
    # is past Databento's daily-bar publication, which 422s. -1 day is safe.
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    start = end - timedelta(days=days)
    return _client().metadata.get_cost(
        dataset=dataset,
        symbols=[ticker.upper()],
        schema=schema,
        start=start,
        end=end,
        stype_in="raw_symbol",
    )
