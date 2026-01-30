# ACE-Tool CLI

Semantic code search and AI-powered prompt enhancement. MCP-independent CLI for codebase navigation and requirement clarification.

## Features

- **Semantic Search**: Find code using natural language descriptions
- **Prompt Enhancement**: AI-powered prompt refinement with interactive web UI
- **Multiple Backends**: Support for Augment, Claude, OpenAI, and Gemini APIs
- **Local Fallback**: Works offline with keyword-based search

## Installation

```bash
pip install httpx tenacity
```

## Quick Start

```bash
# Set API credentials (optional, enables remote search)
export ACE_API_URL="https://your-api-endpoint.com"
export ACE_API_TOKEN="your-token-here"

# Search codebase
python scripts/ace_cli.py search_context -p . -q "user authentication handler"

# Enhance prompt (opens interactive web UI)
python scripts/ace_cli.py enhance_prompt -p "implement login feature"

# List available tools
python scripts/ace_cli.py get_config
```

## CLI Commands

### Search Operations
| Command | Description |
|---------|-------------|
| `search_context -p <path> -q <query>` | Search codebase with natural language |

### Enhancement Operations
| Command | Description |
|---------|-------------|
| `enhance_prompt -p <prompt>` | Enhance prompt (interactive UI) |
| `enhance_prompt --no-interactive -p <prompt>` | Enhance prompt (JSON output) |
| `enhance_prompt -H <history> -p <prompt>` | Enhance with conversation history |

### Configuration
| Command | Description |
|---------|-------------|
| `get_config` | Show current configuration |

## Global Options

```bash
python scripts/ace_cli.py [OPTIONS] <command>

Options:
  --endpoint TYPE       API endpoint: new, old, claude, openai, gemini
  --api-url URL         Override API base URL
  --token TOKEN         Override API token
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ACE_API_URL` | Augment API base URL |
| `ACE_API_TOKEN` | Augment API token |
| `ACE_ENHANCER_ENDPOINT` | Default endpoint type |
| `PROMPT_ENHANCER_BASE_URL` | Third-party API base URL |
| `PROMPT_ENHANCER_TOKEN` | Third-party API key |
| `PROMPT_ENHANCER_MODEL` | Model override |

### .env File

Create `.env` in scripts directory:

```bash
cp scripts/.env.example scripts/.env
```

Edit `.env`:
```bash
ACE_API_URL=https://your-augment-api.com
ACE_API_TOKEN=your-augment-token
ACE_ENHANCER_ENDPOINT=new

# Third-party API (optional)
PROMPT_ENHANCER_BASE_URL=https://api.anthropic.com
PROMPT_ENHANCER_TOKEN=your-api-key
PROMPT_ENHANCER_MODEL=claude-sonnet-4-5-20250929
```

## Output Format

All CLI output is JSON:

```json
// Search result
{"results": [{"file": "src/auth.py", "score": 5}], "query": "...", "mode": "local_fallback"}

// Enhancement result
{"enhanced_prompt": "..."}

// Error
{"error": "message", "status_code": 401}
```

## Project Structure

```
skills/ace-tool/
├── SKILL.md              # Agent instructions
├── README.md             # Developer documentation
└── scripts/
    ├── .env.example      # Environment template
    ├── __init__.py
    ├── __main__.py       # Module entry point
    ├── ace_cli.py        # CLI entry point
    ├── client.py         # API client
    ├── templates.py      # Prompt templates
    ├── utils.py          # Utilities
    └── web_ui.py         # Interactive web UI
```

## Acknowledgments

- Based on [missdeer/ace-tool-rs](https://github.com/missdeer/ace-tool-rs)
