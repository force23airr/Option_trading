"""Per-run action panel: export, broker ticket, raw transcripts.

Shown at the top of the History page when a row's SELECT button is clicked.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import streamlit as st

from agent_swarm.dashboard.components import data_loader


def _ticket_dict(quant: dict) -> dict:
    """Best-effort parse of the Quant Strategist's structured trade ticket."""
    if not quant:
        return {}
    raw = quant.get("raw") or ""
    try:
        # Quant returns a JSON object — find first { ... } block
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(raw[start : end + 1])
            ticket = parsed.get("trade_ticket") or {}
            if isinstance(ticket, dict):
                return ticket
    except Exception:
        pass
    return {}


def _format_csv(meta: dict, data: dict) -> str:
    """Flatten a run into a single-row CSV for Google Sheets."""
    consensus = data.get("consensus") or {}
    quant = data.get("quant") or {}
    gate = data.get("hard_rules") or consensus.get("hard_rules") or {}
    snap = data.get("snapshot") or {}
    summary = data.get("event_summary") or {}

    row = {
        "ticker": meta["ticker"],
        "timestamp": meta["timestamp"].isoformat(),
        "close": snap.get("close"),
        "rsi": snap.get("rsi"),
        "ma20": snap.get("ma20"),
        "ma50": snap.get("ma50"),
        "consensus_stance": consensus.get("consensus_stance"),
        "consensus_confidence": consensus.get("consensus_confidence"),
        "horizon": consensus.get("horizon"),
        "structure": consensus.get("suggested_structure"),
        "headline": consensus.get("headline"),
        "decision": gate.get("decision"),
        "trade_allowed": gate.get("trade_allowed"),
        "size_multiplier": gate.get("position_size_multiplier"),
        "hard_blocks": "; ".join(gate.get("hard_blocks") or []),
        "adjustments": "; ".join(gate.get("adjustments") or []),
        "quant_stance": quant.get("stance"),
        "quant_confidence": quant.get("confidence"),
        "quant_structure": quant.get("pattern"),
        "quant_summary": quant.get("summary"),
        "event_count": summary.get("event_count"),
        "event_risk_score": summary.get("event_risk_score"),
        "nearest_event_days": summary.get("nearest_event_days"),
    }
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    return buf.getvalue()


def _format_markdown(meta: dict, data: dict) -> str:
    """Render the run as Markdown — paste straight into a Google Doc."""
    consensus = data.get("consensus") or {}
    quant = data.get("quant") or {}
    gate = data.get("hard_rules") or consensus.get("hard_rules") or {}
    snap = data.get("snapshot") or {}
    views = data.get("round2") or data.get("round1") or []

    lines = []
    lines.append(f"# {meta['ticker']} — Swarm Analysis")
    lines.append(f"_Run at {meta['timestamp'].isoformat()}_\n")

    lines.append("## Snapshot")
    for k, v in snap.items():
        if isinstance(v, float):
            lines.append(f"- **{k}**: {v:,.2f}")
        else:
            lines.append(f"- **{k}**: {v}")
    lines.append("")

    lines.append("## Consensus")
    lines.append(f"- **Stance**: {str(consensus.get('consensus_stance', '—')).upper()} "
                 f"({(consensus.get('consensus_confidence') or 0) * 100:.0f}%)")
    lines.append(f"- **Horizon**: {consensus.get('horizon', '—')}")
    lines.append(f"- **Structure**: {consensus.get('suggested_structure', '—')}")
    if consensus.get("headline"):
        lines.append(f"\n> {consensus['headline']}")
    if consensus.get("rationale"):
        lines.append(f"\n{consensus['rationale']}")
    lines.append("")

    if gate:
        lines.append("## Hard Rules")
        lines.append(f"- **Decision**: {gate.get('decision', '—')}")
        lines.append(f"- **Trade allowed**: {gate.get('trade_allowed')}")
        lines.append(f"- **Size multiplier**: x{gate.get('position_size_multiplier', 0):.2f}")
        if gate.get("hard_blocks"):
            lines.append("\n**Blocks:**")
            for b in gate["hard_blocks"]:
                lines.append(f"- {b}")
        if gate.get("adjustments"):
            lines.append("\n**Adjustments:**")
            for a in gate["adjustments"]:
                lines.append(f"- {a}")
        lines.append("")

    if quant:
        lines.append("## Quant Strategist")
        lines.append(f"- **Structure**: {quant.get('pattern', '—')}")
        lines.append(f"- **Summary**: {quant.get('summary', '')}")
        for o in quant.get("observations") or []:
            lines.append(f"  - {o}")
        lines.append("")

    if views:
        lines.append("## Analyst Views")
        for v in views:
            lines.append(f"### {v.get('analyst', '?')}  ·  "
                         f"{str(v.get('stance', '—')).upper()} ({(v.get('confidence') or 0) * 100:.0f}%)")
            if v.get("summary"):
                lines.append(v["summary"])
            for o in v.get("observations") or []:
                lines.append(f"- {o}")
            lines.append("")

    return "\n".join(lines)


def _render_export(meta: dict, data: dict) -> None:
    st.markdown("##### EXPORT")
    csv_data = _format_csv(meta, data)
    md_data = _format_markdown(meta, data)
    base = f"{meta['ticker']}_{meta['timestamp'].strftime('%Y%m%d_%H%M')}_swarm"

    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "⤓  CSV (Google Sheets)", data=csv_data,
        file_name=f"{base}.csv", mime="text/csv", use_container_width=True,
    )
    c2.download_button(
        "⤓  Markdown (Google Docs)", data=md_data,
        file_name=f"{base}.md", mime="text/markdown", use_container_width=True,
    )
    c3.download_button(
        "⤓  Raw JSON", data=json.dumps(data, indent=2),
        file_name=f"{base}.json", mime="application/json", use_container_width=True,
    )
    st.caption(
        "CSV opens directly in Google Sheets (File → Import). "
        "Markdown pastes cleanly into a Google Doc with formatting preserved."
    )


def _render_broker_ticket(meta: dict, data: dict) -> None:
    """Render the Quant ticket as a broker-order-entry-style panel."""
    quant = data.get("quant") or {}
    if not quant:
        st.info("No Quant trade ticket — this run did not include `--with-options`.")
        return

    ticket = _ticket_dict(quant)
    if not ticket:
        # Fall back to observations text if structured ticket missing
        st.warning("Could not parse structured trade ticket. Showing observations instead:")
        for o in quant.get("observations") or []:
            st.code(o, language="text")
        return

    structure = ticket.get("structure") or quant.get("pattern", "—")
    expiry = ticket.get("expiry", "—")
    legs = ticket.get("legs") or []
    cash_flow = ticket.get("cash_flow")
    max_profit = ticket.get("max_profit")
    max_loss = ticket.get("max_loss")
    breakevens = ticket.get("breakevens") or []
    pop = ticket.get("pop_estimate_pct")
    net_delta = ticket.get("net_delta")
    net_vega = ticket.get("net_vega")
    net_theta = ticket.get("net_theta_per_day")

    cash_label = "CREDIT" if (cash_flow or 0) > 0 else "DEBIT"
    cash_amt = abs(float(cash_flow or 0))

    st.markdown("##### BROKER ORDER TICKET")
    st.markdown(
        f"""
        <div style="border:1px solid #10b981;padding:12px 16px;background:#11161d;
                    font-family:monospace;color:#d6deeb;">
          <div style="color:#10b981;font-weight:700;letter-spacing:0.06em;
                      border-bottom:1px solid #1f2937;padding-bottom:6px;margin-bottom:8px;">
            ── {meta['ticker']} · {structure} · EXPIRY {expiry} ──
          </div>
        """,
        unsafe_allow_html=True,
    )

    # Legs as a clear buy/sell list
    leg_rows = []
    for leg in legs:
        side = (leg.get("side") or "").upper()
        right = (leg.get("right") or "").upper()
        strike = leg.get("strike")
        action = "BUY" if side == "LONG" else "SELL"
        opt_type = "CALL" if right == "C" else ("PUT" if right == "P" else right)
        try:
            strike_str = f"{float(strike):g}"
        except (TypeError, ValueError):
            strike_str = str(strike)
        mid = leg.get("mid")
        mid_str = f"@ ${float(mid):.2f}" if mid is not None else ""
        leg_rows.append(
            f"  {action:<5}  1 × {meta['ticker']:<6} {expiry}  {strike_str:>7} {opt_type:<4}  {mid_str}"
        )
    legs_block = "\n".join(leg_rows) if leg_rows else "  (no legs)"

    st.code(legs_block, language="text")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(cash_label, f"${cash_amt:.2f}")
    c2.metric("MAX PROFIT", f"${abs(float(max_profit or 0)):.2f}")
    c3.metric("MAX LOSS", f"${abs(float(max_loss or 0)):.2f}")
    if pop is not None:
        c4.metric("POP", f"{float(pop):.0f}%")

    if breakevens:
        be_str = " / ".join(f"${be:g}" if isinstance(be, (int, float)) else str(be)
                            for be in breakevens if be is not None)
        st.caption(f"**Breakevens:** {be_str}")

    greeks = []
    if net_delta is not None:
        greeks.append(f"Δ {float(net_delta):+.3f}")
    if net_vega is not None:
        greeks.append(f"vega {float(net_vega):+.3f}")
    if net_theta is not None:
        greeks.append(f"θ/day {float(net_theta):+.3f}")
    if greeks:
        st.caption("**Net Greeks:**  " + "   ".join(greeks))

    # Limit price guidance
    if cash_flow is not None and legs:
        per_share = abs(float(cash_flow))
        st.caption(
            f"**Limit price guidance:** ${per_share:.2f} per contract "
            f"({cash_label.lower()}) — start at the mid; work toward "
            f"{'the bid' if cash_label == 'CREDIT' else 'the ask'} if not filled."
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # Sizing calc against the gate's account constraints
    gate = data.get("hard_rules") or {}
    metrics = gate.get("metrics") or {}
    account_size = metrics.get("account_size")
    max_loss_pct = metrics.get("max_loss_pct")
    contract_mult = metrics.get("contract_multiplier") or 100
    if account_size and max_loss_pct and max_loss:
        try:
            allowed_dollars = float(account_size) * float(max_loss_pct)
            per_contract_loss = float(max_loss) * float(contract_mult)
            if per_contract_loss > 0:
                qty = int(allowed_dollars // per_contract_loss)
                size_mult = gate.get("position_size_multiplier") or 1.0
                qty_adj = max(0, int(qty * float(size_mult)))
                st.markdown("##### POSITION SIZING")
                st.code(
                    f"  Account                ${float(account_size):>12,.2f}\n"
                    f"  Risk budget per trade  {float(max_loss_pct) * 100:>5.2f}%  "
                    f"(${allowed_dollars:,.2f})\n"
                    f"  Loss per contract      ${per_contract_loss:>12,.2f}\n"
                    f"  Max qty by risk        {qty:>5} contracts\n"
                    f"  Gate size multiplier   x{float(size_mult):>5.2f}\n"
                    f"  ─────────────────────────────────────\n"
                    f"  RECOMMENDED QTY        {qty_adj:>5} contracts",
                    language="text",
                )
        except (TypeError, ValueError):
            pass


def _render_transcripts(data: dict) -> None:
    views = data.get("round2") or data.get("round1") or []
    if not views:
        st.caption("No analyst views in this run.")
        return
    st.markdown("##### ANALYST TRANSCRIPTS")
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


def render(meta: dict, data: dict) -> None:
    st.markdown(
        f"### ▸ ACTIONS — {meta['ticker']}  "
        f"<span style='color:#7d8590;font-size:0.85rem;font-weight:400;'>"
        f"{meta['timestamp'].strftime('%Y-%m-%d %H:%M')}  ·  "
        f"{meta['stance']}  ·  {meta['structure']}</span>",
        unsafe_allow_html=True,
    )
    if st.button("✕  CLOSE", key="close_actions"):
        st.session_state.pop("selected_run_path", None)
        st.rerun()

    tab_export, tab_ticket, tab_transcripts = st.tabs(
        ["EXPORT", "OPTION CONTRACT", "TRANSCRIPTS"]
    )
    with tab_export:
        _render_export(meta, data)
    with tab_ticket:
        _render_broker_ticket(meta, data)
    with tab_transcripts:
        _render_transcripts(data)
