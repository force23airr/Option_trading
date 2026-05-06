"""Sidebar filters for the run list."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st


def render(runs_meta: list[dict]) -> list[dict]:
    """Mutate-and-return: caller passes all runs, gets filtered list."""
    st.sidebar.markdown("### Filters")

    if not runs_meta:
        return runs_meta

    tickers = sorted({m["ticker"] for m in runs_meta})
    stances = sorted({m["stance"] for m in runs_meta})

    selected_tickers = st.sidebar.multiselect("Ticker", tickers, default=[])
    selected_stances = st.sidebar.multiselect("Stance", stances, default=[])

    earliest = min(m["timestamp"].date() for m in runs_meta)
    latest = max(m["timestamp"].date() for m in runs_meta)
    date_range = st.sidebar.date_input(
        "Date range", value=(earliest, latest),
        min_value=earliest, max_value=latest,
    )
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = earliest, latest

    out = []
    for m in runs_meta:
        if selected_tickers and m["ticker"] not in selected_tickers:
            continue
        if selected_stances and m["stance"] not in selected_stances:
            continue
        d = m["timestamp"].date()
        if d < start_date or d > end_date:
            continue
        out.append(m)
    st.sidebar.caption(f"{len(out)} of {len(runs_meta)} runs match")
    return out
