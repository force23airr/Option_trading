# Reading the reports

Every swarm run writes two files to `data_cache/`:

```
COIN_2026-04-29_1942_BEARISH_call-credit-spread.txt   ← human-readable
COIN_2026-04-29_1942_BEARISH_call-credit-spread.json  ← raw structured data
```

## Filename anatomy

```
{TICKER}_{YYYY-MM-DD}_{HHMM}_{STANCE}_{structure}.{ext}
```

You can read the whole conclusion from the filename alone — ticker, when,
which way the team leaned, and what trade structure was picked.

## What's in the .txt file

The transcript has 5 sections in order:

### 1. Header + snapshot

```
================================================================================
  COIN_2026-04-29_1942_BEARISH_call-credit-spread   ticker=COIN
================================================================================

Snapshot at run time:
  close                191.55
  rsi                   50.41
  ma20                 187.79
  ma50                 186.30
  ma200                267.22       ← only populates with --days 365+
  ...
```

This is what every analyst saw. If `ma200` is `nan`, you ran with too few days
and the Trend Analyst was flying blind.

### 2. Spawned / skipped analysts

```
Spawned analysts:  Trend Analyst, Pattern Analyst, ..., Options Analyst
Skipped:
  ✗ Macro Rates Analyst  (data deps not met)
```

Tells you which analysts ran and why others didn't (usually you forgot a
`--with-*` flag).

### 3. ROUND 1 / ROUND 2

For each analyst:

```
▸ Trend Analyst  [deepseek/deepseek-chat]  →  bearish  (65%)
    summary: MA stack is bearish (price below 200d MA at 267)...
    pattern: lower swing highs below 200-day MA
    horizon: 1-4w
    observations:
      • MA20 (187.79) and MA50 (186.30) are both well below MA200 (267.22)...
      • Price is ~28% below the 200-day MA...
      • [more observations]
```

How to read this:
- **Provider/model** in brackets — Claude vs DeepSeek vs DeepSeek-R1
- **Stance + confidence** — the headline view in 3 words
- **Pattern** — the named pattern they identified (or empty)
- **Observations** — the actual evidence cited

Compare Round 1 to Round 2. If an analyst's stance changed between rounds,
they updated based on what peers said in Round 1. That's debate working.

### 4. ⚡ Quant Strategist (only if `--with-options`)

```
⚡ QUANT STRATEGIST  [deepseek/deepseek-reasoner]

  Stance: bearish  Confidence: 75%
  Selected structure: 2026-05-08 212/230 Call Credit Spread

  Trade ticket:
    • Selected: 2026-05-08 212/230 Call Credit Spread
    • Cash flow: $+2.97/contract
    • Max profit: $+2.97
    • Max loss: $+14.53
    • Breakevens: [215.47, None]
    • POP estimate: 71%
    • net_delta: -0.141
    • net_vega: -0.033
    • net_theta_per_day: +0.001
    • Rationale: ...
```

This is the actionable part. The numbers are computed in Python before the
LLM sees them — DeepSeek-R1 only **chooses** which pre-built structure fits
best, it can't invent the credit/breakeven/POP.

### 5. Coordinator consensus

```
COORDINATOR CONSENSUS:  BEARISH  (62%)

  COIN shows rising wedge breakdown...

  Patterns:
    • Rising Wedge / Failed Breakout
    • Distribution after rally
    ...

  Agreements:
    • Price is below the 200MA...
    • Volume has been declining on the bounce...
    ...

  Disagreements:
    • Trend Analyst is only 30% confident...
    • Mean Reversion Analyst sees no actionable setup...

  Horizon:   1-4w
  Structure: ...iron condor or call credit spread, anchored to Quant ticket...

  Rationale: ...
```

The coordinator does no new analysis — it weighs the team. Watch the
**Disagreements** section: when there's split, confidence is capped, which is
honest.

## How to interpret confidence

| Range | Meaning |
|---|---|
| 0% | Analyst saw no setup in their lens (often correct — Mean Reversion at RSI 50) |
| 30–50% | Weak signal; don't bet conviction on this analyst alone |
| 60–70% | Standard read — trade-worthy if structure is defined-risk |
| 75–85% | Strong conviction — multiple confirmations |
| 90%+ | Either an obvious setup or the analyst is overcalibrated |

The **consensus confidence** is usually below the highest individual analyst
because the coordinator caps it when the team splits.

## How to interpret stance

| Stance | Direction |
|---|---|
| `bullish` / `bearish` / `neutral` | Standard directional |
| `bullish_vol` / `bearish_vol` | Vol direction (not price). Long-vol vs short-vol. |
| `directional_bullish` / `directional_bearish` | Price direction even though analyst is vol-focused |

## When to ignore an analyst

- **Mean Reversion at 0%** is usually correct (no extreme present). Not a contrarian signal — it just means "no setup in my lens."
- **Trend Analyst with `nan` for MA200** — re-run with `--days 365`.
- **Volatility Analyst calling things based on a 0–2 DTE option** — IV solver wobbles at very short DTE; cross-check with longer expiries.

## Quick comparisons across runs

```
ls -lt data_cache/COIN_*.txt | head    # latest COIN runs by time
ls data_cache/*_BEARISH_*.txt          # every bearish call across all tickers
```
