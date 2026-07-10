---
name: cc-codex
description: |
  Delegates coding tasks to Codex CLI for prototyping, debugging, and code review. Use when: (1) Backend/logic implementation, (2) Algorithm design and optimization, (3) Bug analysis and debugging, (4) API/database code generation, (5) Code quality review and refactoring. Triggers: "implement algorithm", "debug", "analyze code", "backend task", "API implementation", "optimize performance", "refactor", "generate prototype", "code review". IMPORTANT: Always use sandbox="read-only" and request unified diff patches only. Supports multi-turn sessions via SESSION_ID.
---

## Quick Start

```bash
python scripts/codex_bridge.py --cd "/path/to/project" --PROMPT "Your task"
```

**Output:** JSON with `success`, `SESSION_ID`, `agent_messages`, `stream_file` (path to the raw JSONL stream persisted line-by-line), optional `stderr`, and optional `error`.

## Parameters

```
usage: codex_bridge.py [-h] [--PROMPT PROMPT] [--cd CD]
                       [--sandbox {read-only,workspace-write,danger-full-access}]
                       [--SESSION_ID SESSION_ID] [--skip-git-repo-check]
                       [--return-all-messages] [--image IMAGE] [--model MODEL]
                       [--yolo] [--profile PROFILE] [--stream-file STREAM_FILE]
                       [--idle-timeout IDLE_TIMEOUT] [--ignore-user-config]
                       [--dangerously-bypass-hook-trust]
                       {mcp,plugin} ...

Codex Bridge

options:
  --PROMPT PROMPT       Instruction for the task to send to codex.
  --cd CD               Set the workspace root for codex before executing the task.
  --sandbox {read-only,workspace-write,danger-full-access}
                        Sandbox policy for model-generated commands. Defaults to `read-only`.
  --SESSION_ID SESSION_ID
                        Resume the specified session of the codex.
  --skip-git-repo-check
                        Allow codex running outside a Git repository.
  --return-all-messages
                        Return all messages (reasoning, tool calls, etc.).
  --image IMAGE         Attach image files to the initial prompt.
  --model MODEL         Model for the session (only when user explicitly requests).
  --yolo                Bypass approvals/sandboxing (last resort).
  --profile PROFILE     Load `~/.codex/<name>.config.toml` profile (only when user requests).
  --stream-file STREAM_FILE
                        Persist raw JSONL stream path.
  --idle-timeout IDLE_TIMEOUT
                        Kill codex if no output for N seconds (default 600; 0 disables).
  --ignore-user-config  Do not load `$CODEX_HOME/config.toml` (auth still uses CODEX_HOME).
  --dangerously-bypass-hook-trust
                        Run Codex hooks without persisted hook trust. DANGEROUS.

subcommands:
  mcp                   Thin passthrough to `codex mcp` (list/get/add/remove/login/logout).
  plugin                Thin passthrough to `codex plugin` (add/list/remove/marketplace).
```

## Multi-turn Sessions

**Always capture `SESSION_ID`** from the first response for follow-up:

```bash
# Initial task
python scripts/codex_bridge.py --cd "/project" --PROMPT "Analyze auth in login.py"

# Continue with SESSION_ID
python scripts/codex_bridge.py --cd "/project" --SESSION_ID "uuid-from-response" --PROMPT "Write unit tests for that"
```

## Config Inheritance 

| Source | Inherited by default? |
|--------|------------------------|
| `~/.codex/config.toml` | Yes (unless `--ignore-user-config`) |
| Profile (`--profile`) | Only when explicitly passed |
| Project `.codex/` (trusted) | Yes, when Codex trusts the project |
| Hooks / MCP / plugins / skills / `AGENTS.md` | Yes, via Codex runtime |

## Management Passthrough

```bash
python scripts/codex_bridge.py mcp list
python scripts/codex_bridge.py plugin list
```

## Common Patterns

**Prototyping (read-only, request diffs):**
```bash
python scripts/codex_bridge.py --cd "/project" --PROMPT "Generate unified diff to add logging"
```

**Debug with full trace:**
```bash
python scripts/codex_bridge.py --cd "/project" --PROMPT "Debug this error" --return-all-messages
```

**Headless hooks (vetted automation only):**
```bash
python scripts/codex_bridge.py --cd "/project" --PROMPT "..." --dangerously-bypass-hook-trust
```
