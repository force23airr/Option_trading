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


def _conf_bar(conf: float | None, cells: int = 5) -> str:
    try:
        c = float(conf or 0)
    except (TypeError, ValueError):
        c = 0.0
    filled = max(0, min(cells, round(c * cells)))
    return "█" * filled + "░" * (cells - filled)


_STANCE_ALIASES = {
    "directional_bullish": "dir-bull",
    "directional_bearish": "dir-bear",
}


def _stance_short(view: dict, max_len: int = 10) -> str:
    s = (view.get("stance") or "?").lower()
    s = _STANCE_ALIASES.get(s, s)
    return s[:max_len]


_SENTENCE_SPLIT = re.compile(r"\.(?=\s|$)")


def _summary_short(view: dict, width: int = 38) -> str:
    s = (view.get("summary") or "").strip()
    if not s:
        return ""
    # Split on period followed by whitespace/end so decimals (29.41) don't break
    first = _SENTENCE_SPLIT.split(s, maxsplit=1)[0].strip()
    return (first[: width - 1] + "…") if len(first) > width else first


def _ticket_field(observations: list, needle: str) -> str:
    for o in observations or []:
        if needle.lower() in o.lower():
            return o.split(":", 1)[-1].strip()
    return ""


def render_verdict_panel(data: dict, out=None) -> None:
    """At-a-glance panel: every analyst's stance + gates + final disposition.

    Prints both at the top of the saved .txt report and on the live CLI after
    the swarm finishes. The detailed transcript still follows below it.
    """
    if out is None:
        out = sys.stdout

    def p(*args, **kwargs):
        print(*args, file=out, **kwargs)

    consensus = data.get("consensus") or {}
    quant = data.get("quant")
    gate = data.get("hard_rules") or consensus.get("hard_rules") or {}
    views = data.get("round2") or data.get("round1") or []

    ticker = data.get("ticker", "?")
    final_stance = str(consensus.get("consensus_stance", "?")).upper()
    final_conf = consensus.get("consensus_confidence", 0) or 0

    p("═" * 80)
    header = f"  AGENT VERDICTS — {ticker}"
    suffix = f"CONSENSUS: {final_stance} {final_conf:.0%}"
    pad = max(1, 80 - len(header) - len(suffix) - 2)
    p(f"{header}{' ' * pad}{suffix}  ")
    p("═" * 80)

    for v in views:
        name = v.get("analyst", "?")
        stance = _stance_short(v)
        try:
            conf = float(v.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        bar = _conf_bar(conf)
        summary = _summary_short(v)
        p(f"  {name:<22} {bar}  {stance:<10} {conf:>4.0%}  {summary}")

    p("  " + "─" * 76)

    if quant:
        obs = quant.get("observations") or []
        delta = _ticket_field(obs, "net_delta")
        max_loss = _ticket_field(obs, "max loss")
        structure = (quant.get("pattern") or "?").lstrip("# ").strip() or "?"
        delta_str = f"Δ{delta}" if delta else "Δ?"
        line = f"  {'Quant Strategist':<22} {delta_str:<10}  {structure}"
        if max_loss:
            line += f"   max loss {max_loss}"
        p(line)

    if consensus.get("conflict_flag"):
        if consensus.get("ticket_substituted"):
            mark = "↻ substituted"
        else:
            mark = "⚠ flagged"
        note = consensus.get("conflict_note", "")
        p(f"  {'Reconcile':<22} {mark}")
        if note:
            p(_wrap(note, indent="                           "))
    elif quant:
        p(f"  {'Reconcile':<22} ✓ aligned")

    decision = ""
    if gate:
        decision = str(gate.get("decision", "?")).upper()
        size = gate.get("position_size_multiplier", 1.0) or 0.0
        marks = {
            "REJECT": "✗ REJECT",
            "APPROVE": "✓ APPROVE",
            "APPROVE_WITH_REDUCED_SIZE": f"~ reduce → x{size:.2f}",
            "NOT_EVALUATED": "— not evaluated",
        }
        mark = marks.get(decision, decision)
        p(f"  {'Hard Rules':<22} {mark}")
        for b in (gate.get("hard_blocks") or []):
            p(f"  {'':<22}   • {b}")
        for a in (gate.get("adjustments") or []):
            p(f"  {'':<22}   • {a}")

    p("  " + "─" * 76)

    if gate and gate.get("trade_allowed") is False:
        final_line = (
            f"FINAL: trade BLOCKED  "
            f"(consensus {final_stance.lower()} {final_conf:.0%}; gate {decision.lower() or '—'})"
        )
    elif gate and gate.get("trade_allowed") and (gate.get("position_size_multiplier") or 0) < 1.0:
        final_line = (
            f"FINAL: trade APPROVED at reduced size  "
            f"(consensus {final_stance.lower()} {final_conf:.0%})"
        )
    elif gate and gate.get("trade_allowed"):
        final_line = (
            f"FINAL: trade APPROVED  "
            f"(consensus {final_stance.lower()} {final_conf:.0%})"
        )
    else:
        final_line = f"FINAL: consensus {final_stance.lower()} {final_conf:.0%} (no trade ticket)"
    p(f"  {final_line}")
    p("═" * 80)
    p()


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
    p()
    render_verdict_panel(data, out=out)

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

    events = data.get("events") or []
    event_summary = data.get("event_summary") or {}
    if events:
        p(f"\n{'═' * 80}")
        p(f"  SCHEDULED EVENTS:  {len(events)} event(s), risk score {event_summary.get('event_risk_score', 0)}")
        p("═" * 80)
        for event in events[:12]:
            p(_wrap(
                f"• {event.get('date')} ({event.get('days_away')}d) "
                f"{event.get('name')} — importance {event.get('importance')}/5; "
                f"{event.get('risk', '')}",
                indent="    ",
            ))

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

    gate = data.get("hard_rules")
    if not gate and c:
        gate = c.get("hard_rules")
    if gate:
        p(f"\n{'═' * 80}")
        p(f"  HARD RULES:  {str(gate.get('decision', '?')).upper()}")
        p("═" * 80)
        p(_wrap(gate.get("summary", ""), indent="  "))
        p(f"  Trade allowed: {gate.get('trade_allowed')}  Size x{gate.get('position_size_multiplier', 0):.2f}")
        if gate.get("hard_blocks"):
            p(f"\n  Blocks:")
            for block in gate["hard_blocks"]:
                p(_wrap(f"• {block}", indent="    "))
        if gate.get("adjustments"):
            p(f"\n  Adjustments:")
            for adj in gate["adjustments"]:
                p(_wrap(f"• {adj}", indent="    "))
        if gate.get("notes"):
            p(f"\n  Notes:")
            for note in gate["notes"]:
                p(_wrap(f"• {note}", indent="    "))
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
