"""Run the pattern-analysis swarm on one ticker, with live event printing.

    python -m agent_swarm.tools.run_swarm COIN
    python -m agent_swarm.tools.run_swarm COIN --days 120 --no-debate
    python -m agent_swarm.tools.run_swarm COIN --provider deepseek
"""
from __future__ import annotations

import argparse
import json
import os

from agent_swarm.core import swarm


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
        print("   chain empty (off-hours?) — skipping Options Analyst")
    elif et == "options:error":
        print(f"   options fetch failed: {payload['error']}")
    elif et == "round:start":
        print(f"\n🧠 ROUND {payload['round']}: {', '.join(payload['analysts'])}")
    elif et == "analyst:view":
        v = payload["view"]
        line = f"   [{v.analyst:<24}] {v.stance:<8} {v.confidence:>4.0%}  {v.summary}"
        if v.pattern:
            line += f"   pattern={v.pattern!r}"
        print(line)
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
    ap.add_argument("--with-options", action="store_true", help="pull live OPRA chain (~$0.18) and add Options Analyst")
    ap.add_argument("--provider", help="default LLM provider (anthropic|deepseek|openai|openrouter)")
    ap.add_argument("--model", help="default LLM model")
    ap.add_argument("--save-json", help="path to write full result as JSON")
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
        on_event=_print_event,
    )

    if args.save_json:
        with open(args.save_json, "w") as f:
            json.dump({
                "ticker": result.ticker,
                "snapshot": result.snapshot,
                "round1": [v.__dict__ for v in result.round1],
                "round2": [v.__dict__ for v in result.round2],
                "consensus": result.consensus,
            }, f, indent=2, default=str)
        print(f"\n💾 saved → {args.save_json}")


if __name__ == "__main__":
    main()
