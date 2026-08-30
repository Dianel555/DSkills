---
name: cc-agy
description: |
  Delegates coding/research tasks to the Google Antigravity CLI (`agy`) for external-model execution (Gemini 3.x, Claude Sonnet/Opus 4.6, GPT-OSS). Replaces the broken `collaborating-with-gemini` skill. Use when: (1) External-model delegation via Antigravity, (2) Multi-model prototyping (switch model per call), (3) Backend/logic implementation, (4) Algorithm design and optimization, (5) Bug analysis and debugging, (6) API/database code generation, (7) Code review. Triggers: "delegate to agy", "use Antigravity", "external model", "agy", "Gemini 3.5", "Claude Sonnet 4.6", "GPT-OSS". IMPORTANT: Always request unified diff patches only. Supports multi-turn sessions via SESSION_ID.
---

## Quick Start

```bash
python scripts/agy_bridge.py --cd "/path/to/project" --PROMPT "Your task"
```

**Output:** JSON with `success`, `SESSION_ID`, `agent_messages`, `steps_file`, and optional `error` / `note` / `stderr`. On failure, `error` names the upstream cause agy recorded (e.g. a 400/503 status) when one exists.

## Parameters

```
usage: agy_bridge.py [-h] --PROMPT PROMPT --cd CD
                     [--model MODEL] [--SESSION_ID SESSION_ID]
                     [--sandbox] [--no-skip-permissions]
                     [--print-timeout PRINT_TIMEOUT]
                     [--return-all-messages]
                     {check,plugin} ...

Antigravity (agy) Bridge

options:
  -h, --help            show this help message and exit
  --PROMPT PROMPT       Instruction for the task to send to agy.
  --cd CD               Workspace root for agy (sets cwd + --add-dir).
  --model MODEL         Model alias (flash-low/medium/high, pro-low/high, sonnet,
                        opus, gpt-oss) or canonical string. Omit to use the
                        settings.json default.
  --SESSION_ID SESSION_ID
                        Resume a conversation by UUID. Maps to agy --conversation.
  --sandbox             Run in agy sandbox mode.
  --no-skip-permissions
                        Do NOT pass --dangerously-skip-permissions. WARNING:
                        with default toolPermission=request-review, print mode
                        WILL HANG. Only for interactive review workflows.
  --print-timeout PRINT_TIMEOUT
                        agy --print-timeout (e.g. 5m, 10m). Default 10m.
  --return-all-messages
                        Include reasoning + all type=15 steps in the response.

subcommands:
  check                 Probe agy install / version / auth / current model.
  plugin                Thin passthrough to `agy plugin list|import|install|enable|disable`.
```

## Multi-turn Sessions

**Always capture `SESSION_ID`** from the first response for follow-up (maps to agy `--conversation <UUID>`, which appends to the same conversation DB):

```bash
# Initial task
python scripts/agy_bridge.py --cd "/project" --PROMPT "Analyze auth in login.py"

# Continue with SESSION_ID
python scripts/agy_bridge.py --cd "/project" --SESSION_ID "uuid-from-response" --PROMPT "Write unit tests for that"
```

## Common Patterns

**Prototyping (request diffs):**
```bash
python scripts/agy_bridge.py --cd "/project" --PROMPT "Generate unified diff to add logging" --model pro
```

**Switch model per call:**
```bash
python scripts/agy_bridge.py --cd "/project" --PROMPT "Review this Rust" --model sonnet
python scripts/agy_bridge.py --cd "/project" --PROMPT "Same code" --model opus
```

**Setup check:**
```bash
python scripts/agy_bridge.py check
```

**Manage skills/plugins (passthrough to agy):**
```bash
python scripts/agy_bridge.py plugin list
python scripts/agy_bridge.py plugin import /path/to/plugin
```

## How It Works

`agy --print` writes nothing to stdout. The bridge instead runs agy, discovers the new conversation SQLite DB at `~/.gemini/antigravity-cli/conversations/<UUID>.db`, and extracts the assistant reply from the `step_type=15` rows' `step_payload` protobuf (field `f20` → `f1`). MCP servers (`~/.gemini/antigravity/mcp_config.json`), the memory doc (`~/.gemini/GEMINI.md`), and skills are pre-configured by the user and auto-loaded by agy — the bridge does not manage them.

When a run fails upstream, agy writes no reply text at all and instead records the executor error in a `step_type=17` row (`f24` → `f3`: `f1` user-facing line, `f2` status detail). The bridge reads that row and reports the real cause — e.g. `FAILED_PRECONDITION (code 400): User location is not supported for the API use.` or `UNAVAILABLE (code 503): No capacity available for model ...` — instead of blaming its own parsing. `stderr` alone carries only agy's generic `Agent execution terminated due to error.` and no status code.

On resume, both extractors window on `idx > after_idx`, where the boundary spans **all** step types: a failed run's `type=17` row lands after its last `type=15` step, so a `type=15`-only boundary would re-attribute that stale error to the next run.

The bridge does not retry. A 400 geo rejection will almost certainly fail again on an immediate retry, and 503 capacity exhaustion is better answered by switching `--model` than by replaying — which could also repeat tool side effects. The structured error is passed through so the caller decides.

## Security Note

By default the bridge passes `--dangerously-skip-permissions` to agy. This is **mandatory for non-interactive `--print` mode** because agy's default `toolPermission` is `request-review`, which blocks waiting for a human to approve tool calls — and since `--print` captures no TTY, the process hangs until timeout. With `--dangerously-skip-permissions`, agy auto-approves all tool calls. Only pass `--no-skip-permissions` if agy can service interactive permission prompts. The bridge always runs under a hard outer timeout (`--print-timeout` + 60s) so a hung agy cannot block indefinitely.

## Known Limitations

- **Protobuf extraction is schema-dependent.** The bridge parses agy's conversation DB without a `.proto` file: replies from `f20` → `f1` of `step_type=15` rows, upstream errors from `f24` → `f3` of `step_type=17` rows. If agy changes its internal schema, extraction returns empty. The reported error distinguishes the two cases — a message naming an upstream status means agy failed and the bridge worked; the schema-drift hint appears only when no error row explains the empty reply. Fix locations: `extract_answer()` and `extract_run_error()` in `scripts/agy_bridge.py`.
- `agy models` returns empty on this build; model aliases are hardcoded.
- `--continue` is intentionally NOT exposed (target selection is opaque); use `--SESSION_ID` to resume a specific conversation.
