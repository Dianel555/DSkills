# Exa Search CLI

Standalone CLI for the Exa semantic search API. 
## Installation

```bash
pip install httpx tenacity
```

## Configuration

Set `EXA_API_KEY` via an environment variable or a `.env` file at the skill
root (`skills/exa/.env`). The file is auto-discovered no matter which directory
you launch the CLI from (the legacy `scripts/.env` still works as a fallback):

```bash
export EXA_API_KEY=your-api-key-here
```

Or copy `.env.example` to `.env` and fill in your key:

```bash
cp .env.example .env   # from skills/exa/
```

## Usage

```bash
cd skills/exa  # the shim auto-chdirs here if launched from elsewhere

# Semantic search (highlights always on)
python scripts/exa_cli.py web_search_exa --query "TypeScript design patterns"

# Embed category in the query
python scripts/exa_cli.py web_search_exa --query "category:company Anthropic AI safety"

# Batch URL fetch (--urls is a repeatable flag)
python scripts/exa_cli.py web_fetch_exa \
  --urls "https://example.com/a" --urls "https://example.com/b" \
  --max-chars 2000

# Advanced filtered search (list params are repeatable flags)
python scripts/exa_cli.py web_search_advanced_exa --query "machine learning" \
  --include-domains arxiv.org --include-domains papers.nips.cc \
  --start-date 2024-01-01 --text --highlights

# Configuration + connectivity probe
python scripts/exa_cli.py get_config_info

# Create an Agent run, then resume the same retained run if needed
python scripts/exa_cli.py agent_run \
  --query "Build an evidence-backed company list" \
  --effort low --wait-seconds 750 --out agent.json
python scripts/exa_cli.py agent_run --run-id agent_run_123

# Third-party endpoint with Bearer authentication
export EXA_API_URL=https://pool.example.com
export EXA_AUTH_SCHEME=bearer
export EXA_API_KEY=your-bearer-token
python scripts/exa_cli.py web_search_exa --query "AI research"
```

## Available Commands

| Command | Description |
|---------|-------------|
| `web_search_exa` | Semantic web search (highlights always on; supports inline `category:<type>`) |
| `web_search_advanced_exa` | Filtered search (`--type auto/fast/instant`, repeatable domain/text flags) |
| `web_fetch_exa` | Batch URL extraction via `/contents` (`--urls` repeatable) |
| `get_config_info` | Show config + optional connectivity probe |
| `agent_run` | Create, wait for, resume, or continue an Exa Agent run |

## Agent Runs

Create mode requires `--query`; resume mode requires `--run-id`. The two modes
are mutually exclusive. Create mode additionally supports:

- `--system-prompt`
- UTF-8 JSON files via `--output-schema`, `--input-data`, and `--input-exclusion`
- up to five unique repeatable `--data-source` values
- `--previous-run-id` for a follow-up to a completed run
- `--effort minimal|low|medium|high|xhigh|auto` (default `low`)
- `--wait-seconds` (default 750), `--poll-interval` (default 4), and `--out`

`--run-id` resumes the same unfinished run using GET only. In contrast,
`--previous-run-id` is supplied with a new query and creates a new ID using a
completed run as context. Never create a replacement for a queued/running run.

The CLI always performs at least one GET, including when `--wait-seconds 0`.
Lifecycle results are normalized as follows:

| Status | Result | Exit |
|--------|--------|------|
| `completed` | `success=true`, `outputReady=true`, output plus optional usage/cost | 0 |
| queued/running/unknown at deadline | `status="running"`, same ID, resume command | 0 |
| `failed` | `success=false`, same ID and upstream error | 1 |
| `cancelled` | `success=false`, same ID | 1 |
| Ctrl-C | stderr resume event when ID is known | 130 |

Agent create is non-idempotent and is attempted exactly once. Network errors,
408, 429, or 5xx responses are not retried because an upstream run may already
exist without a recoverable ID. GET polling retains the four-attempt bounded
retry policy. The standalone CLI does not support ZDR streaming.

See [exa-agent.md](exa-agent.md) for objective/schema definition, coverage and
evidence validation, deterministic batch routing, and safe resume/continuation.

## Global Options

Place before the subcommand.

| Option | Purpose |
|--------|---------|
| `--api-url` | Override `EXA_API_URL` |
| `--api-key` | Override `EXA_API_KEY` |
| `--debug` | Stream JSON debug events on stderr (`EXA_DEBUG=true`) |
| `--max-retry-wait <s>` | Cap (seconds) for single retry + exponential backoff (default 60, env: `EXA_MAX_RETRY_WAIT`) |
| `--auth-scheme <scheme>` | Authentication scheme: `x-api-key` (default) or `bearer` for third-party endpoints (env: `EXA_AUTH_SCHEME`) |

## Output

JSON is printed to stdout (`ensure_ascii=False`, indent 2). Use `--out <file>`
to write JSON to a file; stdout then becomes `{"status":"ok","file":"<file>"}`.
Errors go to stderr as `{"error":"<message>"}` with a non-zero exit.
Agent create/interruption progress events also use stderr, leaving stdout as one
machine-readable JSON result. Failed/cancelled Agent results still exit 1 when
the full result is successfully written with `--out`.

## References

`references/` carries 11 prompt-engineering guides (searching,
extraction, filtering, synthesis, source-quality, six pattern files) . Read them on demand for query crafting and migration
context.
