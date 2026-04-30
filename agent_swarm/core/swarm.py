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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas as pd

from ..analysts import (
    AnalystView,
    BaseAnalyst,
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
from . import black_scholes as bs
from . import data, llm, options as opt, signals
from .context import DataContext
from ..data import macro_source, news_source, opra_source


# Order matters only for display
ALL_ANALYST_CLASSES: list[type[BaseAnalyst]] = [
    TrendAnalyst,
    PatternAnalyst,
    VolumeAnalyst,
    VolatilityAnalyst,
    MeanReversionAnalyst,
    MacroRatesAnalyst,
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
    consensus: dict = field(default_factory=dict)


def _run_analyst_view(a: BaseAnalyst, ctx: DataContext, peer_views) -> AnalystView:
    """Dispatch — analysts that need extra context have specialized entry points."""
    if isinstance(a, OptionsAnalyst):
        return a.analyze_with_chain(ctx.ticker, ctx.df, ctx.snap, ctx.chain_summary, peer_views=peer_views)
    if isinstance(a, MacroRatesAnalyst):
        return a.analyze_with_rates(ctx, peer_views=peer_views)
    if isinstance(a, NewsAnalyst):
        return a.analyze_with_news(ctx, peer_views=peer_views)
    return a.analyze(ctx.ticker, ctx.df, ctx.snap, peer_views=peer_views)


def _run_round(analysts: list[BaseAnalyst], ctx: DataContext, peer_views) -> list[AnalystView]:
    if not analysts:
        return []
    with ThreadPoolExecutor(max_workers=len(analysts)) as ex:
        futs = [ex.submit(_run_analyst_view, a, ctx, peer_views) for a in analysts]
        return [f.result() for f in futs]


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


def _build_context(ticker: str, days: int, with_options: bool, with_rates: bool, with_news: bool, emit) -> DataContext:
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
            chain = opt.build_chain(quotes, spot=ctx.spot)
            if not chain.empty:
                ctx.chain_df = chain
                ctx.chain_summary = summarize_chain(chain, ctx.spot, ctx.rv30, ctx.rv60)
                emit("options:done", contracts=len(chain), iv_rv_spread=ctx.chain_summary.iv_rv_spread)
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
            items = news_source.fetch_news(ticker, limit=25)
            ctx.news = items
            ctx.earnings_date = news_source.fetch_earnings_date(ticker)
            if items:
                emit("news:done", count=len(items), earnings_date=ctx.earnings_date)
            else:
                emit("news:empty")
        except Exception as exc:
            emit("news:error", error=str(exc))

    return ctx


def run(
    ticker: str,
    days: int = 180,
    analyst_classes: list[type[BaseAnalyst]] | None = None,
    do_debate: bool = True,
    with_options: bool = False,
    with_rates: bool = False,
    with_news: bool = False,
    with_quant: bool = True,
    deep: bool = False,
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

    ctx = _build_context(ticker, days, with_options, with_rates, with_news, emit)

    classes = analyst_classes or ALL_ANALYST_CLASSES
    spawned: list[BaseAnalyst] = []
    skipped: list[dict] = []
    skip_reasons = {
        OptionsAnalyst: "needs option chain",
        MacroRatesAnalyst: "needs --with-rates",
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

    emit("coordinator:start")
    consensus = _coordinator(ctx, final_views, quant_view)
    emit("coordinator:done", consensus=consensus)

    return SwarmResult(
        ticker=ticker,
        snapshot=ctx.snap,
        spawned=[a.name for a in spawned],
        skipped=skipped,
        round1=round1,
        round2=round2,
        quant=quant_view,
        consensus=consensus,
    )
