"""Audit / transparency tool.

Lists every agent in the swarm and exactly what math, concepts, and inputs
it uses. Self-introspecting — reads the actual code so it can't drift from
reality.

    python -m agent_swarm.tools.audit                # full manifest
    python -m agent_swarm.tools.audit --analyst Trend
    python -m agent_swarm.tools.audit --math         # just the math primitives
    python -m agent_swarm.tools.audit --prompts      # show full system prompts
"""
from __future__ import annotations

import argparse
import inspect
import textwrap

from agent_swarm.analysts import (
    BaseAnalyst, MeanReversionAnalyst, PatternAnalyst,
    TrendAnalyst, VolatilityAnalyst, VolumeAnalyst,
)
from agent_swarm.analysts.options_analyst import OptionsAnalyst
from agent_swarm.core import black_scholes as bs
from agent_swarm.core import signals


# --- Manifest data: what each analyst's mathematical / conceptual toolkit is.
# Kept here so it stays close to the prompts. If you change an analyst's focus
# or its prompt, update this too.
ANALYST_TOOLKITS: dict[str, dict] = {
    "Trend Analyst": {
        "school": "Dow Theory / classical trend following",
        "looks_for": [
            "Moving-average stack alignment (MA20 > MA50 > MA200 = bullish)",
            "MA slope (rising = trend up; flattening = trend exhaustion)",
            "Swing-high / swing-low structure (higher-highs vs lower-highs)",
            "Proximity to 52-week extremes",
            "Failed retests of prior swings",
        ],
        "math_inputs": [
            "MA20, MA50, MA200 (simple moving averages of close)",
            "52-week rolling high / low",
            "Recent close prices for swing identification",
            "RSI for momentum context",
        ],
        "calculations_run": [
            "signals.add_indicators() → SMAs, RSI, 52w extremes",
        ],
        "ignores": ["short-term noise", "mean-reversion setups", "options pricing"],
    },
    "Pattern Analyst": {
        "school": "Classical technical analysis (Edwards & Magee)",
        "looks_for": [
            "Triangles (ascending, descending, symmetrical)",
            "Flags & pennants (continuation patterns)",
            "Head-and-shoulders / inverse H&S (reversal)",
            "Double tops / double bottoms",
            "Channels & range breakouts",
            "Gap fills",
            "Wedges (rising / falling)",
        ],
        "math_inputs": [
            "30 bars of OHLC (geometry, not formulas)",
            "Volume context for breakout confirmation",
        ],
        "calculations_run": [
            "Pure pattern recognition by the LLM — no numerical algorithm",
        ],
        "ignores": ["intraday tape", "exotic harmonic patterns", "indicator divergences"],
    },
    "Volume Analyst": {
        "school": "Wyckoff / accumulation-distribution analysis",
        "looks_for": [
            "Volume on up-days vs down-days (effort vs result)",
            "Climax / capitulation volume",
            "Volume dry-ups before breakouts",
            "Distribution: heavy volume at resistance with no progress",
            "Volume-price divergence",
        ],
        "math_inputs": [
            "Daily Volume",
            "20-day average volume (Vol_avg20)",
            "Recent close direction (up/down day)",
        ],
        "calculations_run": [
            "Vol_avg20 = 20-period rolling mean of Volume",
            "Comparison of day's volume vs 20d avg",
        ],
        "ignores": ["price patterns without volume context"],
    },
    "Volatility Analyst": {
        "school": "Range / regime analysis (ATR-school, no Black-Scholes)",
        "looks_for": [
            "Realized range expansion vs contraction",
            "Multi-day range behavior",
            "Gap behavior",
            "Vol regime translated to options-trader language",
        ],
        "math_inputs": [
            "30 bars of OHLC (computes ranges from H-L)",
            "Recent close-to-close moves",
        ],
        "calculations_run": [
            "Implicit range computation by LLM (no explicit ATR call yet)",
        ],
        "ignores": ["chart patterns", "trend slope", "explicit IV (that's the Options Analyst's job)"],
    },
    "Mean Reversion Analyst": {
        "school": "Statistical mean-reversion (Bollinger / RSI extremes)",
        "looks_for": [
            "Overbought / oversold RSI (>70 / <30)",
            "RSI divergences vs price",
            "Distance from MA20 (stretched setups)",
            "Exhaustion candles at extremes",
        ],
        "math_inputs": [
            "RSI (14-period Wilder smoothing)",
            "Close price relative to MA20",
        ],
        "calculations_run": [
            "RSI: avg_gain / avg_loss EMA over 14 periods",
            "% distance from MA20",
        ],
        "ignores": ["trends in progress (will say neutral if no extreme present)"],
    },
    "Options Analyst": {
        "school": "Black-Scholes vol trading / volatility surface analysis",
        "looks_for": [
            "Implied volatility vs realized volatility (rich/cheap premium)",
            "Term structure: front-month IV vs back-month IV (contango/backwardation)",
            "25-delta skew: put IV - call IV (positioning indicator)",
            "Best-fit options structure given vol regime + directional bias",
        ],
        "math_inputs": [
            "Spot price S",
            "Risk-free rate r (default 0.045)",
            "Realized vol 30d & 60d (annualized log-return std × √252)",
            "Bid/ask mid for every option contract",
            "ATM IV per expiry (median of 4 strikes nearest spot)",
            "25-delta skew per expiry",
        ],
        "calculations_run": [
            "Black-Scholes price (closed-form, q=0)",
            "Greeks: delta, gamma, vega, theta, rho",
            "Newton-Raphson implied-vol solver (with bisection fallback)",
            "Realized vol: σ = std(log(p/p_prev)) × √252",
            "OCC symbol parsing (strike/expiry/right from raw symbol)",
            "Term-structure & skew tables",
        ],
        "ignores": ["pure technicals (delegates to chart specialists)"],
    },
}


COORDINATOR = {
    "school": "Portfolio manager / synthesis",
    "role": "Reads all analyst views, weights confidence, identifies agreement vs conflict, picks final structure.",
    "looks_for": [
        "Where the team agrees (high-conviction signal)",
        "Where the team splits (lower confidence cap)",
        "Cross-analyst signals that no single agent could see (e.g. directional bias + rich IV → credit structure)",
    ],
    "calculations_run": [
        "No new math — pure synthesis. Every number it cites came from an analyst.",
    ],
    "outputs": [
        "consensus_stance, consensus_confidence, headline, key_patterns,",
        "agreements, disagreements, horizon, suggested_structure, rationale",
    ],
}


MATH_PRIMITIVES = {
    "agent_swarm.core.signals": [
        ("rsi", "Wilder's RSI: 100 - 100/(1 + EMA(gain)/EMA(loss)) over 14 periods"),
        ("add_indicators", "Computes MA20/50/200, RSI, 52w high/low, Vol_avg20"),
        ("snapshot", "Latest indicator dict + 1d/5d/20d % changes"),
    ],
    "agent_swarm.core.black_scholes": [
        ("d1_d2", "Standard Black-Scholes d1, d2 with optional dividend yield q"),
        ("price", "Call/put closed-form price (Black-Scholes-Merton)"),
        ("greeks", "Delta, gamma, vega, theta, rho — analytical, not numerical"),
        ("implied_vol", "Newton-Raphson with bisection fallback, ~6-digit accuracy"),
        ("realized_vol", "Annualized log-return std deviation: σ = std(log(p/p_prev)) × √252"),
        ("realized_vol_series", "Rolling realized vol series for backtests/charts"),
    ],
    "agent_swarm.core.options": [
        ("parse_occ", "OCC symbol parser: 'COIN  260918C00200000' → root/expiry/right/strike"),
        ("latest_quote_per_contract", "Collapse streaming bid/ask into one row per contract"),
        ("build_chain", "Per-contract: bid/ask/mid → IV → full greeks"),
        ("near_atm", "Slice the chain to N strikes nearest spot for analysis"),
    ],
}


def hr(c: str = "─", n: int = 78) -> str:
    return c * n


def render_analyst(name: str, cls: type[BaseAnalyst], show_prompt: bool = False) -> None:
    tk = ANALYST_TOOLKITS.get(name, {})
    a = cls()
    print(f"\n{hr('═')}")
    print(f"  {name}")
    print(hr("═"))
    print(f"  School:    {tk.get('school', '?')}")
    print(f"  Provider:  {a.provider or 'env default (anthropic)'}")
    print(f"  Model:     {a.model or 'env default'}")
    print(f"  Focus:     {a.focus}")

    if tk.get("looks_for"):
        print("\n  Looks for:")
        for x in tk["looks_for"]:
            print(textwrap.fill(f"• {x}", width=78, initial_indent="    ", subsequent_indent="      "))

    if tk.get("math_inputs"):
        print("\n  Math inputs (data fed to the LLM):")
        for x in tk["math_inputs"]:
            print(textwrap.fill(f"• {x}", width=78, initial_indent="    ", subsequent_indent="      "))

    if tk.get("calculations_run"):
        print("\n  Calculations run before LLM is called:")
        for x in tk["calculations_run"]:
            print(textwrap.fill(f"• {x}", width=78, initial_indent="    ", subsequent_indent="      "))

    if tk.get("ignores"):
        print("\n  Deliberately ignores:")
        for x in tk["ignores"]:
            print(f"    • {x}")

    if show_prompt:
        print("\n  System prompt (verbatim):")
        for line in textwrap.wrap(a.system_prompt, width=72):
            print(f"    │ {line}")


def render_math() -> None:
    print(f"\n{hr('═')}")
    print("  MATH PRIMITIVES")
    print(hr("═"))
    print("  Pure-Python (numpy + math). No external libraries beyond pandas/numpy.\n")
    for module, items in MATH_PRIMITIVES.items():
        print(f"  {module}")
        for fn, desc in items:
            print(textwrap.fill(f"  • {fn}() — {desc}", width=78, subsequent_indent="      "))
        print()


def render_coordinator() -> None:
    print(f"\n{hr('═')}")
    print("  COORDINATOR (head PM)")
    print(hr("═"))
    print(f"  Role:  {COORDINATOR['role']}")
    print("\n  Looks for:")
    for x in COORDINATOR["looks_for"]:
        print(textwrap.fill(f"• {x}", width=78, initial_indent="    ", subsequent_indent="      "))
    print("\n  Calculations run:")
    for x in COORDINATOR["calculations_run"]:
        print(f"    • {x}")
    print("\n  Outputs (JSON):")
    for x in COORDINATOR["outputs"]:
        print(f"    • {x}")


def render_data_layer() -> None:
    print(f"\n{hr('═')}")
    print("  DATA LAYER (what feeds the swarm)")
    print(hr("═"))
    print("""  Equities/Futures (OHLCV):
    • Primary:   Databento Historical (XNAS.ITCH for stocks, GLBX.MDP3 for futures)
    • Fallback:  yfinance
    • Schema:    ohlcv-1d (daily bars)

  Options (chain + IV):
    • Source:    Databento OPRA.PILLAR
    • Schema:    cbbo-1m (consolidated bid/ask, 1-minute sampled, ~$0.18/day/ticker)
    • Selector:  stype_in='parent', symbol='{ROOT}.OPT' → all contracts under a root

  News & macro:
    • yfinance (no Databento equivalent yet)
    • Macro tickers: SPY, QQQ, DXY, TLT, GLD, USO, ^VIX""")


ALL_ANALYSTS = [
    ("Trend Analyst", TrendAnalyst),
    ("Pattern Analyst", PatternAnalyst),
    ("Volume Analyst", VolumeAnalyst),
    ("Volatility Analyst", VolatilityAnalyst),
    ("Mean Reversion Analyst", MeanReversionAnalyst),
    ("Options Analyst", OptionsAnalyst),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyst", help="show only one analyst (case-insensitive substring match)")
    ap.add_argument("--math", action="store_true", help="show math primitives only")
    ap.add_argument("--prompts", action="store_true", help="include full system prompts")
    args = ap.parse_args()

    if args.math:
        render_math()
        return

    if args.analyst:
        for name, cls in ALL_ANALYSTS:
            if args.analyst.lower() in name.lower():
                render_analyst(name, cls, show_prompt=args.prompts)
        return

    print(f"\n{hr('═')}")
    print("  AGENT SWARM AUDIT — what every agent uses, looks for, and ignores")
    print(hr("═"))
    render_data_layer()
    print(f"\n{hr('═')}")
    print(f"  ANALYSTS  ({len(ALL_ANALYSTS)} specialists, run twice — Round 1 independent, Round 2 with peers)")
    print(hr("═"))
    for name, cls in ALL_ANALYSTS:
        render_analyst(name, cls, show_prompt=args.prompts)
    render_coordinator()
    render_math()
    print()


if __name__ == "__main__":
    main()
