# ACE-Tool CLI

Semantic code search, incremental code indexing, and AI-powered prompt enhancement. MCP-independent CLI for codebase navigation and requirement clarification.

## Features

- **Code Indexing**: Incremental scan, hash (SHA-256), chunk, and upload code blobs to ACE service
- **Remote Search**: Semantic codebase retrieval via `POST /agents/codebase-retrieval` with local fallback
- **Prompt Enhancement**: AI-powered prompt refinement with interactive web UI
- **Cloud Context Injection**: All endpoints (old, new, third-party) inject retrieval context when `--project-root` is provided
- **Multiple Backends**: Support for Augment, Claude, OpenAI, and Gemini APIs
- **Local Fallback**: Works offline with keyword-based search

## Installation

```bash
pip install httpx tenacity
```

## Quick Start

```bash
# Set API credentials (optional, enables remote search and indexing)
export ACE_API_URL="https://your-api-endpoint.com"
export ACE_API_TOKEN="your-token-here"

# Index project (scan, hash, upload code blobs)
python scripts/ace_cli.py index -p .

# Search codebase (remote retrieval if API configured, else local fallback)
python scripts/ace_cli.py search_context -p . -q "user authentication handler"

# Enhance prompt (opens interactive web UI)
python scripts/ace_cli.py enhance_prompt -p "implement login feature" --project-root .

# Enhance prompt (non-interactive, JSON output)
python scripts/ace_cli.py enhance_prompt --no-interactive -p "implement login feature" --project-root .

# Show configuration
python scripts/ace_cli.py get_config
```

## CLI Commands

### Indexing
| Command | Description |
|---------|-------------|
| `index -p <path>` | Index project: scan, hash, chunk, upload blobs |

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
| `enhance_prompt --project-root <path> -p <prompt>` | Enhance with cloud code context |

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

## Indexing Details

The `index` command performs incremental indexing:

- **Scan**: Walks project files filtered by extension whitelist, binary blacklist, `.gitignore` patterns (with glob support), and `EXCLUDE_PATTERNS`
- **Hash**: `SHA-256(path_bytes + content_bytes)` per blob
- **Chunk**: Files >800 lines split as `file.py#chunk1of3` format
- **Cache**: Incremental via `mtime + size` check; stored as `.ace-tool/index.json.gz`
- **Upload**: Batch upload (≤30 blobs, ≤1MB per batch) to `POST /batch-upload` with retry (429 Retry-After, 5xx exponential backoff, 401/403 abort)
- **Rollback**: Upload failure prevents index save, preserving previous valid state
- **Encoding**: Multi-encoding detection chain (`utf-8 → gbk → gb18030 → cp1252`)

## Output Format

All CLI output is JSON:

```json
// Index result
{"total_blobs": 42, "last_indexed": 1234567890.0, "project_root": "."}

// Search result (remote)
{"results": "formatted retrieval text...", "query": "...", "mode": "remote", "blob_count": 42}

// Search result (local fallback)
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
    ├── client.py         # API client (search, enhance, retrieval)
    ├── indexer.py         # Code indexer (scan, hash, chunk, upload)
    ├── templates.py      # Prompt templates and constants
    ├── utils.py          # Utilities (encoding detection, content sanitization)
    └── web_ui.py         # Interactive web UI
```

## Acknowledgments

- Based on [missdeer/ace-tool-rs](https://github.com/missdeer/ace-tool-rs)
