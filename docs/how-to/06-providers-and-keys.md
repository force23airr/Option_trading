# Providers and API keys

The system uses three external services. All keys live in **one** file:
`/Users/angelfernandez/Option_trading/.env`. Never commit it.

## What goes in `.env`

```
# Required for the swarm to run
ANTHROPIC_API_KEY=sk-ant-api03-...

# Required for any data pull (Databento OHLCV, futures, OPRA)
DATABENTO_API_KEY=db-...

# Recommended — most analysts route here for cheaper/faster runs
DEEPSEEK_API_KEY=sk-...

# Optional — if you want to add more providers
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...
```

## How keys are used

| Service | Where it shows up |
|---|---|
| Anthropic | Pattern Analyst + Coordinator (synthesis) |
| Databento | All OHLCV/futures/OPRA pulls |
| DeepSeek | Trend, Volume, Volatility, MeanRev, Macro Rates, Options analysts (V3) + Quant Strategist (R1) |
| OpenAI / OpenRouter | Optional — only used if you set `LLM_PROVIDER=openai`/`openrouter` or pin a specific analyst there |

## Verify your keys are loaded

```
/opt/anaconda3/bin/python -c "
from agent_swarm.core import llm
print('Available LLM providers:', llm.available_providers())
"
```

Expected output:

```
Available LLM providers: ['anthropic', 'deepseek']
```

If a provider is missing, the corresponding key isn't in `.env` (or has a typo).

## Verify Databento is reachable

```
/opt/anaconda3/bin/python -m agent_swarm.notebooks.test_databento COIN
```

Should print last 10 days of COIN OHLCV. If you get an auth error, the key is
wrong or has stray characters (the `sk=sk-ant-` prefix bug we hit earlier).

## Common key issues

| Symptom | Cause | Fix |
|---|---|---|
| `ANTHROPIC_API_KEY not set in environment / .env` | The dotenv file isn't being read or the line isn't there | Check the file exists at project root and has `ANTHROPIC_API_KEY=...` (no quotes) |
| `401 invalid x-api-key` | Key is malformed or revoked | Inspect with `python -c "from dotenv import load_dotenv; load_dotenv(); import os; k=os.environ['ANTHROPIC_API_KEY']; print(repr(k[:10]), len(k))"` — should start with `sk-ant-` |
| `db-...` rejected by Databento | Wrong account or expired key | Check at databento.com/dashboard |
| Trailing whitespace in key | Pasted from email | `sed -i '' 's/ *$//' .env` to strip trailing spaces |

## Provider routing — defaults

Each analyst class declares its preferred provider. The defaults are sensible
for a typical run, but you can override:

```
# Force everything through DeepSeek (cheapest possible)
... run_swarm COIN --provider deepseek

# Force a specific model
... run_swarm COIN --provider deepseek --model deepseek-reasoner

# Per-run env override
LLM_PROVIDER=anthropic LLM_MODEL=claude-sonnet-4-6 \
    /opt/anaconda3/bin/python -m agent_swarm.tools.run_swarm COIN
```

## Per-analyst provider pinning

If you want to swap a specific analyst to a different provider, edit the class:

`agent_swarm/analysts/trend_analyst.py`:

```python
class TrendAnalyst(BaseAnalyst):
    ...
    provider = "anthropic"            # was "deepseek"
    model = "claude-sonnet-4-6"
```

Run again — the spawn block will show the new provider.

## Cost reference (rough — changes with API pricing)

| Provider | Model | Input / Output per 1M tokens |
|---|---|---|
| Anthropic | claude-sonnet-4-6 | ~$3 / $15 |
| DeepSeek | deepseek-chat (V3) | ~$0.27 / $1.10 |
| DeepSeek | deepseek-reasoner (R1) | ~$0.55 / $2.20 + reasoning tokens |
| OpenAI | gpt-4o-mini | ~$0.15 / $0.60 |

A typical full swarm run uses ~30K input + ~5K output tokens across 8-9 LLM
calls. Cost: ~$0.05-0.15 depending on provider mix.

## Adding a new provider

The `core/llm.py` already supports any OpenAI-compatible endpoint. To add one
(e.g. Together, Groq):

1. Add to `PROVIDER_DEFAULTS` in `core/llm.py`:

```python
"together": {
    "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "base_url": "https://api.together.xyz/v1",
    "key_env": "TOGETHER_API_KEY",
},
```

2. Set `TOGETHER_API_KEY` in `.env`
3. Use it: `--provider together` or set per-analyst
