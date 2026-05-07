"""WHY rationale panel — synthesizes the run JSON into a readable narrative.

Renders directly under the disposition banner so the user can see *why* the
swarm landed where it did without expanding TRANSCRIPTS or hunting through
analyst cards. All content is derived from data already in the run JSON
(consensus headline/rationale/agreements/disagreements, quant observations,
hard_rules metrics, event_summary). No model calls, no extra fetches.
"""
from __future__ import annotations

import re
from typing import Iterable

import streamlit as st


def _budget_section(metrics: dict, quant_summary: str) -> str | None:
    """Compare ticket cost to the user's session-level budget. Returns
    a section HTML string, or None when no budget is set."""
    budget = float(st.session_state.get("user_budget", 0) or 0)
    if budget <= 0:
        return None
    ticket_cost = metrics.get("ticket_cost_dollars") or metrics.get("max_loss_dollars")
    if ticket_cost is None:
        # No quant ticket — but still tell the user the budget is active
        body = (
            f"<span style='color:#7d8590;'>Budget active: "
            f"<b style='color:#58a6ff;'>${budget:,.0f}</b>/contract — "
            f"no quant ticket on this run to compare.</span>"
        )
        return _section("Budget check", body, accent="#58a6ff")
    ticket_cost = float(ticket_cost)
    over = ticket_cost > budget
    if over:
        body = (
            f"<span style='color:#ef4444;font-weight:600;'>✗ OVER BUDGET</span> &nbsp;·&nbsp; "
            f"ticket cost <b>${ticket_cost:,.0f}</b> exceeds your "
            f"<b>${budget:,.0f}</b> per-trade cap "
            f"(by ${ticket_cost - budget:,.0f}, "
            f"{100*(ticket_cost - budget)/budget:.0f}% over).<br/>"
            f"<span style='color:#7d8590;font-size:0.82rem;'>"
            f"No trade for this stock at your preferences. Raise the budget or skip it.</span>"
        )
        accent = "#ef4444"
    else:
        room = budget - ticket_cost
        body = (
            f"<span style='color:#10b981;font-weight:600;'>✓ FITS BUDGET</span> &nbsp;·&nbsp; "
            f"ticket cost <b>${ticket_cost:,.0f}</b> ≤ your "
            f"<b>${budget:,.0f}</b> cap "
            f"(${room:,.0f} of headroom)."
        )
        accent = "#10b981"
    return _section("Budget check", body, accent=accent)


def _section(label: str, body_html: str, accent: str = "#10b981") -> str:
    return (
        f'<div style="display:grid;grid-template-columns:160px 1fr;gap:14px;'
        f'padding:8px 0;border-top:1px dashed #1f2937;">'
        f'<div style="color:{accent};font-size:0.78rem;letter-spacing:0.08em;'
        f'text-transform:uppercase;font-weight:600;padding-top:2px;">{label}</div>'
        f'<div style="color:#d6deeb;font-size:0.88rem;line-height:1.55;">'
        f'{body_html}</div></div>'
    )


def _bullets(items: Iterable[str], cap: int = 4) -> str:
    items = [i.strip() for i in items if i and str(i).strip()]
    if not items:
        return '<span style="color:#7d8590;">—</span>'
    cut = items[:cap]
    return "<ul style='margin:0;padding-left:18px;'>" + "".join(
        f"<li style='margin-bottom:3px;'>{i}</li>" for i in cut
    ) + "</ul>"


def _pick_obs(observations: list[str], keys: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for o in observations or []:
        low = o.lower()
        if any(k in low for k in keys):
            out.append(o)
    return out


def _format_money(x: float | None) -> str:
    if x is None:
        return "—"
    return f"${x:,.0f}"


def _greeks_line(observations: list[str]) -> str:
    """Pull the per-greek observations and compress to one line."""
    pieces: list[str] = []
    pat = re.compile(r"(net_delta|net_vega|net_theta_per_day|POP estimate|Max loss|Max profit|Cash flow|Breakevens)\s*[:=]\s*(.+)")
    for o in observations or []:
        m = pat.search(o)
        if not m:
            continue
        label, val = m.group(1), m.group(2).strip().rstrip(".,")
        # Shorten the labels
        label = (label.replace("net_theta_per_day", "θ/day")
                      .replace("net_delta", "Δ")
                      .replace("net_vega", "vega")
                      .replace("POP estimate", "POP")
                      .replace("Cash flow", "credit"))
        pieces.append(f"<b>{label}</b> {val}")
    return " &nbsp;·&nbsp; ".join(pieces) if pieces else ""


def render(data: dict) -> None:
    consensus = data.get("consensus") or {}
    quant = data.get("quant") or {}
    hard_rules = data.get("hard_rules") or {}
    metrics = hard_rules.get("metrics") or {}
    event_summary = data.get("event_summary") or {}

    headline = consensus.get("headline") or "—"
    rationale = consensus.get("rationale") or ""
    agreements = consensus.get("agreements") or []
    disagreements = consensus.get("disagreements") or []
    structure = consensus.get("suggested_structure") or quant.get("pattern") or "—"
    horizon = consensus.get("horizon") or quant.get("horizon") or "—"

    # Build sections
    sections: list[str] = []

    # 1. THESIS — headline + rationale
    thesis_html = f"<div style='font-weight:600;margin-bottom:4px;'>{headline}</div>"
    if rationale:
        thesis_html += f"<div style='color:#a3aab8;font-size:0.82rem;'>{rationale}</div>"
    sections.append(_section("Thesis", thesis_html))

    # 2. KEY DRIVERS — agreements
    sections.append(_section("Key drivers", _bullets(agreements, cap=4)))

    # 3. RISKS / DISSENTS — disagreements + any hard_rules adjustments
    risks: list[str] = list(disagreements)
    for adj in hard_rules.get("adjustments") or []:
        risks.append(f"Gate adjustment: {adj}")
    for note in hard_rules.get("notes") or []:
        risks.append(f"Note: {note}")
    sections.append(_section("Risks / dissents", _bullets(risks, cap=4), accent="#f59e0b"))

    # 4. TICKET LOGIC — structure + greeks + max loss in dollars
    if quant:
        greeks = _greeks_line(quant.get("observations") or [])
        max_loss_dollars = metrics.get("max_loss_dollars")
        max_allowed = metrics.get("max_allowed_loss_dollars")
        risk_line = ""
        if max_loss_dollars is not None:
            risk_line = (
                f"<div style='color:#a3aab8;font-size:0.82rem;margin-top:4px;'>"
                f"Risk: <b>{_format_money(max_loss_dollars)}</b> max loss"
            )
            if max_allowed:
                pct = 100.0 * max_loss_dollars / max_allowed if max_allowed else 0
                risk_line += f" ({pct:.0f}% of {_format_money(max_allowed)} cap)"
            risk_line += f" &nbsp;·&nbsp; horizon <b>{horizon}</b></div>"

        ticket_html = (
            f"<div style='font-weight:600;'>{structure}</div>"
            + (f"<div style='color:#b6e5d0;font-size:0.82rem;margin-top:4px;'>{greeks}</div>" if greeks else "")
            + risk_line
        )
        sections.append(_section("Ticket logic", ticket_html, accent="#58a6ff"))

    # 4b. BUDGET CHECK — only when the user has set a per-trade budget
    budget_html = _budget_section(metrics, quant.get("summary") or "")
    if budget_html:
        sections.append(budget_html)

    # 5. EVENTS IN WINDOW — only if there are events
    events = event_summary.get("events") or []
    if events:
        ev_lines: list[str] = []
        for e in events[:3]:
            name = e.get("name", "?")
            days = e.get("days_away")
            risk = e.get("risk", "")
            action = e.get("rule_action") or "monitor"
            day_txt = f"in {days}d" if isinstance(days, int) else (e.get("date") or "")
            ev_lines.append(
                f"<b>{name}</b> ({day_txt}) — {risk} "
                f"<span style='color:#7d8590;'>[{action}]</span>"
            )
        score = event_summary.get("event_risk_score")
        score_chip = (
            f"<div style='color:#a3aab8;font-size:0.78rem;margin-top:4px;'>"
            f"Event risk score: <b>{score}</b></div>" if score is not None else ""
        )
        sections.append(
            _section(
                "Events in window",
                _bullets(ev_lines, cap=3) + score_chip,
                accent="#f59e0b",
            )
        )

    # Wrap everything in a single bordered card
    inner = "".join(sections)
    st.markdown(
        f"""
        <div style="border:1px solid #1f2937;background:#0e131a;
                    padding:10px 16px 14px 16px;margin-bottom:14px;
                    font-family:monospace;">
          <div style="color:#7d8590;font-size:0.78rem;letter-spacing:0.1em;
                      padding-bottom:6px;">── WHY THIS DISPOSITION ──</div>
          {inner}
        </div>
        """,
        unsafe_allow_html=True,
    )
