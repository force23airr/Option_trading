# What this program does (today, honestly)

Last updated: 2026-04-29.

## In one sentence

You give it a US-listed ticker. It pulls live equity + options + macro data,
runs 7 specialist LLM analysts who debate, picks a defined-risk options
structure with hard P&L numbers, and saves a human-readable transcript.

## What's actually working

### Data sources (wired and tested)

| Source | What it gives you | Cost |
|---|---|---|
| **Databento equities** (XNAS.ITCH default) | Daily OHLCV for any US single-name | Pennies |
| **Databento futures** (GLBX.MDP3) | CL.c.0 (WTI), NG.c.0 (natgas), GC.c.0 (gold), ES/NQ.c.0 (index) | Pennies |
| **Databento OPRA** (OPRA.PILLAR) | Live US option chains — bid/ask/IV/greeks per contract | ~$0.18 per ticker per day at `cbbo-1m` |
| **yfinance** (fallback) | OHLCV when Databento not available; news; macro tickers | Free |
| **Treasury yields** (yfinance proxies: ^IRX/^FVX/^TNX/^TYX) | 3M / 5Y / 10Y / 30Y rates + curve spreads | Free |

### Analysts (LLM-powered, run conditionally)

7 specialists fan out in parallel, do 2 rounds of debate (independent → see
peers), then a coordinator synthesizes. Provider routing is per-agent.

| Analyst | Spawns when | LLM |
|---|---|---|
| Trend Analyst | Always | DeepSeek V3 |
| Pattern Analyst | Always | Claude (visual intuition) |
| Volume Analyst | Always | DeepSeek V3 |
| Volatility Analyst | Always | DeepSeek V3 |
| Mean Reversion Analyst | Always | DeepSeek V3 |
| Macro Rates Analyst | `--with-rates` | DeepSeek V3 |
| Options Analyst | `--with-options` | DeepSeek V3 |
| **Quant Strategist** ⚡ (power agent) | `--with-options` | **DeepSeek-R1 reasoning** |
| Coordinator (synthesizer) | Always at end | Claude |

The Quant Strategist is the power move: pre-computes 4 candidate option
structures from the live chain (iron condor, put credit spread, call credit
spread, call debit spread) with all greeks/breakevens/POP, then DeepSeek-R1
picks one and produces a trade ticket. Math is in code; LLM only chooses, so
it can't hallucinate numbers.

### Math primitives (pure Python in `core/`)

- `signals.py` — RSI (14-period Wilder), MA20/50/200, 52-week high/low, volume averages
- `black_scholes.py` — closed-form pricer, all greeks (Δ Γ V Θ ρ), Newton-Raphson IV solver, realized vol (annualized log-return σ × √252)
- `options.py` — OCC symbol parser, chain builder, near-ATM slicing

### Outputs (auto-saved per run)

Every swarm run drops two files in `data_cache/`:

```
{TICKER}_{YYYY-MM-DD_HHMM}_{STANCE}_{structure}.txt   ← human-readable transcript
{TICKER}_{YYYY-MM-DD_HHMM}_{STANCE}_{structure}.json  ← machine-readable raw data
```

Example: `COIN_2026-04-29_1942_BEARISH_call-credit-spread.txt`

## What's NOT working / not built yet

- **No backtester.** The swarm produces calls but there's no system to walk it
  forward through history and score consensus vs. realized P&L.
- **No dashboard.** Output is terminal + file only. No browser UI yet.
  (Streamlit prototype is on the roadmap.)
- **No watchlist runner.** Run one ticker at a time; no batch+rank command.
- **No earnings calendar.** Swarm has no idea an event is coming.
- **No options on futures.** OPRA covers US equity options only.
- **No crypto spot data.** Coinbase/Kraken not wired.
- **No streaming/intraday.** Daily bars only by default.
- **Hardcoded risk-free rate at 4.5%.** Should pull from FRED 3-month T-bill.
- **No first-class tests.** Code works but isn't pinned by an automated test suite.

## Costs per run (rough)

| Run type | OPRA | LLM (DeepSeek + Claude) | Total |
|---|---|---|---|
| Equity-only (`run_swarm TSLA`) | $0 | ~$0.02-0.05 | **~$0.05** |
| With options (`--with-options`) | ~$0.18 | ~$0.05-0.10 | **~$0.25** |
| With options + rates (`--with-options --with-rates`) | ~$0.18 | ~$0.07-0.12 | **~$0.30** |

A daily watchlist of 5 tickers with full features ≈ **$1.50/day** in API costs.

## Best-fit data right now

Liquid US single-name stocks with active options markets, holding period 1-30
days, ≥ 1 year of history. See [reference/data-sources.md](reference/data-sources.md)
for the full sweet-spot table and what doesn't fit.
