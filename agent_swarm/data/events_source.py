"""Scheduled event source.

This is intentionally a calendar/rules layer, not a raw news firehose. It
combines company earnings with an optional local JSON calendar for macro,
sector, and company events. The JSON path defaults to
`data_cache/events_calendar.json` and can be overridden with
`SWARM_EVENTS_CALENDAR`.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import news_source


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALENDAR_PATH = PROJECT_ROOT / "data_cache" / "events_calendar.json"


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _coerce_importance(value: Any) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 3


def _normalize_event(raw: dict, *, default_source: str = "local_calendar") -> dict | None:
    event_date = _parse_date(raw.get("date"))
    name = str(raw.get("name") or raw.get("title") or "").strip()
    if event_date is None or not name:
        return None

    tickers = raw.get("tickers") or []
    if isinstance(tickers, str):
        tickers = [tickers]

    sectors = raw.get("sectors") or []
    if isinstance(sectors, str):
        sectors = [sectors]

    return {
        "name": name,
        "date": event_date.isoformat(),
        "scope": str(raw.get("scope") or "market").lower(),
        "tickers": [str(t).upper() for t in tickers],
        "sectors": [str(s).lower() for s in sectors],
        "asset_classes": raw.get("asset_classes") or [],
        "importance": _coerce_importance(raw.get("importance")),
        "risk": str(raw.get("risk") or "").strip(),
        "rule_action": str(raw.get("rule_action") or "").strip().lower(),
        "action_window_days": raw.get("action_window_days"),
        "source": str(raw.get("source") or default_source),
    }


def _load_calendar(calendar_path: str | Path | None = None) -> list[dict]:
    path = Path(calendar_path or os.environ.get("SWARM_EVENTS_CALENDAR") or DEFAULT_CALENDAR_PATH)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []

    raw_events = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(raw_events, list):
        return []

    out = []
    for raw in raw_events:
        if isinstance(raw, dict):
            event = _normalize_event(raw)
            if event:
                out.append(event)
    return out


def _event_applies(event: dict, ticker: str) -> bool:
    scope = event.get("scope", "market")
    tickers = set(event.get("tickers") or [])
    if scope in {"market", "macro", "global"}:
        return True
    if ticker.upper() in tickers:
        return True
    # Sector mapping can be added later when the project has a sector source.
    return False


def fetch_events(
    ticker: str,
    *,
    lookahead_days: int = 30,
    include_earnings: bool = True,
    calendar_path: str | Path | None = None,
) -> list[dict]:
    """Return upcoming scheduled events relevant to ticker or the broad market."""
    today = date.today()
    end = today + timedelta(days=lookahead_days)
    ticker = ticker.upper()

    events: list[dict] = []
    if include_earnings:
        earnings_date = news_source.fetch_earnings_date(ticker)
        if earnings_date:
            events.append({
                "name": f"{ticker} earnings",
                "date": earnings_date.isoformat(),
                "scope": "ticker",
                "tickers": [ticker],
                "sectors": [],
                "asset_classes": ["equity", "options"],
                "importance": 5,
                "risk": "single-stock gap risk and implied-volatility repricing",
                "rule_action": "reduce_size",
                "action_window_days": 2,
                "source": "yfinance_calendar",
            })

    events.extend(_load_calendar(calendar_path))

    filtered = []
    for event in events:
        event_date = _parse_date(event.get("date"))
        if event_date is None or event_date < today or event_date > end:
            continue
        if not _event_applies(event, ticker):
            continue
        item = dict(event)
        item["days_away"] = (event_date - today).days
        filtered.append(item)

    return sorted(filtered, key=lambda e: (e["days_away"], -int(e.get("importance", 0)), e["name"]))


def summarize_events(events: list[dict]) -> dict:
    """Compute deterministic event risk metrics for analyst prompts and gates."""
    if not events:
        return {
            "event_count": 0,
            "event_risk_score": 0,
            "nearest_event_days": None,
            "rule_actions": [],
            "events": [],
        }

    max_score = 0
    rule_actions = []
    compact = []
    for event in events:
        importance = _coerce_importance(event.get("importance"))
        days = int(event.get("days_away", 999))
        urgency = 5 if days <= 1 else 4 if days <= 3 else 3 if days <= 7 else 2 if days <= 14 else 1
        score = min(100, importance * 12 + urgency * 8)
        max_score = max(max_score, score)

        action = str(event.get("rule_action") or "").lower()
        action_window = event.get("action_window_days")
        try:
            action_window = int(action_window)
        except (TypeError, ValueError):
            action_window = 3 if action == "reduce_size" else 1
        if action in {"reject", "reduce_size", "watchlist_only"}:
            if days <= action_window:
                rule_actions.append({
                    "action": action,
                    "name": event.get("name", ""),
                    "date": event.get("date", ""),
                    "days_away": days,
                    "importance": importance,
                    "action_window_days": action_window,
                })

        compact.append({
            "name": event.get("name", ""),
            "date": event.get("date", ""),
            "days_away": days,
            "scope": event.get("scope", ""),
            "importance": importance,
            "risk": event.get("risk", ""),
            "rule_action": action,
            "action_window_days": action_window,
            "source": event.get("source", ""),
        })

    return {
        "event_count": len(events),
        "event_risk_score": max_score,
        "nearest_event_days": min(int(e.get("days_away", 999)) for e in events),
        "rule_actions": rule_actions,
        "events": compact[:20],
    }


def events_block(events: list[dict], n: int = 12) -> str:
    if not events:
        return "(no scheduled events)"
    lines = []
    for event in events[:n]:
        lines.append(
            f"- [{event.get('date')}] {event.get('name')} "
            f"({event.get('days_away')}d, importance={event.get('importance')}/5, "
            f"scope={event.get('scope')}) risk={event.get('risk')}"
        )
    return "\n".join(lines)
