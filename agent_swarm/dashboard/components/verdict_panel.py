"""Top-of-page verdict panel — every analyst at a glance + final disposition."""
from __future__ import annotations

import streamlit as st


def _stance_color(stance: str) -> str:
    s = (stance or "").lower()
    if "bull" in s:
        return "#10b981"  # green
    if "bear" in s:
        return "#ef4444"  # red
    if "caution" in s:
        return "#f59e0b"  # amber
    return "#6b7280"      # grey


def _decision_color(decision: str) -> str:
    d = (decision or "").lower()
    if d == "approve":
        return "#10b981"
    if d == "reject":
        return "#ef4444"
    if d == "approve_with_reduced_size":
        return "#f59e0b"
    return "#6b7280"


def _short_summary(text: str, max_chars: int = 90) -> str:
    if not text:
        return ""
    s = text.strip().split(".")[0].strip()
    return s[: max_chars - 1] + "…" if len(s) > max_chars else s


def render(data: dict) -> None:
    consensus = data.get("consensus") or {}
    quant = data.get("quant") or {}
    gate = data.get("hard_rules") or consensus.get("hard_rules") or {}
    views = data.get("round2") or data.get("round1") or []

    ticker = data.get("ticker", "?")
    stance = str(consensus.get("consensus_stance") or "—").upper()
    conf = consensus.get("consensus_confidence") or 0
    decision = str(gate.get("decision") or "—").upper()
    size_mult = gate.get("position_size_multiplier") or 0
    trade_allowed = gate.get("trade_allowed")

    # Top banner
    if trade_allowed is False:
        banner_text = f"FINAL: trade BLOCKED   — consensus {stance} {conf:.0%}, gate {decision}"
        banner_color = _decision_color("reject")
    elif trade_allowed and size_mult and size_mult < 1.0:
        banner_text = f"FINAL: APPROVED at reduced size   — consensus {stance} {conf:.0%}, size x{size_mult:.2f}"
        banner_color = _decision_color("approve_with_reduced_size")
    elif trade_allowed:
        banner_text = f"FINAL: APPROVED   — consensus {stance} {conf:.0%}"
        banner_color = _decision_color("approve")
    else:
        banner_text = f"FINAL: consensus {stance} {conf:.0%} (no trade ticket)"
        banner_color = "#6b7280"

    st.markdown(
        f"""
        <div style="background:{banner_color};color:#fff;padding:14px 18px;
                    border-radius:8px;font-size:1.15rem;font-weight:600;
                    margin-bottom:14px;">
            <span style="opacity:0.85;font-size:0.9rem;">{ticker}</span>
            <br/>{banner_text}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Analyst grid
    if views:
        st.markdown("##### Analyst verdicts")
        cols = st.columns(2)
        for i, v in enumerate(views):
            col = cols[i % 2]
            stance_v = str(v.get("stance") or "—")
            conf_v = float(v.get("confidence") or 0)
            color = _stance_color(stance_v)
            with col:
                st.markdown(
                    f"""
                    <div style="border-left:4px solid {color};padding:8px 12px;
                                margin-bottom:6px;background:#f9fafb;border-radius:4px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <strong>{v.get('analyst', '?')}</strong>
                            <span style="color:{color};font-weight:600;">
                                {stance_v} · {conf_v:.0%}
                            </span>
                        </div>
                        <div style="color:#374151;font-size:0.88rem;margin-top:4px;">
                            {_short_summary(v.get('summary', ''))}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # Quant + gates
    cols = st.columns(3)
    with cols[0]:
        if quant:
            st.markdown("**Quant Strategist**")
            st.write(quant.get("pattern", "—"))
            for o in quant.get("observations") or []:
                low = o.lower()
                if any(k in low for k in ("net_delta", "net_vega", "max loss", "pop")):
                    st.caption(o)
        else:
            st.markdown("**Quant Strategist** — not run")

    with cols[1]:
        st.markdown("**Reconcile**")
        if consensus.get("conflict_flag"):
            mark = "↻ substituted" if consensus.get("ticket_substituted") else "⚠ flagged"
            st.warning(f"{mark}\n\n{consensus.get('conflict_note', '')}")
        elif quant:
            st.success("✓ aligned with peer consensus")
        else:
            st.caption("not applicable")

    with cols[2]:
        st.markdown("**Hard Rules**")
        if not gate:
            st.caption("not evaluated")
        elif decision == "REJECT":
            st.error(f"✗ REJECT\n\n" + "\n".join(f"• {b}" for b in gate.get("hard_blocks") or []))
        elif decision == "APPROVE":
            st.success("✓ APPROVE")
        elif decision == "APPROVE_WITH_REDUCED_SIZE":
            adj = gate.get("adjustments") or []
            st.warning(f"~ reduce x{size_mult:.2f}\n\n" + "\n".join(f"• {a}" for a in adj))
        else:
            st.caption(decision)
