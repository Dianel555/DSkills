# ACE-Tool CLI

Semantic code search, incremental code indexing, and AI-powered prompt enhancement. MCP-independent CLI for codebase navigation and requirement clarification.

## Features

- **Code Indexing**: Incremental scan, hash (SHA-256), chunk, and upload code blobs to ACE service
- **Remote Search**: Semantic codebase retrieval via `POST /agents/codebase-retrieval` with local fallback
- **Prompt Enhancement**: AI-powered prompt refinement with interactive web UI
- **Cloud Context Injection**: All endpoints (old, new, third-party) inject retrieval context when `--project-root` is provided
- **Multiple Backends**: Support for Augment (`new`/`old`), Claude, OpenAI, Gemini, and Codex APIs
- **Search Context Injection**: Optional codebase context injection for third-party endpoints via XML tags
- **`.aceignore` Support**: Project-level ignore patterns merged with `.gitignore` for indexing
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

# Enhance with codex endpoint
python scripts/ace_cli.py --endpoint codex enhance_prompt -p "implement feature"

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
  --endpoint TYPE       API endpoint: new, old, claude, openai, gemini, codex
  --api-url URL         Override API base URL
  --token TOKEN         Override API token
```

## Endpoint Architecture

### Supported Endpoints

| Endpoint | API Path | Default Model | Type |
|----------|----------|---------------|------|
| `new` | `/prompt-enhancer` | `claude-sonnet-4-5` | Augment |
| `old` | `/chat-stream` (SSE) | `claude-sonnet-4-5` | Augment |
| `claude` | `/v1/messages` | `sonnet-4-6-20250929` | Third-party |
| `openai` | `/v1/chat/completions` | `gpt-5.4` | Third-party |
| `gemini` | `/v1beta/models/{model}:generateContent` | `gemini-3-flash-preview` | Third-party |
| `codex` | `/v1/responses` | `gpt-5.4` | Third-party |

### Endpoint Resolution

Priority order (highest wins):

1. `PROMPT_ENHANCER_ENDPOINT` env var
2. `ACE_ENHANCER_ENDPOINT` env var (legacy fallback)
3. `--endpoint` CLI flag
4. Default: `new`

### Codex Endpoint

The `codex` endpoint routes to OpenAI's Responses API (`/v1/responses`). It uses the `input`/`output` array format instead of the Chat Completions `messages` format. Response parsing handles `output_text` content parts, `final_answer` phase priority, and refusal detection.

```bash
export PROMPT_ENHANCER_ENDPOINT=codex
export PROMPT_ENHANCER_BASE_URL=https://api.openai.com
export PROMPT_ENHANCER_TOKEN=sk-...
python scripts/ace_cli.py enhance_prompt -p "implement feature"
```

### URL Construction

All HTTP calls use `build_api_url(base_url, path)` which handles version prefix deduplication (e.g., `https://api.example.com/v1` + `/v1/messages` → `https://api.example.com/v1/messages`, not `.../v1/v1/messages`).

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ACE_API_URL` | Augment API base URL (required for remote search/indexing) |
| `ACE_API_TOKEN` | Augment API token |
| `PROMPT_ENHANCER_ENDPOINT` | Endpoint type override (takes precedence over `ACE_ENHANCER_ENDPOINT`) |
| `ACE_ENHANCER_ENDPOINT` | Legacy endpoint override (fallback) |
| `PROMPT_ENHANCER_BASE_URL` | Third-party API base URL |
| `PROMPT_ENHANCER_TOKEN` | Third-party API key |
| `PROMPT_ENHANCER_MODEL` | Model override for third-party endpoints |
| `PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT` | Enable search context injection (`1`, `true`, `yes`, `on`) |

### .env File

Create `.env` in scripts directory:

```bash
cp scripts/.env.example scripts/.env
```

Edit `.env`:
```bash
ACE_API_URL=https://your-augment-api.com
ACE_API_TOKEN=your-augment-token
PROMPT_ENHANCER_ENDPOINT=new

# Third-party API (optional)
# PROMPT_ENHANCER_BASE_URL=https://api.anthropic.com
# PROMPT_ENHANCER_TOKEN=your-api-key
# PROMPT_ENHANCER_MODEL=sonnet-4-6-20250929

# Search context injection (optional, for third-party endpoints)
# PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT=1
```

## Search Context Injection

When `PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT` is enabled and a third-party endpoint is used, the system:

1. Searches the codebase via ACE API using the original prompt as query
2. Normalizes the result (placeholder if empty, truncates at 12,000 chars)
3. Wraps search results in `<codebase_context>` XML tags
4. Wraps the original prompt in `<original_request>` XML tags
5. Sends the combined prompt to the third-party LLM

Requirements:
- `--project-root` must be provided (raises `ValueError` otherwise)
- `ACE_API_URL` and `ACE_API_TOKEN` must be configured

This is separate from the cloud retrieval context that Augment endpoints (`new`/`old`) inject automatically via `--project-root`.

## .aceignore

Place a `.aceignore` file in the project root to exclude additional patterns from code indexing. Uses the same glob syntax as `.gitignore`. Patterns from both `.gitignore` and `.aceignore` are merged (union). Comments (`#`) and empty lines are skipped.

```
# .aceignore example
test_fixtures/
*.generated.ts
large_data/
node_modules/
.*/
logs/
tests/
```
## Indexing Details

The `index` command performs incremental indexing:

- **Scan**: Walks project files filtered by extension whitelist, binary blacklist, `.gitignore` + `.aceignore` patterns (with glob support), and `EXCLUDE_PATTERNS`
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

// Configuration
{"base_url": "...", "endpoint": "new", "endpoint_effective": "new", "endpoint_env_ready": true, "token_configured": true, "third_party_configured": false, "search_context_injection": false}

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
    ├── client.py         # API client (search, enhance, retrieval, all endpoints)
    ├── indexer.py         # Code indexer (scan, hash, chunk, upload, .aceignore)
    ├── templates.py      # Prompt templates and constants
    ├── utils.py          # Utilities (encoding detection, content sanitization)
    └── web_ui.py         # Interactive web UI
```

## Acknowledgments

- Based on [missdeer/ace-tool-rs](https://github.com/missdeer/ace-tool-rs)

