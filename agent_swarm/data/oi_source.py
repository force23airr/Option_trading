"""Per-contract open interest from Databento OPRA.

One pull:
  - schema="statistics" filtered to OPEN_INTEREST stat_type — start-of-day OI
    is published before the RTH open

Returns one row per option `symbol` with `[symbol, open_interest]` ready to
merge onto the chain DataFrame produced by `core.options.build_chain`.

Cost: ~$0.22/ticker/day on top of the existing $0.22 cbbo-1m chain pull
(~2× total). We deliberately *don't* fetch `ohlcv-1d` for option volume —
that schema costs ~$0.67/ticker/day and the per-contract volume isn't used
in OI-level computation or the analyst prompts.

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


def fetch_oi_volume(parent: str, trade_date: dt.date | None = None) -> pd.DataFrame:
    """Return one row per option symbol with `[symbol, open_interest]`.

    Name kept as `fetch_oi_volume` for call-site stability; volume column is
    no longer fetched (see module docstring). Empty DataFrame on failure so
    callers can degrade gracefully.
    """
    trade_date = trade_date or _default_trade_date()
    try:
        client = ds._client()
        oi = _fetch_oi(client, parent, trade_date)
    except Exception:
        return pd.DataFrame(columns=["symbol", "open_interest"])

    if oi.empty:
        return pd.DataFrame(columns=["symbol", "open_interest"])

    oi["open_interest"] = oi["open_interest"].fillna(0).astype(int)
    return oi
