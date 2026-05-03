# Exa Search CLI

Standalone CLI for the Exa semantic search API. 
## Installation

```bash
pip install httpx tenacity
```

## Configuration

Set `EXA_API_KEY` via environment variable or `.env` file (loaded from cwd,
`scripts/`, or `skills/exa/`):

```bash
export EXA_API_KEY=your-api-key-here
```

Or copy `scripts/.env.example` to `scripts/.env`.

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

## References

`references/` carries 11 prompt-engineering guides (searching,
extraction, filtering, synthesis, source-quality, six pattern files) . Read them on demand for query crafting and migration
context.
