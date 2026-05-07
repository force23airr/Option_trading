"""Cross-run aggregations — gate firing frequency + run history table."""
from __future__ import annotations

from collections import Counter
from datetime import datetime

import streamlit as st
import plotly.graph_objects as go

from agent_swarm.dashboard.components import data_loader


def _decision_color(d: str) -> str:
    d = (d or "").lower()
    return {
        "approve": "#10b981",
        "reject": "#ef4444",
        "approve_with_reduced_size": "#f59e0b",
    }.get(d, "#6b7280")


_DECISION_BADGE = {
    "approve": ("✓", "#10b981"),
    "approve_with_reduced_size": ("~", "#f59e0b"),
    "reject": ("✗", "#ef4444"),
    "not_evaluated": ("·", "#6b7280"),
}


def _stance_color(stance: str) -> str:
    s = (stance or "").lower()
    if "bull" in s:
        return "#10b981"
    if "bear" in s:
        return "#ef4444"
    return "#7d8590"


def render_history_table(runs_meta: list[dict]) -> None:
    """Custom row renderer with a SELECT button per run.

    Clicking SELECT writes the chosen run path to st.session_state and
    triggers a rerun so the History page can show the action panel above.
    """
    if not runs_meta:
        st.caption("No saved runs yet.")
        return

    # Header row
    h = st.columns([0.7, 0.9, 1.5, 1.0, 0.9, 1.4, 2.0])
    h[0].markdown("**SELECT**")
    h[1].markdown("**TICKER**")
    h[2].markdown("**WHEN**")
    h[3].markdown("**CONSENSUS**")
    h[4].markdown("**DECISION**")
    h[5].markdown("**STRUCTURE**")
    h[6].markdown("**BLOCKS**")
    st.markdown("<hr style='margin:4px 0;border-color:#1f2937;' />", unsafe_allow_html=True)

    selected_path = st.session_state.get("selected_run_path")

    for meta in runs_meta:
        try:
            data = data_loader.load_run(meta["path"])
        except Exception:
            continue
        gate = data.get("hard_rules") or (data.get("consensus") or {}).get("hard_rules") or {}
        consensus = data.get("consensus") or {}
        decision = str(gate.get("decision") or "—").lower()
        badge_char, badge_color = _DECISION_BADGE.get(decision, ("·", "#6b7280"))
        stance = str(consensus.get("consensus_stance") or "—").upper()
        stance_color = _stance_color(stance)
        conf = (consensus.get("consensus_confidence") or 0) * 100
        size_mult = gate.get("position_size_multiplier") or 0
        blocks = ", ".join(gate.get("hard_blocks") or []) or "—"

        is_selected = selected_path == str(meta["path"])
        cols = st.columns([0.7, 0.9, 1.5, 1.0, 0.9, 1.4, 2.0])

        # SELECT button — keyed by path so each row is unique
        btn_label = "▶ SELECTED" if is_selected else "▶ SELECT"
        if cols[0].button(btn_label, key=f"select::{meta['path']}", use_container_width=True):
            if is_selected:
                st.session_state.pop("selected_run_path", None)
            else:
                st.session_state["selected_run_path"] = str(meta["path"])
            st.rerun()

        cols[1].markdown(f"**{meta['ticker']}**")
        cols[2].caption(meta["timestamp"].strftime("%Y-%m-%d %H:%M"))
        cols[3].markdown(
            f"<span style='color:{stance_color};font-weight:600;'>{stance}</span> "
            f"<span style='color:#7d8590;font-size:0.85rem;'>{conf:.0f}%</span>",
            unsafe_allow_html=True,
        )
        decision_text = decision.upper() + (f" x{size_mult:.2f}" if 0 < size_mult < 1 else "")
        cols[4].markdown(
            f"<span style='color:{badge_color};font-weight:600;'>"
            f"{badge_char} {decision_text}</span>",
            unsafe_allow_html=True,
        )
        cols[5].caption(meta["structure"])
        cols[6].caption(blocks if len(blocks) <= 80 else blocks[:77] + "…")


def render_gate_firing(runs_meta: list[dict], top_n: int = 10) -> None:
    if not runs_meta:
        return

    block_counter: Counter[str] = Counter()
    decision_counter: Counter[str] = Counter()
    total = 0
    for meta in runs_meta:
        try:
            data = data_loader.load_run(meta["path"])
        except Exception:
            continue
        total += 1
        gate = data.get("hard_rules") or (data.get("consensus") or {}).get("hard_rules") or {}
        decision_counter[str(gate.get("decision", "—")).lower()] += 1
        for b in gate.get("hard_blocks") or []:
            # Truncate dynamic numbers to bucket repeated rules
            short = b.split(" exceeds")[0] if "exceeds" in b else b.split(":")[0]
            short = short.split("(")[0].strip()
            block_counter[short[:60]] += 1

    if total == 0:
        return

    cols = st.columns(2)
    with cols[0]:
        st.markdown("##### Decisions across runs")
        labels = list(decision_counter.keys())
        values = [decision_counter[k] for k in labels]
        colors = [_decision_color(k) for k in labels]
        fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors))
        fig.update_layout(
            height=280, margin=dict(t=10, l=20, r=20, b=20),
            xaxis_title=None, yaxis_title="runs",
            template="plotly_dark",
            plot_bgcolor="#0b0f14", paper_bgcolor="#0b0f14",
            font=dict(family="monospace", color="#d6deeb", size=11),
        )
        st.plotly_chart(fig, use_container_width=True)

    with cols[1]:
        st.markdown("##### Most frequent hard-rule blocks")
        if not block_counter:
            st.caption("No blocks fired yet — every run was approved.")
            return
        items = block_counter.most_common(top_n)
        fig = go.Figure(go.Bar(
            x=[v for _, v in items],
            y=[k for k, _ in items],
            orientation="h",
            marker_color="#ef4444",
        ))
        fig.update_layout(
            height=max(220, 30 * len(items) + 40),
            margin=dict(t=10, l=20, r=20, b=20),
            xaxis_title="times fired", yaxis_title=None,
            yaxis=dict(autorange="reversed"),
            template="plotly_dark",
            plot_bgcolor="#0b0f14", paper_bgcolor="#0b0f14",
            font=dict(family="monospace", color="#d6deeb", size=11),
        )
        st.plotly_chart(fig, use_container_width=True)
