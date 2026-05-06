"""Load and index saved swarm runs from data_cache/."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[3] / "data_cache"

# Filename pattern emitted by tools/report.report_filename:
#   {TICKER}_{YYYY-MM-DD}_{HHMM}_{STANCE}_{structure-slug}.json
_FNAME_RE = re.compile(
    r"^(?P<ticker>[A-Z\.\-]+)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{4})_"
    r"(?P<stance>BULLISH|BEARISH|NEUTRAL)_(?P<structure>[a-z\-]+)\.json$"
)


def parse_filename(path: Path) -> dict | None:
    m = _FNAME_RE.match(path.name)
    if not m:
        return None
    g = m.groupdict()
    return {
        "ticker": g["ticker"],
        "stance": g["stance"],
        "structure": g["structure"],
        "timestamp": datetime.strptime(f"{g['date']} {g['time']}", "%Y-%m-%d %H%M"),
    }


def list_runs() -> list[dict]:
    """Return metadata for every saved run, newest first."""
    if not CACHE_DIR.exists():
        return []
    out = []
    for path in CACHE_DIR.glob("*.json"):
        meta = parse_filename(path)
        if not meta:
            continue
        meta["path"] = path
        meta["mtime"] = path.stat().st_mtime
        out.append(meta)
    return sorted(out, key=lambda m: m["mtime"], reverse=True)


def load_run(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def load_decision(data: dict) -> str:
    """Best-effort extraction of the hard-rule decision from a run dict."""
    gate = data.get("hard_rules") or (data.get("consensus") or {}).get("hard_rules") or {}
    return str(gate.get("decision") or "—").lower()


def load_consensus_stance(data: dict) -> str:
    return str((data.get("consensus") or {}).get("consensus_stance") or "—").lower()
