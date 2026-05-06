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
| `--with-events` | off | Pull structured scheduled events + earnings and spawn Events Analyst |
| `--no-debate` | off | Skip Round 2 (single-pass; faster but lower quality) |
| `--no-quant` | off | Skip the Quant Strategist (rare; only for testing) |
| `--account-size N` | env | Account value used by the deterministic hard-rules max-loss cap |
| `--max-loss-pct X` | `0.02` | Reject if ticket max loss exceeds this account fraction |
| `--max-bid-ask-spread-pct X` | `0.15` | Reject if any selected option leg spread/mid exceeds this fraction |
| `--earnings-reduce-days N` | `5` | Reduce size 50% if earnings within this many days |
| `--max-event-risk-score X` | unset | Reject if `event_risk_score` exceeds this 0–100 cap (off when unset) |
| `--no-report` | off | Skip the auto-saved `.txt` report |
| `--provider X` | env default | Override default LLM provider for analysts that don't pin one |
| `--model X` | env default | Override default model |
| `--save-json PATH` | auto | Override the auto-saved JSON path |

## Hard-rules gate

Every run now applies a deterministic post-coordinator gate to the Quant ticket.
This is not an LLM analyst. It blocks or modifies trades using fixed rules:

- Reject if any selected option leg's bid/ask spread is wider than the configured cap.
- Reject if ticket max loss exceeds `account_size * max_loss_pct`.
- Reduce size by 50% if earnings are inside the near-event window
  (`SWARM_EARNINGS_REDUCE_DAYS`, default 5).
- Apply `reject`, `watchlist_only`, or `reduce_size` actions from structured events.
- Reject if the aggregate `event_risk_score` exceeds `SWARM_MAX_EVENT_RISK_SCORE`
  when set (0–100; off by default).

Account size can be passed on the command line:

```
/opt/anaconda3/bin/python -m agent_swarm.tools.run_swarm COIN --with-options --with-news --account-size 25000 --max-loss-pct 0.01
```

Or via environment:

```
SWARM_ACCOUNT_SIZE=25000
SWARM_MAX_LOSS_PCT=0.01
SWARM_MAX_BID_ASK_SPREAD_PCT=0.12
SWARM_EARNINGS_REDUCE_DAYS=5
SWARM_MAX_EVENT_RISK_SCORE=85
```

## Events calendar

`--with-events` builds a structured event calendar from:

- earnings date from yfinance, when available
- optional local JSON calendar at `data_cache/events_calendar.json`
- optional override path via `SWARM_EVENTS_CALENDAR`

Use [events-calendar.example.json](../reference/events-calendar.example.json) as
the schema reference. Broad macro events use `"scope": "macro"` or `"market"`.
Ticker-specific events use `"scope": "ticker"` and a `tickers` list. The
`rule_action` field can be `reduce_size`, `watchlist_only`, or `reject`; use
`action_window_days` to control how close the event must be before the hard
rules apply the action.

## Recommended commands by use case

| You want to... | Run this |
|---|---|
| Quick read on a stock | `run_swarm TSLA --days 365` |
| Full analysis with options structure | `run_swarm TSLA --days 365 --with-options` |
| Full analysis + macro context | `run_swarm TSLA --days 365 --with-options --with-rates` |
| Full analysis + calendar risk | `run_swarm TSLA --days 365 --with-options --with-events --account-size 25000` |
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
