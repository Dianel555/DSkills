---
name: exa
description: |
  High-precision semantic search and content retrieval via Exa API. Use when: (1) Deep research requiring semantic understanding, (2) Code documentation and examples lookup, (3) Company/professional research, (4) AI-powered comprehensive research tasks, (5) URL content extraction with structured output. Triggers: "research", "find papers", "code examples", "company info", "LinkedIn profiles", "deep analysis". Differentiator: Exa excels at semantic/neural search while grok-search is better for real-time news and general web content.
---

# Exa Search

High-precision semantic search via Exa API. Standalone CLI only (no MCP dependency).

## Execution Method

```bash
# Prerequisites: pip install httpx tenacity
# Environment: EXA_API_KEY (required), EXA_API_URL (optional, default: https://api.exa.ai)

# All examples assume cwd == skills/exa/. The shim auto-chdirs if you launch
# it from elsewhere (e.g., the repo root).
cd skills/exa
python scripts/exa_cli.py --help
```

## Available Tools

```bash
# Basic semantic search (highlights always on; supports inline category:<type>)
python scripts/exa_cli.py web_search_exa --query "TypeScript design patterns" [--num-results 10]
python scripts/exa_cli.py web_search_exa --query "category:company Anthropic AI safety"

# Batch URL fetch (urls is a repeatable flag; payload field is upstream `ids`)
python scripts/exa_cli.py web_fetch_exa \
  --urls "https://a.com" --urls "https://b.com" \
  [--max-chars 3000] [--out content.json]

# Advanced filtered search (list params are repeatable flags, no comma syntax)
python scripts/exa_cli.py web_search_advanced_exa --query "transformer" \
  [--type auto|fast|instant] [--category research\ paper] \
  [--include-domains arxiv.org --include-domains papers.nips.cc] \
  [--exclude-domains medium.com] \
  [--include-text "attention"] [--exclude-text "tutorial"] \
  [--start-date 2024-01-01] [--end-date 2024-12-31] \
  [--num-results 10] [--max-age-hours 168] \
  [--text] [--highlights] [--summary] \
  [--max-chars 5000]   # only effective when --text is set; emits stderr warning otherwise
  [--out results.json]

# Configuration / connectivity probe (omit --no-test to run a numResults=1 ping)
python scripts/exa_cli.py get_config_info [--no-test]
```

## Tool Capability Matrix

| Tool | Required | Optional | Output |
|------|----------|----------|--------|
| `web_search_exa` | `--query` | `--num-results` (1-100) | Search results JSON (highlights always present) |
| `web_fetch_exa` | `--urls` (repeatable, ≥1) | `--max-chars` (default 3000), `--out` | `/contents` response JSON |
| `web_search_advanced_exa` | `--query` | `--type`, `--category`, repeatable `--include-domains`/`--exclude-domains`/`--include-text`/`--exclude-text`, `--start-date`, `--end-date`, `--num-results`, `--max-age-hours`, `--text`, `--highlights`, `--summary`, `--max-chars`, `--out` | Filtered search results JSON |
| `get_config_info` | – | `--no-test` | Config + (default) `connection_test` |

## Global Options

Place before the subcommand:

| Option | Purpose |
|--------|---------|
| `--api-url` | Override `EXA_API_URL` (does not write to `os.environ`) |
| `--api-key` | Override `EXA_API_KEY` |
| `--debug`   | Enable JSON debug events on stderr (`EXA_DEBUG=true`) — never logs auth values |
| `--max-retry-wait <s>` | Cap (seconds) for single retry wait + exponential backoff (default 60, env: `EXA_MAX_RETRY_WAIT`) |

## Tool Routing Guide

| Use Case | Recommended Tool |
|----------|------------------|
| Real-time news, current events | grok-search |
| Semantic/conceptual research | **exa** (`web_search_exa`) |
| Domain or date-bounded research | **exa** (`web_search_advanced_exa`) |
| Read full content of one or more URLs | **exa** (`web_fetch_exa`) |
| Academic papers, technical docs | **exa** (`web_search_advanced_exa --include-domains arxiv.org ...`) |

## Workflow Patterns

### Pattern 1: Quick Semantic Search
```bash
python scripts/exa_cli.py web_search_exa --query "best practices for React hooks" --num-results 5
```

### Pattern 2: Filtered Research (repeatable flags)
```bash
python scripts/exa_cli.py web_search_advanced_exa --query "transformer architecture" \
  --include-domains arxiv.org --include-domains papers.nips.cc \
  --start-date 2023-01-01 --text --summary
```

### Pattern 3: Batch URL Read
```bash
python scripts/exa_cli.py web_fetch_exa \
  --urls "https://example.com/a" --urls "https://example.com/b" \
  --max-chars 4000 --out batch.json
```

## References

The `references/` directory carries 11 prompt-engineering guides. Open them on demand when crafting queries:

| File | When to read |
|------|--------------|
| `searching.md` | Crafting `web_search_exa` queries (semantic phrasing, category usage) |
| `extraction.md` | Choosing between highlights / text / summary on advanced search |
| `filtering.md` | Building include/exclude domain & date filters |
| `synthesis.md` | Aggregating multiple result sets into a coherent answer |
| `source-quality.md` | Vetting source credibility |
| `patterns-code.md` | Code/library research recipes |
| `patterns-companies.md` | Company research recipes |
| `patterns-news.md` | Current-events research recipes |
| `patterns-papers.md` | Academic paper recipes |
| `patterns-people.md` | People search recipes |
| `patterns-relationships.md` | Multi-entity relationship research |

## Error Handling

| Error | Recovery |
|-------|----------|
| `EXA_API_KEY not configured` | Set environment variable or pass `--api-key` |
| HTTP 408/429/5xx | Automatic retry with exponential backoff (max 4 attempts, capped by `--max-retry-wait`) |
| HTTP 401 | Verify API key |
| Timeout | Reduce `--num-results` or retry |

## Output Format

All commands print JSON (`ensure_ascii=False`, indent 2) to stdout. With `--out
<file>`, the response JSON is written to that path and stdout becomes
`{"status":"ok","file":"<file>"}`. Errors go to stderr as
`{"error":"<message>"}` with non-zero exit.
