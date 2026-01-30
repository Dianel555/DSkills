# GrokSearch CLI

Standalone command-line interface for Grok web search. No MCP dependency required.

## Installation

```bash
pip install httpx tenacity
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
```

Example:
```bash
python groksearch_cli.py web_fetch -u "https://docs.python.org/3/whatsnew/3.12.html" -o python312.md
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

- `web_search`: JSON array `[{title, url, description}]`
- `web_fetch`: Structured Markdown
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
