---
name: context7-fetcher
description: |
  Internal sub-skill that executes Context7 API calls in a forked context. Invoked only by the `context7` main skill via the Task tool — never standalone. Use when: a forked agent must run `context7-api.cjs search` or `context` and return raw JSON without carrying the parent conversation. Triggers: Task-tool delegation from `context7` SKILL.md (Steps 2 & 4 of the research workflow).
context: fork
---

# Context7 Fetcher Sub-skill

> **Internal-only.** This sub-skill is invoked by the [`context7`](SKILL.md) main skill through the Task tool. It is not meant to be called directly by the user or routed to by intent detection.

## Purpose

Execute Context7 API calls in an isolated (`context: fork`) context so the parent conversation's history is not carried into the HTTP request. This minimizes token cost and keeps API execution pure: input command → JSON output, nothing else.

The selection logic (which library to pick, how to integrate the docs) lives in the **main skill** ([`SKILL.md`](SKILL.md)). The fetcher only runs the command and returns raw JSON.

## Call Contract

Invoked via the Task tool by `context7`. The main skill passes a complete command string in the Task `prompt`:

```
Task:
- subagent_type: Bash
- description: "<Search Context7 for X>" | "<Fetch Context7 docs for X>"
- prompt: node skills/context7/context7-api.cjs <command> <args...>
```

### Commands (mirrors the Tool Capability Matrix in SKILL.md)

| Command | Args | Returns |
|---------|------|---------|
| `search` | `<libraryName> <query>` | `{libraries:[{id,name,description,trustScore,versions[]}]}` |
| `context` | `<libraryId> <query>` | `{results:[{title,content,source,relevance}]}` |

## Execution Flow

1. Receive the command from the Task `prompt`
2. Execute `node skills/context7/context7-api.cjs <command> <args>`
3. Return the API response JSON verbatim — no summarization, no selection, no integration

> The fetcher must **not** decide which library to select or which snippet to surface. Those decisions belong to the main skill. Returning raw JSON keeps the forked context stateless and reusable across parallel calls.

## Command Examples

```bash
# Search libraries (Step 2 of main skill workflow)
node skills/context7/context7-api.cjs search "react" "useEffect hook"

# Get documentation (Step 4 of main skill workflow)
node skills/context7/context7-api.cjs context "/facebook/react" "useEffect cleanup"

# Version-pinned documentation
node skills/context7/context7-api.cjs context "/vercel/next.js/v15.1.8" "middleware"
```

## Output Format

### `search` Response
```json
{
  "libraries": [
    {
      "id": "/facebook/react",
      "name": "React",
      "description": "A JavaScript library for building user interfaces",
      "trustScore": 98,
      "versions": ["v19.0.0", "v18.3.1"]
    }
  ]
}
```

### `context` Response
```json
{
  "results": [
    {
      "title": "useEffect",
      "content": "useEffect is a React Hook that lets you synchronize...",
      "source": "docs/reference/react/useEffect.md",
      "relevance": 0.95
    }
  ]
}
```

## API Key Resolution

Handled by `context7-api.cjs` (see [`SKILL.md` Environment Setup](SKILL.md#environment-setup)):

1. `CONTEXT7_API_KEY` environment variable
2. `.env` file in the skill directory

The fetcher does not manage keys itself; it just runs the script.

## Error Handling

| Error | Fetcher Behavior |
|-------|------------------|
| Missing args (`search`/`context` without required params) | Script prints usage to stderr, exits non-zero — return that to the main skill |
| API 4xx/5xx | Script prints `API Error <code>: <body>` to stderr, returns `null` on stdout — return raw, let main skill decide retry/fallback |
| Network failure | Script prints error to stderr, returns `null` — return raw |
| Windows Git Bash path mangling | `context7-api.cjs` auto-fixes MSYS-converted library IDs |

The fetcher does **not** retry or fall back. All retry/version-selection/fallback decisions are the main skill's responsibility (see [`SKILL.md` Error Handling](SKILL.md#error-handling)).

## Important Notes

- Script path is relative to the repository root: `skills/context7/context7-api.cjs`
- The forked context has no conversation history — pass everything needed in the Task `prompt`
- Timeouts default to Node.js HTTPS control; the main skill sets expectations via its own timeout guidance
- Output is always JSON to stdout; errors always go to stderr with non-zero exit
