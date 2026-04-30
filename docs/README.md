# Option_trading docs

Project: a multi-agent options-trading research system. You give it a ticker; a
team of LLM-powered specialist analysts reasons over the data and produces a
trade ticket with hard numbers.

## Where to start

If you're doing this for the first time today, read in this order:

1. **[how-to/01-quickstart.md](how-to/01-quickstart.md)** — get a swarm run on screen in 3 minutes
2. **[what-the-program-does.md](what-the-program-does.md)** — honest description of what's working today vs. what isn't
3. **[reference/commands.md](reference/commands.md)** — every command, copy-pasteable

## How-to (task-oriented)

| File | When to read it |
|---|---|
| [01-quickstart.md](how-to/01-quickstart.md) | First time running anything |
| [02-running-the-swarm.md](how-to/02-running-the-swarm.md) | You want to analyze a ticker |
| [03-reading-reports.md](how-to/03-reading-reports.md) | Output landed, what does it mean |
| [04-pulling-data.md](how-to/04-pulling-data.md) | You just want raw data, not analysis |
| [05-adding-a-data-source.md](how-to/05-adding-a-data-source.md) | You have a new API/CSV to plug in |
| [06-providers-and-keys.md](how-to/06-providers-and-keys.md) | Setting up Anthropic / DeepSeek / Databento keys |
| [07-scenarios.md](how-to/07-scenarios.md) | "I have data X — what command do I run?" — quick lookup |

## Reference (lookup)

| File | What it answers |
|---|---|
| [commands.md](reference/commands.md) | Every CLI command + flags + examples |
| [agents.md](reference/agents.md) | Each analyst — what it looks at, what it ignores, which LLM |
| [data-sources.md](reference/data-sources.md) | What data is wired today + what fits the architecture |
| [architecture.md](reference/architecture.md) | The system in one diagram |

## What's NOT in here

- API keys (those live in `.env` at the project root, never committed)
- Generated reports (`data_cache/` — auto-named per run, never committed)
- Code internals — read the source. Files are short and named by purpose.
