---
name: context7-fetcher
description: Optional isolated worker for the co-located Context7 v3 CLI. Use only when the runtime supports isolated subtasks.
context: fork
---

# Context7 Fetcher

Run the same one-request search as the main [context7 skill](SKILL.md) and return the JSON verbatim. The parent resolves the installed skill directory and supplies the question and optional hints. The fetcher does not select or summarize snippets.

```bash
cd <context7-skill-dir> && node ./context7-api.cjs search "<question>" [--library "<name-or-id>"] [--version "<version>"] [--language "<language>"]
```

The CLI requests `/api/v3/search?type=json`. Its output includes `codeSnippets[]`, `infoSnippets[]`, and normalized `results[]`. It uses `CONTEXT7_API_KEY` from the environment or a `.env` file next to the script. Errors go to stderr with a nonzero exit code; `404 no_documentation_found` returns empty arrays.

Use the actual installed skill directory. A hardcoded project-relative `skills/context7` path may point to the wrong copy.
