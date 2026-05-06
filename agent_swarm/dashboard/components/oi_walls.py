"""Open-interest walls visualization — call wall / put wall / max pain per expiry.

Renders the deterministic OI levels carried in `options_summary.oi_levels`
(populated by core.oi_levels.compute_oi_levels). No fetch — pure display.
"""
from __future__ import annotations

import streamlit as st


def render(data: dict) -> None:
    options_summary = data.get("options_summary") or {}
    levels = options_summary.get("oi_levels") or []
    if not levels:
        st.caption("No OI levels saved with this run (run with `--with-options` to populate).")
        return

    st.markdown("##### OI walls per expiry")
    cols = st.columns(min(len(levels), 3))
    for i, lvl in enumerate(levels[:3]):
        col = cols[i % len(cols)]
        with col:
            expiry = lvl.get("expiry", "?")
            dte = lvl.get("dte")
            cw = lvl.get("call_wall")
            pw = lvl.get("put_wall")
            mp = lvl.get("max_pain")
            total = lvl.get("total_oi") or lvl.get("oi_total") or 0

            st.markdown(f"**{expiry}**  ·  {dte} DTE  ·  {total:,} OI" if dte is not None else f"**{expiry}** · {total:,} OI")
            metric_cols = st.columns(3)
            metric_cols[0].metric("Call wall", cw if cw is not None else "—")
            metric_cols[1].metric("Put wall", pw if pw is not None else "—")
            metric_cols[2].metric("Max pain", mp if mp is not None else "—")

    # IV term structure as a quick second view
    atm_iv = options_summary.get("atm_iv_by_expiry") or {}
    if atm_iv:
        st.markdown("##### ATM implied vol by expiry")
        rows = sorted(atm_iv.items())
        st.dataframe(
            [{"expiry": e, "atm_iv_%": round(float(v) * 100, 1)} for e, v in rows],
            use_container_width=True, hide_index=True,
        )
