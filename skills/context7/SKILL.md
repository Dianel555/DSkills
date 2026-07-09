---
name: context7
description: |
  Fetch up-to-date library/framework/API documentation from Context7, bypassing training-cutoff limits. Use when: (1) User asks how to use/configure/install a library, framework, or SDK, (2) Code examples or API reference needed for a specific package, (3) Version-specific behavior questions (e.g., "React 19", "Next.js 15"), (4) Any npm package, GitHub repo, or framework mention (React/Vue/Next/Prisma/Tailwind/Supabase/...). Triggers: "如何实现", "怎么写", "配置", "安装", "文档", "How do I", "Show me how", "generate code", library/framework names. Differentiator: Real-time authoritative docs via Context7 API, complements grok-search (real-time news) and exa (semantic web research) — use this for library/API specifics, not general web search.
---

# Context7

Fetches current library/framework/API documentation from the Context7 API, so responses cite authoritative docs rather than potentially outdated training data. Standalone Node CLI only (no MCP dependency).

## Architecture: Two-Skill Split

| Skill | Role | Context | Token Cost |
|-------|------|---------|------------|
| **context7** (this file) | Intent detection, library selection, response integration | Full conversation | Higher |
| [context7-fetcher](context7-fetcher.md) | Pure API calls (`search` / `context`) | `context: fork` (isolated) | Lower |

The main skill never calls the API directly. It delegates each HTTP call to `context7-fetcher` via the Task tool so the forked subagent executes without carrying conversation history. The fetcher's contract is defined in [`context7-fetcher.md`](context7-fetcher.md).

### Call Flow

```
User Query → context7 (detect trigger + extract library)
    ↓ Task(context7-fetcher) → search <library> <query>   → JSON libraries[]
context7 (select best match: name / trustScore / version)
    ↓ Task(context7-fetcher) → context <libraryId> <query> → JSON results[]
context7 (integrate relevant snippets into answer)
```

## Implementation Layout

- `context7-api.cjs` - Node CLI entrypoint (HTTPS client, .env + env-var API key, MSYS path fix)
- `context7-fetcher.md` - Sub-skill definition (forked context, API executor)
- `.env.example` - API key template (copy to `.env`)

## Execution Method

```bash
# Prerequisites: Node.js 18+ (no npm install needed; stdlib only)
# Environment: CONTEXT7_API_KEY (optional; public rate limits apply if unset)

# All examples assume cwd == skills/context7/. Relative path also works from repo root.
node context7-api.cjs search "<library-name>" "<user-query>"
node context7-api.cjs context "<library-id>" "<specific-query>"
```

> In practice, invoke these **through the Task tool pointing at `context7-fetcher`** (see Call Flow), not via direct Bash — that keeps API calls in a forked context and minimizes token use.

## Tool Capability Matrix

| Command | Required Args | Optional Args | Output |
|---------|---------------|---------------|--------|
| `search` | `<libraryName>`, `<query>` | – | `{libraries:[{id,name,description,trustScore,versions[]}]}` |
| `context` | `<libraryId>`, `<query>` | – | `{results:[{title,content,source,relevance}]}` |

Library IDs are Context7 slugs (e.g., `/facebook/react`, `/vercel/next.js`). For version-specific docs, append the version: `/vercel/next.js/v15.1.8`.

## Research Workflow

### Step 1: Extract Library Information
From the user query, identify:
- Library name (e.g., "react", "next.js", "prisma")
- Version if specified (e.g., "React 19", "Next.js 15")
- Specific feature/API (e.g., "useEffect cleanup", "middleware")

### Step 2: Search for Library → delegate to fetcher
```
Task:
- subagent_type: Bash
- description: "Search Context7 for <library>"
- prompt: node skills/context7/context7-api.cjs search "<library>" "<full user question>"
```

### Step 3: Select Best Match
From search results, choose by:
1. Exact name match to the user's query
2. Highest `trustScore` (quality/popularity signal)
3. Version match if the user specified one
4. Official packages over community forks

### Step 4: Fetch Documentation → delegate to fetcher
```
Task:
- subagent_type: Bash
- description: "Fetch Context7 docs for <library>"
- prompt: node skills/context7/context7-api.cjs context "<libraryId>" "<feature query>"
```

### Step 5: Integrate into Response
1. Answer accurately with the fetched, current information
2. Include code examples drawn from the docs
3. Cite version when relevant
4. Quote only the relevant snippet — do not dump entire documentation

## Environment Setup

The `context7-api.cjs` script loads the API key in priority order:

1. `CONTEXT7_API_KEY` environment variable
2. `.env` file in the skill directory (`.claude/skills/context7/.env` or `skills/context7/.env`)

```bash
cp .env.example .env
# Edit .env: CONTEXT7_API_KEY=<your-key>
```

Get a key at [context7.com/dashboard](https://context7.com/dashboard). Without a key, the API falls back to public rate limits (lower quota).

## Error Handling

| Error | Recovery |
|-------|----------|
| `search` returns no libraries | Broaden the name; suggest alternatives to the user |
| API 429 (rate limit) | Retry once after a short delay; switch to public endpoint if key unset |
| API 5xx / network failure | Retry once; if still failing, fall back to training data and **state it may be outdated** |
| Library ID path mangled (Windows Git Bash) | `context7-api.cjs` auto-fixes MSYS path conversion; verify the ID slug |

## Best Practices

- Pass the **full user question** as the query for better relevance ranking
- Prefer version-pinned IDs (`/vercel/next.js/v15.1.8`) when the user names a version
- For multiple libraries, fire parallel Task calls (each forked independently)
- Set a reasonable timeout (5–10s) and always have a training-data fallback with a disclaimer

## Anti-Patterns

| Prohibited | Correct |
|------------|---------|
| Direct `node context7-api.cjs` from main context | Delegate via `Task` → `context7-fetcher` (forked) |
| Dump entire fetched documentation | Extract only the relevant snippet |
| Silently use training data when API fails | Tell the user the data may be outdated |
| Hardcode library IDs across versions | Re-run `search` if version uncertainty exists |

## Example Workflows

### Example 1: React Hook (version-specific)
**User:** "How do I use useEffect to fetch data in React 19?"
1. Detect: "How do I use" + "useEffect" + "React 19"
2. `search "react" "useEffect fetch data"` → select `/facebook/react/v19.0.0`
3. `context "/facebook/react/v19.0.0" "useEffect data fetching"`
4. Respond with current React 19 patterns

### Example 2: Next.js Configuration
**User:** "配置 Next.js 15 的中间件"
1. Detect: "配置" + "Next.js 15" + "中间件"
2. `search "next.js" "middleware configuration"` → select `/vercel/next.js/v15.1.8`
3. `context "/vercel/next.js/v15.1.8" "middleware"`
4. Respond with Next.js 15 middleware setup

## Limitations

- Requires internet connection
- Subject to Context7 API rate limits
- May lack documentation for very new or obscure libraries
- Documentation quality depends on the source repository structure
