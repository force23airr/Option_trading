# Commands reference

Every CLI in the project, with flags and copy-pasteable examples.

All commands assume `cwd = /Users/angelfernandez/Option_trading`.
Python is at `/opt/anaconda3/bin/python` (Anaconda).

## Swarm runner

`agent_swarm.tools.run_swarm` — the main command.

```
python -m agent_swarm.tools.run_swarm TICKER [flags]
```

| Flag | Default | Effect |
|---|---|---|
| (positional) `TICKER` | required | The symbol to analyze |
| `--days N` | 180 | OHLCV history depth — use 365+ for MA200 / 52w to populate |
| `--with-options` | off | Pull OPRA chain (~$0.18) → Options Analyst + Quant Strategist spawn |
| `--with-rates` | off | Pull Treasury yield curve → Macro Rates Analyst spawns |
| `--no-debate` | off | Single-pass (skip Round 2) |
| `--no-quant` | off | Skip Quant Strategist |
| `--no-report` | off | Skip auto-saved .txt report |
| `--provider X` | env | LLM provider override (anthropic/deepseek/openai/openrouter) |
| `--model X` | env | LLM model override |
| `--save-json PATH` | auto | Override JSON output path |

Examples:

```
# Cheapest equity-only run
python -m agent_swarm.tools.run_swarm AAPL --days 365

# Full options analysis with rates context
python -m agent_swarm.tools.run_swarm COIN --days 365 --with-options --with-rates

# Force DeepSeek for everything
python -m agent_swarm.tools.run_swarm TSLA --with-options --provider deepseek
```

## Report viewer

`agent_swarm.tools.report` — read past swarm runs.

```
python -m agent_swarm.tools.report [TICKER] [flags]
```

| Flag | Effect |
|---|---|
| (positional) `TICKER` | Show the latest run for this ticker |
| `--file PATH` | Render a specific JSON file |
| `--list` | List all saved runs |
| `--raw NAME` | Print verbatim LLM reply for an analyst whose name contains `NAME` |

Examples:

```
python -m agent_swarm.tools.report                           # latest run, any ticker
python -m agent_swarm.tools.report COIN                      # latest COIN run
python -m agent_swarm.tools.report --list                    # all saved runs
python -m agent_swarm.tools.report COIN --raw "Quant"        # full DeepSeek-R1 reply
python -m agent_swarm.tools.report --file data_cache/COIN_2026-04-29_1942_BEARISH_call-credit-spread.json
```

## Data viewer

`agent_swarm.tools.view_data` — pull + display OHLCV without running the swarm.

```
python -m agent_swarm.tools.view_data TICKER [flags]
```

| Flag | Default | Effect |
|---|---|---|
| `--days N` | 90 | History depth |
| `--csv` | off | Save CSV to `data_cache/{TICKER}_{N}d.csv` |

Examples:

```
python -m agent_swarm.tools.view_data COIN
python -m agent_swarm.tools.view_data COIN --days 365 --csv
```

## Option chain viewer

`agent_swarm.tools.option_chain` — pull live OPRA chain, compute IV, display.

```
python -m agent_swarm.tools.option_chain TICKER [flags]
```

| Flag | Default | Effect |
|---|---|---|
| `--days N` | 1 | Days of cbbo-1m quotes to pull |
| `--rate R` | 0.045 | Risk-free rate for Black-Scholes |
| `--n-strikes N` | 12 | Strikes near ATM to display per expiry |
| `--save` | off | Save chain CSV to `data_cache/{TICKER}_chain.csv` |

```
python -m agent_swarm.tools.option_chain COIN --save
python -m agent_swarm.tools.option_chain TSLA --days 1 --n-strikes 20
```

## OPRA cost preview

`agent_swarm.tools.opra_check` — preview Databento billing before paying.

```
python -m agent_swarm.tools.opra_check                # cost previews only
python -m agent_swarm.tools.opra_check --pull COIN    # cost + 500-row trade sample
```

## WTI demo

`agent_swarm.tools.wti_demo` — pull WTI data + Black-Scholes pricing demo.

```
python -m agent_swarm.tools.wti_demo                 # USO ETF
python -m agent_swarm.tools.wti_demo --futures       # CL.c.0 front-month future
python -m agent_swarm.tools.wti_demo --futures --strike-pct 0.95 --dte 30
```

| Flag | Default | Effect |
|---|---|---|
| `--futures` | off | Use CL.c.0 instead of USO |
| `--days N` | 180 | History depth |
| `--strike-pct R` | 1.0 | Strike as multiple of spot (1.0 = ATM) |
| `--dte N` | 30 | Days-to-expiry for the option |
| `--rate R` | 0.045 | Risk-free rate |

## Audit / transparency manifest

`agent_swarm.tools.audit` — explains every analyst's toolkit.

```
python -m agent_swarm.tools.audit                    # full manifest
python -m agent_swarm.tools.audit --analyst Trend    # one analyst
python -m agent_swarm.tools.audit --math             # math primitives only
python -m agent_swarm.tools.audit --prompts          # include verbatim system prompts
```

## Databento smoke test

`agent_swarm.notebooks.test_databento` — verify Databento connectivity.

```
python -m agent_swarm.notebooks.test_databento COIN
python -m agent_swarm.notebooks.test_databento HOOD
```

## Common multi-step recipes

### Run a watchlist

```bash
for t in COIN HOOD CRCL TSLA NVDA; do
    /opt/anaconda3/bin/python -m agent_swarm.tools.run_swarm $t --days 365 --with-options
done
ls -lt data_cache/*.txt | head
```

### Compare two providers on the same ticker

```bash
/opt/anaconda3/bin/python -m agent_swarm.tools.run_swarm COIN --provider anthropic --save-json data_cache/COIN_anthropic.json
/opt/anaconda3/bin/python -m agent_swarm.tools.run_swarm COIN --provider deepseek --save-json data_cache/COIN_deepseek.json
diff data_cache/COIN_anthropic.json data_cache/COIN_deepseek.json | head -50
```

### Pull data for offline analysis (no LLM cost)

```bash
for t in COIN HOOD CRCL; do
    /opt/anaconda3/bin/python -m agent_swarm.tools.view_data $t --days 365 --csv
    /opt/anaconda3/bin/python -m agent_swarm.tools.option_chain $t --save
done
```
