"""SEC EDGAR — primary-source corporate filings.

Free, no key required. SEC requires a real User-Agent (name + email) per
their fair-use policy: https://www.sec.gov/os/accessing-edgar-data

Pipeline:
  1. ticker → CIK via the public ticker map (cached for the process)
  2. CIK → recent submissions JSON (`data.sec.gov/submissions/CIK{...}.json`)
  3. Filter for material forms (8-K, 10-Q, 10-K, S-1) within `days`
  4. Return canonical dicts that merge straight into ctx.news so the News
     Analyst sees them alongside headlines

We *don't* fetch the body of each filing — that's a per-file XBRL/HTML pull
and expensive. The form type + filing date + a built link is enough signal
for a narrative analyst; the Coordinator can flag anything 8-K-shaped as
high-priority.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from functools import lru_cache

import requests


_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "Option_trading research agent (fernandezangel23@yahoo.com)",
)
_HEADERS = {"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip, deflate"}
_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# Forms worth surfacing. 8-K = material event, 10-Q/10-K = periodic, S-1 =
# IPO, SC 13D/G = activist stake, 4 = insider trade. Skip the noisier ones.
MATERIAL_FORMS = {"8-K", "10-Q", "10-K", "S-1", "SC 13D", "SC 13G", "4"}


@lru_cache(maxsize=1)
def _ticker_to_cik_map() -> dict[str, int]:
    """Pull the SEC's public ticker→CIK map. Cached for the process."""
    resp = requests.get(_TICKER_MAP_URL, headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    return {row["ticker"].upper(): int(row["cik_str"]) for row in payload.values()}


def lookup_cik(ticker: str) -> int | None:
    try:
        return _ticker_to_cik_map().get(ticker.upper())
    except Exception:
        return None


def fetch_recent_filings(ticker: str, days: int = 90, limit: int = 10) -> list[dict]:
    """Return material filings within the last `days`. [] on any failure."""
    cik = lookup_cik(ticker)
    if cik is None:
        return []

    try:
        resp = requests.get(_SUBMISSIONS_URL.format(cik=cik), headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        recent = resp.json().get("filings", {}).get("recent", {})
    except Exception:
        return []

    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    primary_docs = recent.get("primaryDocument") or []
    items_col = recent.get("items") or []

    cutoff = date.today() - timedelta(days=days)
    out: list[dict] = []
    for i, form in enumerate(forms):
        if form not in MATERIAL_FORMS:
            continue
        try:
            fdate = datetime.strptime(dates[i], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            continue
        if fdate < cutoff:
            continue

        accession = accessions[i] if i < len(accessions) else ""
        accession_clean = accession.replace("-", "")
        primary = primary_docs[i] if i < len(primary_docs) else ""
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/{primary}"
            if accession_clean and primary
            else ""
        )
        items = items_col[i] if i < len(items_col) else ""

        title = f"[{form}] {ticker.upper()} filed with SEC"
        if items:
            title += f" — items {items}"

        out.append({
            "title": title,
            "publisher": "SEC EDGAR",
            "url": url,
            "published": fdate.isoformat(),
            "summary": f"Form {form} filed {fdate.isoformat()}." + (f" Items: {items}" if items else ""),
            "form": form,
            "source": "edgar",
        })
        if len(out) >= limit:
            break

    return out
