"""Events timeline — Gantt-style horizontal bars for upcoming scheduled events."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import streamlit as st
import plotly.graph_objects as go


_RULE_COLOR = {
    "reject": "#ef4444",
    "watchlist_only": "#f97316",
    "reduce_size": "#f59e0b",
    "": "#10b981",  # no rule
    None: "#10b981",
}


def render(data: dict) -> None:
    events = data.get("events") or []
    summary = data.get("event_summary") or {}
    if not events:
        st.caption("No scheduled events for this run (use `--with-events`).")
        return

    score = summary.get("event_risk_score", 0)
    nearest = summary.get("nearest_event_days")
    cols = st.columns(3)
    cols[0].metric("Event risk score", score)
    cols[1].metric("Events ahead", summary.get("event_count", len(events)))
    cols[2].metric("Nearest", f"{nearest}d" if nearest is not None else "—")

    today = date.today()
    bars = []
    labels = []
    colors = []
    hovers = []
    for event in events:
        try:
            ed = datetime.fromisoformat(str(event.get("date"))[:10]).date()
        except ValueError:
            continue
        days_away = (ed - today).days
        # Bar from today out to event date — width tells you "time until"
        bars.append((today, ed, days_away))
        labels.append(event.get("name", "?"))
        colors.append(_RULE_COLOR.get(event.get("rule_action"), "#6b7280"))
        hovers.append(
            f"{event.get('name')}<br>"
            f"date: {event.get('date')}<br>"
            f"days_away: {days_away}<br>"
            f"importance: {event.get('importance')}/5<br>"
            f"rule_action: {event.get('rule_action') or '(none)'}<br>"
            f"window: {event.get('action_window_days') or '—'}d"
        )

    if not bars:
        st.caption("Events present but couldn't parse dates.")
        return

    fig = go.Figure()
    for i, (start, end, _days) in enumerate(bars):
        fig.add_trace(go.Bar(
            x=[(end - start).days + 0.5],
            y=[labels[i]],
            base=[(start - today).days],
            orientation="h",
            marker_color=colors[i],
            hovertext=hovers[i],
            hoverinfo="text",
            showlegend=False,
        ))

    fig.update_layout(
        height=max(140, 36 * len(bars) + 60),
        margin=dict(t=20, l=20, r=20, b=20),
        xaxis=dict(title="Days from today", range=[-1, max((end - today).days for _, end, _ in bars) + 2]),
        yaxis=dict(title=None, autorange="reversed"),
        bargap=0.35,
        template="plotly_dark",
        plot_bgcolor="#0b0f14", paper_bgcolor="#0b0f14",
        font=dict(family="monospace", color="#d6deeb", size=11),
    )
    fig.add_vline(x=0, line_color="#374151", line_dash="dot",
                  annotation_text="today", annotation_position="top")
    st.plotly_chart(fig, use_container_width=True)

    # Rule-action legend
    legend_html = (
        '<div style="font-size:0.85rem;color:#374151;">'
        '<span style="color:#10b981;">●</span> none&nbsp;&nbsp;'
        '<span style="color:#f59e0b;">●</span> reduce_size&nbsp;&nbsp;'
        '<span style="color:#f97316;">●</span> watchlist_only&nbsp;&nbsp;'
        '<span style="color:#ef4444;">●</span> reject'
        '</div>'
    )
    st.markdown(legend_html, unsafe_allow_html=True)
