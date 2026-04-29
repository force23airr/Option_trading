# Architecture

## The pipeline in one screen

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            DATA LAYER                                   │
│                                                                         │
│   Databento equities    Databento futures    Databento OPRA             │
│   (XNAS.ITCH)           (GLBX.MDP3)          (OPRA.PILLAR)              │
│        │                     │                    │                     │
│        └──── OHLCV ──────────┘                    │                     │
│                  │                                │                     │
│                  ▼                                │                     │
│        signals.add_indicators()         options.build_chain()           │
│        MA20/50/200, RSI, 52w hi/lo      OCC parse + IV solver +         │
│        volume averages                   greeks per contract            │
│                  │                                │                     │
│                  └──────────────┬─────────────────┘                     │
│                                 │                                       │
│   yfinance proxies              ▼                                       │
│   ^IRX/^FVX/^TNX/^TYX     ┌──────────────┐                              │
│   (yield curve)──────────►│ DataContext  │                              │
│                            │              │                             │
│   Future: NOAA, FRED,      │  ticker      │                             │
│   USDA, FIRMS, EIA, etc. ─►│  df          │                             │
│                            │  snap        │                             │
│                            │  chain_df    │                             │
│                            │  yield_curve │                             │
│                            │  ...         │                             │
│                            └──────┬───────┘                             │
└───────────────────────────────────┼─────────────────────────────────────┘
                                    │
                                    │  for each analyst:
                                    │  if cls.should_spawn(ctx): instantiate
                                    │
        ┌───────────────────────────┴──────────────────────────────┐
        │                                                          │
┌───────▼────────────────────────────┐               ┌─────────────▼──────────────┐
│       SPECIALIST ANALYSTS          │               │   POWER AGENT              │
│                                    │               │                            │
│  Trend          (DeepSeek V3)      │               │   Quant Strategist         │
│  Pattern        (Claude)           │               │   (DeepSeek-R1 reasoning)  │
│  Volume         (DeepSeek V3)      │               │                            │
│  Volatility     (DeepSeek V3)      │               │   Pre-computes 4 candidate │
│  MeanReversion  (DeepSeek V3)      │               │   structures from chain    │
│  Macro Rates    (DeepSeek V3)*     │               │   (iron condor, credit/    │
│  Options        (DeepSeek V3)*     │               │   debit spreads) with all  │
│                                    │               │   greeks/POP/breakevens.   │
│  ROUND 1 — independent             │               │   R1 picks one and writes  │
│  ROUND 2 — sees Round-1 peers      │               │   the trade ticket.        │
│                                    │               │                            │
│  *spawn only with --with-rates     │               │   Spawns only with         │
│  *spawn only with --with-options   │               │   --with-options           │
└──────────────────┬─────────────────┘               └────────────────┬───────────┘
                   │                                                  │
                   │   final_views (from Round 2 if debate, else R1)  │
                   │                                                  │
                   └──────────────────────┬───────────────────────────┘
                                          │
                                          ▼
                            ┌─────────────────────────┐
                            │      COORDINATOR        │
                            │      (Claude)           │
                            │                         │
                            │   Synthesizes — does    │
                            │   no new analysis. Caps │
                            │   confidence when team  │
                            │   splits. Anchors       │
                            │   structure to Quant    │
                            │   ticket if present.    │
                            └────────────┬────────────┘
                                         │
                                         ▼
                            ┌─────────────────────────┐
                            │   SwarmResult           │
                            │                         │
                            │   ticker, snapshot,     │
                            │   round1, round2,       │
                            │   quant view,           │
                            │   consensus dict        │
                            └────────────┬────────────┘
                                         │
                                         ▼
                            data_cache/{TICKER}_{TS}_{STANCE}_{structure}.{txt,json}
```

## Module map

```
agent_swarm/
├── core/
│   ├── data.py              # OHLCV fetch (Databento with yfinance fallback)
│   ├── signals.py           # RSI, MAs, snapshot()
│   ├── black_scholes.py     # price, greeks, implied_vol, realized_vol
│   ├── options.py           # OCC parser, build_chain
│   ├── llm.py               # multi-provider LLM dispatch
│   ├── context.py           # DataContext dataclass
│   └── swarm.py             # the orchestrator + Coordinator
├── data/
│   ├── databento_source.py  # equities + futures
│   ├── opra_source.py       # OPRA option chains
│   └── macro_source.py      # Treasury yield curve via yfinance proxies
├── analysts/
│   ├── base.py              # BaseAnalyst, AnalystView, JSON parsing
│   ├── trend_analyst.py
│   ├── pattern_analyst.py
│   ├── volume_analyst.py
│   ├── volatility_analyst.py
│   ├── mean_reversion_analyst.py
│   ├── macro_rates_analyst.py
│   ├── options_analyst.py
│   └── quant_strategist.py  # ⚡ power agent — DeepSeek-R1
└── tools/
    ├── run_swarm.py         # main CLI
    ├── view_data.py
    ├── option_chain.py
    ├── opra_check.py
    ├── wti_demo.py
    ├── audit.py             # transparency manifest
    └── report.py            # human-readable transcripts + auto-save
```

## Key design choices

### Why conditional spawning

`should_spawn(ctx)` lets a new data source bring its own analyst without
touching swarm code. If you wire weather, the WeatherAnalyst class declares
`should_spawn = ctx.has_weather` and the swarm picks it up automatically.

### Why provider routing per agent

DeepSeek V3 produces structured JSON cheaply and accurately for technical
analysts. Claude is better at synthesis and visual pattern intuition.
DeepSeek-R1 is the best numerical reasoner per dollar. Each agent points at
the model that fits its job.

### Why pre-compute structures in Python

LLMs hallucinate numbers. By computing all candidate structures (credit,
breakevens, POP, greeks) in Python before the LLM sees them, the LLM's job
narrows to "pick one" — it can't invent a $5 credit out of thin air. Math
correctness is enforced by code; judgment is delegated to the LLM.

### Why two rounds of debate

Round 1 catches what each analyst sees independently. Round 2 lets analysts
update based on what others observed (e.g., Trend Analyst going from neutral
30% to bearish 65% after seeing Pattern Analyst's wedge breakdown). This
mimics a real trading-desk meeting.

### Why no streaming

Each LLM call is 2-30s; the swarm is a snapshot-based decision system, not a
real-time stream. For execution you'd build a separate event loop that
consumes the swarm's saved consensus calls.

## Extension points

- New data source → see [how-to/05-adding-a-data-source.md](../how-to/05-adding-a-data-source.md)
- New LLM provider → add to `PROVIDER_DEFAULTS` in `core/llm.py`
- New trade structure → add to `build_candidates()` in `analysts/quant_strategist.py`
- New report format → add to `tools/report.py`'s `render()` or write a new tool
- New CLI command → add a file in `tools/` that imports from `core/` and `analysts/`
