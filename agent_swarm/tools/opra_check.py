"""Preview OPRA dataset access and cost before issuing a paid query.

    python -m agent_swarm.tools.opra_check                # cost previews only
    python -m agent_swarm.tools.opra_check --pull COIN    # also pull a small sample
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from agent_swarm.data import databento_source as ds


def preview(symbol: str, schema: str, stype_in: str, days: int) -> None:
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    print(f"\n  schema={schema:<10} stype={stype_in:<11} symbols={symbol}  ({days}d)")
    try:
        cost = ds._client().metadata.get_cost(
            dataset="OPRA.PILLAR",
            symbols=[symbol],
            schema=schema,
            start=start,
            end=end,
            stype_in=stype_in,
        )
        print(f"    estimated cost: ${cost:.4f}")
    except Exception as exc:
        print(f"    ERROR: {exc}")


def pull_sample(parent: str) -> None:
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=2)
    print(f"\n  pulling sample: trades for {parent}.OPT, last 2 days, limit=500")
    try:
        data = ds._client().timeseries.get_range(
            dataset="OPRA.PILLAR",
            schema="trades",
            stype_in="parent",
            symbols=[f"{parent}.OPT"],
            start=start,
            end=end,
            limit=500,
        )
        df = data.to_df()
        if df.empty:
            print("    (no trades)")
            return
        cols = [c for c in ("symbol", "price", "size") if c in df.columns]
        print(f"    rows: {len(df)}")
        print(df[cols].head(10).to_string())
        print("    ...")
        print(df[cols].tail(5).to_string())
    except Exception as exc:
        print(f"    ERROR: {exc}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", help="ticker root to pull a small trade sample for (e.g. COIN)")
    args = ap.parse_args()

    print("OPRA cost previews:")
    preview("COIN.OPT", "trades", "parent", days=1)
    preview("COIN.OPT", "cbbo-1s", "parent", days=1)
    preview("COIN.OPT", "cbbo-1m", "parent", days=1)
    preview("COIN.OPT", "ohlcv-1d", "parent", days=30)

    if args.pull:
        pull_sample(args.pull.upper())


if __name__ == "__main__":
    main()
