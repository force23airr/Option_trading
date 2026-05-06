"""Local Streamlit dashboard for saved swarm reports."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data_cache"


def _load_reports() -> list[Path]:
    if not CACHE_DIR.exists():
        return []
    return sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _pct(value, default=0.0) -> str:
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return f"{default:.0%}"


def _metric_row(data: dict) -> None:
    snap = data.get("snapshot") or {}
    cols = st.columns(5)
    cols[0].metric("Ticker", data.get("ticker", ""))
    cols[1].metric("Close", f"{snap.get('close', 0):,.2f}" if snap.get("close") is not None else "-")
    cols[2].metric("RSI", f"{snap.get('rsi', 0):.1f}" if snap.get("rsi") is not None else "-")
    cols[3].metric("MA20", f"{snap.get('ma20', 0):,.2f}" if snap.get("ma20") is not None else "-")
    cols[4].metric("MA50", f"{snap.get('ma50', 0):,.2f}" if snap.get("ma50") is not None else "-")


def _render_consensus(data: dict) -> None:
    consensus = data.get("consensus") or {}
    st.subheader("Consensus")
    cols = st.columns(3)
    cols[0].metric("Stance", str(consensus.get("consensus_stance", "-")).upper())
    cols[1].metric("Confidence", _pct(consensus.get("consensus_confidence")))
    cols[2].metric("Horizon", consensus.get("horizon", "-"))
    st.write(consensus.get("headline", ""))
    if consensus.get("suggested_structure"):
        st.caption(f"Structure: {consensus['suggested_structure']}")
    if consensus.get("rationale"):
        st.write(consensus["rationale"])


def _render_hard_rules(data: dict) -> None:
    gate = data.get("hard_rules") or (data.get("consensus") or {}).get("hard_rules") or {}
    if not gate:
        return
    st.subheader("Hard Rules")
    cols = st.columns(3)
    cols[0].metric("Decision", str(gate.get("decision", "-")).upper())
    cols[1].metric("Trade Allowed", str(gate.get("trade_allowed", "-")))
    cols[2].metric("Size", f"x{gate.get('position_size_multiplier', 0):.2f}")
    st.write(gate.get("summary", ""))
    if gate.get("hard_blocks"):
        st.error("\n".join(f"- {x}" for x in gate["hard_blocks"]))
    if gate.get("adjustments"):
        st.warning("\n".join(f"- {x}" for x in gate["adjustments"]))
    if gate.get("notes"):
        with st.expander("Gate Notes"):
            for note in gate["notes"]:
                st.write(f"- {note}")


def _render_events(data: dict) -> None:
    events = data.get("events") or []
    if not events:
        return
    summary = data.get("event_summary") or {}
    st.subheader("Scheduled Events")
    st.metric("Event Risk Score", summary.get("event_risk_score", 0))
    st.dataframe(
        [
            {
                "date": e.get("date"),
                "days": e.get("days_away"),
                "name": e.get("name"),
                "importance": e.get("importance"),
                "rule": e.get("rule_action"),
                "risk": e.get("risk"),
            }
            for e in events
        ],
        use_container_width=True,
        hide_index=True,
    )


def _render_quant(data: dict) -> None:
    quant = data.get("quant")
    if not quant:
        return
    st.subheader("Quant Ticket")
    cols = st.columns(3)
    cols[0].metric("Stance", str(quant.get("stance", "-")).upper())
    cols[1].metric("Confidence", _pct(quant.get("confidence")))
    cols[2].metric("Structure", quant.get("pattern", "-"))
    st.write(quant.get("summary", ""))
    for obs in quant.get("observations") or []:
        st.write(f"- {obs}")


def _render_analysts(data: dict) -> None:
    st.subheader("Analysts")
    rounds = {"Round 1": data.get("round1") or [], "Round 2": data.get("round2") or []}
    tabs = st.tabs(list(rounds))
    for tab, (label, views) in zip(tabs, rounds.items()):
        with tab:
            for view in views:
                with st.expander(
                    f"{view.get('analyst')} | {str(view.get('stance', '')).upper()} | {_pct(view.get('confidence'))}"
                ):
                    st.write(view.get("summary", ""))
                    if view.get("pattern"):
                        st.caption(f"Pattern: {view['pattern']}")
                    for obs in view.get("observations") or []:
                        st.write(f"- {obs}")


def main() -> None:
    st.set_page_config(page_title="Agent Swarm Dashboard", layout="wide")
    st.title("Agent Swarm Dashboard")

    reports = _load_reports()
    if not reports:
        st.info("No saved JSON reports found in data_cache/. Run the swarm first.")
        return

    labels = [p.name for p in reports]
    selected = st.sidebar.selectbox("Saved report", labels)
    path = reports[labels.index(selected)]
    data = _load_json(path)

    st.sidebar.caption(str(path))
    _metric_row(data)
    _render_consensus(data)
    _render_hard_rules(data)
    _render_events(data)
    _render_quant(data)
    _render_analysts(data)


if __name__ == "__main__":
    main()
