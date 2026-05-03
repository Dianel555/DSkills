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
- Other commands: JSON object

## .env File Search Order

1. Current working directory
2. Script directory (`scripts/`)
3. Parent directory of script

## Configuration Persistence

- Model settings: `~/.config/grok-search/config.json`
- Built-in tools toggle: `<project>/.claude/settings.json`

##  Acknowledgments

- Based on the original [GuDaStudio/GrokSearch](https://github.com/GuDaStudio/GrokSearch).
