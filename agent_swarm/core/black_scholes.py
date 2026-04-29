"""Black-Scholes pricing, greeks, implied & realized volatility.

Pure-Python (numpy + math); no external deps beyond what's already installed.
Inputs use plain floats / arrays — no pandas in here.

Conventions:
    S  spot price
    K  strike
    T  time to expiry in YEARS  (e.g. 30 days = 30/365)
    r  risk-free rate as decimal (0.045 = 4.5%)
    q  continuous dividend yield as decimal (default 0)
    sigma  volatility as decimal (0.40 = 40%)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


SQRT_2PI = math.sqrt(2 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


def d1_d2(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> tuple[float, float]:
    if T <= 0 or sigma <= 0:
        return float("nan"), float("nan")
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def price(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0, kind: str = "call") -> float:
    if T <= 0:
        return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    d1, d2 = d1_d2(S, K, T, r, sigma, q)
    if kind == "call":
        return S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * math.exp(-q * T) * _norm_cdf(-d1)


@dataclass
class Greeks:
    price: float
    delta: float
    gamma: float
    vega: float    # per 1.00 change in vol (i.e. per 100 vol points). Divide by 100 for per-1%-vol.
    theta: float   # per year. Divide by 365 for per-day.
    rho: float     # per 1.00 change in rate. Divide by 100 for per-1%-rate.


def greeks(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0, kind: str = "call") -> Greeks:
    p = price(S, K, T, r, sigma, q, kind)
    if T <= 0 or sigma <= 0:
        return Greeks(p, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"))
    d1, d2 = d1_d2(S, K, T, r, sigma, q)
    pdf_d1 = _norm_pdf(d1)

    if kind == "call":
        delta = math.exp(-q * T) * _norm_cdf(d1)
        rho = K * T * math.exp(-r * T) * _norm_cdf(d2)
        theta = (
            -S * math.exp(-q * T) * pdf_d1 * sigma / (2 * math.sqrt(T))
            - r * K * math.exp(-r * T) * _norm_cdf(d2)
            + q * S * math.exp(-q * T) * _norm_cdf(d1)
        )
    else:
        delta = -math.exp(-q * T) * _norm_cdf(-d1)
        rho = -K * T * math.exp(-r * T) * _norm_cdf(-d2)
        theta = (
            -S * math.exp(-q * T) * pdf_d1 * sigma / (2 * math.sqrt(T))
            + r * K * math.exp(-r * T) * _norm_cdf(-d2)
            - q * S * math.exp(-q * T) * _norm_cdf(-d1)
        )

    gamma = math.exp(-q * T) * pdf_d1 / (S * sigma * math.sqrt(T))
    vega = S * math.exp(-q * T) * pdf_d1 * math.sqrt(T)
    return Greeks(p, delta, gamma, vega, theta, rho)


def implied_vol(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    q: float = 0.0,
    kind: str = "call",
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    """Newton-Raphson with bisection fallback. Returns nan if it can't converge."""
    intrinsic = max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    if market_price < intrinsic - 1e-8 or T <= 0:
        return float("nan")

    sigma = 0.5
    for _ in range(max_iter):
        p = price(S, K, T, r, sigma, q, kind)
        diff = p - market_price
        if abs(diff) < tol:
            return sigma
        d1, _ = d1_d2(S, K, T, r, sigma, q)
        vega = S * math.exp(-q * T) * _norm_pdf(d1) * math.sqrt(T)
        if vega < 1e-10:
            break
        sigma = max(1e-4, sigma - diff / vega)

    lo, hi = 1e-4, 5.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if price(S, K, T, r, mid, q, kind) > market_price:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            return mid
    return float("nan")


def realized_vol(closes: pd.Series, window: int = 30, annualize: int = 252) -> float:
    """Annualized close-to-close vol over the last `window` returns."""
    rets = np.log(closes / closes.shift(1)).dropna().tail(window)
    if len(rets) < 2:
        return float("nan")
    return float(rets.std(ddof=1) * math.sqrt(annualize))


def realized_vol_series(closes: pd.Series, window: int = 30, annualize: int = 252) -> pd.Series:
    rets = np.log(closes / closes.shift(1))
    return rets.rolling(window).std(ddof=1) * math.sqrt(annualize)
