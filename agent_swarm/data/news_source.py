"""News + corporate-event source.

Free path via yfinance:
  - `Ticker.news`     headlines + publisher + URL (last ~10-30 items)
  - `Ticker.calendar` upcoming earnings date

yfinance has shifted the news payload shape across versions; we defensively
handle both the legacy flat dict and the newer `{"content": {...}}` wrapper.

Returns plain dicts so they slot directly into DataContext.news.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import yfinance as yf


def _coerce_item(raw: dict) -> dict | None:
    """Flatten one news item into our canonical shape."""
    inner = raw.get("content") if isinstance(raw.get("content"), dict) else raw

    title = inner.get("title") or raw.get("title")
    if not title:
        return None

    publisher = (
        (inner.get("provider") or {}).get("displayName")
        if isinstance(inner.get("provider"), dict)
        else inner.get("publisher") or raw.get("publisher")
    )

    url = None
    ct = inner.get("clickThroughUrl") or inner.get("canonicalUrl")
    if isinstance(ct, dict):
        url = ct.get("url")
    url = url or inner.get("link") or raw.get("link")

    ts = inner.get("pubDate") or inner.get("providerPublishTime") or raw.get("providerPublishTime")
    published = None
    if isinstance(ts, (int, float)):
        published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    elif isinstance(ts, str):
        published = ts

    summary = inner.get("summary") or inner.get("description") or ""

    return {
        "title": title.strip(),
        "publisher": (publisher or "").strip(),
        "url": url or "",
        "published": published or "",
        "summary": (summary or "").strip(),
    }


def fetch_news(ticker: str, limit: int = 25) -> list[dict]:
    """Pull recent headlines for `ticker`. Returns [] on any failure."""
    try:
        raw_items = yf.Ticker(ticker).news or []
    except Exception:
        return []

    out: list[dict] = []
    for raw in raw_items[:limit]:
        item = _coerce_item(raw) if isinstance(raw, dict) else None
        if item:
            out.append(item)
    return out


def fetch_earnings_date(ticker: str) -> date | None:
    """Next scheduled earnings date if yfinance has it."""
    try:
        cal: Any = yf.Ticker(ticker).calendar
    except Exception:
        return None

    if cal is None:
        return None

    candidate = None
    if isinstance(cal, dict):
        candidate = cal.get("Earnings Date")
        if isinstance(candidate, list) and candidate:
            candidate = candidate[0]
    else:
        try:
            candidate = cal.loc["Earnings Date"].iloc[0]
        except Exception:
            candidate = None

    if candidate is None:
        return None
    if isinstance(candidate, datetime):
        return candidate.date()
    if isinstance(candidate, date):
        return candidate
    try:
        return datetime.fromisoformat(str(candidate)).date()
    except Exception:
        return None


def headlines_block(news: list[dict], n: int = 15) -> str:
    """Compact text block ready to drop into an LLM prompt.

    Splits SEC EDGAR filings (primary-source, higher signal) from syndicated
    headlines so the analyst can weight them differently.
    """
    if not news:
        return "(no headlines)"

    filings = [i for i in news if i.get("source") == "edgar"]
    headlines = [i for i in news if i.get("source") != "edgar"]

    sections = []
    if filings:
        lines = ["SEC FILINGS (primary source — material events):"]
        for item in filings[:n]:
            when = item.get("published", "")[:10]
            lines.append(f"- [{when}] {item.get('title', '')}")
        sections.append("\n".join(lines))

    if headlines:
        lines = ["NEWS HEADLINES (syndicated):"]
        for item in headlines[:n]:
            when = item.get("published", "")[:10]
            pub = item.get("publisher", "")
            lines.append(f"- [{when}] ({pub}) {item.get('title', '')}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)
