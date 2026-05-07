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


def render_history_table(runs_meta: list[dict]) -> None:
    if not runs_meta:
        st.caption("No saved runs yet.")
        return

    rows = []
    for meta in runs_meta:
        try:
            data = data_loader.load_run(meta["path"])
        except Exception:
            continue
        gate = data.get("hard_rules") or (data.get("consensus") or {}).get("hard_rules") or {}
        consensus = data.get("consensus") or {}
        rows.append({
            "ticker": meta["ticker"],
            "when": meta["timestamp"].strftime("%Y-%m-%d %H:%M"),
            "consensus": str(consensus.get("consensus_stance", "—")).upper(),
            "conf": f"{(consensus.get('consensus_confidence') or 0) * 100:.0f}%",
            "decision": str(gate.get("decision", "—")).upper(),
            "size_x": f"x{gate.get('position_size_multiplier', 0):.2f}",
            "structure": meta["structure"],
            "blocks": ", ".join(gate.get("hard_blocks", [])) or "—",
        })
    if not rows:
        st.caption("Could not parse any saved runs.")
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


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
