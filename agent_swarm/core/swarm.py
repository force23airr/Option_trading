"""Pattern-analysis swarm.

Architecture:
  1. Build a DataContext (price df + optional chain + macro + news + earnings)
  2. Spawn only analysts whose data dependencies are satisfied
  3. Round 1 — analysts work independently
  4. Round 2 — each analyst sees peer views and refines (debate)
  5. Coordinator (Claude) synthesizes the final call
  6. Quant Strategist (DeepSeek-R1) produces the concrete trade ticket if a
     chain is present

Provider routing:
  - DeepSeek-V3 (deepseek-chat):    Trend, Volume, Volatility, MeanRev, Options
  - DeepSeek-R1 (deepseek-reasoner): Quant Strategist
  - Claude (env default):            Pattern Analyst, Coordinator
"""
from __future__ import annotations

import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from ..analysts import (
    AnalystView,
    BaseAnalyst,
    EventsAnalyst,
    MacroRatesAnalyst,
    MeanReversionAnalyst,
    NewsAnalyst,
    OptionsAnalyst,
    PatternAnalyst,
    QuantStrategist,
    TrendAnalyst,
    VolatilityAnalyst,
    VolumeAnalyst,
)
from ..analysts.options_analyst import summarize_chain
from ..analysts.base import _parse_json_reply
from ..analysts.quant_strategist import build_candidates
from . import black_scholes as bs
from . import data, llm, options as opt, signals
from .context import DataContext
from ..data import edgar_source, events_source, macro_source, news_source, oi_source, opra_source


# Order matters only for display
ALL_ANALYST_CLASSES: list[type[BaseAnalyst]] = [
    TrendAnalyst,
    PatternAnalyst,
    VolumeAnalyst,
    VolatilityAnalyst,
    MeanReversionAnalyst,
    MacroRatesAnalyst,
    EventsAnalyst,
    NewsAnalyst,
    OptionsAnalyst,
]
# Quant Strategist is run separately (single-pass, after the debate)


@dataclass
class SwarmResult:
    ticker: str
    snapshot: dict
    spawned: list[str] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # [{name, reason}]
    round1: list[AnalystView] = field(default_factory=list)
    round2: list[AnalystView] = field(default_factory=list)
    quant: AnalystView | None = None
    hard_rules: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    event_summary: dict | None = None
    options_summary: dict | None = None
    consensus: dict = field(default_factory=dict)


def _run_analyst_view(a: BaseAnalyst, ctx: DataContext, peer_views) -> AnalystView:
    """Dispatch — analysts that need extra context have specialized entry points."""
    if isinstance(a, OptionsAnalyst):
        return a.analyze_with_chain(ctx.ticker, ctx.df, ctx.snap, ctx.chain_summary, peer_views=peer_views)
    if isinstance(a, MacroRatesAnalyst):
        return a.analyze_with_rates(ctx, peer_views=peer_views)
    if isinstance(a, EventsAnalyst):
        return a.analyze_with_events(ctx, peer_views=peer_views)
    if isinstance(a, NewsAnalyst):
        return a.analyze_with_news(ctx, peer_views=peer_views)
    return a.analyze(ctx.ticker, ctx.df, ctx.snap, peer_views=peer_views)


def _run_round(analysts: list[BaseAnalyst], ctx: DataContext, peer_views) -> list[AnalystView]:
    if not analysts:
        return []
    with ThreadPoolExecutor(max_workers=len(analysts)) as ex:
        futs = [ex.submit(_run_analyst_view, a, ctx, peer_views) for a in analysts]
        return [f.result() for f in futs]


_NON_DIRECTIONAL_ANALYSTS = {"Events Analyst"}


def _peer_directional_score(views: list[AnalystView]) -> float:
    """Confidence-weighted directional score over peer analysts.

    +1.0 = strong bullish consensus, -1.0 = strong bearish, 0 = mixed.
    Neutral stances contribute to weight (denominator) but not the score.
    Risk-only analysts (e.g. Events) are excluded — their stance reflects
    event risk, not direction, and would skew the consensus.
    """
    score = 0.0
    weight = 0.0
    for v in views:
        if v.analyst in _NON_DIRECTIONAL_ANALYSTS:
            continue
        c = float(v.confidence or 0)
        if c <= 0:
            continue
        weight += c
        s = (v.stance or "").lower()
        if "bull" in s:
            score += c
        elif "bear" in s:
            score -= c
    return score / weight if weight > 0 else 0.0


def _reconcile_ticket(
    ctx: DataContext,
    peer_views: list[AnalystView],
    quant_view: AnalystView | None,
) -> tuple[AnalystView | None, dict | None]:
    """Hard gate ensuring the Quant ticket's net delta agrees with peer
    directional consensus. If they disagree past thresholds, try to swap to
    a candidate matching the consensus direction with the same vega sign
    (preserving the vol-regime thesis). Otherwise flag the conflict.
    """
    if quant_view is None or not quant_view.raw:
        return quant_view, None
    if ctx.chain_df is None or ctx.chain_df.empty:
        return quant_view, None

    parsed = _parse_json_reply(quant_view.raw)
    ticket = parsed.get("trade_ticket") or {}
    net_delta = ticket.get("net_delta")
    quant_vega = ticket.get("net_vega") or 0
    if net_delta is None:
        return quant_view, None

    score = _peer_directional_score(peer_views)
    bull_consensus = score >= 0.40
    bear_consensus = score <= -0.40
    bull_ticket = float(net_delta) >= 0.05
    bear_ticket = float(net_delta) <= -0.05
    conflict = (bull_consensus and bear_ticket) or (bear_consensus and bull_ticket)
    if not conflict:
        return quant_view, None

    desired_delta_sign = 1 if bull_consensus else -1
    desired_vega_sign = 0 if abs(quant_vega) < 0.001 else (1 if quant_vega > 0 else -1)

    def _finite(*xs) -> bool:
        for x in xs:
            if x is None:
                return False
            try:
                if not math.isfinite(float(x)):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    candidates = build_candidates(ctx.chain_df, spot=ctx.spot)
    eligible = []
    for c in candidates:
        if c.name == quant_view.pattern:
            continue
        # Skip candidates with non-finite financials — typically from deep-OTM
        # legs whose bid/ask is missing, producing NaN mid → NaN credit/max_loss.
        if not _finite(c.net_credit_or_debit, c.max_profit, c.max_loss,
                       c.net_delta, c.net_vega):
            continue
        if c.max_loss <= 0:
            continue
        delta_sign = 0 if abs(c.net_delta) < 0.05 else (1 if c.net_delta > 0 else -1)
        if delta_sign != desired_delta_sign:
            continue
        if desired_vega_sign != 0:
            vega_sign = 0 if abs(c.net_vega) < 0.001 else (1 if c.net_vega > 0 else -1)
            if vega_sign != desired_vega_sign:
                continue
        eligible.append(c)

    original = parsed.get("selected_structure", quant_view.pattern or "?")
    if not eligible:
        return quant_view, {
            "conflict_flag": True,
            "substituted": False,
            "conflict_note": (
                f"Quant ticket '{original}' (net_delta={net_delta:+.3f}) "
                f"contradicts peer consensus (score={score:+.2f}); no candidate "
                f"with matching vega sign found — ticket kept but FLAGGED."
            ),
        }

    best = max(eligible, key=lambda c: (c.reward_to_risk, c.pop_estimate))
    new_view = AnalystView(
        analyst=quant_view.analyst,
        ticker=quant_view.ticker,
        stance="bullish" if desired_delta_sign > 0 else "bearish",
        confidence=quant_view.confidence,
        summary=(
            f"[reconciled] Original pick '{original}' had net_delta={net_delta:+.3f} "
            f"vs peer consensus={score:+.2f}; swapped to {best.name} to align "
            f"direction while preserving vega sign."
        ),
        observations=[
            f"Selected: {best.name}",
            f"Cash flow: ${best.net_credit_or_debit:+.2f}/contract",
            f"Max profit: ${best.max_profit:+.2f}",
            f"Max loss: ${best.max_loss:+.2f}",
            f"Breakevens: [{best.breakeven_lo}, {best.breakeven_hi}]",
            f"POP estimate: {best.pop_estimate * 100:.0f}%",
            f"net_delta: {best.net_delta:+.3f}",
            f"net_vega: {best.net_vega:+.3f}",
            f"net_theta: {best.net_theta:+.3f}",
            f"Reconciliation: replaced original '{original}' due to delta/consensus conflict.",
        ],
        pattern=best.name,
        horizon=quant_view.horizon,
        raw=quant_view.raw,
        provider=quant_view.provider,
        model=quant_view.model,
    )
    return new_view, {
        "conflict_flag": True,
        "substituted": True,
        "original_ticket": original,
        "new_ticket": best.name,
        "peer_score": score,
        "original_net_delta": float(net_delta),
        "new_net_delta": float(best.net_delta),
        "conflict_note": (
            f"Quant chose '{original}' (Δ={net_delta:+.3f}) but peer "
            f"consensus score={score:+.2f}. Auto-substituted to '{best.name}' "
            f"(Δ={best.net_delta:+.3f})."
        ),
    }


COORDINATOR_SYSTEM = (
    "You are the head portfolio manager. You read specialist analyst views and produce a "
    "single consensus call. You are skeptical, you weigh confidence, and you flag when the "
    "team disagrees. You do NOT add new analysis — you synthesize. If a Quant Strategist "
    "produced a concrete trade ticket, anchor your suggested_structure to that ticket."
)


def _coordinator(ctx: DataContext, views: list[AnalystView], quant: AnalystView | None) -> dict:
    views_block = "\n\n".join(
        f"### {v.analyst}  ({v.provider}/{v.model})\n"
        f"stance: {v.stance}  confidence: {v.confidence:.0%}  horizon: {v.horizon}\n"
        f"pattern: {v.pattern or '(none)'}\n"
        f"summary: {v.summary}\n"
        f"observations:\n  - " + "\n  - ".join(v.observations)
        for v in views
    )
    quant_block = ""
    if quant:
        quant_block = (
            f"\n\nQUANT STRATEGIST TRADE TICKET (concrete numbers, do not alter):\n"
            f"  selected: {quant.pattern}\n"
            f"  summary: {quant.summary}\n"
            f"  observations:\n  - " + "\n  - ".join(quant.observations)
        )

    prompt = f"""Ticker: {ctx.ticker}

Indicator snapshot:
{json.dumps(ctx.snap, indent=2, default=str)}

Specialist analyst views (after debate round):
{views_block}
{quant_block}

Produce a single consensus call. Reply with one JSON object and nothing else:
{{
  "consensus_stance": "bullish" | "bearish" | "neutral",
  "consensus_confidence": <float 0.0-1.0>,
  "headline": "<one sentence>",
  "key_patterns": ["<pattern 1>", "..."],
  "agreements": ["<point most analysts agree on>", "..."],
  "disagreements": ["<point analysts split on>", "..."],
  "horizon": "intraday" | "1-5d" | "1-4w" | "longer",
  "suggested_structure": "<copy verbatim from Quant Strategist if present, else short description>",
  "rationale": "<2-3 sentences>"
}}"""
    raw = llm.chat(prompt, system=COORDINATOR_SYSTEM, max_tokens=900, temperature=0.2)
    from ..analysts.base import _parse_json_reply
    return _parse_json_reply(raw) or {"raw": raw}


def _env_float(name: str, default: float | None = None) -> float | None:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _ticket_from_quant(quant_view: AnalystView | None) -> dict:
    if quant_view is None or not quant_view.raw:
        return {}
    parsed = _parse_json_reply(quant_view.raw)
    ticket = parsed.get("trade_ticket")
    return ticket if isinstance(ticket, dict) else {}


def _leg_spread_checks(ctx: DataContext, ticket: dict, max_spread_pct: float) -> tuple[list[dict], list[str]]:
    """Check selected option legs against the live chain's bid/ask width."""
    if ctx.chain_df is None or ctx.chain_df.empty:
        return [], ["option chain unavailable; bid/ask gate skipped"]

    expiry = str(ticket.get("expiry", ""))
    legs = ticket.get("legs") or []
    if not expiry or not legs:
        return [], ["trade ticket missing expiry/legs; bid/ask gate skipped"]

    checks: list[dict] = []
    notes: list[str] = []
    for leg in legs:
        try:
            right = str(leg.get("right", "")).upper()
            strike = float(leg.get("strike"))
        except (TypeError, ValueError):
            notes.append(f"malformed leg skipped: {leg}")
            continue

        rows = ctx.chain_df[
            (ctx.chain_df["right"].astype(str).str.upper() == right)
            & (ctx.chain_df["strike"].astype(float).sub(strike).abs() < 0.0001)
            & (ctx.chain_df["expiry"].astype(str) == expiry)
        ]
        if rows.empty:
            notes.append(f"no quote match for {right} {strike:g} {expiry}; leg spread gate skipped")
            continue

        row = rows.iloc[0]
        bid = float(row.get("bid", float("nan")))
        ask = float(row.get("ask", float("nan")))
        mid = float(row.get("mid", float("nan")))
        if not all(math.isfinite(x) and x > 0 for x in (bid, ask, mid)):
            notes.append(f"bad quote for {right} {strike:g} {expiry}; leg spread gate skipped")
            continue

        spread_pct = (ask - bid) / mid
        checks.append({
            "right": right,
            "strike": strike,
            "expiry": expiry,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread_pct": spread_pct,
            "threshold_pct": max_spread_pct,
            "pass": spread_pct <= max_spread_pct,
        })
    return checks, notes


def _hard_rules_gate(
    ctx: DataContext,
    quant_view: AnalystView | None,
    *,
    account_size: float | None = None,
    max_loss_pct: float | None = None,
    max_bid_ask_spread_pct: float | None = None,
    earnings_reduce_days: int | None = None,
    max_event_risk_score: float | None = None,
    contract_multiplier: float | None = None,
) -> dict:
    """Deterministic post-coordinator risk gate.

    This does not create a trade idea. It only rejects, reduces, or approves the
    existing Quant ticket using rules that should never depend on an LLM.
    """
    account_size = account_size if account_size is not None else _env_float("SWARM_ACCOUNT_SIZE")
    max_loss_pct = max_loss_pct if max_loss_pct is not None else _env_float("SWARM_MAX_LOSS_PCT", 0.02)
    max_bid_ask_spread_pct = (
        max_bid_ask_spread_pct
        if max_bid_ask_spread_pct is not None
        else _env_float("SWARM_MAX_BID_ASK_SPREAD_PCT", 0.15)
    )
    contract_multiplier = (
        contract_multiplier
        if contract_multiplier is not None
        else _env_float("SWARM_OPTION_CONTRACT_MULTIPLIER", 100.0)
    )
    if earnings_reduce_days is None:
        env_val = _env_float("SWARM_EARNINGS_REDUCE_DAYS", 5)
        earnings_reduce_days = int(env_val) if env_val is not None else 5
    if max_event_risk_score is None:
        max_event_risk_score = _env_float("SWARM_MAX_EVENT_RISK_SCORE")

    hard_blocks: list[str] = []
    adjustments: list[str] = []
    notes: list[str] = []
    metrics: dict = {
        "account_size": account_size,
        "max_loss_pct": max_loss_pct,
        "max_bid_ask_spread_pct": max_bid_ask_spread_pct,
        "earnings_reduce_days": earnings_reduce_days,
        "max_event_risk_score": max_event_risk_score,
        "contract_multiplier": contract_multiplier,
    }

    ticket = _ticket_from_quant(quant_view)
    if not ticket:
        return {
            "decision": "not_evaluated",
            "trade_allowed": False,
            "position_size_multiplier": 0.0,
            "summary": "No Quant trade ticket was available for hard-rule gating.",
            "hard_blocks": ["missing quant trade ticket"],
            "adjustments": [],
            "notes": [],
            "metrics": metrics,
        }

    max_loss = ticket.get("max_loss")
    try:
        max_loss = abs(float(max_loss))
    except (TypeError, ValueError):
        max_loss = None
    metrics["ticket_max_loss"] = max_loss

    if max_loss is None or not math.isfinite(max_loss) or max_loss <= 0:
        hard_blocks.append("trade ticket max_loss missing or invalid")
    elif account_size and max_loss_pct and contract_multiplier:
        max_loss_dollars = max_loss * contract_multiplier
        max_allowed_dollars = account_size * max_loss_pct
        metrics["max_loss_dollars"] = max_loss_dollars
        metrics["max_allowed_loss_dollars"] = max_allowed_dollars
        if max_loss_dollars > max_allowed_dollars:
            hard_blocks.append(
                f"max loss ${max_loss_dollars:,.2f} exceeds "
                f"{max_loss_pct:.1%} account cap (${max_allowed_dollars:,.2f})"
            )
    else:
        notes.append("account_size not set; account-loss cap skipped")

    if max_bid_ask_spread_pct is not None:
        leg_checks, leg_notes = _leg_spread_checks(ctx, ticket, max_bid_ask_spread_pct)
        metrics["leg_spread_checks"] = leg_checks
        notes.extend(leg_notes)
        failed_legs = [c for c in leg_checks if not c["pass"]]
        if failed_legs:
            worst = max(failed_legs, key=lambda c: c["spread_pct"])
            hard_blocks.append(
                f"option leg spread {worst['spread_pct']:.1%} exceeds "
                f"{max_bid_ask_spread_pct:.1%} cap on {worst['right']} {worst['strike']:g}"
            )

    if ctx.earnings_date:
        days_to_earnings = (ctx.earnings_date - date.today()).days
        metrics["days_to_earnings"] = days_to_earnings
        if 0 <= days_to_earnings < earnings_reduce_days:
            adjustments.append(
                f"earnings in {days_to_earnings} day(s); reduce size by 50%"
            )
    else:
        notes.append("earnings_date unavailable; earnings proximity gate skipped")

    event_summary = ctx.event_summary or {}
    if event_summary:
        score = event_summary.get("event_risk_score", 0) or 0
        metrics["event_risk_score"] = score
        metrics["nearest_event_days"] = event_summary.get("nearest_event_days")
        metrics["event_rule_actions"] = event_summary.get("rule_actions", [])
        for action in event_summary.get("rule_actions", []):
            name = action.get("name", "scheduled event")
            days = action.get("days_away", "?")
            kind = action.get("action")
            if kind == "reject":
                hard_blocks.append(f"{name} in {days} day(s) has rule_action=reject")
            elif kind == "watchlist_only":
                hard_blocks.append(f"{name} in {days} day(s) has rule_action=watchlist_only")
            elif kind == "reduce_size":
                adjustments.append(f"{name} in {days} day(s); reduce size by 50%")
        if max_event_risk_score is not None and score > max_event_risk_score:
            hard_blocks.append(
                f"event risk score {score} exceeds cap {max_event_risk_score:g}"
            )
    else:
        notes.append("event_summary unavailable; scheduled-event gate skipped")

    if hard_blocks:
        decision = "reject"
        trade_allowed = False
        position_size_multiplier = 0.0
    elif adjustments:
        decision = "approve_with_reduced_size"
        trade_allowed = True
        position_size_multiplier = 0.5
    else:
        decision = "approve"
        trade_allowed = True
        position_size_multiplier = 1.0

    if hard_blocks:
        summary = "Rejected by hard rules: " + "; ".join(hard_blocks)
    elif adjustments:
        summary = "Approved with reduced size: " + "; ".join(adjustments)
    else:
        summary = "Approved by hard rules."

    return {
        "decision": decision,
        "trade_allowed": trade_allowed,
        "position_size_multiplier": position_size_multiplier,
        "summary": summary,
        "hard_blocks": hard_blocks,
        "adjustments": adjustments,
        "notes": notes,
        "metrics": metrics,
    }


def _build_context(
    ticker: str,
    days: int,
    with_options: bool,
    with_rates: bool,
    with_news: bool,
    with_events: bool,
    emit,
) -> DataContext:
    emit("data:start", ticker=ticker, days=days)
    df = signals.add_indicators(data.fetch_ohlcv(ticker, days=days))
    if df.empty:
        raise RuntimeError(f"no data for {ticker}")
    snap = signals.snapshot(df)
    emit("data:done", bars=len(df), snapshot=snap)

    ctx = DataContext(ticker=ticker, df=df, snap=snap, spot=float(df["Close"].iloc[-1]))
    ctx.rv30 = bs.realized_vol(df["Close"], window=30)
    ctx.rv60 = bs.realized_vol(df["Close"], window=60)

    if with_options:
        emit("options:start", ticker=ticker)
        try:
            quotes = opra_source.fetch_quotes(ticker, days=1)
            # Pin OI fetch to the actual trade date in the quote feed (avoids
            # UTC midnight skew that can land OI requests on dates with no data)
            trade_date = None
            if not quotes.empty:
                try:
                    trade_date = quotes.index.max().date()
                except Exception:
                    trade_date = None
            oi_df = oi_source.fetch_oi_volume(ticker, trade_date=trade_date)
            chain = opt.build_chain(quotes, spot=ctx.spot, oi_df=oi_df)
            if not chain.empty:
                ctx.chain_df = chain
                ctx.chain_summary = summarize_chain(chain, ctx.spot, ctx.rv30, ctx.rv60)
                top_oi_total = sum(lvl.get("total_oi", 0) for lvl in ctx.chain_summary.oi_levels)
                emit("options:done",
                     contracts=len(chain),
                     iv_rv_spread=ctx.chain_summary.iv_rv_spread,
                     top_oi_total=top_oi_total,
                     oi_levels=ctx.chain_summary.oi_levels)
            else:
                emit("options:empty")
        except Exception as exc:
            emit("options:error", error=str(exc))

    if with_rates:
        emit("rates:start")
        try:
            curve = macro_source.fetch_yield_curve()
            if not curve.empty:
                ctx.yield_curve = curve
                ctx.yield_summary = macro_source.yield_curve_summary(curve)
                emit("rates:done", summary=ctx.yield_summary)
            else:
                emit("rates:empty")
        except Exception as exc:
            emit("rates:error", error=str(exc))

    if with_news:
        emit("news:start", ticker=ticker)
        try:
            headlines = news_source.fetch_news(ticker, limit=25)
            filings = edgar_source.fetch_recent_filings(ticker, days=90, limit=10)
            # EDGAR first — primary-source filings outrank syndicated headlines
            ctx.news = filings + headlines
            ctx.earnings_date = news_source.fetch_earnings_date(ticker)
            if ctx.news:
                emit("news:done",
                     count=len(ctx.news),
                     headlines=len(headlines),
                     filings=len(filings),
                     earnings_date=ctx.earnings_date)
            else:
                emit("news:empty")
        except Exception as exc:
            emit("news:error", error=str(exc))

    if with_events:
        emit("events:start", ticker=ticker)
        try:
            ctx.events = events_source.fetch_events(ticker, lookahead_days=30)
            ctx.event_summary = events_source.summarize_events(ctx.events)
            if ctx.events:
                emit("events:done", count=len(ctx.events), summary=ctx.event_summary)
            else:
                emit("events:empty")
        except Exception as exc:
            emit("events:error", error=str(exc))

    return ctx


def run(
    ticker: str,
    days: int = 180,
    analyst_classes: list[type[BaseAnalyst]] | None = None,
    do_debate: bool = True,
    with_options: bool = False,
    with_rates: bool = False,
    with_news: bool = False,
    with_events: bool = False,
    with_quant: bool = True,
    deep: bool = False,
    account_size: float | None = None,
    max_loss_pct: float | None = None,
    max_bid_ask_spread_pct: float | None = None,
    earnings_reduce_days: int | None = None,
    max_event_risk_score: float | None = None,
    on_event=None,
) -> SwarmResult:
    """Run the swarm.

    Spawning is conditional — analysts whose data isn't present are skipped.
    The Quant Strategist runs once (single-pass) after the debate, using
    DeepSeek-R1 reasoning to produce a concrete trade ticket.
    """
    def emit(et, **payload):
        if on_event:
            on_event(et, payload)

    ctx = _build_context(ticker, days, with_options, with_rates, with_news, with_events, emit)

    classes = analyst_classes or ALL_ANALYST_CLASSES
    spawned: list[BaseAnalyst] = []
    skipped: list[dict] = []
    skip_reasons = {
        OptionsAnalyst: "needs option chain",
        MacroRatesAnalyst: "needs --with-rates",
        EventsAnalyst: "needs --with-events (no scheduled events fetched)",
        NewsAnalyst: "needs --with-news (no headlines fetched)",
    }
    for cls in classes:
        if cls.should_spawn(ctx):
            inst = cls()
            # --deep: upgrade DeepSeek V3 analysts to R1 (reasoner) for deeper analysis.
            if deep and inst.provider == "deepseek" and inst.model == "deepseek-chat":
                inst.model = "deepseek-reasoner"
            spawned.append(inst)
        else:
            skipped.append({"name": cls.name, "reason": skip_reasons.get(cls, "data deps not met")})

    emit("spawn:done",
         spawned=[(a.name, a.provider or "anthropic", a.model or "default") for a in spawned],
         skipped=skipped)

    emit("round:start", round=1, analysts=[a.name for a in spawned])
    round1 = _run_round(spawned, ctx, peer_views=None)
    for v in round1:
        emit("analyst:view", round=1, view=v)

    round2: list[AnalystView] = []
    if do_debate:
        emit("round:start", round=2, analysts=[a.name for a in spawned])
        round2 = _run_round(spawned, ctx, peer_views=round1)
        for v in round2:
            emit("analyst:view", round=2, view=v)

    final_views = round2 if round2 else round1

    quant_view = None
    if with_quant and QuantStrategist.should_spawn(ctx):
        emit("quant:start")
        try:
            quant_view = QuantStrategist().analyze_quant(ctx, peer_views=final_views)
            emit("quant:done", view=quant_view)
        except Exception as exc:
            emit("quant:error", error=str(exc))

    conflict_meta = None
    if quant_view is not None:
        quant_view, conflict_meta = _reconcile_ticket(ctx, final_views, quant_view)
        if conflict_meta:
            emit("reconcile:conflict", **conflict_meta)

    emit("coordinator:start")
    consensus = _coordinator(ctx, final_views, quant_view)
    if conflict_meta:
        consensus["conflict_flag"] = bool(conflict_meta.get("conflict_flag"))
        consensus["conflict_note"] = conflict_meta.get("conflict_note", "")
        consensus["ticket_substituted"] = bool(conflict_meta.get("substituted"))
    emit("coordinator:done", consensus=consensus)

    hard_rules = _hard_rules_gate(
        ctx,
        quant_view,
        account_size=account_size,
        max_loss_pct=max_loss_pct,
        max_bid_ask_spread_pct=max_bid_ask_spread_pct,
        earnings_reduce_days=earnings_reduce_days,
        max_event_risk_score=max_event_risk_score,
    )
    consensus["hard_rules"] = hard_rules
    emit("rules:done", hard_rules=hard_rules)

    options_summary = None
    if ctx.chain_summary is not None:
        cs = ctx.chain_summary
        options_summary = {
            "spot": getattr(cs, "spot", ctx.spot),
            "iv_rv_spread": getattr(cs, "iv_rv_spread", None),
            "realized_vol_30d": getattr(cs, "realized_vol_30d", None),
            "realized_vol_60d": getattr(cs, "realized_vol_60d", None),
            "atm_iv_by_expiry": getattr(cs, "atm_iv_by_expiry", {}) or {},
            "skew_by_expiry": getattr(cs, "skew_by_expiry", {}) or {},
            "oi_levels": getattr(cs, "oi_levels", []) or [],
            "contracts": int(len(ctx.chain_df)) if ctx.chain_df is not None else 0,
        }

    return SwarmResult(
        ticker=ticker,
        snapshot=ctx.snap,
        spawned=[a.name for a in spawned],
        skipped=skipped,
        round1=round1,
        round2=round2,
        quant=quant_view,
        hard_rules=hard_rules,
        events=ctx.events,
        event_summary=ctx.event_summary,
        options_summary=options_summary,
        consensus=consensus,
    )
