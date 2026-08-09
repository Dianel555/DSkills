---
name: context7
description: |
  Fetch up-to-date library/framework/API documentation from Context7, bypassing training-cutoff limits. Use when: (1) User asks how to use/configure/install a library, framework, or SDK, (2) Code examples or API reference needed for a specific package, (3) Version-specific behavior questions (e.g., "React 19", "Next.js 15"), (4) Any npm package, GitHub repo, or framework mention (React/Vue/Next/Prisma/Tailwind/Supabase/...). Triggers: "如何实现", "怎么写", "配置", "安装", "文档", "How do I", "Show me how", "generate code", library/framework names. Differentiator: Real-time authoritative docs via Context7 API, complements grok-search (real-time news) and exa (semantic web research) — use this for library/API specifics, not general web search.
---

# Context7

Fetch current library/framework/API documentation from the Context7 API, so answers cite authoritative docs instead of relying on outdated training data. This skill uses the co-located Node CLI in `context7-api.cjs`; no MCP dependency is required.

## Architecture

| Piece | Role | Recommended Use |
|-------|------|-----------------|
| **context7** (this file) | Intent detection, library selection, answer integration | **Default path** |
| [context7-fetcher](context7-fetcher.md) | Optional low-context wrapper around the same CLI | Use only if your runtime truly supports isolated workers/subtasks |

The canonical execution path is to run the co-located CLI directly. Do **not** require a `Task`/`Bash`-specific subtask mechanism, and do **not** hardcode repo-relative paths like `skills/context7/context7-api.cjs` — that breaks when the skill is installed globally outside the source repo.

### Call Flow

```
User Query → context7 (detect trigger + extract library)
    ↓ shell / worker → node <context7-skill-dir>/context7-api.cjs search <library> <query>
                         → JSON libraries[] (+ raw results[])
context7 (select best match: name / trustScore / version)
    ↓ shell / worker → node <context7-skill-dir>/context7-api.cjs context <libraryId> <query>
                         → JSON results[] (+ raw codeSnippets[] / infoSnippets[])
context7 (integrate relevant snippets into answer)
```

## Implementation Layout

- `context7-api.cjs` - Node CLI entrypoint (HTTPS client, `.env` + env-var API key, MSYS path fix, response normalization)
- `context7-fetcher.md` - Optional helper wrapper around the same CLI
- `.env.example` - API key template (copy to `.env`)
- `tests/test_context7_api.cjs` - Regression tests for response-shape compatibility and error exits

## Execution Method

```bash
# Prerequisites: Node.js 18+ (no npm install needed; stdlib only)
# Environment: CONTEXT7_API_KEY (optional; public rate limits apply if unset)

# Run from the context7 skill directory
node ./context7-api.cjs search "<library-name>" "<user-query>"
node ./context7-api.cjs context "<library-id>" "<specific-query>"
```

> Safe default: resolve the actual `context7` skill directory first, `cd` into it, then run `node ./context7-api.cjs ...`.

## Stable Output Contract

The Context7 HTTP API payload changed shape, so `context7-api.cjs` now exposes a compatibility contract:

- `search` always provides `libraries[]` and preserves the raw `results[]`
- `context` always provides `results[]` and preserves raw `codeSnippets[]` / `infoSnippets[]`

Prefer the normalized aliases (`libraries[]`, `results[]`) in downstream logic.

## Tool Capability Matrix

| Command | Required Args | Output |
|---------|---------------|--------|
| `search` | `<libraryName>`, `<query>` | `{libraries:[...], results:[...], searchFilterApplied?:boolean}` |
| `context` | `<libraryId>`, `<query>` | `{results:[...], codeSnippets?:[...], infoSnippets?:[...]}` |

Library IDs are Context7 slugs (for example `/reactjs/react.dev`, `/vercel/next.js`, `/vercel/next.js/v15.1.8`). If the user specifies a version, prefer a version-pinned ID returned by `search`.

## Research Workflow

### Step 1: Extract Library Information

From the user query, identify:

- Library name (for example `react`, `next.js`, `prisma`)
- Version if specified (for example `React 19`, `Next.js 15`)
- Specific feature/API (for example `useEffect cleanup`, `middleware`)

### Step 2: Search for the Library

```bash
cd <context7-skill-dir>
node ./context7-api.cjs search "<library>" "<full user question>"
```

### Step 3: Select the Best Match

Choose from `libraries[]` by:

1. Exact name match to the user's query
2. Highest `trustScore`
3. Version match if specified
4. Official packages over community forks

### Step 4: Fetch Documentation

```bash
cd <context7-skill-dir>
node ./context7-api.cjs context "<libraryId>" "<feature query>"
```

### Step 5: Integrate into the Answer

1. Answer accurately with fetched current information
2. Include code examples drawn from the docs
3. Cite the version when relevant
4. Quote only the relevant snippet instead of dumping entire documentation

> If your runtime can spawn generic workers/subagents, pass the exact shell commands above. Do not assume a special `Task` API or a `subagent_type: Bash` feature exists.

## Environment Setup

The CLI loads the API key in this order:

1. `CONTEXT7_API_KEY` environment variable
2. `.env` file in the skill directory

```bash
cp .env.example .env
# Edit .env: CONTEXT7_API_KEY=<your-key>
```

Get a key at `context7.com/dashboard`. Without a key, the API falls back to public rate limits.

## Error Handling

| Error | Recovery |
|-------|----------|
| `search` returns no libraries | Broaden the library name; suggest alternatives |
| API 429 (rate limit) | Retry once after a short delay; if it still fails, say Context7 is rate-limited |
| API 5xx / network failure | CLI exits non-zero after writing the error to stderr; retry once, then fall back to training data and say it may be outdated |
| Library ID path mangled (Windows Git Bash) | `context7-api.cjs` auto-fixes MSYS path conversion |
| Search/context payload shape drift | Use normalized `libraries[]` / `results[]` aliases from `context7-api.cjs` |
| Global skill install + path issues | Resolve the actual skill directory first; never blindly run `node skills/context7/...` |

## Best Practices

- Pass the full user question as the query for better ranking
- Prefer version-pinned IDs when the user names a version
- Resolve the skill directory before running the CLI
- Parallelize multiple libraries only if your runtime supports it safely
- Keep a training-data fallback with an explicit staleness disclaimer

## Anti-Patterns

| Prohibited | Correct |
|------------|---------|
| `node skills/context7/context7-api.cjs ...` from an arbitrary project root | Resolve the skill directory, then run `node ./context7-api.cjs ...` there |
| Depending on raw `results` / `codeSnippets` only | Read normalized `libraries[]` / `results[]` first |
| Requiring a `Task` / `Bash`-only subtask API | Use direct CLI execution or a generic worker that runs the same command |
| Dumping entire fetched documentation | Extract only the relevant snippet |
| Silently falling back to training data | Tell the user the fallback may be outdated |
| Hardcoding library IDs across versions | Re-run `search` when version uncertainty exists |

## Example Workflows

### Example 1: React Hook

**User:** `How do I use useEffect to fetch data in React 19?`

1. Detect `React 19` + `useEffect` + `fetch data`
2. `search "react" "How do I use useEffect to fetch data in React 19?"`
3. Choose the best version-aware result from `libraries[]`
4. `context "<selected-library-id>" "useEffect data fetching"`
5. Respond with current React guidance

### Example 2: Next.js Configuration

**User:** `配置 Next.js 15 的中间件`

1. Detect `Next.js 15` + `middleware`
2. `search "next.js" "middleware configuration"`
3. Choose the version-pinned result if present
4. `context "<selected-library-id>" "middleware"`
5. Respond with current Next.js 15 setup

## Limitations

- Requires internet connection
- Subject to Context7 API rate limits
- May lack docs for very new or obscure libraries
- Documentation quality depends on the indexed source material
