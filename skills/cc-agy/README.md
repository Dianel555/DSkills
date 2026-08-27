# cc-agy

A Claude Code **Agent Skill** that bridges Claude with the Google Antigravity CLI (`agy`) for external-model delegation(Gemini CLI stopped working for person).

## Overview

This Skill lets Claude delegate coding/research tasks to `agy`, which runs external models — Gemini 3.x, Claude Sonnet/Opus 4.6, GPT-OSS — with their own configured MCP servers, skills, and memory doc. Claude orchestrates the workflow and refines the output; agy executes on the external model.

`agy --print` writes nothing to stdout, so the bridge instead discovers the conversation SQLite DB that agy persists and extracts the assistant reply from its protobuf payload. MCP (`~/.gemini/antigravity/mcp_config.json`), the memory doc (`~/.gemini/GEMINI.md`), and skills are pre-configured by the user and auto-loaded by agy — the bridge does not manage them.

## Features

- **Multi-turn sessions**: Resume conversations via `SESSION_ID` (maps to agy `--conversation`)
- **Multi-model prototyping**: Switch model per call with `--model` aliases (flash, pro, sonnet, opus, gpt-oss)
- **JSON output**: Structured responses isomorphic to `gemini_bridge.py`
- **Cross-platform**: Windows path / UTF-8 handled automatically
- **Setup probe**: `check` subcommand reports agy install / version / auth / current model
- **Plugin passthrough**: `plugin` subcommand forwards to `agy plugin list|import|install|enable|disable`

## Prerequisites

1. Install the Antigravity CLI:
   ```bash
   curl -fsSL https://antigravity.google/cli/install.sh | bash
   ```
2. Authenticate: run `agy` once interactively (browser OAuth), or export `ANTIGRAVITY_API_KEY`.
3. Pick a default model: open `agy` and use `/model`, which writes `~/.gemini/antigravity-cli/settings.json`.

Verify with:
```bash
python scripts/agy_bridge.py check
```

## Installation

Copy this Skill to your Claude Code skills directory:
- User-level: `~/.claude/skills/cc-agy/`
- Project-level: `.claude/skills/cc-agy/`

Or, in the DSkills marketplace, it is registered in `.claude-plugin/marketplace.json` as the `cc-agy` plugin.

## Usage

### Basic

```bash
python scripts/agy_bridge.py --cd "/path/to/project" --PROMPT "Analyze the authentication flow"
```

### Multi-turn Session

```bash
# Start a session
python scripts/agy_bridge.py --cd "/project" --PROMPT "Review login.py for security issues"
# Response includes SESSION_ID

# Continue the session
python scripts/agy_bridge.py --cd "/project" --SESSION_ID "uuid-from-response" --PROMPT "Suggest fixes for the issues found"
```

### Switch Model Per Call

```bash
python scripts/agy_bridge.py --cd "/project" --PROMPT "Review this Rust" --model sonnet
python scripts/agy_bridge.py --cd "/project" --PROMPT "Same code" --model opus
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--PROMPT` | Yes | Task instruction |
| `--cd` | Yes | Workspace root (agy cwd + `--add-dir`) |
| `--model` | No | Model alias or canonical string; omit for settings default |
| `--SESSION_ID` | No | Resume a conversation by UUID (maps to `--conversation`) |
| `--sandbox` | No | Run in agy sandbox mode |
| `--no-skip-permissions` | No | Do NOT pass `--dangerously-skip-permissions` (WARNING: hangs print mode) |
| `--print-timeout` | No | agy `--print-timeout` (e.g. `5m`, `10m`); default `10m` |
| `--return-all-messages` | No | Include reasoning + all `type=15` steps |

Model aliases: `flash-low/medium/high`, `pro-low/high`, `sonnet`, `opus`, `gpt-oss`.

### Subcommands

| Subcommand | Description |
|------------|-------------|
| `check` | Probe agy install / version / auth / current model |
| `plugin` | Thin passthrough to `agy plugin list\|import\|install\|enable\|disable` |

### Output Format

```json
{
  "success": true,
  "SESSION_ID": "uuid",
  "agent_messages": "agy response text"
}
```

## Security Note

By default the bridge passes `--dangerously-skip-permissions` to agy. This is **mandatory for non-interactive `--print` mode**: agy's default `toolPermission` is `request-review`, which blocks waiting for a human to approve tool calls, and `--print` captures no TTY — so the process hangs until timeout. With `--dangerously-skip-permissions`, agy auto-approves all tool calls. The bridge always runs under a hard outer timeout (`--print-timeout` + 60s) so a hung agy cannot block indefinitely. Only use `--no-skip-permissions` in a context where interactive permission prompts can be serviced.

## Known Limitations

- **Protobuf extraction is schema-dependent.** The reply is read from field `f1` inside field `f20` of the last `step_type=15` row in the conversation DB. If agy changes its internal schema, extraction returns empty. Fix location: `extract_answer()` in `scripts/agy_bridge.py`.
- `agy models` returns empty on this build; model aliases are hardcoded.
- `--continue` is intentionally not exposed (target selection is opaque); use `--SESSION_ID` to resume a specific conversation.

## License

MIT License. See [LICENSE](LICENSE) for details.
