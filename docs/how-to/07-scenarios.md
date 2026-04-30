# Scenarios — what to run for each kind of data

Quick lookup: pick the row that matches your input, copy the command.

All commands assume `cwd = /Users/angelfernandez/Option_trading` and use
`/opt/anaconda3/bin/python`.

## Stock OHLCV — single ticker

### Dataset auto-routing (Databento)

By default the system picks the right Databento dataset:

| Ticker type | Auto-routes to | Note |
|---|---|---|
| Nasdaq names (AAPL, NVDA, COIN, MSTR, TSLA, etc.) | `XNAS.ITCH` | Full Nasdaq tape |
| NYSE names (JPM, BAC, GS, JNJ, XOM, PCG, V, MA, T, WMT, etc.) | `XNYS.PILLAR` | NYSE primary venue, real volumes |

To override:

```
python -m agent_swarm.tools.view_data SOMETICKER --dataset DBEQ.BASIC
```

If neither default works (e.g. an exotic ETF), the system silently falls back
to yfinance.

### 1 year of history (default depth)

```
python -m agent_swarm.tools.run_swarm AAPL --days 365
```
- **Spawns:** Trend, Pattern, Volume, Volatility, MeanRev, Coordinator (6 agents)
- **LLM calls:** 8 DeepSeek + 3 Claude
- **Cost:** ~$0.05–0.10  •  **Time:** 25–40s

### 5 years of history (best quality, MA200 + 52w fully populated)

```
python -m agent_swarm.tools.run_swarm AAPL --days 1825
```
- **Same agents as above.** Same LLM call count and cost.
- **What you gain:** MA200 + 52w extremes + multi-cycle trend reads — Trend Analyst output dramatically better.

### Equity + macro rates context

```
python -m agent_swarm.tools.run_swarm AAPL --days 1825 --with-rates
```
- **Adds:** Macro Rates Analyst (yield curve → ticker pressure)
- **LLM calls:** +2 DeepSeek (×2 rounds)  •  **Extra cost:** ~$0.005

### Full stack — equity + options + rates + Quant Strategist

```
python -m agent_swarm.tools.run_swarm AAPL --days 1825 --with-options --with-rates
```
- **Spawns:** all 7 specialists + Quant Strategist + Coordinator (9 agents)
- **Adds:** Options Analyst (DeepSeek), ⚡ Quant Strategist (DeepSeek-R1) with concrete trade ticket
- **Cost:** ~$0.30 total ($0.18 OPRA + ~$0.10 LLM)  •  **Time:** 90–150s
- **Note:** OPRA chain is meaningful only during/near US market hours

### Cheapest possible run (single-pass, no debate, no Quant)

```
python -m agent_swarm.tools.run_swarm AAPL --days 365 --no-debate --no-quant
```
- **Cost:** ~$0.02  •  **Time:** 10–20s

### Force everything through DeepSeek

```
python -m agent_swarm.tools.run_swarm AAPL --days 1825 --provider deepseek
```
- **Cost:** ~$0.02 (cheapest LLM mix)

## Futures (CME via Databento GLBX.MDP3)

### WTI crude oil

```
python -m agent_swarm.tools.run_swarm CL.c.0 --days 365   # ⚠ may not work — see below
```

The swarm currently uses the equity OHLCV path; for futures use the standalone tool:

```
python -m agent_swarm.tools.wti_demo --futures --days 365
```
- **Pulls:** WTI front-month + realized vol + Black-Scholes pricer demo
- **No LLM cost** — pure data + math display

For other futures (NG, gold, S&P, Nasdaq), use the Python API directly:

```python
from agent_swarm.data import databento_source as ds
df = ds.fetch_futures("NG.c.0", days=365)   # natural gas
df = ds.fetch_futures("GC.c.0", days=365)   # gold
df = ds.fetch_futures("ES.c.0", days=365)   # E-mini S&P
df = ds.fetch_futures("NQ.c.0", days=365)   # E-mini Nasdaq
```

## ETFs

### Sector ETF or commodity ETF (USO, GLD, TLT, etc.)

```
python -m agent_swarm.tools.run_swarm USO --days 1825
```
- Same agents as a stock. **Skip `--with-options`** if the ETF has thin chains.

### Treasury / bond ETF

```
python -m agent_swarm.tools.run_swarm TLT --days 1825 --with-rates
```
- **Why `--with-rates`:** TLT/IEF/SHY are duration plays — Macro Rates Analyst is the most relevant agent.

## Yield curve only (rates without a swarm)

No CLI for this yet. Use the Python API:

```python
from agent_swarm.data import macro_source
curve = macro_source.fetch_yield_curve(days=90)
print(curve)
print(macro_source.yield_curve_summary(curve))
```

## Options chain — no swarm, just data

```
python -m agent_swarm.tools.option_chain COIN --save
```
- Pulls live OPRA chain, computes IV + greeks for every contract, saves CSV
- **Cost:** ~$0.18 (OPRA only, no LLM calls)

### Cost preview before paying

```
python -m agent_swarm.tools.opra_check
python -m agent_swarm.tools.opra_check --pull COIN
```

## Just look at the data (no analysis at all)

```
python -m agent_swarm.tools.view_data COIN --days 365 --csv
```
- Pulls OHLCV + indicators + ASCII chart, optionally saves CSV
- **Cost:** $0 (no LLM)  •  **Time:** seconds

## Watchlist — run multiple tickers

```bash
for t in COIN HOOD CRCL TSLA NVDA; do
    python -m agent_swarm.tools.run_swarm $t --days 1825 --with-options
done
ls -lt data_cache/*.txt | head
```
- **Cost:** ~$0.30 × 5 = **~$1.50** for full options analysis on each
- Reports auto-saved with sortable filenames; `ls -lt` shows newest first

### Cheaper watchlist (no options chain)

```bash
for t in COIN HOOD CRCL TSLA NVDA; do
    python -m agent_swarm.tools.run_swarm $t --days 1825 --with-rates
done
```
- **Cost:** ~$0.07 × 5 = **~$0.35** (no OPRA, just LLM + free yield curve)

## Compare two providers on the same ticker

```bash
python -m agent_swarm.tools.run_swarm COIN --provider anthropic \
    --save-json data_cache/COIN_anthropic.json
python -m agent_swarm.tools.run_swarm COIN --provider deepseek \
    --save-json data_cache/COIN_deepseek.json
```
Then read both with `python -m agent_swarm.tools.report --file ...json`.

## Read a past run

```
python -m agent_swarm.tools.report COIN              # latest COIN run
python -m agent_swarm.tools.report --list            # all saved runs
python -m agent_swarm.tools.report COIN --raw "Quant"  # raw R1 reply
```

## Cheat sheet — pick by goal

| Goal | Command |
|---|---|
| First time, just verify everything works | `python -m agent_swarm.tools.view_data COIN --days 60` |
| Quick technical read on a stock | `python -m agent_swarm.tools.run_swarm AAPL --days 1825` |
| With rate-regime context (still cheap) | `... --with-rates` |
| Full options analysis with trade ticket | `... --with-options --with-rates` |
| Daily watchlist, full analysis | `for t in ...; do ... --with-options; done` |
| Just raw data → CSV | `python -m agent_swarm.tools.view_data TICKER --days N --csv` |
| Just options chain → CSV | `python -m agent_swarm.tools.option_chain TICKER --save` |
| Inspect a past run | `python -m agent_swarm.tools.report TICKER` |

## What's NOT supported yet (and what to do instead)

| You want | Status | Workaround |
|---|---|---|
| Dump your own CSV through the swarm | ❌ no `--from-csv` flag yet | Edit `core/data.py:fetch_ohlcv` to read a path |
| Run the swarm directly on `CL.c.0` | ❌ swarm assumes equity OHLCV path | Use `wti_demo --futures` for now |
| Crypto spot prices | ❌ not wired | Use COIN/MSTR equity proxies |
| Intraday / minute bars | ❌ daily only | Pass `schema="ohlcv-1m"` to `databento_source.fetch_ohlcv` directly |
| Earnings calendar | ❌ not wired | Check externally before running |
