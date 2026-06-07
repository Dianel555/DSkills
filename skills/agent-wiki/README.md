# agent-wiki

Incremental LLM-friendly wiki generator for Obsidian note vaults.

`agent-wiki` scans a vault, tracks source markdown files with SHA-256, and helps the main Agent maintain a reusable `wiki/` directory without modifying source notes or attachments.

## Prerequisites

```bash
pip install PyYAML
```

## Vault Selection

Pass a vault explicitly or set an environment variable:

```bash
python scripts/agent_wiki_cli.py scan --vault /path/to/vault

# or
export AGENT_WIKI_VAULT=/path/to/vault
python scripts/agent_wiki_cli.py scan
```

Resolution order:

1. `--vault PATH`
2. `AGENT_WIKI_VAULT`
3. JSON error to stderr

## Commands

```bash
python scripts/agent_wiki_cli.py init --vault /path/to/vault
python scripts/agent_wiki_cli.py scan --vault /path/to/vault
python scripts/agent_wiki_cli.py plan --batch-size 20 --vault /path/to/vault
python scripts/agent_wiki_cli.py batch-done --batch 1 --vault /path/to/vault
python scripts/agent_wiki_cli.py cache-get <relpath> --vault /path/to/vault
python scripts/agent_wiki_cli.py cache-put <relpath> --topics topic1.md,topic2.md --vault /path/to/vault
python scripts/agent_wiki_cli.py cleanup --vault /path/to/vault
python scripts/agent_wiki_cli.py status --vault /path/to/vault
python scripts/agent_wiki_cli.py index --vault /path/to/vault
python scripts/agent_wiki_cli.py normalize-source-type --vault /path/to/vault
python scripts/agent_wiki_cli.py gen-base --name sources --vault /path/to/vault
python scripts/agent_wiki_cli.py extract-authors --vault /path/to/vault
python scripts/agent_wiki_cli.py aggregate-authors --vault /path/to/vault
```

| Command | Purpose |
|---|---|
| `init` | Create `wiki/` layout, cache, retrieval index, topics, archive, and URL cache directories |
| `scan` | Classify source notes as `new`, `modified`, or `deleted` |
| `plan` | Split pending sources into batches (default 20/round); write a task report to `wiki/_archived/ingest-tasks.md` |
| `batch-done` | Mark a round complete after verifying every doc in it was `cache-put` |
| `cache-get` | Return the cached ingest record for one source path |
| `cache-put` | Record a completed ingest for one source path and derived topics |
| `cleanup` | Remove deleted-source references and archive orphaned topics |
| `status` | Emit machine-readable wiki health metrics, including index and batch progress (read-only) |
| `index` | Rebuild `wiki/.wiki-index.json` from topic frontmatter (no `.base` written) |
| `normalize-source-type` | Rewrite each topic's `source_type` frontmatter to its `sources[]` file format (in place; no-source topics skipped) |
| `gen-base` | Rebuild the index, then write Obsidian Bases views: `wiki/index.base` + `<name>.base` source master table |
| `extract-authors` | Raw `作者:` row per topic source note (read-only) |
| `aggregate-authors` | Deduplicated first author per topic for frontmatter backfill (read-only) |

All command outputs are JSON.

## Wiki Layout

```text
{vault}/
├── <name>.base              # source master table (Bases, at vault root)
└── wiki/
    ├── index.md
    ├── index.base           # topic overview + per-dimension faceted views (Bases)
    ├── log.md
    ├── topics/
    ├── _archived/YYYY-MM-DD/
    ├── .wiki-cache.json
    ├── .wiki-index.json     # derived retrieval index (normalized metadata)
    └── .wiki-url-cache/
```

Source markdown files remain outside `wiki/`. The scanner skips `wiki/`, `.obsidian/`, `attachments/`, `.git/`, `.trash/`, `.wikiignore` matches, and symlinked markdown files.

## Agent Workflow

1. Run `scan`.
2. For each `new` or `modified` item:
   - read the source note
   - update or create topic pages under `wiki/topics/`, enriching frontmatter (`year_start`/`year_end` for the topic's year span, `authors`, `institutions`, `methods`, `technical_routes`, `research_trends`, `summary`, `keywords`) when the source supports it
   - preserve Obsidian links such as `[[note]]` and embeds such as `![[image.png]]`
   - run `cache-put <relpath> --topics ...`
3. For deleted sources, run `cleanup`.
4. Run `index` to refresh `wiki/.wiki-index.json`, then `gen-base` to refresh the Bases views, update `wiki/index.md`, and append `wiki/log.md` entries.

**Batched ingest (large vaults)**: instead of processing every `scan` result at once, run `plan --batch-size 20` to split pending sources into rounds (task report at `wiki/_archived/ingest-tasks.md`), process one batch's docs, then `batch-done --batch <id>` (it refuses until each doc in the round is `cache-put`). Repeat until `complete`. Re-running `plan` re-derives remaining work; `status.batch` tracks progress.

**Authors backfill**: when source notes carry a `作者:` row, `aggregate-authors` returns the deduplicated first author per topic for writing into `authors` frontmatter (`extract-authors` shows the raw rows).

`source_type` is **always derived from the source file formats** in `sources[]` (`.md`→`markdown`, `.pdf`→`pdf`, `.doc/.docx`→`word`, `.xls/.xlsx/.csv`→`spreadsheet`, `.txt`→`text`, URL→`web`; multi-format topics become `mixed`). Values are lowercase ASCII categories. The frontmatter value is ignored on rebuild; `normalize-source-type` rewrites it in place to match (no hand-authored values). A pure-`.md` vault resolves to `markdown` for every topic — format discernibility requires `sources[]` to point at the original files.

**Hybrid retrieval**: read `wiki/.wiki-index.json` to route quickly by `title`/`keywords`/`summary`/`source_type`/`sources`, then follow each topic's `sources` paths to the original notes for deep, source-grounded answers. The index is a derived cache — topic frontmatter is the single source of truth, and a source note wins on conflict.

Topic pages should contain YAML frontmatter:

```yaml
---
title: Topic Title
sources:
  - "课程/量子力学.md"
last_updated: 2026-06-04T15:30:00
---
```

`sources` values are vault-relative POSIX paths, not wikilinks. Optional enrichment fields above are additive and normalized into the retrieval index.

## URL and PDF Rules

The CLI does not fetch external URLs. The main Agent should use available search/fetch skills when needed.

Do not fetch PDFs. For URLs ending in `.pdf` or returning `Content-Type: application/pdf`, record only the URL and link text in the topic page.

## Safety

- Source notes and `attachments/` are not modified.
- Cache writes use same-directory temp files and atomic replace.
- Cache-put detects concurrent cache changes before replace.
- Paths stored in cache/frontmatter are NFC-normalized POSIX relative paths.
