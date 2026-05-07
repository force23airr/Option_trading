"""Local Streamlit dashboard for the agent swarm — terminal aesthetic.

Launch:
    streamlit run agent_swarm/dashboard/app.py

Reads saved runs from data_cache/. Read-only on existing runs; the NEW RUN
page can spawn fresh swarm runs via subprocess.
"""
from __future__ import annotations

import sys
from pathlib import Path

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
    live_runner,
    oi_walls,
    price_chart,
    run_actions,
    verdict_panel,
    why_panel,
)


_TERMINAL_CSS = """
<style>
:root {
    --term-bg: #0b0f14;
    --term-panel: #11161d;
    --term-border: #1f2937;
    --term-text: #d6deeb;
    --term-dim: #7d8590;
    --term-accent: #10b981;
    --term-amber: #f59e0b;
    --term-red: #ef4444;
    --term-blue: #58a6ff;
}

html, body, [class*="css"], .stApp, .stMarkdown, .stMetric, .stDataFrame,
.stTextInput input, .stNumberInput input, .stSelectbox, .stMultiSelect,
.stCheckbox, .stRadio, code, pre, button {
    font-family: 'JetBrains Mono', 'Fira Code', 'Menlo', 'Consolas', monospace !important;
}

.stApp { background-color: var(--term-bg); }

/* Reduce default padding */
.block-container { padding-top: 1.4rem !important; padding-bottom: 1.4rem !important; max-width: 1400px; }

/* Section headers in green accent */
h1, h2, h3, h4, h5, h6 {
    color: var(--term-accent) !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid var(--term-border);
    padding-bottom: 4px;
    margin-top: 1.2rem !important;
}
h1 { font-size: 1.4rem !important; }
h2 { font-size: 1.2rem !important; }
h3 { font-size: 1.05rem !important; }
h4, h5 { font-size: 0.95rem !important; }

/* Tables / dataframes */
.stDataFrame { border: 1px solid var(--term-border); }

/* Buttons — sharp, no rounded corners */
.stButton button, .stFormSubmitButton button, .stDownloadButton button {
    border-radius: 0 !important;
    border: 1px solid var(--term-accent) !important;
    background: transparent !important;
    color: var(--term-accent) !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em;
    transition: all 0.12s;
}
.stButton button:hover, .stFormSubmitButton button:hover {
    background: var(--term-accent) !important;
    color: var(--term-bg) !important;
}

/* Inputs — sharp edges, mono font */
.stTextInput input, .stNumberInput input, .stSelectbox > div, .stMultiSelect > div {
    border-radius: 0 !important;
    border: 1px solid var(--term-border) !important;
    background: var(--term-panel) !important;
    color: var(--term-text) !important;
}

/* Metrics */
[data-testid="stMetricValue"] {
    color: var(--term-accent) !important;
    font-size: 1.3rem !important;
}
[data-testid="stMetricLabel"] {
    color: var(--term-dim) !important;
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: var(--term-panel);
    border-right: 1px solid var(--term-border);
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: var(--term-accent) !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 1px solid var(--term-border);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 0 !important;
    background: transparent !important;
    border-bottom: 2px solid transparent !important;
    color: var(--term-dim) !important;
    padding: 8px 16px !important;
}
.stTabs [aria-selected="true"] {
    border-bottom: 2px solid var(--term-accent) !important;
    color: var(--term-accent) !important;
}

/* Code blocks — terminal log feel */
.stCode, code {
    background: #060a0e !important;
    border: 1px solid var(--term-border) !important;
    border-radius: 0 !important;
    color: #b6e5d0 !important;
    font-size: 0.82rem !important;
}

/* Expanders */
.streamlit-expanderHeader { background: var(--term-panel) !important; border-radius: 0 !important; }

/* Plotly chart container — tighter borders */
.stPlotlyChart { border: 1px solid var(--term-border); padding: 4px; background: var(--term-panel); }

/* Status bar — small footprint */
.term-status {
    font-family: monospace;
    font-size: 0.78rem;
    color: var(--term-dim);
    padding: 4px 8px;
    border: 1px solid var(--term-border);
    background: var(--term-panel);
    margin-bottom: 8px;
    letter-spacing: 0.04em;
}
.term-status .ok { color: var(--term-accent); }
.term-status .warn { color: var(--term-amber); }
.term-status .err { color: var(--term-red); }
</style>
"""


def _render_status_bar(runs_meta: list[dict]) -> None:
    n = len(runs_meta)
    latest = runs_meta[0]["timestamp"].strftime("%Y-%m-%d %H:%M") if runs_meta else "—"
    st.markdown(
        f"""
        <div class="term-status">
          <span class="ok">●</span> SWARM IDLE  |
          RUNS_INDEXED: <b>{n}</b>  |
          LATEST: <b>{latest}</b>  |
          DATA_DIR: data_cache/
        </div>
        """,
        unsafe_allow_html=True,
    )


def _page_run_detail(filtered: list[dict]) -> None:
    if not filtered:
        st.info("No runs match the current filters.")
        return

    labels = [
        f"{m['ticker']:<6}  {m['timestamp'].strftime('%Y-%m-%d %H:%M')}  {m['stance']:<8} {m['structure']}"
        for m in filtered
    ]
    selected_label = st.sidebar.selectbox("RUN", labels, label_visibility="collapsed")
    meta = filtered[labels.index(selected_label)]
    path: Path = meta["path"]
    st.sidebar.caption(path.name)

    try:
        data = data_loader.load_run(path)
    except Exception as exc:
        st.error(f"Failed to load run: {exc}")
        return

    verdict_panel.render(data)
    why_panel.render(data)

    tab_chart, tab_events, tab_options, tab_analysts = st.tabs(
        ["PRICE", "EVENTS", "OPTIONS & VOL", "TRANSCRIPTS"]
    )

    with tab_chart:
        price_chart.render(data)

    with tab_events:
        events_timeline.render(data)

    with tab_options:
        st.markdown("##### IV TERM STRUCTURE & SKEW")
        iv_term.render(data)
        st.markdown("---")
        oi_walls.render(data)

    with tab_analysts:
        for round_name in ("round1", "round2"):
            views = data.get(round_name) or []
            if not views:
                continue
            st.markdown(f"##### {round_name.upper()}")
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
    # If a row was selected, show its action panel at the top
    selected_path = st.session_state.get("selected_run_path")
    if selected_path:
        for m in filtered:
            if str(m["path"]) == selected_path:
                try:
                    data = data_loader.load_run(m["path"])
                    run_actions.render(m, data)
                    st.markdown("---")
                except Exception as exc:
                    st.error(f"Could not load selected run: {exc}")
                break

    st.markdown("### RUN HISTORY")
    cross_run_stats.render_history_table(filtered)
    st.markdown("---")
    st.markdown("### GATE FIRING")
    cross_run_stats.render_gate_firing(filtered)


def _page_new_run() -> None:
    live_runner.render()


def main() -> None:
    st.set_page_config(
        page_title="SWARM // TERMINAL",
        page_icon="◉",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_TERMINAL_CSS, unsafe_allow_html=True)
    st.markdown(
        '<h1 style="border:none;margin-bottom:0;">◉ SWARM TERMINAL</h1>',
        unsafe_allow_html=True,
    )

    runs_meta = data_loader.list_runs()
    _render_status_bar(runs_meta)

    page = st.sidebar.radio("PAGE", ("New run", "Run detail", "History & gates"))

    if page == "New run":
        _page_new_run()
        return

    if not runs_meta:
        st.info("No saved runs yet. Use the **New run** page to spawn the first one.")
        return

    filtered = filters.render(runs_meta)
    if page == "Run detail":
        _page_run_detail(filtered)
    else:
        _page_history(filtered)


if __name__ == "__main__":
    main()
