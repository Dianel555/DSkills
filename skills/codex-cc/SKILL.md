---
name: codex-cc
description: |
  Delegates coding tasks from Codex to local Claude Code in print mode while preserving Claude's normal runtime customizations by default. Use when: (1) You want Codex to call Claude Code locally, (2) You need Claude-side skills, plugins, MCP servers, custom commands, CLAUDE.md rules, or workspace settings to stay active, (3) You want resumable Claude sessions from Codex via SESSION_ID, (4) You need thin `claude mcp` / `claude plugin` passthrough from the same bridge.
---

## Quick Start

```bash
python scripts/claude_bridge.py --cd "/path/to/project" --PROMPT "Analyze auth flow"
```

**Output:** JSON with `success`, `SESSION_ID`, `agent_messages`, `stream_file`
(the raw Claude JSONL stream), and optional `all_messages`, `stderr`, or `error`.

## Runtime Contract

- Default execution uses `claude -p` and does **not** force `--safe-mode`, `--bare`, `--disable-slash-commands`, or `--strict-mcp-config`.
- Claude Code therefore keeps its normal loading path for trusted-workspace customizations such as `CLAUDE.md`, skills, plugins, MCP servers, custom commands, and rules.
- `claude -p` skips the interactive trust dialog and silently ignores invalid settings files, so use this only in workspaces you already trust and whose `.claude` settings already validate.
- The bridge requests `stream-json`, persists each record immediately, and only treats Claude's final `result` record as a completed answer. Intermediate `assistant` records never mask a failed or incomplete turn.

## Parameters

```text
usage: claude_bridge.py [-h] --PROMPT PROMPT --cd CD [--SESSION_ID SESSION_ID]
                        [--model MODEL]
                        [--permission-mode {,acceptEdits,auto,bypassPermissions,manual,dontAsk,plan}]
                        [--dangerously-skip-permissions] [--timeout TIMEOUT]
                        [--stream-file STREAM_FILE] [--return-all-messages]
                        {mcp,plugin} ...

options:
  --PROMPT PROMPT                Instruction for the task to send to Claude Code.
  --cd CD                        Workspace root for Claude Code (cwd + --add-dir).
  --SESSION_ID SESSION_ID        Resume a conversation by session UUID.
  --model MODEL                  Claude model override.
  --permission-mode ...          Claude permission mode override.
  --dangerously-skip-permissions Bypass Claude permission checks.
  --timeout TIMEOUT              Bridge-level timeout in seconds. Omit for no bridge deadline.
  --stream-file STREAM_FILE      Raw Claude stream-json JSONL destination.
  --return-all-messages          Include parsed stream records in the result.

subcommands:
  mcp                            Thin passthrough to `claude mcp`.
  plugin                         Thin passthrough to `claude plugin`.
```

## Sessions

Capture `SESSION_ID` from the first successful response and reuse it for follow-ups:

```bash
# New Claude session
python scripts/claude_bridge.py --cd "/project" --PROMPT "Inspect failing tests"

# Resume the same Claude session
python scripts/claude_bridge.py --cd "/project" --SESSION_ID "uuid-from-response" --PROMPT "Now propose the fix"
```

## Passthrough

```bash
python scripts/claude_bridge.py mcp list
python scripts/claude_bridge.py plugin list
```
