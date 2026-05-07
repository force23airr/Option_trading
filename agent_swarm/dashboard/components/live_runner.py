"""Live ticker → swarm runner. Runs the swarm in a subprocess and tails output.

Long-running (30s–3min). Streamlit's execution model makes synchronous spawn
awkward, so we shell out to the existing CLI entry point and read stdout
incrementally.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _build_command(form: dict) -> list[str]:
    cmd = [
        sys.executable, "-m", "agent_swarm.tools.run_swarm",
        form["ticker"].upper(),
        "--days", str(form["days"]),
    ]
    if form["with_options"]:
        cmd.append("--with-options")
    if form["with_events"]:
        cmd.append("--with-events")
    if form["with_rates"]:
        cmd.append("--with-rates")
    if form["with_news"]:
        cmd.append("--with-news")
    if form["account_size"]:
        cmd.extend(["--account-size", str(form["account_size"])])
    if form["max_loss_pct"]:
        cmd.extend(["--max-loss-pct", str(form["max_loss_pct"])])
    return cmd


def render() -> None:
    st.markdown(
        """
        <style>
          .live-form input, .live-form select { font-family: monospace !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("##### NEW RUN — enter a symbol, hit GO")

    with st.form("new_run_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([2, 1, 1])
        ticker = c1.text_input("TICKER", value="AAPL", max_chars=8,
                               help="Any equity symbol — AAPL, NVDA, COIN, TDC...").strip().upper()
        days = c2.number_input("DAYS", min_value=30, max_value=1825, value=365, step=30)
        account_size = c3.number_input("ACCOUNT $", min_value=0, value=25000, step=1000)

        c4, c5, c6, c7 = st.columns(4)
        with_options = c4.checkbox("with-options", value=True, help="OPRA chain + Quant Strategist")
        with_events = c5.checkbox("with-events", value=True, help="scheduled events + Events Analyst")
        with_rates = c6.checkbox("with-rates", value=True, help="Treasury yield curve + Macro Rates")
        with_news = c7.checkbox("with-news", value=True, help="headlines + filings + News Analyst")

        c8, _ = st.columns([1, 3])
        max_loss_pct = c8.number_input("MAX LOSS %", min_value=0.001, max_value=0.5,
                                       value=0.02, step=0.005, format="%.3f",
                                       help="reject trades whose max loss exceeds this fraction of account")

        go = st.form_submit_button("▶  RUN SWARM", type="primary", use_container_width=True)

    if not go:
        return

    if not ticker:
        st.error("Enter a ticker.")
        return

    form = {
        "ticker": ticker, "days": int(days), "account_size": float(account_size),
        "with_options": with_options, "with_events": with_events,
        "with_rates": with_rates, "with_news": with_news,
        "max_loss_pct": float(max_loss_pct),
    }
    cmd = _build_command(form)

    st.markdown("##### LIVE LOG")
    cmd_str = " ".join(cmd)
    st.code(cmd_str, language="bash")
    log_box = st.empty()
    status = st.empty()

    env = os.environ.copy()
    # Use the example calendar by default if user hasn't set their own
    env.setdefault("SWARM_EVENTS_CALENDAR",
                   str(PROJECT_ROOT / "docs" / "reference" / "events-calendar.example.json"))

    started = time.time()
    status.info(f"⏳ running... (started {time.strftime('%H:%M:%S')})")
    proc = subprocess.Popen(
        cmd, cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, env=env,
    )

    lines: list[str] = []
    try:
        for raw in proc.stdout:
            lines.append(raw.rstrip())
            # Keep last 200 lines so the box doesn't get unwieldy
            if len(lines) > 200:
                del lines[: len(lines) - 200]
            log_box.code("\n".join(lines), language="text")
    finally:
        rc = proc.wait()

    elapsed = time.time() - started
    if rc == 0:
        status.success(f"✓ DONE in {elapsed:.0f}s — switch to Run Detail page (newest run is auto-selected)")
        st.balloons()
    else:
        status.error(f"✗ swarm exited rc={rc} after {elapsed:.0f}s")
