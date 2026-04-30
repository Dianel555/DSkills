---
name: ace-tool
description: |
  Semantic codebase search, code indexing, and prompt enhancement via standalone CLI. Use when: (1) Semantic code search with natural language queries, (2) Code indexing for remote codebase retrieval, (3) Prompt enhancement with codebase context, (4) Before grep/find/glob operations for better accuracy, (5) Complex requirements clarification, (6) Large codebase navigation. Triggers: "search context", "enhance prompt", "find code that", "index project", "clarify requirements". IMPORTANT: Always use ace-tool BEFORE grep/find/glob for semantic-level code location.
---

# ACE-Tool - Semantic Code Search & Prompt Enhancement

High-performance semantic search, code indexing, and AI-powered prompt enhancement. Standalone CLI (no MCP dependency).

## Execution Methods

```bash
# Prerequisites: pip install httpx tenacity
# Environment: ACE_API_URL, ACE_API_TOKEN (optional for local fallback)

# Index project for remote search (upload code blobs to ACE service)
python scripts/ace_cli.py index -p /path/to/project

# Search codebase with natural language (remote if API configured, else local fallback)
python scripts/ace_cli.py search_context -p /path/to/project -q "function that handles authentication"

# Enhance prompt (interactive mode - default, opens browser)
python scripts/ace_cli.py enhance_prompt -p "implement login feature" -H "User: what auth method?\nAssistant: JWT"

# Enhance prompt (non-interactive, JSON output)
python scripts/ace_cli.py enhance_prompt --no-interactive -p "implement login feature"

# Enhance prompt with project context (enables cloud retrieval for all endpoints)
python scripts/ace_cli.py enhance_prompt -p "implement login feature" --project-root /path/to/project

# Enhance prompt with specific endpoint
python scripts/ace_cli.py --endpoint claude enhance_prompt -p "implement login feature"

# Enhance prompt with codex endpoint
python scripts/ace_cli.py --endpoint codex enhance_prompt -p "implement feature"

# Check configuration
python scripts/ace_cli.py get_config
```

## Tool Routing Policy

### Prefer ACE-Tool Over Built-in Tools

| Task | Avoid | Use ACE-Tool CLI |
|------|-------|------------------|
| Find function by purpose | `grep "def func"` | `search_context -q "function that..."` |
| Locate feature code | `find . -name "*.py"` | `search_context -q "feature description"` |
| Clarify requirements | Manual analysis | `enhance_prompt -p "requirement"` |
| Understand code flow | Multiple grep/read | `search_context -q "flow description"` |
| Index codebase | N/A | `index -p <project_root>` |

### When to Use Built-in Tools
- Exact string matching (known identifiers)
- File path patterns (known naming conventions)
- Simple text replacement

## Command Reference

### index
Index project files for remote codebase retrieval. Scans, hashes, chunks large files, and uploads to the ACE batch-upload API. Uses incremental indexing with gzip JSON cache at `.ace-tool/index.json.gz`. Respects both `.gitignore` and `.aceignore` patterns.

```bash
python scripts/ace_cli.py index -p <project_root>

Options:
  -p, --project-root    Project root path (required)
```

### search_context
Search codebase using natural language descriptions. Routes to remote API (`POST /agents/codebase-retrieval`) when configured, with automatic local keyword fallback.

```bash
python scripts/ace_cli.py search_context -p <project_root> -q <query>

Options:
  -p, --project-root    Project root path (required)
  -q, --query           Natural language query (required)
```

### enhance_prompt
Enhance prompts with codebase context and conversation history. All endpoints inject cloud retrieval context when `--project-root` is provided. Third-party endpoints additionally support search context injection via `PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT`.

```bash
python scripts/ace_cli.py [--endpoint TYPE] enhance_prompt -p <prompt> [options]

Global Options:
  --endpoint            Endpoint type: new, old, claude, openai, gemini, codex (default: new)
  --api-url             Override API base URL
  --token               Override API token

Command Options:
  -p, --prompt          Original prompt (required)
  -H, --history         Conversation history: "User: xxx\nAssistant: yyy"
  --history-file        File containing conversation history
  --project-root        Project root path (enables cloud retrieval context)
  --no-interactive      Disable web UI, output JSON directly
  --no-browser          Don't auto-open browser, just print URL
  --port                Port for web server (default: 8765)
```

### get_config
Show current configuration status including endpoint resolution, env readiness, and search context injection state.

```bash
python scripts/ace_cli.py get_config
```

Output fields: `base_url`, `endpoint`, `endpoint_effective`, `endpoint_env_ready`, `token_configured`, `third_party_configured`, `search_context_injection`.
## Interactive Enhancement

Default mode opens web UI with actions:

| Button | Action |
|--------|--------|
| **Regenerate** | Discard current, generate new enhancement from original prompt |
| **Refine** | Iteratively improve current version, preserving your edits |
| **Use Original** | Return the original prompt without enhancement |
| **Send Enhanced** | Confirm and use the current enhanced prompt |
| **Cancel** | Abort the enhancement process |

**Keyboard Shortcuts:** `Ctrl+Enter` Send | `Esc` Cancel

## Endpoint Architecture

### Supported Endpoints

| Endpoint | API Path | Default Model | Auth Header |
|----------|----------|---------------|-------------|
| `new` | `/prompt-enhancer` | `claude-sonnet-4-5` | `Bearer ACE_API_TOKEN` |
| `old` | `/chat-stream` (SSE) | `claude-sonnet-4-5` | `Bearer ACE_API_TOKEN` |
| `claude` | `/v1/messages` | `sonnet-4-6-20250929` | `x-api-key` |
| `openai` | `/v1/chat/completions` | `gpt-5.4` | `Bearer PROMPT_ENHANCER_TOKEN` |
| `gemini` | `/v1beta/models/{model}:generateContent` | `gemini-3-flash-preview` | `x-goog-api-key` |
| `codex` | `/v1/responses` | `gpt-5.4` | `Bearer PROMPT_ENHANCER_TOKEN` |

### Endpoint Resolution Order

`PROMPT_ENHANCER_ENDPOINT` > `ACE_ENHANCER_ENDPOINT` (legacy) > `--endpoint` CLI flag > `new` (default)

### Third-Party Endpoints

`claude`, `openai`, `gemini`, `codex` are third-party endpoints. They require:
- `PROMPT_ENHANCER_BASE_URL` — API base URL
- `PROMPT_ENHANCER_TOKEN` — API key/token
- `PROMPT_ENHANCER_MODEL` — (optional) override default model

Missing configuration raises `ValueError` immediately (hard error, no silent fallback).

### URL Construction

All HTTP calls use `build_api_url(base_url, path)` which handles `/v1/`, `/v1beta/` version prefix deduplication. No hardcoded f-string URL construction.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ACE_API_URL` | ACE API base URL (required for remote search/indexing) |
| `ACE_API_TOKEN` | ACE API authentication token |
| `PROMPT_ENHANCER_ENDPOINT` | Endpoint override: `new`, `old`, `claude`, `openai`, `gemini`, `codex` |
| `ACE_ENHANCER_ENDPOINT` | Legacy endpoint override (fallback if `PROMPT_ENHANCER_ENDPOINT` not set) |
| `PROMPT_ENHANCER_BASE_URL` | Third-party API base URL (for claude/openai/gemini/codex endpoints) |
| `PROMPT_ENHANCER_TOKEN` | Third-party API token |
| `PROMPT_ENHANCER_MODEL` | Override default model for third-party endpoints |
| `PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT` | Enable search context injection for third-party endpoints (`1`, `true`, `yes`, `on`) |

## Search Context Injection

When `PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT` is enabled and a third-party endpoint is used, the system automatically:
1. Performs a remote codebase search via ACE API using the original prompt as query
2. Normalizes the result (placeholder if empty, truncate at 12000 chars if too long)
3. Wraps the search results in `<codebase_context>` XML tags
4. Wraps the original prompt in `<original_request>` XML tags
5. Sends the combined prompt to the third-party LLM

Requires `--project-root` and valid `ACE_API_URL`/`ACE_API_TOKEN`. Raises `ValueError` if `project_root` is missing when injection is enabled.

## .aceignore

Place a `.aceignore` file in the project root to exclude additional patterns from code indexing (beyond `.gitignore`). Uses the same glob syntax as `.gitignore`. Patterns from both files are merged (union). Comments (`#`) and empty lines are skipped.

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
## Workflow

### Phase 0: Index Project (once or after major changes)
```bash
index -p .                                            # Upload code blobs to ACE
```

### Phase 1: Semantic Search
```bash
search_context -p . -q "database connection pooling"  # Remote retrieval or local fallback
```

### Phase 2: Prompt Enhancement
```bash
enhance_prompt -p "optimize query performance" --project-root .  # With cloud context
# Review and refine enhanced prompt
# Use Regenerate/Refine as needed
# Send Enhanced to confirm
```

## Error Handling

```json
{"error": "error message", "status_code": 401}
```

| Error | Recovery |
|-------|----------|
| No API configured | Uses local fallback for search_context; returns original for enhance |
| Token invalid (401) | Check API token (logged at ERROR level) |
| Access denied (403) | Token may be disabled (logged at ERROR level) |
| Upload failure | Index rollback to previous state; cached blobs still returned |
| Connection timeout | Retries up to 3 times with exponential backoff |
| No results | Broaden search query |
| Third-party not configured | `ValueError` raised immediately (no silent fallback) |
| Search context missing project_root | `ValueError` raised when injection enabled without `--project-root` |

## Anti-Patterns

| Prohibited | Correct |
|------------|---------|
| Grep before semantic search | Use `search_context` first |
| Skip prompt enhancement | Use `enhance_prompt` for complex tasks |
| Ignore conversation history | Include history in `enhance_prompt` |
| Use exact match for conceptual search | Use natural language query |
| Always use non-interactive mode | Use interactive mode for review |
| Skip `--project-root` for enhance | Include it for cloud-based code context |


