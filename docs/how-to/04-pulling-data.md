# Pulling raw data (no swarm)

When you want data without analysis. Three tools cover the cases.

## Equity / futures OHLCV

```
/opt/anaconda3/bin/python -m agent_swarm.tools.view_data COIN
/opt/anaconda3/bin/python -m agent_swarm.tools.view_data COIN --days 365
/opt/anaconda3/bin/python -m agent_swarm.tools.view_data COIN --days 365 --csv
```

Prints:
- Snapshot (close, RSI, MAs, 52w extremes, volume averages, % changes)
- Last 10 bars
- ASCII chart of the closing price
- (with `--csv`) saves `data_cache/COIN_365d.csv`

Works for any US single-name (uses Databento `XNAS.ITCH` by default, falls
back to yfinance).

## WTI oil + Black-Scholes demo

```
# USO ETF (always works)
/opt/anaconda3/bin/python -m agent_swarm.tools.wti_demo --days 180

# Real WTI futures (needs GLBX.MDP3 on your Databento plan)
/opt/anaconda3/bin/python -m agent_swarm.tools.wti_demo --futures --days 180

# With option pricing demo
/opt/anaconda3/bin/python -m agent_swarm.tools.wti_demo --futures --strike-pct 0.95 --dte 30
```

Prints:
- WTI spot, realized vol 30d / 60d, RSI
- Last 5 bars
- Black-Scholes call/put prices + greeks for a hypothetical option

## Live OPRA option chain

```
# 1-day chain pull, default settings
/opt/anaconda3/bin/python -m agent_swarm.tools.option_chain COIN

# Save the chain CSV
/opt/anaconda3/bin/python -m agent_swarm.tools.option_chain COIN --save

# Adjust strike count near ATM
/opt/anaconda3/bin/python -m agent_swarm.tools.option_chain COIN --n-strikes 20
```

Prints:
- Spot price + realized vol 30d
- Cost preview ($0.18 ish for 1 day of 1-min quotes for one ticker)
- Number of contracts pulled, number of expiries
- Near-ATM slice for the first 3 expiries with: bid, ask, mid, IV, Δ, Γ, vega, θ
- ATM IV summary + IV-RV spread

CSV is saved to `data_cache/COIN_chain.csv` if you pass `--save`.

## OPRA cost previews (don't pay yet)

```
/opt/anaconda3/bin/python -m agent_swarm.tools.opra_check                # cost previews
/opt/anaconda3/bin/python -m agent_swarm.tools.opra_check --pull COIN    # cost + small sample
```

Useful to check a new ticker's options data is available before paying.

## Common patterns

```
# Pull data for 3 tickers, save CSVs
for t in COIN HOOD CRCL TSLA; do
    /opt/anaconda3/bin/python -m agent_swarm.tools.view_data $t --days 365 --csv
done
ls data_cache/*.csv

# Quick chain comparison
for t in COIN MSTR MARA; do
    /opt/anaconda3/bin/python -m agent_swarm.tools.option_chain $t --save
done
```

## Data dataset cheatsheet

| Symbol | Dataset | What it is |
|---|---|---|
| `COIN`, `TSLA`, etc. | `XNAS.ITCH` (default) | Nasdaq-listed single-name stocks |
| Same, but for NYSE-listed | `DBEQ.BASIC` (override required) | NYSE/composite |
| `CL.c.0` | `GLBX.MDP3` | WTI crude oil front-month continuous future |
| `NG.c.0`, `GC.c.0`, `ES.c.0`, `NQ.c.0` | `GLBX.MDP3` | natgas, gold, S&P, Nasdaq futures |
| `COIN.OPT` | `OPRA.PILLAR` | All COIN options (with `stype_in="parent"`) |

For non-default datasets you'd call the source module directly:

```python
from agent_swarm.data import databento_source as ds
df = ds.fetch_ohlcv("AMD", days=365, dataset="DBEQ.BASIC")
```
