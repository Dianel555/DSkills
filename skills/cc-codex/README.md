# cc-codex

A Claude Code **Agent Skill** that bridges Claude with OpenAI Codex CLI for multi-model collaboration on coding tasks.

## Overview

This Skill enables Claude to delegate coding tasks to Codex CLI, combining the strengths of multiple AI models. Codex handles algorithm implementation, debugging, and code analysis while Claude orchestrates the workflow and refines the output.

Codex config (`~/.codex/config.toml`), hooks, MCP servers, plugins, skills, and `AGENTS.md` are loaded by the **Codex process itself**. This bridge does not sync Claude Code MCP/hooks/plugins into Codex — the two runtimes stay separate.

## Features

- **Multi-turn sessions**: Maintain conversation context across multiple interactions via `SESSION_ID`
- **Sandboxed execution**: Three security levels (`read-only`, `workspace-write`, `danger-full-access`)
- **JSON output**: Structured responses for easy parsing and integration
- **Image support**: Attach images to prompts for visual context
- **Cross-platform**: Windows path escaping handled automatically
- **Config isolation**: Optional `--ignore-user-config`
- **Hook trust bypass**: Optional `--dangerously-bypass-hook-trust` for vetted automation
- **Management passthrough**: `mcp` / `plugin` subcommands forward to `codex mcp|plugin`

## Installation

1. Ensure [Codex CLI](https://github.com/openai/codex) is installed and available in your PATH
2. Copy this Skill to your Claude Code skills directory:
   - User-level: `~/.claude/skills/cc-codex/`
   - Project-level: `.claude/skills/cc-codex/`

Or install via the DSkills marketplace entry `cc-codex`.

## Usage

### Basic

```bash
python scripts/codex_bridge.py --cd "/path/to/project" --PROMPT "Analyze the authentication flow"
```

### Multi-turn Session

```bash
# Start a session
python scripts/codex_bridge.py --cd "/project" --PROMPT "Review login.py for security issues"
# Response includes SESSION_ID

# Continue the session
python scripts/codex_bridge.py --cd "/project" --SESSION_ID "uuid-from-response" --PROMPT "Suggest fixes for the issues found"
```

### Manage Codex MCP / plugins

```bash
python scripts/codex_bridge.py mcp list
python scripts/codex_bridge.py plugin list
python scripts/codex_bridge.py plugin marketplace list
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--PROMPT` | Yes* | Task instruction (*not required for `mcp`/`plugin` subcommands) |
| `--cd` | Yes* | Workspace root directory |
| `--sandbox` | No | Security level: `read-only` (default), `workspace-write`, `danger-full-access` |
| `--SESSION_ID` | No | Resume a previous session |
| `--return-all-messages` | No | Include full reasoning trace in output |
| `--image` | No | Attach image files (comma-separated or repeated) |
| `--model` | No | Specify model (use only when explicitly requested) |
| `--profile` | No | Codex profile name (use only when explicitly requested) |
| `--yolo` | No | Bypass all approvals (use with caution) |
| `--ignore-user-config` | No | Skip loading `$CODEX_HOME/config.toml` |
| `--dangerously-bypass-hook-trust` | No | Run hooks without persisted trust (dangerous) |

### Output Format

```json
{
  "success": true,
  "SESSION_ID": "uuid",
  "agent_messages": "Codex response text",
  "stream_file": "/tmp/codex_stream_....jsonl",
  "all_messages": []
}
```

Passthrough (`mcp` / `plugin`) output:

```json
{
  "success": true,
  "output": "...",
  "error": "",
  "returncode": 0
}
```

## License

MIT License. See [LICENSE](LICENSE) for details.
