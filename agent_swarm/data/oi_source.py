"""Per-contract open-interest + volume from Databento OPRA.

Two pulls (matching the working notebook in `notebooks/nvda_oi_by_strike.py`):
  - schema="statistics" filtered to OPEN_INTEREST stat_type — start-of-day OI
    is published before the RTH open
  - schema="ohlcv-1d" — daily volume per contract

Returns one row per option `symbol` with `[symbol, open_interest, option_volume]`
ready to merge onto the chain DataFrame produced by `core.options.build_chain`.

Designed to fail soft: any error returns an empty DataFrame so the swarm can
still run with quotes-only data.
"""
from __future__ import annotations

import datetime as dt
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

import databento as db
import pandas as pd

from . import databento_source as ds


OPRA_DATASET = "OPRA.PILLAR"


def _default_trade_date() -> dt.date:
    """Yesterday UTC — matches `opra_source.fetch_quotes` clamping."""
    end = dt.datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    return end.date()


def _fetch_oi(client: db.Historical, parent: str, trade_date: dt.date) -> pd.DataFrame:
    end_time = dt.time(9, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    stats = client.timeseries.get_range(
        dataset=OPRA_DATASET,
        symbols=f"{parent.upper()}.OPT",
        schema="statistics",
        stype_in="parent",
        start=trade_date,
        end=dt.datetime.combine(trade_date, end_time),
    ).to_df()

    if stats.empty:
        return pd.DataFrame(columns=["symbol", "open_interest"])

    stats = stats[stats["stat_type"] == db.StatType.OPEN_INTEREST]
    stats = stats.drop_duplicates("symbol", keep="last").copy()
    stats["open_interest"] = stats["quantity"]
    return stats[["symbol", "open_interest"]]


def _fetch_volume(client: db.Historical, parent: str, trade_date: dt.date) -> pd.DataFrame:
    vol = client.timeseries.get_range(
        dataset=OPRA_DATASET,
        symbols=f"{parent.upper()}.OPT",
        schema="ohlcv-1d",
        stype_in="parent",
        start=trade_date,
    ).to_df()

    if vol.empty:
        return pd.DataFrame(columns=["symbol", "option_volume"])

    return vol.groupby("symbol")["volume"].sum().reset_index().rename(columns={"volume": "option_volume"})


def fetch_oi_volume(parent: str, trade_date: dt.date | None = None) -> pd.DataFrame:
    """Return one row per option symbol with `[symbol, open_interest, option_volume]`.

    Empty DataFrame on any failure so callers can degrade gracefully.
    """
    trade_date = trade_date or _default_trade_date()
    try:
        client = ds._client()
        oi = _fetch_oi(client, parent, trade_date)
        vol = _fetch_volume(client, parent, trade_date)
    except Exception:
        return pd.DataFrame(columns=["symbol", "open_interest", "option_volume"])

    if oi.empty and vol.empty:
        return pd.DataFrame(columns=["symbol", "open_interest", "option_volume"])

    if oi.empty:
        oi = pd.DataFrame(columns=["symbol", "open_interest"])
    if vol.empty:
        vol = pd.DataFrame(columns=["symbol", "option_volume"])

    merged = oi.merge(vol, on="symbol", how="outer")
    merged["open_interest"] = merged["open_interest"].fillna(0).astype(int)
    merged["option_volume"] = merged["option_volume"].fillna(0).astype(int)
    return merged
