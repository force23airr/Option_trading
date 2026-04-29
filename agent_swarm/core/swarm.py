"""Pattern-analysis swarm.

Two-round flow:
  Round 1 — every analyst sees only the data and writes their thesis.
  Round 2 — every analyst sees Round-1 peer takes and refines their own.
A coordinator (LLM) then synthesizes the final consensus.

All LLM calls fan out via a thread pool so wall-clock stays low.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas as pd

from ..analysts import (
    AnalystView,
    BaseAnalyst,
    MeanReversionAnalyst,
    PatternAnalyst,
    TrendAnalyst,
    VolatilityAnalyst,
    VolumeAnalyst,
)
from ..analysts.options_analyst import OptionsAnalyst, summarize_chain
from . import black_scholes as bs
from . import data, llm, options as opt, signals
from ..data import opra_source


DEFAULT_ANALYSTS: list[type[BaseAnalyst]] = [
    TrendAnalyst,
    PatternAnalyst,
    VolumeAnalyst,
    VolatilityAnalyst,
    MeanReversionAnalyst,
]


@dataclass
class SwarmResult:
    ticker: str
    snapshot: dict
    round1: list[AnalystView] = field(default_factory=list)
    round2: list[AnalystView] = field(default_factory=list)
    consensus: dict = field(default_factory=dict)


def _run_analysts(
    analysts: list[BaseAnalyst],
    ticker: str,
    df: pd.DataFrame,
    snap: dict,
    peer_views: list[AnalystView] | None,
) -> list[AnalystView]:
    with ThreadPoolExecutor(max_workers=len(analysts)) as ex:
        futs = [ex.submit(a.analyze, ticker, df, snap, peer_views) for a in analysts]
        return [f.result() for f in futs]


COORDINATOR_SYSTEM = (
    "You are the head portfolio manager. You read specialist analyst views and produce a "
    "single consensus call. You are skeptical, you weigh confidence, and you flag when the "
    "team disagrees. You do NOT add new analysis — you synthesize."
)


def _coordinator(ticker: str, snap: dict, views: list[AnalystView]) -> dict:
    views_block = "\n\n".join(
        f"### {v.analyst}\n"
        f"stance: {v.stance}  confidence: {v.confidence:.0%}  horizon: {v.horizon}\n"
        f"pattern: {v.pattern or '(none)'}\n"
        f"summary: {v.summary}\n"
        f"observations:\n  - " + "\n  - ".join(v.observations)
        for v in views
    )

    prompt = f"""Ticker: {ticker}

Indicator snapshot:
{json.dumps(snap, indent=2, default=str)}

Specialist analyst views (after debate round):
{views_block}

Produce a single consensus call. Reply with one JSON object and nothing else:
{{
  "consensus_stance": "bullish" | "bearish" | "neutral",
  "consensus_confidence": <float 0.0-1.0>,
  "headline": "<one sentence>",
  "key_patterns": ["<pattern 1>", "..."],
  "agreements": ["<point most analysts agree on>", "..."],
  "disagreements": ["<point analysts split on>", "..."],
  "horizon": "intraday" | "1-5d" | "1-4w" | "longer",
  "suggested_structure": "<long stock | calls | puts | call spread | put spread | iron condor | stay flat>",
  "rationale": "<2-3 sentences>"
}}"""
    raw = llm.chat(prompt, system=COORDINATOR_SYSTEM, max_tokens=900, temperature=0.2)
    from ..analysts.base import _parse_json_reply
    return _parse_json_reply(raw) or {"raw": raw}


def run(
    ticker: str,
    days: int = 180,
    analyst_classes: list[type[BaseAnalyst]] | None = None,
    do_debate: bool = True,
    with_options: bool = False,
    on_event=None,
) -> SwarmResult:
    """Run the swarm. on_event(event_type: str, payload: dict) is an optional hook.

    If with_options=True, pulls a 1-day OPRA chain (~$0.18 per ticker) and runs
    an Options Analyst alongside the chart specialists.
    """
    def emit(et, **payload):
        if on_event:
            on_event(et, payload)

    emit("data:start", ticker=ticker, days=days)
    df = signals.add_indicators(data.fetch_ohlcv(ticker, days=days))
    if df.empty:
        raise RuntimeError(f"no data for {ticker}")
    snap = signals.snapshot(df)
    emit("data:done", bars=len(df), snapshot=snap)

    chain_summary = None
    if with_options:
        emit("options:start", ticker=ticker)
        try:
            spot = float(df["Close"].iloc[-1])
            rv30 = bs.realized_vol(df["Close"], window=30)
            rv60 = bs.realized_vol(df["Close"], window=60)
            quotes = opra_source.fetch_quotes(ticker, days=1)
            chain = opt.build_chain(quotes, spot=spot)
            if not chain.empty:
                chain_summary = summarize_chain(chain, spot, rv30, rv60)
                emit("options:done", contracts=len(chain), iv_rv_spread=chain_summary.iv_rv_spread)
            else:
                emit("options:empty")
        except Exception as exc:
            emit("options:error", error=str(exc))

    classes = analyst_classes or DEFAULT_ANALYSTS
    analysts = [cls() for cls in classes]

    emit("round:start", round=1, analysts=[a.name for a in analysts])
    round1 = _run_analysts(analysts, ticker, df, snap, peer_views=None)

    if chain_summary is not None:
        opts_view = OptionsAnalyst().analyze_with_chain(ticker, df, snap, chain_summary, peer_views=None)
        round1.append(opts_view)

    for v in round1:
        emit("analyst:view", round=1, view=v)

    round2: list[AnalystView] = []
    if do_debate:
        emit("round:start", round=2, analysts=[a.name for a in analysts])
        round2 = _run_analysts(analysts, ticker, df, snap, peer_views=round1)
        if chain_summary is not None:
            opts_view2 = OptionsAnalyst().analyze_with_chain(ticker, df, snap, chain_summary, peer_views=round1)
            round2.append(opts_view2)
        for v in round2:
            emit("analyst:view", round=2, view=v)

    final_views = round2 if round2 else round1
    emit("coordinator:start")
    consensus = _coordinator(ticker, snap, final_views)
    emit("coordinator:done", consensus=consensus)

    return SwarmResult(ticker=ticker, snapshot=snap, round1=round1, round2=round2, consensus=consensus)
