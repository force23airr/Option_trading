"""OPRA options data via Databento.

Two convenience pulls:
- `fetch_quotes(parent, days, schema)` — bid/ask quotes for every contract under
  a parent symbol (e.g. "COIN" → all COIN options).
- `fetch_trades(parent, days)` — every option print.

Default schema is `cbbo-1m` (consolidated BBO sampled at 1 minute) — the cost
sweet spot for chain analysis (~$0.18/day per ticker).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from . import databento_source as ds


OPRA_DATASET = "OPRA.PILLAR"


def fetch_quotes(
    parent: str,
    days: int = 1,
    schema: str = "cbbo-1m",
) -> pd.DataFrame:
    """Bid/ask quotes for every option contract under `parent` (e.g. 'COIN')."""
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    data = ds._client().timeseries.get_range(
        dataset=OPRA_DATASET,
        schema=schema,
        stype_in="parent",
        symbols=[f"{parent.upper()}.OPT"],
        start=start,
        end=end,
    )
    return data.to_df()


def fetch_trades(parent: str, days: int = 1, limit: int | None = None) -> pd.DataFrame:
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    kwargs = dict(
        dataset=OPRA_DATASET,
        schema="trades",
        stype_in="parent",
        symbols=[f"{parent.upper()}.OPT"],
        start=start,
        end=end,
    )
    if limit:
        kwargs["limit"] = limit
    return ds._client().timeseries.get_range(**kwargs).to_df()


def cost_estimate(parent: str, days: int = 1, schema: str = "cbbo-1m") -> float:
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    return ds._client().metadata.get_cost(
        dataset=OPRA_DATASET,
        schema=schema,
        stype_in="parent",
        symbols=[f"{parent.upper()}.OPT"],
        start=start,
        end=end,
    )
