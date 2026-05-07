"""Candlestick + MA20/MA50 + volume chart, fetched live for the run's ticker."""
from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots


@st.cache_data(show_spinner=False, ttl=600)
def _fetch_ohlcv(ticker: str, days: int):
    from agent_swarm.core import data, signals
    df = signals.add_indicators(data.fetch_ohlcv(ticker, days=days))
    return df


def render(data_dict: dict, days: int = 180) -> None:
    ticker = data_dict.get("ticker")
    if not ticker:
        return

    try:
        df = _fetch_ohlcv(ticker, days)
    except Exception as exc:
        st.warning(f"Could not fetch OHLCV for {ticker}: {exc}")
        return
    if df is None or df.empty:
        st.warning(f"No price data available for {ticker}.")
        return

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.78, 0.22], vertical_spacing=0.03,
        subplot_titles=(None, "Volume"),
    )
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            name="OHLC", showlegend=False,
        ),
        row=1, col=1,
    )
    if "MA20" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["MA20"], name="MA20",
                       line=dict(color="#2563eb", width=1.4)),
            row=1, col=1,
        )
    if "MA50" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["MA50"], name="MA50",
                       line=dict(color="#9333ea", width=1.4)),
            row=1, col=1,
        )

    if "Volume" in df.columns:
        fig.add_trace(
            go.Bar(x=df.index, y=df["Volume"], name="Volume",
                   marker_color="#6b7280", showlegend=False),
            row=2, col=1,
        )

    snap = data_dict.get("snapshot") or {}
    close = snap.get("close")
    if close is not None:
        fig.add_hline(y=float(close), line_dash="dot", line_color="#374151",
                      annotation_text=f"Run close: {close:,.2f}", row=1, col=1)

    fig.update_layout(
        height=520, margin=dict(t=30, l=20, r=20, b=20),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
        plot_bgcolor="#0b0f14", paper_bgcolor="#0b0f14",
        font=dict(family="monospace", color="#d6deeb", size=11),
    )
    st.plotly_chart(fig, use_container_width=True)
