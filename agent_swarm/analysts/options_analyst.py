"""Model-vs-market options analyst.

Looks at the actual option chain (not just price) and judges:
- Is implied vol rich or cheap vs realized?
- Is the term structure in contango or backwardation?
- What does skew tell us about positioning?
- Which structures (debit vs credit, calls vs puts vs spreads) are favored?
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from dataclasses import field

from ..core import black_scholes as bs
from ..core import options
from ..core import oi_levels as oi_levels_mod
from .base import AnalystView, BaseAnalyst, _parse_json_reply
from ..core import llm


@dataclass
class ChainSummary:
    spot: float
    realized_vol_30d: float
    realized_vol_60d: float
    atm_iv_by_expiry: dict[str, float]   # str(expiry) -> median ATM IV
    skew_by_expiry: dict[str, float]     # 25-delta put IV - 25-delta call IV
    iv_rv_spread: float                  # nearest-expiry ATM IV minus realized 30d
    oi_levels: list[dict] = field(default_factory=list)  # one dict per top expiry


def summarize_chain(chain: pd.DataFrame, spot: float, rv30: float, rv60: float) -> ChainSummary:
    atm_iv = {}
    skew = {}
    for expiry, group in chain.groupby("expiry"):
        # ATM = nearest 4 strikes to spot, avg IV
        atm = group.iloc[(group["strike"] - spot).abs().to_numpy().argsort()[:4]]
        if not atm["iv"].isna().all():
            atm_iv[str(expiry)] = float(atm["iv"].median())

        # 25-delta skew: nearest put with delta ~ -0.25 vs call with delta ~ +0.25
        puts = group[group["right"] == "P"].copy()
        calls = group[group["right"] == "C"].copy()
        if not puts.empty and not calls.empty:
            puts_clean = puts.dropna(subset=["delta"])
            calls_clean = calls.dropna(subset=["delta"])
            if puts_clean.empty or calls_clean.empty:
                continue
            p25 = puts_clean.iloc[(puts_clean["delta"] + 0.25).abs().to_numpy().argsort()[:1]]
            c25 = calls_clean.iloc[(calls_clean["delta"] - 0.25).abs().to_numpy().argsort()[:1]]
            if not p25.empty and not c25.empty and not (p25["iv"].isna().any() or c25["iv"].isna().any()):
                skew[str(expiry)] = float(p25["iv"].iloc[0] - c25["iv"].iloc[0])

    nearest_expiry = sorted(atm_iv.keys())[0] if atm_iv else None
    iv_rv_spread = (atm_iv[nearest_expiry] - rv30) if nearest_expiry else float("nan")

    levels: list[dict] = []
    if "open_interest" in chain.columns:
        for exp in oi_levels_mod.pick_top_expiries(chain, n=2):
            d = oi_levels_mod.compute_oi_levels(chain, exp)
            if d:
                levels.append(d)

    return ChainSummary(
        spot=spot,
        realized_vol_30d=rv30,
        realized_vol_60d=rv60,
        atm_iv_by_expiry=atm_iv,
        skew_by_expiry=skew,
        iv_rv_spread=iv_rv_spread,
        oi_levels=levels,
    )


class OptionsAnalyst(BaseAnalyst):
    name = "Options Analyst"
    focus = "implied vs realized vol, term structure, skew, choosing the right options structure"
    system_prompt = (
        "You are a vol/options trader. You read the option chain — not the underlying — to "
        "judge whether premium is rich or cheap, what the term structure says about expected "
        "movement, and what skew says about positioning. You translate these into specific "
        "structure choices: long calls/puts (debit), credit spreads, iron condors, calendars, "
        "diagonals. You never pick a structure that's misaligned with the vol regime. "
        "You also read OI CONCENTRATION as a positioning proxy — not as proof of dealer "
        "gamma sign. A CALL WALL is the strike with the largest call OI and TYPICALLY acts "
        "as resistance when retail is net long calls (so dealers are net short and hedge "
        "by selling stock into rallies); the same OI can act differently if dealers are "
        "net long. A PUT WALL similarly tends toward support but is conditional. MAX-PAIN "
        "is the strike that minimizes total option-holder ITM value at expiry; price often "
        "drifts toward it in the final 5 DTE under gamma pinning, but this is a tendency, "
        "not a law. Treat walls as soft barriers: prefer short legs beyond a wall when "
        "selling premium, and acknowledge debit structures may fight a same-side wall — "
        "but never assert a directional outcome from OI alone."
    )
    provider = "deepseek"
    model = "deepseek-chat"

    @classmethod
    def should_spawn(cls, ctx) -> bool:
        return ctx.has_options

    def analyze_with_chain(
        self,
        ticker: str,
        df: pd.DataFrame,
        snap: dict,
        chain_summary: ChainSummary,
        peer_views: list[AnalystView] | None = None,
    ) -> AnalystView:
        peers_block = ""
        if peer_views:
            peers_block = "\n\nPEER ANALYSTS' INITIAL TAKES:\n"
            for v in peer_views:
                peers_block += f"- {v.short()}\n"

        chain_block = {
            "spot": chain_summary.spot,
            "realized_vol_30d_pct": round(chain_summary.realized_vol_30d * 100, 1),
            "realized_vol_60d_pct": round(chain_summary.realized_vol_60d * 100, 1),
            "atm_iv_by_expiry_pct": {k: round(v * 100, 1) for k, v in chain_summary.atm_iv_by_expiry.items()},
            "skew_25delta_pct": {k: round(v * 100, 1) for k, v in chain_summary.skew_by_expiry.items()},
            "iv_minus_rv30_pct": round(chain_summary.iv_rv_spread * 100, 1),
            "front_oi_levels": chain_summary.oi_levels,
        }

        prompt = f"""Ticker: {ticker}
Your specialty: {self.focus}

Underlying snapshot:
{json.dumps(snap, indent=2, default=str)}

OPTION CHAIN SUMMARY (live):
{json.dumps(chain_block, indent=2)}
{peers_block}
Translate this into a vol view. Reply with one JSON object:
{{
  "stance": "bullish_vol" | "bearish_vol" | "directional_bullish" | "directional_bearish" | "neutral",
  "confidence": <float 0.0-1.0>,
  "summary": "<one sentence>",
  "vol_regime": "rich" | "cheap" | "fair",
  "term_structure": "contango" | "backwardation" | "flat",
  "skew_read": "<what put-call skew implies>",
  "preferred_structure": "long calls | long puts | call debit spread | put debit spread | call credit spread | put credit spread | iron condor | calendar | diagonal | stay flat",
  "horizon": "intraday" | "1-5d" | "1-4w" | "longer",
  "observations": ["<concrete observation>", "..."]
}}"""

        raw = llm.chat(
            prompt,
            system=self.system_prompt,
            provider=self.provider,
            model=self.model,
            max_tokens=1800,
            temperature=0.3,
        )
        parsed = _parse_json_reply(raw)
        return AnalystView(
            analyst=self.name,
            ticker=ticker,
            stance=str(parsed.get("stance", "neutral")).lower(),
            confidence=float(parsed.get("confidence", 0.0) or 0.0),
            summary=str(parsed.get("summary", "")).strip(),
            observations=[str(o) for o in parsed.get("observations", [])][:8],
            pattern=str(parsed.get("preferred_structure", "")).strip(),
            horizon=str(parsed.get("horizon", "")).strip(),
            raw=raw,
            provider=self.provider or "default",
            model=self.model or "default",
        )
