"""Run the pattern-analysis swarm on one ticker, with live event printing.

    python -m agent_swarm.tools.run_swarm COIN
    python -m agent_swarm.tools.run_swarm COIN --days 365 --with-options
    python -m agent_swarm.tools.run_swarm COIN --no-quant         # skip the power agent
"""
from __future__ import annotations

import argparse
import json
import os

from agent_swarm.core import swarm
from agent_swarm.tools import report as report_module


def _print_event(et: str, payload: dict) -> None:
    if et == "data:start":
        print(f"📊 fetching {payload['ticker']} ({payload['days']}d)...")
    elif et == "data:done":
        snap = payload["snapshot"]
        print(f"   {payload['bars']} bars  close={snap.get('close'):,.2f}  rsi={snap.get('rsi'):.1f}")
    elif et == "options:start":
        print(f"📡 fetching OPRA chain for {payload['ticker']}...")
    elif et == "options:done":
        spread = payload['iv_rv_spread'] * 100
        print(f"   {payload['contracts']} contracts  IV-RV spread {spread:+.1f}pts")
    elif et == "options:empty":
        print("   chain empty (off-hours?) — Options analysts will be skipped")
    elif et == "options:error":
        print(f"   options fetch failed: {payload['error']}")
    elif et == "rates:start":
        print(f"📡 fetching Treasury yield curve...")
    elif et == "rates:done":
        s = payload['summary']
        print(f"   3M={s.get('3M', '?'):.2f}%  5Y={s.get('5Y', '?'):.2f}%  10Y={s.get('10Y', '?'):.2f}%  30Y={s.get('30Y', '?'):.2f}%")
        print(f"   2s10s={s.get('spread_5y10y_bps', 0):+.0f}bps  10y Δ30d={s.get('chg_10y_30d_bps', 0):+.0f}bps")
    elif et == "rates:empty":
        print("   yield curve unavailable")
    elif et == "rates:error":
        print(f"   rates fetch failed: {payload['error']}")
    elif et == "spawn:done":
        print(f"\n🧬 SPAWNED {len(payload['spawned'])} analyst(s):")
        for name, prov, model in payload["spawned"]:
            print(f"   • {name:<24}  →  {prov}/{model}")
        if payload["skipped"]:
            print(f"   skipped:")
            for s in payload["skipped"]:
                print(f"   ✗ {s['name']:<24}  ({s['reason']})")
    elif et == "round:start":
        print(f"\n🧠 ROUND {payload['round']}: {', '.join(payload['analysts'])}")
    elif et == "analyst:view":
        v = payload["view"]
        line = f"   [{v.analyst:<22}] {v.stance:<8} {v.confidence:>4.0%}  {v.summary}"
        if v.pattern:
            line += f"   → {v.pattern!r}"
        print(line)
    elif et == "quant:start":
        print(f"\n⚡ QUANT STRATEGIST  (DeepSeek-R1 reasoning)...")
    elif et == "quant:done":
        v = payload["view"]
        print(f"   📋 TRADE TICKET")
        print(f"   {v.summary}")
        for o in v.observations[:8]:
            print(f"     • {o}")
    elif et == "quant:error":
        print(f"   quant strategist failed: {payload['error']}")
    elif et == "coordinator:start":
        print("\n🎯 coordinator synthesizing...")
    elif et == "coordinator:done":
        c = payload["consensus"]
        print("\n" + "=" * 70)
        print(f"  CONSENSUS: {str(c.get('consensus_stance','?')).upper()}  ({c.get('consensus_confidence', 0):.0%})")
        print("=" * 70)
        print(f"  {c.get('headline','')}")
        if c.get("key_patterns"):
            print(f"\n  Patterns: {', '.join(c['key_patterns'])}")
        if c.get("agreements"):
            print("\n  Agreements:")
            for a in c["agreements"]:
                print(f"    • {a}")
        if c.get("disagreements"):
            print("\n  Disagreements:")
            for d in c["disagreements"]:
                print(f"    • {d}")
        print(f"\n  Horizon:   {c.get('horizon','')}")
        print(f"  Structure: {c.get('suggested_structure','')}")
        print(f"\n  Rationale: {c.get('rationale','')}")
        print("=" * 70)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--no-debate", action="store_true", help="skip round-2 debate")
    ap.add_argument("--with-options", action="store_true", help="pull live OPRA chain (~$0.18) and add Options analysts")
    ap.add_argument("--with-rates", action="store_true", help="pull Treasury yield curve (3M/5Y/10Y/30Y) and add Macro Rates Analyst")
    ap.add_argument("--no-quant", action="store_true", help="skip the Quant Strategist (DeepSeek-R1) power agent")
    ap.add_argument("--provider", help="default LLM provider (anthropic|deepseek|openai|openrouter)")
    ap.add_argument("--model", help="default LLM model")
    ap.add_argument("--save-json", help="path to write full result as JSON (overrides auto-save)")
    ap.add_argument("--no-report", action="store_true", help="skip the auto-generated .txt report")
    args = ap.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    result = swarm.run(
        args.ticker.upper(),
        days=args.days,
        do_debate=not args.no_debate,
        with_options=args.with_options,
        with_rates=args.with_rates,
        with_quant=not args.no_quant,
        on_event=_print_event,
    )

    result_dict = {
        "ticker": result.ticker,
        "snapshot": result.snapshot,
        "spawned": result.spawned,
        "skipped": result.skipped,
        "round1": [v.__dict__ for v in result.round1],
        "round2": [v.__dict__ for v in result.round2],
        "quant": result.quant.__dict__ if result.quant else None,
        "consensus": result.consensus,
    }

    if args.save_json:
        with open(args.save_json, "w") as f:
            json.dump(result_dict, f, indent=2, default=str)
        print(f"\n💾 saved → {args.save_json}")

    if not args.no_report:
        paths = report_module.save_run_artifacts(
            result_dict, ticker=result.ticker, consensus=result.consensus,
        )
        print(f"\n📄 report → {paths['txt']}")
        print(f"💾 data   → {paths['json']}")
        print(f"\n  open {paths['txt']}   # to read the full agent transcript")


if __name__ == "__main__":
    main()
