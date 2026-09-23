---
name: context7
description: Fetch current library and API documentation from Context7 when a coding answer needs authoritative, up-to-date examples or version-specific behavior.
---

# Context7

Use the co-located Node CLI to search Context7 documentation through the [v3 Search API](https://context7.com/docs/search-api). The v3 endpoint accepts a question and returns relevant snippets in one request. A library ID is optional.

## Run the CLI

Resolve the actual directory containing this skill first. The CLI needs Node.js 18+ and no npm dependencies. Run it from that directory:

```bash
node ./context7-api.cjs search "How do I clean up a React effect?"
node ./context7-api.cjs search "How do I configure route handlers?" --library Next.js --version 15.4.0
node ./context7-api.cjs search "How do I stream a response?" --library Next.js --library OpenAI --language TypeScript
```

`--library` accepts a name or Context7 ID and may appear up to four times. `--version` requires at least one `--library`; with one library it is a strict filter, and with several it is a preference. `--language` is a preference. Pass the user's specific question as the query. Do not use a repo-relative path when this skill is installed elsewhere.

The old `context <libraryId> <query>` command remains an alias for `search <query> --library <libraryId>` so existing callers can migrate. It also uses v3.

## Read the response

The CLI requests `type=json` and prints the raw `codeSnippets[]` and `infoSnippets[]`, plus a normalized `results[]` array. Each normalized result has `title`, `content`, `source`, and `libraryId`. Use the snippet's source link when citing documentation. When a query has no matching documentation, all three arrays are empty.

The v3 REST endpoint returns plain text by default. Keep `type=json` when calling it directly if structured snippets are needed.

## Authentication and errors

Set `CONTEXT7_API_KEY` in the environment or in a `.env` file next to the CLI. An environment variable takes precedence. Use `.env.example` as the template and get a key from `context7.com/dashboard`. Requests without a key are for testing and have low IP-based limits.

The CLI exits nonzero and writes errors to stderr for invalid arguments, network failures, invalid JSON, and API errors other than `404 no_documentation_found`. For `429`, wait for the rate limit before retrying. For other transient failures, retry once and report that current documentation could not be verified if it still fails.

The optional [context7-fetcher](context7-fetcher.md) can run the same command in an isolated worker when the runtime supports one. Direct CLI execution is the default.
