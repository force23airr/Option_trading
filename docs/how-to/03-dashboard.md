# Dashboard

Local Streamlit dashboard for browsing saved swarm runs. Read-only — never
mutates the swarm or the saved JSON files.

## Launch

```
streamlit run agent_swarm/dashboard/app.py
```

Opens at `http://localhost:8501`.

## Pages

### Run detail (default)

Pick a saved run from the sidebar dropdown. Shows:

- **Verdict panel** — colored banner with the FINAL trade disposition,
  every analyst's stance + confidence + summary, the Quant ticket, the
  Reconcile gate verdict, and the Hard Rules verdict.
- **Price & indicators tab** — candlestick + MA20/MA50 + volume,
  fetched live from the configured OHLCV source. The horizontal dotted
  line marks the close at run time.
- **Events timeline tab** — Gantt-style horizontal bars of upcoming
  scheduled events, color-coded by `rule_action`
  (green = none, amber = reduce_size, orange = watchlist_only, red = reject).
- **Options & vol tab** — IV term-structure curve + 25-delta skew, plus
  call wall / put wall / max pain per expiry. Requires the run to have
  been executed with `--with-options`.
- **Analyst transcripts tab** — round-by-round expandable cards with
  each analyst's full summary, pattern, observations.

### History & gate stats

Cross-run aggregations across whatever subset of runs the sidebar
filters select:

- **Run history table** — every run with timestamp, consensus, decision,
  size multiplier, and which hard-rule blocks fired.
- **Decisions across runs** — bar chart of approve / reject /
  reduced-size frequencies.
- **Most frequent hard-rule blocks** — horizontal bar chart of which
  block messages fire most often. Use this to tune thresholds (if
  `event risk score` is rejecting half your runs, your cap is probably
  too tight).

## Filters (sidebar)

- **Ticker** — multi-select.
- **Stance** — bullish / bearish / neutral.
- **Date range** — calendar picker.

Filters apply to both pages.

## What's NOT in this dashboard (yet)

- ❌ Live broker connections (Schwab/IBKR/Fidelity APIs are Phase 2).
- ❌ Order entry — kept in the broker app intentionally.
- ❌ Live tick streaming — current view is end-of-run snapshot.
- ❌ Backtest engine.

## Saving runs that the dashboard can read

The dashboard reads any file in `data_cache/` matching the pattern
`{TICKER}_{YYYY-MM-DD}_{HHMM}_{STANCE}_{structure}.json`. These are
auto-saved by `tools/run_swarm.py`. To populate the **Options & vol**
tab, run with `--with-options`. To populate the **Events timeline** tab,
run with `--with-events`.

```
python -m agent_swarm.tools.run_swarm AAPL --with-options --with-events
```
