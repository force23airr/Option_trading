"""Pretty-print a saved swarm run so you can read what every agent said.

    python -m agent_swarm.tools.report                         # latest run
    python -m agent_swarm.tools.report COIN                    # latest for ticker
    python -m agent_swarm.tools.report --file path/to.json     # specific file
    python -m agent_swarm.tools.report --list                  # list all saved runs
    python -m agent_swarm.tools.report COIN --raw Trend        # full LLM reply for one analyst
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[2] / "data_cache"


def list_runs() -> list[Path]:
    # Look for both old-style (*_swarm*.json) and new-style ({TICKER}_{ts}_*.json) results
    files = list(CACHE_DIR.glob("*_swarm*.json")) + list(CACHE_DIR.glob("*_BEARISH_*.json")) \
            + list(CACHE_DIR.glob("*_BULLISH_*.json")) + list(CACHE_DIR.glob("*_NEUTRAL_*.json"))
    return sorted(set(files), key=lambda p: p.stat().st_mtime)


def find_latest(ticker: str | None) -> Path | None:
    files = list_runs()
    if ticker:
        files = [f for f in files if f.name.upper().startswith(ticker.upper())]
    return files[-1] if files else None


def _wrap(s: str, width: int = 78, indent: str = "      ") -> str:
    import textwrap
    if not s:
        return ""
    return textwrap.fill(s, width=width, initial_indent=indent, subsequent_indent=indent)


_STRUCTURE_SHORTNAMES: list[tuple[str, str]] = [
    ("iron condor", "iron-condor"),
    ("iron butterfly", "iron-butterfly"),
    ("call credit spread", "call-credit-spread"),
    ("put credit spread", "put-credit-spread"),
    ("call debit spread", "call-debit-spread"),
    ("put debit spread", "put-debit-spread"),
    ("credit spread", "credit-spread"),
    ("debit spread", "debit-spread"),
    ("calendar", "calendar"),
    ("diagonal", "diagonal"),
    ("strangle", "strangle"),
    ("straddle", "straddle"),
    ("long call", "long-call"),
    ("long put", "long-put"),
    ("long stock", "long-stock"),
    ("short stock", "short-stock"),
    ("stay flat", "flat"),
    ("no setup", "no-setup"),
]


def structure_short(structure: str) -> str:
    s = (structure or "").lower()
    for needle, short in _STRUCTURE_SHORTNAMES:
        if needle in s:
            return short
    return "trade"


def report_filename(ticker: str, consensus: dict, when: datetime | None = None) -> str:
    """Generate a sortable, descriptive filename for a swarm run report."""
    when = when or datetime.now()
    stance = (consensus.get("consensus_stance") or "neutral").upper()
    structure = consensus.get("suggested_structure") or ""
    short = structure_short(structure)
    ts = when.strftime("%Y-%m-%d_%H%M")
    return f"{ticker.upper()}_{ts}_{stance}_{short}"


def render(data, title: str = "", raw_for: str | None = None, out=None) -> None:
    """Render a swarm result dict (or load from a path) to a writable stream.

    Pass `out=open(path, 'w')` to save to a file; defaults to sys.stdout.
    """
    if out is None:
        out = sys.stdout
    if isinstance(data, (str, Path)):
        path = Path(data)
        data = json.loads(path.read_text())
        title = title or path.name

    def p(*args, **kwargs):
        print(*args, file=out, **kwargs)

    p("=" * 80)
    p(f"  {title or 'swarm run'}   ticker={data['ticker']}")
    p("=" * 80)

    snap = data.get("snapshot", {})
    if snap:
        p("\nSnapshot at run time:")
        for k, v in snap.items():
            if isinstance(v, float):
                p(f"  {k:<14} {v:>12,.2f}")
            else:
                p(f"  {k:<14} {v}")

    if data.get("spawned"):
        p(f"\nSpawned analysts:  {', '.join(data['spawned'])}")
    if data.get("skipped"):
        p(f"Skipped:")
        for s in data["skipped"]:
            p(f"  ✗ {s.get('name','?')}  ({s.get('reason','?')})")

    for round_name in ("round1", "round2"):
        views = data.get(round_name) or []
        if not views:
            continue
        p(f"\n{'─' * 80}")
        p(f"  ROUND {round_name[-1]}  ({len(views)} analysts)")
        p("─" * 80)
        for v in views:
            provider = v.get("provider", "?")
            model = v.get("model", "?")
            p(f"\n  ▸ {v['analyst']}  [{provider}/{model}]  →  {v['stance']}  ({v['confidence']:.0%})")
            p(_wrap(f"summary: {v['summary']}"))
            if v.get("pattern"):
                p(f"      pattern: {v['pattern']}")
            if v.get("horizon"):
                p(f"      horizon: {v['horizon']}")
            if v.get("observations"):
                p("      observations:")
                for o in v["observations"]:
                    p(_wrap(f"• {o}", indent="        "))
            if raw_for and raw_for.lower() in v["analyst"].lower():
                p(f"\n      ── raw LLM reply ──")
                for line in (v.get("raw") or "").splitlines():
                    p(f"        {line}")

    quant = data.get("quant")
    if quant:
        p(f"\n{'═' * 80}")
        p(f"  ⚡ QUANT STRATEGIST  [{quant.get('provider','?')}/{quant.get('model','?')}]")
        p("═" * 80)
        p(f"\n  Stance: {quant.get('stance','?')}  Confidence: {quant.get('confidence', 0):.0%}")
        p(f"  Selected structure: {quant.get('pattern','?')}")
        if quant.get("summary"):
            p(_wrap(f"\n{quant['summary']}", indent="  "))
        if quant.get("observations"):
            p("\n  Trade ticket:")
            for o in quant["observations"]:
                p(_wrap(f"• {o}", indent="    "))
        if raw_for and raw_for.lower() in "quant strategist":
            p(f"\n  ── raw LLM reply ──")
            for line in (quant.get("raw") or "").splitlines():
                p(f"    {line}")

    c = data.get("consensus") or {}
    if c:
        p(f"\n{'═' * 80}")
        p(f"  COORDINATOR CONSENSUS:  "
          f"{str(c.get('consensus_stance','?')).upper()}  "
          f"({c.get('consensus_confidence', 0):.0%})")
        p("═" * 80)
        if c.get("headline"):
            p(_wrap(c["headline"], indent="  "))
        if c.get("key_patterns"):
            p(f"\n  Patterns:")
            for pat in c["key_patterns"]:
                p(_wrap(f"• {pat}", indent="    "))
        if c.get("agreements"):
            p(f"\n  Agreements:")
            for a in c["agreements"]:
                p(_wrap(f"• {a}", indent="    "))
        if c.get("disagreements"):
            p(f"\n  Disagreements:")
            for d in c["disagreements"]:
                p(_wrap(f"• {d}", indent="    "))
        p(f"\n  Horizon:   {c.get('horizon', '')}")
        p(f"  Structure: {c.get('suggested_structure', '')}")
        if c.get("rationale"):
            p(f"\n  Rationale:")
            p(_wrap(c["rationale"], indent="    "))
        p()


def save_run_artifacts(result_dict: dict, ticker: str, consensus: dict, when=None) -> dict:
    """Auto-save the run as both .json (machine) and .txt (human) in data_cache/.

    Returns {'json': Path, 'txt': Path} with the paths written.
    Filename includes ticker, timestamp, stance, and structure for sortability.
    """
    when = when or datetime.now()
    base = report_filename(ticker, consensus, when=when)
    CACHE_DIR.mkdir(exist_ok=True)
    json_path = CACHE_DIR / f"{base}.json"
    txt_path = CACHE_DIR / f"{base}.txt"

    json_path.write_text(json.dumps(result_dict, indent=2, default=str))
    with open(txt_path, "w") as fh:
        render(result_dict, title=base, out=fh)

    return {"json": json_path, "txt": txt_path}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="?", help="show latest run for this ticker")
    ap.add_argument("--file", help="path to a specific saved run JSON")
    ap.add_argument("--list", action="store_true", help="list all saved runs and exit")
    ap.add_argument("--raw", help="show full raw LLM reply for an analyst whose name contains this")
    args = ap.parse_args()

    if args.list:
        runs = list_runs()
        if not runs:
            print("No saved runs in data_cache/")
            return
        print(f"{len(runs)} saved run(s):")
        for r in runs:
            print(f"  {r.name:<40} {r.stat().st_size // 1024:>5} KB")
        return

    path = Path(args.file) if args.file else find_latest(args.ticker)
    if not path or not path.exists():
        print("No saved runs found. Run: python -m agent_swarm.tools.run_swarm COIN --with-options --save-json data_cache/COIN.json")
        return
    render(path, raw_for=args.raw)


if __name__ == "__main__":
    main()
