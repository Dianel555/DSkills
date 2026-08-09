# codex-cc

A Codex-facing DSkills bridge that shells out to local Claude Code and returns a stable JSON envelope.

## Overview

`codex-cc` is for the inverse direction of `cc-codex`: Codex calls Claude Code locally.

By default the bridge preserves Claude Code's normal runtime behavior. It does not force `--safe-mode`, `--bare`, `--disable-slash-commands`, or `--strict-mcp-config`, so trusted-workspace customizations such as `CLAUDE.md`, skills, plugins, MCP servers, custom commands, and rules continue to load the same way Claude normally would.

Two runtime caveats still come from Claude Code itself:

- `claude -p` skips the interactive trust dialog, so only use this in directories you already trust.
- Invalid settings files may be silently ignored in print mode, so if inheritance seems missing, validate the workspace `.claude` configuration first.

## Installation

Copy this skill to your Codex skills directory:

```bash
cp -r skills/codex-cc ~/.codex/skills/
```

The bridge expects a working local Claude Code installation available as `claude` on `PATH`.

## Usage

### Basic

```bash
python scripts/claude_bridge.py --cd "/path/to/project" --PROMPT "Analyze the auth flow"
```

### Resume a Claude session

```bash
# Initial turn
python scripts/claude_bridge.py --cd "/project" --PROMPT "Review the failing tests"

# Follow-up turn using the returned SESSION_ID
python scripts/claude_bridge.py --cd "/project" --SESSION_ID "uuid-from-response" --PROMPT "Now write the minimal fix"
```

### Permission overrides are explicit

```bash
python scripts/claude_bridge.py --cd "/project" --PROMPT "Run the test suite" --permission-mode plan
python scripts/claude_bridge.py --cd "/project" --PROMPT "Run unattended in sandbox" --dangerously-skip-permissions
```

### Claude management passthrough

```bash
python scripts/claude_bridge.py mcp list
python scripts/claude_bridge.py plugin list
python scripts/claude_bridge.py plugin marketplace list
```

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--PROMPT` | Yes* | Task instruction for Claude Code |
| `--cd` | Yes* | Workspace root used for both process `cwd` and `--add-dir` |
| `--SESSION_ID` | No | Resume an existing Claude conversation |
| `--model` | No | Claude model override |
| `--permission-mode` | No | Claude permission mode override |
| `--dangerously-skip-permissions` | No | Opt-in permission bypass |
| `--timeout` | No | Hard timeout in seconds for the bridge call |

`*` Not required for `mcp` / `plugin` passthrough invocations.

## Output Format

Successful task execution:

```json
{
  "success": true,
  "SESSION_ID": "uuid",
  "agent_messages": "Claude response text",
  "stderr": "optional diagnostic text"
}
```

Failed task execution:

```json
{
  "success": false,
  "error": "Failure reason",
  "stderr": "optional diagnostic text"
}
```

Passthrough output:

```json
{
  "success": true,
  "output": "...",
  "error": "",
  "returncode": 0
}
```
