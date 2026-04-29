# Adding a new data source

The architecture is designed to make this a 3-file change. You don't need to
modify the swarm core or any existing analysts.

## The pattern

```
1. data/your_source.py        ← fetch + normalize
2. core/context.py             ← add a slot + a `has_*` property
3. analysts/your_analyst.py    ← consume + reason
```

Then register in `analysts/__init__.py`, add a dispatch line in
`swarm._run_analyst_view()`, and add the spawn class to
`ALL_ANALYST_CLASSES` in `swarm.py`.

## Worked example: Treasury yields (already shipped)

The Macro Rates Analyst is the reference implementation. Look at:

- `agent_swarm/data/macro_source.py` — fetcher (yfinance ^IRX/^FVX/^TNX/^TYX)
- `agent_swarm/core/context.py` — `yield_curve` and `yield_summary` fields, `has_rates` property
- `agent_swarm/analysts/macro_rates_analyst.py` — analyst with `should_spawn()` and `analyze_with_rates()`

That's it. ~80 lines of new code total.

## Recipe step-by-step

### Step 1 — write the fetcher

`agent_swarm/data/your_source.py`:

```python
import pandas as pd
import requests  # or yfinance, or whatever

def fetch_my_data(thing: str, days: int = 30) -> pd.DataFrame:
    """Pull data and return a DataFrame.

    Caller passes raw inputs (a ticker, a region, a date). You return a
    pandas DataFrame or a dict — whatever is most natural for the data.
    """
    # ... fetch logic ...
    return df

def my_data_summary(df: pd.DataFrame) -> dict:
    """Translate a DataFrame into the key numbers an analyst cares about.

    Keep this small — analysts see this in their prompt.
    """
    return {"latest": float(df["value"].iloc[-1]), "change_30d": ...}
```

### Step 2 — add the context slot

`agent_swarm/core/context.py`:

```python
@dataclass
class DataContext:
    # ... existing fields ...
    my_data: pd.DataFrame | None = None
    my_summary: dict | None = None

    @property
    def has_my_data(self) -> bool:
        return self.my_data is not None and not self.my_data.empty
```

### Step 3 — write the analyst

`agent_swarm/analysts/your_analyst.py`:

```python
import json
from .base import AnalystView, BaseAnalyst, _parse_json_reply
from ..core import llm


class MyAnalyst(BaseAnalyst):
    name = "My Analyst"
    focus = "what your specialty is in one phrase"
    system_prompt = (
        "You are a [domain] specialist. You read [data type] and translate "
        "it into directional pressure on [the ticker / asset class]. Specifically: "
        "[explain the actual linkages — e.g., 'rising drought severity hurts "
        "ag commodity yields and raises grain prices, supporting CORN/WEAT/SOYB']."
    )
    provider = "deepseek"
    model = "deepseek-chat"

    @classmethod
    def should_spawn(cls, ctx) -> bool:
        return ctx.has_my_data

    def analyze_with_my_data(self, ctx, peer_views=None) -> AnalystView:
        peers_block = ""
        if peer_views:
            peers_block = "\n\nPEER ANALYSTS' VIEWS:\n"
            for v in peer_views:
                peers_block += f"- {v.short()}\n"

        my_block = json.dumps(ctx.my_summary or {}, indent=2)

        prompt = f"""Ticker: {ctx.ticker}
Underlying snapshot:
{json.dumps(ctx.snap, indent=2, default=str)}

[YOUR DATA NAME] (latest):
{my_block}
{peers_block}
Reply with one JSON object:
{{
  "stance": "bullish" | "bearish" | "neutral",
  "confidence": <float 0.0-1.0>,
  "summary": "<one sentence linking your data to the ticker>",
  "horizon": "1-5d" | "1-4w" | "longer",
  "observations": ["<concrete observation>", "..."]
}}"""
        raw = llm.chat(
            prompt, system=self.system_prompt,
            provider=self.provider, model=self.model,
            max_tokens=900, temperature=0.3,
        )
        parsed = _parse_json_reply(raw)
        return AnalystView(
            analyst=self.name, ticker=ctx.ticker,
            stance=str(parsed.get("stance", "neutral")).lower(),
            confidence=float(parsed.get("confidence", 0.0) or 0.0),
            summary=str(parsed.get("summary", "")).strip(),
            observations=[str(o) for o in parsed.get("observations", [])][:8],
            horizon=str(parsed.get("horizon", "")).strip(),
            raw=raw,
            provider=self.provider or "",
            model=self.model or "",
        )
```

### Step 4 — wire it into the swarm

`agent_swarm/analysts/__init__.py`:

```python
from .your_analyst import MyAnalyst
__all__ = [..., "MyAnalyst"]
```

`agent_swarm/core/swarm.py` — add to imports:

```python
from ..analysts import (..., MyAnalyst)
from ..data import your_source
```

Add to `ALL_ANALYST_CLASSES`:

```python
ALL_ANALYST_CLASSES = [..., MyAnalyst]
```

Add a dispatch line in `_run_analyst_view()`:

```python
def _run_analyst_view(a, ctx, peer_views):
    if isinstance(a, OptionsAnalyst):
        return a.analyze_with_chain(...)
    if isinstance(a, MacroRatesAnalyst):
        return a.analyze_with_rates(ctx, peer_views=peer_views)
    if isinstance(a, MyAnalyst):                         # ← new
        return a.analyze_with_my_data(ctx, peer_views=peer_views)
    return a.analyze(ctx.ticker, ctx.df, ctx.snap, peer_views=peer_views)
```

In `_build_context()`, add the optional fetch:

```python
def _build_context(ticker, days, with_options, with_rates, with_my_data, emit):
    # ... existing code ...
    if with_my_data:
        emit("my_data:start")
        try:
            ctx.my_data = your_source.fetch_my_data(...)
            ctx.my_summary = your_source.my_data_summary(ctx.my_data)
            emit("my_data:done", summary=ctx.my_summary)
        except Exception as exc:
            emit("my_data:error", error=str(exc))
    return ctx
```

And expose the flag in `tools/run_swarm.py`:

```python
ap.add_argument("--with-my-data", action="store_true", help="...")
# ... and pass with_my_data=args.with_my_data to swarm.run()
```

### Step 5 — test it

```
/opt/anaconda3/bin/python -m agent_swarm.tools.run_swarm COIN --with-my-data
```

You should see:
- `🧬 SPAWNED N analyst(s):` includes your new analyst
- The new analyst's view in Round 1 / Round 2
- The Coordinator citing your analyst's evidence

## Common gotchas

- **`should_spawn` returns True for the wrong cases.** If you spawn for non-applicable tickers (e.g. a wildfire analyst spawning on COIN), the analyst will produce noise. Restrict via ticker filter:

  ```python
  @classmethod
  def should_spawn(cls, ctx):
      return ctx.has_my_data and ctx.ticker.upper() in {"PCG", "EIX", "ALL"}
  ```

- **System prompt is too generic.** "You are an analyst" produces nothing. Be specific about the linkage from data → asset.

- **Returning a 30-page dataframe in the prompt.** The LLM can't read 1000 rows. Compress to a summary dict (latest values + recent changes) before feeding in.

- **No peer-view context.** If you want the analyst to update in Round 2, accept and use `peer_views`.

## Quick template for common domains

| Domain | Tickers it should spawn for | Linkage to articulate in system prompt |
|---|---|---|
| Weather (temperature) | UNG, BOIL, KOLD, XLE, NG.c.0 | Cold = heating demand → bullish NG; Hot = cooling demand → bullish power |
| Wildfire | PCG, EIX, SRE, ALL, TRV, RNR | Fires near service territory → liability → bearish utility |
| Drought / SPI | CORN, WEAT, SOYB, DE, ADM, MOS | Drought reduces yield → bullish grains, hurts ag equipment demand |
| Hurricane | NHC active storms → ALL, TRV, RNR, RGA, energy producers | Path crosses Gulf = oil supply risk → bullish CL; insurance loss exposure |
| On-chain crypto | COIN, MSTR, MARA, RIOT | Exchange outflows = HODLing = bullish; inflows = sell pressure |
| Earnings calendar | Any single-name | Within 14 days of earnings = expect IV crush → favor selling premium |
| Fed sentiment (FOMC text) | TLT, IEF, gold, banks | Hawkish language = rates up → bearish duration |
