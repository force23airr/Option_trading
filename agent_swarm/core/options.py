"""Option chain construction + IV.

Parse OCC symbols, build a chain snapshot from a quote DataFrame, and invert
mid prices through Black-Scholes to get implied vol.

OCC option symbol format (21 chars):
    ROOT (1-6, left-padded with spaces) + YYMMDD + C/P + strike*1000 (8 digits)

Example: 'COIN  260918C00200000'
    root='COIN', expiry=2026-09-18, right='C', strike=200.00
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pandas as pd

from . import black_scholes as bs


_OCC_RE = re.compile(r"^(?P<root>[A-Z0-9.]+)\s*(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<right>[CP])(?P<strike>\d{8})$")


@dataclass
class OCCSymbol:
    raw: str
    root: str
    expiry: date
    right: str       # 'C' or 'P'
    strike: float


def parse_occ(symbol: str) -> OCCSymbol | None:
    """Parse an OCC option symbol. Returns None if it doesn't match."""
    s = symbol.strip()
    s_compact = re.sub(r"\s+", "", s)
    m = _OCC_RE.match(s_compact)
    if not m:
        return None
    g = m.groupdict()
    yy, mm, dd = int(g["yy"]), int(g["mm"]), int(g["dd"])
    year = 2000 + yy if yy < 80 else 1900 + yy
    return OCCSymbol(
        raw=symbol,
        root=g["root"],
        expiry=date(year, mm, dd),
        right=g["right"],
        strike=int(g["strike"]) / 1000.0,
    )


def latest_quote_per_contract(quotes: pd.DataFrame) -> pd.DataFrame:
    """Collapse a streaming quote df into one row per contract (the most recent)."""
    if quotes.empty or "symbol" not in quotes.columns:
        return pd.DataFrame()
    df = quotes.sort_index().groupby("symbol").tail(1).copy()

    bid_col = next((c for c in ("bid_px_00", "bid_px") if c in df.columns), None)
    ask_col = next((c for c in ("ask_px_00", "ask_px") if c in df.columns), None)
    if bid_col is None or ask_col is None:
        raise ValueError(f"no bid/ask columns in quote df. cols={df.columns.tolist()}")

    df = df.rename(columns={bid_col: "bid", ask_col: "ask"})
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    return df.reset_index().rename(columns={df.index.name or "ts_recv": "ts"})


def build_chain(
    quotes: pd.DataFrame,
    spot: float,
    rate: float = 0.045,
    asof: date | None = None,
) -> pd.DataFrame:
    """Build a contract-level option chain with IV + greeks.

    Returns a DataFrame with columns:
        symbol, root, expiry, right, strike, dte, bid, ask, mid, iv,
        delta, gamma, vega, theta
    """
    snap = latest_quote_per_contract(quotes)
    if snap.empty:
        return snap

    asof = asof or datetime.now(timezone.utc).date()
    rows = []
    for _, row in snap.iterrows():
        occ = parse_occ(row["symbol"])
        if not occ:
            continue
        bid, ask, mid = float(row["bid"]), float(row["ask"]), float(row["mid"])
        if mid <= 0 or bid <= 0 or ask <= 0:
            continue
        dte = (occ.expiry - asof).days
        if dte <= 0:
            continue
        T = dte / 365.0
        kind = "call" if occ.right == "C" else "put"
        try:
            iv = bs.implied_vol(mid, spot, occ.strike, T, rate, kind=kind)
            g = bs.greeks(spot, occ.strike, T, rate, iv, kind=kind) if iv == iv else None
        except Exception:
            iv, g = float("nan"), None
        rows.append({
            "symbol": occ.raw,
            "root": occ.root,
            "expiry": occ.expiry,
            "right": occ.right,
            "strike": occ.strike,
            "dte": dte,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "iv": iv,
            "delta": g.delta if g else float("nan"),
            "gamma": g.gamma if g else float("nan"),
            "vega": g.vega / 100.0 if g else float("nan"),
            "theta": g.theta / 365.0 if g else float("nan"),
        })

    chain = pd.DataFrame(rows)
    if chain.empty:
        return chain
    return chain.sort_values(["expiry", "right", "strike"]).reset_index(drop=True)


def near_atm(chain: pd.DataFrame, spot: float, expiry: date | None = None, n: int = 10) -> pd.DataFrame:
    """Slice the chain near the money. If `expiry` given, only that expiry."""
    if expiry is not None:
        chain = chain[chain["expiry"] == expiry]
    chain = chain.copy()
    chain["dist"] = (chain["strike"] - spot).abs()
    return chain.sort_values("dist").head(n).drop(columns="dist").sort_values(["expiry", "right", "strike"])
