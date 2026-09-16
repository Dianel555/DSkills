# GrokSearch CLI

Standalone command-line interface for Grok web search. No MCP dependency required.

## Installation

```bash
pip install httpx tenacity
```

## Layout

```text
groksearch_cli.py      # CLI entrypoint and compatibility facade
groksearch/           # Internal implementation modules
  cli.py              # argparse wiring
  commands.py         # command handlers
  config.py           # environment and persisted config
  http.py             # shared client and retry helpers
  provider.py         # Grok OpenAI-compatible provider
  tavily.py           # Tavily search/extract/map calls
  formatting.py       # JSON extraction and result merging
```

## Configuration

### Option 1: .env File (Recommended)

Create a `.env` file in the scripts directory:

```bash
cp .env.example .env
```

Edit `.env`:
```
GROK_API_URL=https://your-api-endpoint.com/v1
GROK_API_KEY=your-api-key-here
```

### Option 2: Environment Variables

```bash
export GROK_API_URL="https://your-api-endpoint.com/v1"
export GROK_API_KEY="your-api-key-here"
export TAVILY_API_KEY="your-tavily-key"  # optional
```

### Option 3: Command Line Arguments

```bash
python groksearch_cli.py --api-url "https://..." --api-key "sk-..." web_search -q "query"
```

## Commands

### web_search - Web Search

```bash
python groksearch_cli.py web_search --query "search terms" [options]

Options:
  -q, --query        Search query (required)
  -p, --platform     Focus platforms, e.g., "GitHub,Reddit"
  --min-results      Minimum results (default: 3)
  --max-results      Maximum results (default: 10)
  --extra-sources    Additional Tavily results to merge (default: 0)
  --raw              Output raw response without JSON parsing
```

Example:
```bash
python groksearch_cli.py web_search -q "latest Python 3.12 features" --max-results 5
```

### web_fetch - Fetch Webpage Content

```bash
python groksearch_cli.py web_fetch --url "https://..." [options]

Options:
  -u, --url          URL to fetch (required)
  -o, --out          Output file path (optional)
  --via              Fetch backend: grok|tavily (default: grok)
```

Example:
```bash
python groksearch_cli.py web_fetch -u "https://docs.python.org/3/whatsnew/3.12.html" -o python312.md
```

### web_map - Map Website Structure

```bash
python groksearch_cli.py web_map --url "https://..." [options]

Options:
  -u, --url          Root URL to map (required)
  --instructions     Natural language filter for crawler
  --max-depth        Max traversal depth (default: 1)
  --max-breadth      Max links per page (default: 20)
  --limit            Total link limit (default: 50)
  --timeout          Operation timeout in seconds (default: 150)
```

### get_config_info - Check Configuration

```bash
python groksearch_cli.py get_config_info [options]

Options:
  --no-test          Skip connection test
```

### switch_model - Switch Grok Model

```bash
python groksearch_cli.py switch_model --model "model-id"

Options:
  -m, --model        Model ID to switch to (required)
```

Example:
```bash
python groksearch_cli.py switch_model -m "grok-2-latest"
```

### toggle_builtin_tools - Toggle Built-in Tools

```bash
python groksearch_cli.py toggle_builtin_tools [options]

Options:
  -a, --action       Action: on/off/status (default: status)
  -r, --root         Project root path (default: auto-detect via .git)
```

Example:
```bash
# Disable built-in WebSearch/WebFetch
python groksearch_cli.py toggle_builtin_tools -a on

# Enable built-in tools
python groksearch_cli.py toggle_builtin_tools -a off

# Check status
python groksearch_cli.py toggle_builtin_tools -a status
```

## Output Format

- `web_search`: JSON array `[{title, url, description, provider?}]`
- `web_fetch`: Structured Markdown
- `web_map`: JSON object `{base_url, results, response_time}`
- `web_crawl`: JSON object `{base_url, results, response_time, usage?}`
- `web_research`: JSON object `{request_id, status, content, sources, usage?}`
- Other commands: JSON object

## .env File Search Order

1. Current working directory
2. Script directory (`scripts/`)
3. Parent directory of script

## Configuration Persistence

- Model settings: `~/.config/grok-search/config.json`
- Built-in tools toggle: `<project>/.claude/settings.json`

## Tavily Tuning

Search and extract are tunable via `.env` (or environment). All are optional; defaults follow
Tavily's own agent guidance.

| Variable | Default | Values | Notes |
|----------|---------|--------|-------|
| `TAVILY_SEARCH_DEPTH` | `advanced` | `advanced` / `basic` / `fast` / `ultra-fast` | `advanced` = 2 credits, highest relevance, reaches more sources — best for grounding niche/recent/multi-facet queries. Others = 1 credit. `ultra-fast` returns one summary per URL instead of reranked chunks. |
| `TAVILY_CHUNKS_PER_SOURCE` | `3` | `1`–`5` | Snippets (≤500 chars) per source; joined by `[...]`. More = stronger evidence per URL. |
| `TAVILY_TOPIC` | `general` | `general` / `news` / `finance` | `news` auto-adds `published_date`. |
| `TAVILY_TIME_RANGE` | *(unset)* | `day` / `week` / `month` / `year` | Publish-date window. Sources with no detectable date are kept unless filtered. |
| `TAVILY_INCLUDE_DOMAINS` | *(unset)* | comma-separated | Restrict or boost to these domains (max 300). |
| `TAVILY_EXCLUDE_DOMAINS` | *(unset)* | comma-separated | Drop these domains (max 150). |
| `TAVILY_INCLUDE_DOMAINS_MODE` | `filter` | `filter` / `boost` | `boost` also searches the wide web, so trusted sources are prioritized without risking empty results. Only sent when `TAVILY_INCLUDE_DOMAINS` is set. |
| `TAVILY_INCLUDE_ANSWER` | `false` | `false` / `basic` / `advanced` | LLM-generated answer. Extra cost; off by default. |
| `TAVILY_INCLUDE_USAGE` | `false` | `true` / `false` | Add credit `usage` to each response. Search attaches it as `tavily_usage` on the first merged result; map/crawl/research include a `usage` key in their JSON object. |
| `TAVILY_EXTRACT_DEPTH` | `basic` | `basic` / `advanced` | `advanced` handles tables, JS-rendered pages, structured data — higher latency and cost. Also used for crawl extraction. |
| `TAVILY_EXTRACT_TIMEOUT` | `30` | `1.0`–`60.0` | Tavily-side timeout for `web_fetch --via tavily`. The HTTP client waits 10s longer so Tavily's diagnosable error wins. Applies per attempt; with retries the total wall time can reach `timeout × attempts`. |
| `TAVILY_CRAWL_TIMEOUT` | `150` | `10`–`150` | Crawl-side timeout (API range). Client waits 10s longer. Applies per attempt; with retries the total wall time can reach `timeout × attempts`. |
| `TAVILY_CRAWL_MAX_DEPTH` | `1` | int | Crawl depth. |
| `TAVILY_CRAWL_MAX_BREADTH` | `20` | int | Links followed per page. |
| `TAVILY_CRAWL_LIMIT` | `50` | int | Total pages crawled. |
| `TAVILY_CRAWL_ALLOW_EXTERNAL` | `true` | `true` / `false` | `false` keeps the crawl on one site. |
| `TAVILY_CRAWL_SELECT_PATHS` | *(unset)* | comma-separated regexes | Include only matching paths. |
| `TAVILY_CRAWL_EXCLUDE_PATHS` | *(unset)* | comma-separated regexes | Exclude matching paths. |
| `TAVILY_RESEARCH_MODEL` | `auto` | `mini` / `pro` / `auto` | Research agent model. |
| `TAVILY_RESEARCH_CITATION_FORMAT` | `numbered` | `numbered` / `mla` / `apa` / `chicago` | Citation style in the report. |
| `TAVILY_RESEARCH_OUTPUT_LENGTH` | `standard` | `short` / `standard` / `long` | Report length. |
| `TAVILY_RESEARCH_OUTPUT_SCHEMA` | *(unset)* | path to a JSON file | Structured output. The file must be a JSON Schema with non-empty `properties`; each property needs `type` (`object`/`string`/`integer`/`number`/`array`) and `description`. Invalid schemas are reported before any request is sent. When set, `content` in the response is an object rather than a string. |
| `TAVILY_RESEARCH_TIMEOUT` | `300` | seconds | Total polling budget before returning `status: timeout` (with `request_id` so the task can be re-fetched). A poll HTTP/network failure returns `status: poll_error` with the same `request_id`. |
| `TAVILY_RESEARCH_POLL_INTERVAL` | `5` | seconds | Delay between status checks. |

Rate limits: 100 RPM (development key) / 1000 RPM (production). A `429` carries a
`retry-after` header, which the retry logic honors. `crawl` is capped at 100 RPM and
`research` at 20 RPM on both tiers.

Example — recent, trusted sources only:

```bash
TAVILY_TOPIC=news TAVILY_TIME_RANGE=week \
TAVILY_INCLUDE_DOMAINS="reuters.com,bloomberg.com" TAVILY_INCLUDE_DOMAINS_MODE=boost \
python groksearch_cli.py web_search -q "AI regulation" --extra-sources 5
```

Invalid values are reported per-key by `get_config_info` rather than silently ignored.

##  Acknowledgments

- Based on the original [GuDaStudio/GrokSearch](https://github.com/GuDaStudio/GrokSearch).
