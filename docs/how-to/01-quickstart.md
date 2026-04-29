# Quickstart — first run in 3 minutes

Goal: see the swarm produce a bearish/bullish/neutral call with a real trade
ticket on a ticker you pick.

## Prereqs

- Python via Anaconda at `/opt/anaconda3/bin/python`
- A `.env` at the project root with **at least** these two keys:

```
ANTHROPIC_API_KEY=sk-ant-...
DATABENTO_API_KEY=db-...
```

Optional but recommended (the cheap workhorse for analysts):

```
DEEPSEEK_API_KEY=sk-...
```

If your `.env` is missing or wrong, see [06-providers-and-keys.md](06-providers-and-keys.md).

## Step 1 — install dependencies (one time)

```
cd /Users/angelfernandez/Option_trading
/opt/anaconda3/bin/pip install -r agent_swarm/requirements.txt
```

## Step 2 — verify data + LLMs work

```
/opt/anaconda3/bin/python -m agent_swarm.tools.view_data COIN --days 60
```

Expected: a printed snapshot, last 10 bars, and an ASCII chart. If you see
this, Databento + the data layer are healthy.

## Step 3 — run the swarm

Equity-only first (no chain pull, fastest, no OPRA cost):

```
/opt/anaconda3/bin/python -m agent_swarm.tools.run_swarm COIN --days 365
```

Then the full version with options + rates:

```
/opt/anaconda3/bin/python -m agent_swarm.tools.run_swarm COIN --days 365 \
    --with-options --with-rates
```

You'll see live output — each analyst spawning, voting, debating, then a final
consensus and a Quant Strategist trade ticket.

## Step 4 — read the report

After the run finishes, the last lines tell you exactly where to look:

```
📄 report → /Users/angelfernandez/Option_trading/data_cache/COIN_2026-04-29_1942_BEARISH_call-credit-spread.txt
💾 data   → /Users/angelfernandez/Option_trading/data_cache/COIN_2026-04-29_1942_BEARISH_call-credit-spread.json

  open /Users/angelfernandez/Option_trading/data_cache/COIN_2026-04-29_1942_BEARISH_call-credit-spread.txt
```

Copy that `open ...` line into your terminal — it pops the file in TextEdit.
The filename itself tells you the conclusion (BEARISH / call-credit-spread).

## What good output looks like

The transcript should contain:
- A snapshot block with close / RSI / MA20-50-200 / volume
- A "Spawned analysts" line showing 5-7 analysts and their LLM
- ROUND 1 + ROUND 2 sections with each analyst's stance / confidence / observations
- A ⚡ QUANT STRATEGIST block with a trade ticket (cash flow, max P&L, breakevens)
- A COORDINATOR CONSENSUS block with the final call

## If something fails

| Error | Fix |
|---|---|
| `ANTHROPIC_API_KEY not set` | Add it to `.env` (see [06-providers-and-keys.md](06-providers-and-keys.md)) |
| `DATABENTO_API_KEY not set` | Same |
| `401 invalid x-api-key` | Key is malformed — check for extra `sk=` prefix or whitespace |
| `422 data_end_after_available_end` | Your local clock is ahead of Databento's data — code clamps this; if you hit it, the file is out of sync |
| `chain empty (off-hours?)` | OPRA quotes only flow during market hours; try during 9:30am–4:00pm ET |
| `tools.run_swarm: command not found` | You forgot the `-m` — must be `python -m agent_swarm.tools.run_swarm` |
