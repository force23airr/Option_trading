# Agents reference

The current swarm has 7 specialist analysts + 1 power agent + 1 coordinator.
Each declares its preferred LLM provider. Provider routing makes the swarm
cheap and tool-fit (DeepSeek for structured math, Claude for synthesis).

## At a glance

| Agent | School / lens | Spawns when | LLM | Role |
|---|---|---|---|---|
| Trend Analyst | Dow Theory: MA stack, slope, swing structure | Always | DeepSeek V3 | Specialist |
| Pattern Analyst | Edwards & Magee: triangles, H&S, wedges | Always | Claude (visual intuition) | Specialist |
| Volume Analyst | Wyckoff: accumulation / distribution | Always | DeepSeek V3 | Specialist |
| Volatility Analyst | Range / regime analysis (no Black-Scholes) | Always | DeepSeek V3 | Specialist |
| Mean Reversion Analyst | RSI / Bollinger extremes | Always | DeepSeek V3 | Specialist |
| Macro Rates Analyst | Treasury yield curve → ticker pressure | `--with-rates` | DeepSeek V3 | Specialist |
| Options Analyst | IV vs RV, term structure, skew | `--with-options` | DeepSeek V3 | Specialist |
| ⚡ Quant Strategist | Black-Scholes scenario analysis | `--with-options` | **DeepSeek-R1** (reasoning) | Power agent |
| Coordinator | Synthesizes the team | Always at end | Claude | Synthesizer |

## Trend Analyst

- **Looks for:** MA20 > MA50 > MA200 alignment; rising slope; sequence of higher-highs / lower-highs; proximity to 52-week extremes; failed retests
- **Math inputs:** MA20/50/200, RSI, 52w hi/lo, recent close prices
- **Pre-LLM calculations:** `signals.add_indicators()`
- **Ignores:** short-term noise, mean-reversion, options
- **Strongest output when:** ticker has clear directional structure (TSLA, NVDA, COIN); MA200 populated (`--days 365+`)

## Pattern Analyst

- **Looks for:** triangles (asc/desc/sym), flags & pennants, H&S / inverse, double tops/bottoms, channels, gap fills, wedges
- **Math inputs:** 30 bars of OHLC + volume context
- **Pre-LLM calculations:** none — pure visual recognition by Claude
- **Ignores:** intraday tape, harmonic patterns, indicator divergences
- **Strongest output when:** clean classical setup forming; NOT for choppy / sideways markets
- **Why Claude:** narrative/visual pattern intuition is Claude's strength

## Volume Analyst

- **Looks for:** volume on up vs down days, climax volume, dry-ups before breakouts, distribution at resistance, volume-price divergence
- **Math inputs:** Volume + Vol_avg20 + recent close direction
- **Strongest output when:** liquid name with > 500K daily volume

## Volatility Analyst

- **Looks for:** realized range expansion vs contraction, multi-day ranges, gap behavior
- **Math inputs:** OHLC ranges, recent close-to-close moves
- **Note:** does NOT compute Black-Scholes IV — that's the Options Analyst's job. This one is range/regime-style, ATR-school.

## Mean Reversion Analyst

- **Looks for:** RSI > 70 or < 30, RSI divergences, distance from MA20, exhaustion candles
- **Math inputs:** RSI, % distance from MA20
- **Honest behavior:** explicitly returns `neutral 0% confidence` when no extreme is present. Don't read this as a contrarian signal.

## Macro Rates Analyst (NEW)

- **Looks for:** rate regime (rising/falling/stable), curve shape (normal/flat/inverted), 2s10s spread, recent 5d/30d 10Y change
- **Math inputs:** 3M / 5Y / 10Y / 30Y yields + spreads
- **Linkages it knows:**
  - Banks/insurers benefit from steepening
  - Long-duration growth (high-multiple tech, COIN, MSTR) hurt by rising 10Y
  - REITs & utilities are duration-sensitive
  - Gold reactive to real-rate moves
  - Crypto proxies (COIN, MSTR, MARA) = risk-on; sell on hawkish surprise
- **Spawns only with `--with-rates`**

## Options Analyst

- **Looks for:** IV vs realized vol (rich/cheap), term structure (contango/backwardation), 25-delta skew (put IV - call IV), best-fit structure type
- **Math inputs:** ChainSummary (ATM IV per expiry, skew per expiry, IV-RV spread)
- **Pre-LLM calculations:** Newton-Raphson IV solver per contract, greeks, term structure aggregation
- **Output:** vol-regime call + structure preference (calls/puts/spreads/condors/calendars)
- **Spawns only with `--with-options`**

## ⚡ Quant Strategist (power agent)

The most important agent.

- **Looks for:** which pre-computed structure has the best regime fit
- **Math inputs:** 4 candidate structures pre-built from the chain:
  1. Iron Condor (sell ATM strangle, buy wings)
  2. Put Credit Spread (bullish, defined risk)
  3. Call Credit Spread (bearish, defined risk)
  4. Call Debit Spread (bullish, debit)
- **Pre-LLM calculations (all done in Python before LLM is called):**
  - Greeks per leg
  - Net cash flow (credit / debit)
  - Max profit / max loss
  - Breakeven points
  - POP estimate via delta
  - Net Δ / vega / θ
  - Reward-to-risk ratio
- **LLM role:** picks ONE and produces the structured trade ticket. Cannot invent numbers — they all came from the pre-computed table.
- **Why DeepSeek-R1:** R1 is a reasoning model with explicit chain-of-thought, best-in-class on numerical decision tasks at low cost
- **Spawns only with `--with-options`**

## Coordinator (synthesizer)

- **Role:** weighs all analyst views, identifies agreements / disagreements, produces final consensus
- **Output:** consensus_stance, consensus_confidence, headline, key_patterns, agreements, disagreements, horizon, suggested_structure (anchored to Quant ticket if present), rationale
- **Calculations run:** none — pure synthesis
- **Why Claude:** synthesis + calibrated uncertainty are Claude's strongest

## Two-round debate

- **Round 1:** every analyst sees only the data → independent view
- **Round 2:** every analyst sees Round-1 peer views → can agree, disagree, or refine
- **Quant Strategist runs once after Round 2** (R1 is too slow to run twice)
- **Coordinator runs once at the end** with final views + Quant ticket

## How to add a new analyst

See [how-to/05-adding-a-data-source.md](../how-to/05-adding-a-data-source.md) — same recipe. ~80 lines of new code.
