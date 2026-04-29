# Data sources reference

What's wired today, what fits the architecture, what doesn't.

## Wired and tested today

| Source | Schema / endpoint | What you get | Cost |
|---|---|---|---|
| **Databento Historical** (`XNAS.ITCH`) | `ohlcv-1d` | Daily OHLCV for any Nasdaq-listed US single-name | Pennies per ticker/year |
| **Databento Historical** (`DBEQ.BASIC`) | `ohlcv-1d` | NYSE-listed names — pass `dataset="DBEQ.BASIC"` explicitly | Pennies |
| **Databento Historical** (`GLBX.MDP3`) | `ohlcv-1d` | CME futures — `CL.c.0`, `NG.c.0`, `GC.c.0`, `ES.c.0`, `NQ.c.0` (continuous front-month) | Pennies |
| **Databento Historical** (`OPRA.PILLAR`) | `cbbo-1m` | Live US option chains, bid/ask sampled every 1 min | ~$0.18 / day / ticker |
| **Databento OPRA** | `trades` | Every option print on the tape | ~$0.36 / day / ticker |
| **Databento OPRA** | `cbbo-1s` | Bid/ask sampled every 1s (smoother but ~12x cost) | ~$2.16 / day / ticker |
| **Databento OPRA** | `ohlcv-1d` | Per-contract daily bars | ~$0.13 / day / ticker |
| **yfinance** | `Ticker.history` | Fallback OHLCV when Databento fails or for ETFs not in `XNAS.ITCH` | Free |
| **yfinance** | `Ticker.news` | Recent news headlines (limited free tier) | Free |
| **yfinance proxies** | `^IRX`, `^FVX`, `^TNX`, `^TYX` | Treasury yield curve (3M, 5Y, 10Y, 30Y) | Free |

## Best-fit data shapes for the architecture

The swarm reasons over JSON-shaped context fed into LLM prompts. Anything that
can be reduced to one of these fits cleanly:

| Shape | Examples |
|---|---|
| **Time series → snapshot** | OHLCV, yields, VIX, weather temp, soil moisture, river flow |
| **Cross-sectional table** | Yield curve, options chain, weather grid, drought severity by county |
| **Discrete event list** | Earnings dates, FOMC meetings, hurricane landfalls, OPEC meetings |
| **Text feed** | News headlines, FOMC minutes, NOAA bulletins, regulatory filings |

## Sources that fit (just need a fetcher written)

These all have free or low-cost APIs and reduce naturally to the shapes above:

| Domain | Source | Best for |
|---|---|---|
| **FRED** (Treasury, GDP, CPI, unemployment, money supply) | api.stlouisfed.org (free key) | Macro context, real rates |
| **EIA** (oil/gas inventory, electricity, refining) | api.eia.gov (free key) | USO, oil majors, NG plays |
| **NOAA NWS** | api.weather.gov (no key) | Wind, temperature, hurricane, drought — energy + ag commodities |
| **Open-Meteo** | api.open-meteo.com (no key) | Same domains, simpler API |
| **NASA FIRMS** | firms.modaps.eosdis.nasa.gov (free key) | Active wildfire detection — utilities (PCG, EIX), insurers |
| **US Drought Monitor** | droughtmonitor.unl.edu (CSV download) | Ag commodities (CORN, WEAT, SOYB), Deere, Mosaic |
| **USDA NASS** | quickstats.nass.usda.gov (free key) | Crop conditions, planting/harvest progress |
| **NHC (Hurricane Center)** | nhc.noaa.gov (free RSS/JSON) | Re-insurers, energy producers, refiners |
| **Glassnode / IntoTheBlock** | API (paid, free tier exists) | On-chain crypto for COIN/MSTR/MARA plays |
| **Polygon.io** | api.polygon.io (paid) | Alternative options/equity feed if you want redundancy |
| **Tiingo** | api.tiingo.com (free tier) | Fundamentals, news with sentiment |
| **NewsAPI / Bing News** | newsapi.org | News sentiment analyst input |
| **Reddit/Twitter** | praw / tweepy | Retail sentiment (use with skepticism) |

## What does NOT fit well today

| Limitation | Why | Workaround |
|---|---|---|
| **Sub-second / tick streams** | Each LLM call is 2-30s; this is a research system, not HFT | Aggregate to bars first (1m/1s) |
| **Multi-GB raw datasets** | Won't fit in LLM context | Pre-aggregate to summary stats / latest snapshot |
| **Images / chart screenshots** | Not parsed automatically | Use a vision-LLM step first to extract structured data |
| **Audio (earnings calls)** | No transcription wired | Run Whisper first, feed transcript as text |
| **Truly proprietary binary formats** | No parser | Write the parser, then feed parsed output |

## What's NOT wired but trivial to add

These are listed in priority order based on how much they'd improve the swarm:

1. **FRED 3-month T-bill** for the Black-Scholes risk-free rate (currently hardcoded 4.5%) — 1 hour
2. **Earnings calendar** (FMP free tier, or yfinance has it) — 1-2 hours; gives the swarm event awareness
3. **Polygon news with sentiment** — 2-3 hours; adds a Sentiment Analyst
4. **EIA oil inventory** — 2 hours; meaningfully better USO / oil-major calls
5. **NOAA weather → NG/energy** — 3-4 hours including the WeatherAnalyst
6. **NASA FIRMS → utility/insurer** — 3-4 hours including the WildfireAnalyst

## Costs at a glance

| Activity | Cost |
|---|---|
| Pull 1 year of daily OHLCV for one ticker (Databento) | ~$0.001 |
| Pull 1 year of WTI continuous futures | ~$0.005 |
| Pull 1 day of option chain for one ticker (`cbbo-1m`) | ~$0.18 |
| Full swarm run with options + rates | ~$0.30 (data + LLM combined) |
| Daily watchlist of 5 tickers, full features | ~$1.50 |

## Direct API examples

```python
# Equities
from agent_swarm.data import databento_source as ds
df = ds.fetch_ohlcv("AAPL", days=365)
df = ds.fetch_ohlcv("AAPL", days=365, dataset="DBEQ.BASIC")  # NYSE-listed

# Futures
df = ds.fetch_futures("CL.c.0", days=365)   # WTI front-month
df = ds.fetch_futures("NG.c.0", days=365)   # Natural gas

# Options
from agent_swarm.data import opra_source
quotes = opra_source.fetch_quotes("COIN", days=1)            # cbbo-1m by default
trades = opra_source.fetch_trades("COIN", days=1, limit=500)

# Yield curve
from agent_swarm.data import macro_source
curve = macro_source.fetch_yield_curve(days=90)
summary = macro_source.yield_curve_summary(curve)
```
