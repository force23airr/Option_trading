"""Quant Strategist — the power agent.

Uses DeepSeek-R1 (`deepseek-reasoner`) for explicit chain-of-thought numerical
reasoning. Unlike the chart analysts that produce qualitative views, this one:

- Computes concrete option-structure candidates from the live chain
- Calculates credit/debit, max profit, max loss, breakevens, POP estimate
- Ranks structures by reward/risk and theta/vega exposure
- Produces a TRADE TICKET with hard numbers, not a paragraph

This is what the swarm escalates to when it needs precise numbers, not vibes.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

import pandas as pd

from ..core import black_scholes as bs
from ..core import llm
from .base import AnalystView, BaseAnalyst, _parse_json_reply


@dataclass
class StructureCandidate:
    """A single defined-risk options structure with all the numbers."""
    name: str               # e.g. "MAY 22 175/180/200/205 Iron Condor"
    expiry: str
    legs: list[dict]        # [{right, strike, side, mid}, ...]
    net_credit_or_debit: float
    max_profit: float
    max_loss: float
    breakeven_lo: float | None
    breakeven_hi: float | None
    pop_estimate: float     # crude probability-of-profit using delta
    net_delta: float
    net_vega: float
    net_theta: float
    reward_to_risk: float


def _short_dte_chain(chain: pd.DataFrame, max_dte: int = 45) -> pd.DataFrame:
    return chain[(chain["dte"] > 0) & (chain["dte"] <= max_dte)].copy()


def _atm_strikes(chain: pd.DataFrame, spot: float, n: int = 1) -> list[float]:
    strikes = sorted(chain["strike"].unique())
    if not strikes:
        return []
    closest = sorted(strikes, key=lambda k: abs(k - spot))[:n]
    return sorted(closest)


def build_candidates(chain: pd.DataFrame, spot: float, max_dte: int = 45) -> list[StructureCandidate]:
    """Build a small set of candidate structures from the live chain.

    We propose 4 archetypes for the LLM to consider:
      1. Iron condor (sell ATM strangle, buy wings)
      2. Put credit spread (bullish, define risk)
      3. Call credit spread (bearish, define risk)
      4. Long call vertical (bullish debit)

    Numbers come from the chain — if a leg has no quote we skip the structure.
    """
    out: list[StructureCandidate] = []
    short_chain = _short_dte_chain(chain, max_dte=max_dte)
    if short_chain.empty:
        return out

    # Pick one expiry — the closest one with > 7 DTE (avoid 0-2 DTE noise)
    valid_exp = short_chain[short_chain["dte"] >= 7]
    if valid_exp.empty:
        return out
    expiry = valid_exp["dte"].min()
    expiry_df = valid_exp[valid_exp["dte"] == expiry]
    expiry_str = str(expiry_df["expiry"].iloc[0])

    # Find strikes near specific deltas
    def closest_strike_by_delta(df: pd.DataFrame, target_delta: float, right: str) -> pd.Series | None:
        slice_ = df[df["right"] == right].dropna(subset=["delta"]).copy()
        if slice_.empty:
            return None
        slice_["d_diff"] = (slice_["delta"] - target_delta).abs()
        return slice_.sort_values("d_diff").iloc[0]

    short_call = closest_strike_by_delta(expiry_df, 0.30, "C")
    long_call = closest_strike_by_delta(expiry_df, 0.15, "C")
    short_put = closest_strike_by_delta(expiry_df, -0.30, "P")
    long_put = closest_strike_by_delta(expiry_df, -0.15, "P")

    # ATM call/put for vertical debit spread
    atm_call_long = expiry_df[expiry_df["right"] == "C"].dropna(subset=["delta"])
    if not atm_call_long.empty:
        atm_call_long = atm_call_long.iloc[(atm_call_long["delta"] - 0.55).abs().to_numpy().argsort()[:1]].iloc[0]
    else:
        atm_call_long = None
    atm_call_short = expiry_df[expiry_df["right"] == "C"].dropna(subset=["delta"])
    if not atm_call_short.empty:
        atm_call_short = atm_call_short.iloc[(atm_call_short["delta"] - 0.30).abs().to_numpy().argsort()[:1]].iloc[0]
    else:
        atm_call_short = None

    # 1. Iron condor
    if all(x is not None for x in (short_call, long_call, short_put, long_put)):
        credit = (short_call["mid"] - long_call["mid"]) + (short_put["mid"] - long_put["mid"])
        call_width = float(long_call["strike"] - short_call["strike"])
        put_width = float(short_put["strike"] - long_put["strike"])
        max_loss = max(call_width, put_width) - credit
        be_lo = float(short_put["strike"]) - credit
        be_hi = float(short_call["strike"]) + credit
        net_delta = -short_call["delta"] + long_call["delta"] - short_put["delta"] + long_put["delta"]
        net_vega = -short_call["vega"] + long_call["vega"] - short_put["vega"] + long_put["vega"]
        net_theta = -short_call["theta"] + long_call["theta"] - short_put["theta"] + long_put["theta"]
        pop = 1.0 - (abs(short_call["delta"]) + abs(short_put["delta"]))
        out.append(StructureCandidate(
            name=f"{expiry_str} {long_put['strike']:.0f}/{short_put['strike']:.0f}/{short_call['strike']:.0f}/{long_call['strike']:.0f} Iron Condor",
            expiry=expiry_str,
            legs=[
                {"right": "P", "strike": float(long_put["strike"]), "side": "long", "mid": float(long_put["mid"])},
                {"right": "P", "strike": float(short_put["strike"]), "side": "short", "mid": float(short_put["mid"])},
                {"right": "C", "strike": float(short_call["strike"]), "side": "short", "mid": float(short_call["mid"])},
                {"right": "C", "strike": float(long_call["strike"]), "side": "long", "mid": float(long_call["mid"])},
            ],
            net_credit_or_debit=float(credit),
            max_profit=float(credit),
            max_loss=float(max_loss),
            breakeven_lo=be_lo,
            breakeven_hi=be_hi,
            pop_estimate=float(pop),
            net_delta=float(net_delta),
            net_vega=float(net_vega),
            net_theta=float(net_theta),
            reward_to_risk=float(credit / max_loss) if max_loss > 0 else float("inf"),
        ))

    # 2. Put credit spread (bullish, sell short_put / buy long_put)
    if short_put is not None and long_put is not None:
        credit = float(short_put["mid"] - long_put["mid"])
        width = float(short_put["strike"] - long_put["strike"])
        max_loss = width - credit
        be = float(short_put["strike"]) - credit
        out.append(StructureCandidate(
            name=f"{expiry_str} {long_put['strike']:.0f}/{short_put['strike']:.0f} Put Credit Spread",
            expiry=expiry_str,
            legs=[
                {"right": "P", "strike": float(long_put["strike"]), "side": "long", "mid": float(long_put["mid"])},
                {"right": "P", "strike": float(short_put["strike"]), "side": "short", "mid": float(short_put["mid"])},
            ],
            net_credit_or_debit=credit,
            max_profit=credit,
            max_loss=max_loss,
            breakeven_lo=None, breakeven_hi=be,
            pop_estimate=float(1.0 - abs(short_put["delta"])),
            net_delta=float(-short_put["delta"] + long_put["delta"]),
            net_vega=float(-short_put["vega"] + long_put["vega"]),
            net_theta=float(-short_put["theta"] + long_put["theta"]),
            reward_to_risk=credit / max_loss if max_loss > 0 else float("inf"),
        ))

    # 3. Call credit spread (bearish)
    if short_call is not None and long_call is not None:
        credit = float(short_call["mid"] - long_call["mid"])
        width = float(long_call["strike"] - short_call["strike"])
        max_loss = width - credit
        be = float(short_call["strike"]) + credit
        out.append(StructureCandidate(
            name=f"{expiry_str} {short_call['strike']:.0f}/{long_call['strike']:.0f} Call Credit Spread",
            expiry=expiry_str,
            legs=[
                {"right": "C", "strike": float(short_call["strike"]), "side": "short", "mid": float(short_call["mid"])},
                {"right": "C", "strike": float(long_call["strike"]), "side": "long", "mid": float(long_call["mid"])},
            ],
            net_credit_or_debit=credit,
            max_profit=credit,
            max_loss=max_loss,
            breakeven_lo=be, breakeven_hi=None,
            pop_estimate=float(1.0 - abs(short_call["delta"])),
            net_delta=float(-short_call["delta"] + long_call["delta"]),
            net_vega=float(-short_call["vega"] + long_call["vega"]),
            net_theta=float(-short_call["theta"] + long_call["theta"]),
            reward_to_risk=credit / max_loss if max_loss > 0 else float("inf"),
        ))

    # 4. Long call vertical (bullish debit)
    if atm_call_long is not None and atm_call_short is not None and atm_call_long["strike"] < atm_call_short["strike"]:
        debit = float(atm_call_long["mid"] - atm_call_short["mid"])
        width = float(atm_call_short["strike"] - atm_call_long["strike"])
        max_profit = width - debit
        be = float(atm_call_long["strike"]) + debit
        out.append(StructureCandidate(
            name=f"{expiry_str} {atm_call_long['strike']:.0f}/{atm_call_short['strike']:.0f} Call Debit Spread",
            expiry=expiry_str,
            legs=[
                {"right": "C", "strike": float(atm_call_long["strike"]), "side": "long", "mid": float(atm_call_long["mid"])},
                {"right": "C", "strike": float(atm_call_short["strike"]), "side": "short", "mid": float(atm_call_short["mid"])},
            ],
            net_credit_or_debit=-debit,  # debit, negative cash flow
            max_profit=max_profit,
            max_loss=debit,
            breakeven_lo=be, breakeven_hi=None,
            pop_estimate=float(atm_call_long["delta"]),
            net_delta=float(atm_call_long["delta"] - atm_call_short["delta"]),
            net_vega=float(atm_call_long["vega"] - atm_call_short["vega"]),
            net_theta=float(atm_call_long["theta"] - atm_call_short["theta"]),
            reward_to_risk=max_profit / debit if debit > 0 else float("inf"),
        ))

    return out


def _candidates_block(cands: list[StructureCandidate]) -> str:
    out = []
    for c in cands:
        cf = "credit" if c.net_credit_or_debit > 0 else "debit"
        out.append(
            f"### {c.name}\n"
            f"  cash flow:  ${c.net_credit_or_debit:+.2f}/contract ({cf})\n"
            f"  max profit: ${c.max_profit:+.2f}/contract\n"
            f"  max loss:   ${c.max_loss:+.2f}/contract\n"
            f"  breakevens: lo={c.breakeven_lo}  hi={c.breakeven_hi}\n"
            f"  POP est:    {c.pop_estimate:.0%}\n"
            f"  net Δ:      {c.net_delta:+.3f}     net vega: {c.net_vega:+.3f}     net θ/yr: {c.net_theta:+.2f}\n"
            f"  R/R:        {c.reward_to_risk:.2f}\n"
            f"  legs:       {c.legs}"
        )
    return "\n\n".join(out)


class QuantStrategist(BaseAnalyst):
    name = "Quant Strategist"
    focus = "concrete option-structure scenario analysis with hard numbers"
    system_prompt = (
        "You are a quantitative options strategist. You think numerically and explicitly. "
        "Given a set of pre-computed candidate structures with all greeks, breakevens, max "
        "P&L, and POP estimates, you pick ONE as the recommended trade and explain WHY "
        "with reference to the actual numbers. You never invent numbers. You never pick a "
        "structure whose net vega contradicts the vol regime (e.g. don't go long vega when "
        "IV is rich). You produce a TRADE TICKET, not a paragraph."
    )
    # Power model: DeepSeek-R1 reasoning model — best at numerical chain-of-thought
    provider = "deepseek"
    model = "deepseek-reasoner"

    @classmethod
    def should_spawn(cls, ctx) -> bool:
        return ctx.has_options

    def analyze_quant(self, ctx, peer_views: list[AnalystView] | None = None) -> AnalystView:
        candidates = build_candidates(ctx.chain_df, spot=ctx.spot)
        if not candidates:
            return AnalystView(
                analyst=self.name, ticker=ctx.ticker,
                stance="neutral", confidence=0.0,
                summary="No viable defined-risk structures from chain (insufficient strikes/expiries).",
                provider=self.provider or "", model=self.model or "",
            )

        peers_block = ""
        if peer_views:
            peers_block = "\n\nPEER ANALYSTS' VIEWS (for directional context):\n"
            for v in peer_views:
                peers_block += f"- {v.short()}\n"

        cs = ctx.chain_summary
        regime_block = {
            "spot": ctx.spot,
            "realized_vol_30d_pct": round(ctx.rv30 * 100, 1) if ctx.rv30 else None,
            "atm_iv_by_expiry_pct": {k: round(v * 100, 1) for k, v in cs.atm_iv_by_expiry.items()} if cs else {},
            "iv_minus_rv30_pct": round(cs.iv_rv_spread * 100, 1) if cs else None,
        }

        prompt = f"""Ticker: {ctx.ticker}
Vol regime:
{json.dumps(regime_block, indent=2)}

CANDIDATE STRUCTURES (computed from live chain — DO NOT alter the numbers):
{_candidates_block(candidates)}
{peers_block}
Pick the single best trade. Reply with one JSON object:
{{
  "stance": "bullish" | "bearish" | "neutral",
  "confidence": <float 0.0-1.0>,
  "selected_structure": "<name copied verbatim from above>",
  "trade_ticket": {{
    "structure": "<name>",
    "expiry": "<expiry>",
    "legs": [...],
    "cash_flow": <number, signed>,
    "max_profit": <number>,
    "max_loss": <number>,
    "breakevens": [<lo>, <hi>],
    "pop_estimate_pct": <number 0-100>,
    "net_delta": <number>,
    "net_vega": <number>,
    "net_theta_per_day": <number>
  }},
  "summary": "<one sentence: structure + why it matches the regime>",
  "rationale": "<2-3 sentences citing specific numbers from the candidate>",
  "horizon": "1-5d" | "1-4w" | "longer"
}}"""

        # DeepSeek-R1 spends a lot of budget on internal reasoning before the
        # answer; give it room. 8000 is the model's hard cap.
        raw = llm.chat(
            prompt, system=self.system_prompt,
            provider=self.provider, model=self.model,
            max_tokens=8000, temperature=0.2,
        )
        parsed = _parse_json_reply(raw)
        ticket = parsed.get("trade_ticket", {})

        observations = []
        if ticket:
            observations.append(f"Selected: {parsed.get('selected_structure', '')}")
            if ticket.get("cash_flow") is not None:
                observations.append(f"Cash flow: ${ticket.get('cash_flow', 0):+.2f}/contract")
            if ticket.get("max_profit") is not None:
                observations.append(f"Max profit: ${ticket.get('max_profit', 0):+.2f}")
            if ticket.get("max_loss") is not None:
                observations.append(f"Max loss: ${ticket.get('max_loss', 0):+.2f}")
            if ticket.get("breakevens"):
                observations.append(f"Breakevens: {ticket['breakevens']}")
            if ticket.get("pop_estimate_pct") is not None:
                observations.append(f"POP estimate: {ticket['pop_estimate_pct']:.0f}%")
            for k in ("net_delta", "net_vega", "net_theta_per_day"):
                if ticket.get(k) is not None:
                    observations.append(f"{k}: {ticket[k]:+.3f}")

        rationale = parsed.get("rationale", "")
        if rationale:
            observations.append(f"Rationale: {rationale}")

        return AnalystView(
            analyst=self.name, ticker=ctx.ticker,
            stance=str(parsed.get("stance", "neutral")).lower(),
            confidence=float(parsed.get("confidence", 0.0) or 0.0),
            summary=str(parsed.get("summary", "")).strip(),
            observations=observations,
            pattern=str(parsed.get("selected_structure", "")).strip(),
            horizon=str(parsed.get("horizon", "")).strip(),
            raw=raw,
            provider=self.provider or "",
            model=self.model or "",
        )
