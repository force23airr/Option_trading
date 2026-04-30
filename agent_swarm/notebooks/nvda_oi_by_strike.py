"""NVDA open interest by strike — Databento OPRA.PILLAR.

Pulls definition + OHLCV-1d volume + start-of-day open-interest stats for
all NVDA options on a given trade date, then plots OI by strike for one
chosen expiration. Saves the chart as a PNG (CLI-friendly).

    python -m agent_swarm.notebooks.nvda_oi_by_strike
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import databento as db
import matplotlib.pyplot as plt
import pandas as pd
from dotenv import load_dotenv
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator


def get_volume_data(client, dataset, symbol, date):
    volume_df = client.timeseries.get_range(
        dataset=dataset,
        symbols=f"{symbol}.OPT",
        schema="ohlcv-1d",
        stype_in="parent",
        start=date,
    ).to_df()
    return volume_df.groupby("symbol")["volume"].sum().reset_index()


def get_oi_data(client, dataset, symbol, date):
    end_time = dt.time(9, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    stats_df = client.timeseries.get_range(
        dataset=dataset,
        symbols=f"{symbol}.OPT",
        schema="statistics",
        stype_in="parent",
        start=date,
        end=dt.datetime.combine(date, end_time),
    ).to_df()

    stats_df = stats_df[stats_df["stat_type"] == db.StatType.OPEN_INTEREST]
    stats_df = stats_df.drop_duplicates("symbol", keep="last")
    stats_df["open_interest"] = stats_df["quantity"]
    return stats_df[["open_interest", "symbol"]]


def get_definition_data(client, dataset, symbol, date):
    def_df = client.timeseries.get_range(
        dataset=dataset,
        symbols=f"{symbol}.OPT",
        schema="definition",
        stype_in="parent",
        start=date,
    ).to_df()

    def_df["days_to_expiration"] = (def_df["expiration"] - def_df.index.normalize()).dt.days
    def_df["expiration"] = def_df["expiration"].dt.normalize().dt.date

    return def_df[["symbol", "strike_price", "instrument_class", "expiration", "days_to_expiration"]]


def plot_oi_by_strike(df, expiration_date, symbol, out_path):
    df = df[df["expiration"] == expiration_date]
    if df.empty:
        print(f"no contracts for expiration {expiration_date}")
        return
    trade_date = df["trade_date"].iloc[0]
    days_to_expiration = df["days_to_expiration"].iloc[0]

    df_strikes = df.groupby(["strike_price", "instrument_class"])["open_interest"].sum().unstack()

    _, ax = plt.subplots(figsize=(14, 6))
    df_strikes.plot(ax=ax, kind="bar", xlabel="Strike price", ylabel="Open interest")

    ax.xaxis.set_major_locator(MaxNLocator(15))
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_title(f"{symbol} open interest \n {trade_date} ({days_to_expiration} DTE)")
    ax.legend(handles=[Patch(facecolor="C0", label="Call"), Patch(facecolor="C1", label="Put")])

    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    print(f"\n📊 chart saved → {out_path}")


def main():
    load_dotenv()
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        raise SystemExit("DATABENTO_API_KEY not set in .env")

    dataset = "OPRA.PILLAR"
    symbol = "NVDA"
    start = dt.date(2025, 8, 19)
    expiration = dt.date(2025, 8, 22)

    client = db.Historical(api_key)

    print(f"📡 fetching definitions for {symbol} ({start})...")
    def_df = get_definition_data(client, dataset, symbol, start)
    print(f"   {len(def_df)} contracts")

    print(f"📡 fetching volume...")
    volume_df = get_volume_data(client, dataset, symbol, start)
    print(f"   {len(volume_df)} symbols with volume")

    print(f"📡 fetching open interest...")
    stats_df = get_oi_data(client, dataset, symbol, start)
    print(f"   {len(stats_df)} symbols with OI")

    df = def_df.merge(volume_df, on="symbol", how="left")
    df = df.merge(stats_df, on="symbol", how="left")
    df["trade_date"] = start
    df["volume"] = df["volume"].fillna(0).astype(int)
    df["open_interest"] = df["open_interest"].fillna(0).astype(int)

    print(f"\nTop 10 contracts by open interest:")
    print(df.nlargest(10, "open_interest").to_string(index=False))

    out_dir = Path(__file__).resolve().parents[2] / "data_cache"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{symbol}_oi_{expiration.isoformat()}.png"
    plot_oi_by_strike(df, expiration, symbol, out_path)


if __name__ == "__main__":
    main()
