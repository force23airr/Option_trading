# Running the swarm

The main command is `agent_swarm.tools.run_swarm`. Everything else builds on top.

> **Looking for "I have X data — what do I run?"** See [07-scenarios.md](07-scenarios.md) — a one-page lookup by data type.

## The simplest run

```
/opt/anaconda3/bin/python -m agent_swarm.tools.run_swarm COIN
```

This runs:
- 5 chart analysts (Trend, Pattern, Volume, Volatility, Mean Reversion)
- 2 rounds (independent → debate)
- Coordinator synthesizes
- Auto-saves report + JSON to `data_cache/`

## Adding the options layer

```
... run_swarm COIN --with-options
```

Adds:
- Live OPRA chain pull (~$0.18)
- Options Analyst (IV vs realized, term structure, skew)
- **Quant Strategist** ⚡ (DeepSeek-R1 produces a concrete trade ticket)
- Coordinator now anchors structure to the Quant ticket

## Adding the rates layer

```
... run_swarm COIN --with-options --with-rates
```

Adds:
- Treasury yield curve (3M / 5Y / 10Y / 30Y)
- Macro Rates Analyst (translates rate regime to directional pressure)

## All flags

| Flag | Default | What it does |
|---|---|---|
| `TICKER` | required | The symbol to analyze (positional) |
| `--days N` | 180 | Days of OHLCV history. **Use 365+** for MA200 / 52w extremes to populate. |
| `--with-options` | off | Pull live OPRA chain + spawn Options Analyst + Quant Strategist |
| `--with-rates` | off | Pull Treasury yield curve + spawn Macro Rates Analyst |
| `--no-debate` | off | Skip Round 2 (single-pass; faster but lower quality) |
| `--no-quant` | off | Skip the Quant Strategist (rare; only for testing) |
| `--no-report` | off | Skip the auto-saved `.txt` report |
| `--provider X` | env default | Override default LLM provider for analysts that don't pin one |
| `--model X` | env default | Override default model |
| `--save-json PATH` | auto | Override the auto-saved JSON path |

## Recommended commands by use case

| You want to... | Run this |
|---|---|
| Quick read on a stock | `run_swarm TSLA --days 365` |
| Full analysis with options structure | `run_swarm TSLA --days 365 --with-options` |
| Full analysis + macro context | `run_swarm TSLA --days 365 --with-options --with-rates` |
| Cheapest possible run | `run_swarm TSLA --days 180 --no-debate --no-quant` |
| Force everything through one provider | `run_swarm TSLA --provider deepseek --with-options` |

## What you'll see while it runs

```
📊 fetching COIN (365d)...
   251 bars  close=191.55  rsi=50.4
📡 fetching OPRA chain for COIN...
   3364 contracts  IV-RV spread +48.2pts
📡 fetching Treasury yield curve...
   3M=4.15%  5Y=4.10%  10Y=4.27%  30Y=4.45%

🧬 SPAWNED 7 analyst(s):
   • Trend Analyst             →  deepseek/deepseek-chat
   • Pattern Analyst           →  anthropic/default
   • Volume Analyst            →  deepseek/deepseek-chat
   • Volatility Analyst        →  deepseek/deepseek-chat
   • Mean Reversion Analyst    →  deepseek/deepseek-chat
   • Macro Rates Analyst       →  deepseek/deepseek-chat
   • Options Analyst           →  deepseek/deepseek-chat

🧠 ROUND 1: ...
🧠 ROUND 2: ...
⚡ QUANT STRATEGIST  (DeepSeek-R1 reasoning)...
🎯 coordinator synthesizing...

==========================================================================
  CONSENSUS: BEARISH  (62%)
==========================================================================
  ...

📄 report → /Users/angelfernandez/Option_trading/data_cache/...txt
💾 data   → /Users/angelfernandez/Option_trading/data_cache/...json
```

## Reading the report later

```
# Latest run for COIN
/opt/anaconda3/bin/python -m agent_swarm.tools.report COIN

# Specific file
/opt/anaconda3/bin/python -m agent_swarm.tools.report --file data_cache/COIN_2026-04-29_1942_BEARISH_call-credit-spread.json

# All saved runs
/opt/anaconda3/bin/python -m agent_swarm.tools.report --list

# Drill into one analyst's full LLM reply
/opt/anaconda3/bin/python -m agent_swarm.tools.report COIN --raw "Quant"
```

See [03-reading-reports.md](03-reading-reports.md) for how to interpret what
the agents wrote.

## Wall-clock time

| Run type | Approx time |
|---|---|
| Equity-only, no debate | 10-20s |
| Equity-only with debate | 25-40s |
| With options + Quant Strategist | 60-120s (R1 reasoning is slower) |
| With options + rates + Quant | 90-150s |
