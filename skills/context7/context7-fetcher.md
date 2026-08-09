---
name: context7-fetcher
description: |
  Optional helper skill that executes the co-located `context7-api.cjs` CLI in a lower-context worker. Use only when the runtime truly supports isolated subtasks; otherwise the main `context7` skill should call the CLI directly. Never depend on repo-relative `skills/context7/...` paths.
context: fork
---

# Context7 Fetcher

> Optional helper only. If your runtime cannot reliably launch isolated subtasks, skip this helper and let [`context7`](SKILL.md) call `context7-api.cjs` directly.

## Purpose

Execute Context7 API calls in an isolated context so parent conversation history is not carried into the HTTP request. The fetcher does **not** choose libraries, rank snippets, or write the final answer.

## Call Contract

The parent skill must resolve the actual `context7` skill directory first, then pass a shell command like:

```bash
cd <context7-skill-dir> && node ./context7-api.cjs <command> <args...>
```

Supported commands:

| Command | Args | Returns |
|---------|------|---------|
| `search` | `<libraryName> <query>` | `{libraries:[...], results:[...], searchFilterApplied?:boolean}` |
| `context` | `<libraryId> <query>` | `{results:[...], codeSnippets?:[...], infoSnippets?:[...]}` |

## Execution Flow

1. Receive the full command from the parent skill
2. Run it from the real `context7` skill directory (or use an absolute path)
3. Return the JSON verbatim with no summarization or selection logic

## Examples

```bash
cd <context7-skill-dir> && node ./context7-api.cjs search "react" "useEffect hook"
cd <context7-skill-dir> && node ./context7-api.cjs context "/reactjs/react.dev" "useEffect cleanup"
cd <context7-skill-dir> && node ./context7-api.cjs context "/vercel/next.js/v15.1.8" "middleware"
```

## Output Notes

- `search` exposes normalized `libraries[]` and preserves raw `results[]`
- `context` exposes normalized `results[]` and preserves raw `codeSnippets[]` / `infoSnippets[]`

The helper should treat those normalized aliases as the stable contract.

## API Key Resolution

Handled by `context7-api.cjs`:

1. `CONTEXT7_API_KEY` environment variable
2. `.env` file in the skill directory

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing args | Script prints usage to stderr and exits non-zero |
| API 4xx/5xx | Script prints the error to stderr and exits non-zero |
| Network failure | Script prints the error to stderr and exits non-zero |
| Windows Git Bash path mangling | `context7-api.cjs` auto-fixes MSYS-converted IDs |
| Global skill install + repo-relative path | Resolve the skill directory first; never call `node skills/context7/...` blindly |

## Important Notes

- Script path is the file co-located with this skill: `./context7-api.cjs`
- Pass everything needed in the command itself; isolated workers may not have parent context
- Output is JSON on success, stderr + non-zero exit on failure
