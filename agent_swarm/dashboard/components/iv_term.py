"""IV term-structure & skew visualization."""
from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go


def render(data: dict) -> None:
    options_summary = data.get("options_summary") or {}
    atm_iv = options_summary.get("atm_iv_by_expiry") or {}
    skew = options_summary.get("skew_by_expiry") or {}
    if not atm_iv and not skew:
        return

    fig = go.Figure()
    if atm_iv:
        x = sorted(atm_iv.keys())
        y = [float(atm_iv[k]) * 100 for k in x]
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", name="ATM IV %",
            line=dict(color="#2563eb", width=2),
            marker=dict(size=8),
        ))
    if skew:
        x = sorted(skew.keys())
        y = [float(skew[k]) * 100 for k in x]
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", name="25Δ skew (P-C, %)",
            line=dict(color="#ef4444", width=2, dash="dot"),
            marker=dict(size=8),
            yaxis="y2",
        ))

    fig.update_layout(
        height=320,
        margin=dict(t=20, l=20, r=20, b=20),
        xaxis=dict(title="Expiry"),
        yaxis=dict(title="ATM IV (%)", side="left"),
        yaxis2=dict(title="25Δ skew (%)", overlaying="y", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    spread = options_summary.get("iv_rv_spread")
    rv30 = options_summary.get("realized_vol_30d")
    cap = []
    if rv30 is not None:
        cap.append(f"30d realized vol: {rv30 * 100:.1f}%")
    if spread is not None:
        cap.append(f"IV-RV spread: {spread * 100:+.1f} pts")
    if cap:
        st.caption("  ·  ".join(cap))
    st.plotly_chart(fig, use_container_width=True)
