"""Local Streamlit dashboard for the agent swarm.

Launch:
    streamlit run agent_swarm/dashboard/app.py

Reads saved runs from data_cache/. Read-only — never mutates the swarm.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Streamlit runs this file as __main__, so absolute imports need the project
# root on sys.path. Add it before any agent_swarm.* imports.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from agent_swarm.dashboard.components import (
    cross_run_stats,
    data_loader,
    events_timeline,
    filters,
    iv_term,
    oi_walls,
    price_chart,
    verdict_panel,
)


def _page_run_detail(filtered: list[dict]) -> None:
    if not filtered:
        st.info("No runs match the current filters.")
        return

    labels = [
        f"{m['ticker']}  ·  {m['timestamp'].strftime('%Y-%m-%d %H:%M')}  ·  {m['stance']}  ·  {m['structure']}"
        for m in filtered
    ]
    selected_label = st.sidebar.selectbox("Saved run", labels)
    meta = filtered[labels.index(selected_label)]
    path: Path = meta["path"]
    st.sidebar.caption(str(path.name))

    try:
        data = data_loader.load_run(path)
    except Exception as exc:
        st.error(f"Failed to load run: {exc}")
        return

    # Top-level verdict panel (replaces the old metric row + scattered sections)
    verdict_panel.render(data)

    # Tabs for the rest
    tab_chart, tab_events, tab_options, tab_analysts = st.tabs(
        ["Price & indicators", "Events timeline", "Options & vol", "Analyst transcripts"]
    )

    with tab_chart:
        price_chart.render(data)

    with tab_events:
        events_timeline.render(data)

    with tab_options:
        st.markdown("#### IV term structure & skew")
        iv_term.render(data)
        st.markdown("---")
        oi_walls.render(data)

    with tab_analysts:
        for round_name in ("round1", "round2"):
            views = data.get(round_name) or []
            if not views:
                continue
            st.markdown(f"#### {round_name.replace('round', 'Round ')}")
            for v in views:
                with st.expander(
                    f"{v.get('analyst')}  ·  {str(v.get('stance', '')).upper()}  ·  "
                    f"{(v.get('confidence') or 0) * 100:.0f}%"
                ):
                    st.write(v.get("summary", ""))
                    if v.get("pattern"):
                        st.caption(f"Pattern: {v['pattern']}")
                    for obs in v.get("observations") or []:
                        st.write(f"- {obs}")


def _page_history(filtered: list[dict]) -> None:
    st.markdown("### Run history")
    cross_run_stats.render_history_table(filtered)
    st.markdown("---")
    st.markdown("### Gate firing across runs")
    cross_run_stats.render_gate_firing(filtered)


def main() -> None:
    st.set_page_config(page_title="Agent Swarm", page_icon="🧠", layout="wide")
    st.title("🧠 Agent Swarm Dashboard")

    runs_meta = data_loader.list_runs()
    if not runs_meta:
        st.info(
            "No saved runs found in `data_cache/`. "
            "Run `python -m agent_swarm.tools.run_swarm <TICKER>` first."
        )
        return

    page = st.sidebar.radio("Page", ("Run detail", "History & gate stats"))
    filtered = filters.render(runs_meta)

    if page == "Run detail":
        _page_run_detail(filtered)
    else:
        _page_history(filtered)


if __name__ == "__main__":
    main()
