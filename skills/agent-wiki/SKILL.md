---
name: agent-wiki
description: "Incremental LLM-friendly wiki generator for Obsidian note vaults. Use when: (1) Building wiki from notes, (2) Ingesting notes to wiki, (3) Obsidian LLM wiki, (4) Incremental knowledge base management. Triggers: 'build wiki from notes', 'ingest notes to wiki', 'Obsidian LLM wiki', 'incremental knowledge base'."
---

# agent-wiki

增量式 Obsidian 笔记仓库 Wiki 生成器，为 LLM 优化的知识库管理工具。

## Prerequisites

```bash
pip install PyYAML
```

## References (load on demand)

Detailed specs live under `references/` in this skill directory — read them only when the task needs them:

| File | Read when |
|------|-----------|
| `references/topic-authoring.md` | Authoring/enriching topic pages (type taxonomy, per-type section templates, conflict convention, quality metric detail) |
| `references/homepage.md` | Working on `wiki/index.md` (layout templates, managed cards, REST write-through, optional CSS) |
| `references/site-export.md` | Running/debugging `gen-site` (design system, page anatomy, determinism guarantees) |
| `references/index-schema.md` | Consuming/producing index or frontmatter fields (full `.wiki-index.json` schema, Bases views, capture contract) |

## Execution

The skill provides a Python CLI with the following subcommands:

```bash
# Initialize wiki structure
python scripts/agent_wiki_cli.py init --vault /path/to/vault

# Scan for changed sources
python scripts/agent_wiki_cli.py scan --vault /path/to/vault

# Plan a batched ingest: split pending sources into rounds (default 20/round)
python scripts/agent_wiki_cli.py plan --batch-size 20 --vault /path/to/vault

# Mark a round complete (verifies every doc in the batch was cache-put)
python scripts/agent_wiki_cli.py batch-done --batch 1 --vault /path/to/vault

# Get cache entry for a source
python scripts/agent_wiki_cli.py cache-get <relative-path> --vault /path/to/vault

# Record ingest result
python scripts/agent_wiki_cli.py cache-put <relative-path> --topics topic1.md,topic2.md --vault /path/to/vault

# Clean up deleted sources
python scripts/agent_wiki_cli.py cleanup --vault /path/to/vault

# Get wiki health status
python scripts/agent_wiki_cli.py status --vault /path/to/vault

# Rebuild the retrieval index (wiki/.wiki-index.json) without writing .base files
python scripts/agent_wiki_cli.py index --vault /path/to/vault

# Backfill source_type frontmatter to match each topic's sources[] file formats
python scripts/agent_wiki_cli.py normalize-source-type --vault /path/to/vault

# Generate Obsidian Bases (.base) views: wiki/index.base + <name>.base master table
python scripts/agent_wiki_cli.py gen-base --name sources --vault /path/to/vault

# Register an Agent-authored research report (wiki/queries/<name>.md) and tag kind: query
python scripts/agent_wiki_cli.py save-report <name> --vault /path/to/vault

# Generate per-topic JSON Canvas knowledge graphs under wiki/graphs/ (one topic or all)
python scripts/agent_wiki_cli.py gen-canvas --topic <name> --vault /path/to/vault
python scripts/agent_wiki_cli.py gen-canvas --all --vault /path/to/vault

# Build/refresh the wiki/index.md skeleton + its managed "工作区" card block
python scripts/agent_wiki_cli.py gen-home --vault /path/to/vault

# Extract raw 作者 rows from each topic's source notes (read-only)
python scripts/agent_wiki_cli.py extract-authors --vault /path/to/vault

# Deduplicated first-author list per topic, for frontmatter backfill (read-only)
python scripts/agent_wiki_cli.py aggregate-authors --vault /path/to/vault

# Compute quality tier distribution and per-topic metrics (read-only)
python scripts/agent_wiki_cli.py quality --vault /path/to/vault

# Identify covered sources vs gaps (read-only)
python scripts/agent_wiki_cli.py coverage --vault /path/to/vault

# Get maintenance worklists: wanted (broken links) and stale topics (read-only)
python scripts/agent_wiki_cli.py worklist --vault /path/to/vault

# Generate static HTML site (optional, requires markdown package)
python scripts/agent_wiki_cli.py gen-site --vault /path/to/vault
```

**Vault Path Resolution**: Use `--vault PATH` or set environment variable `AGENT_WIKI_VAULT`.

## CLI Command Matrix

| Command | Purpose | Input | Output (JSON) |
|---------|---------|-------|---------------|
| `init` | Create wiki structure | vault path | `{"status": "ok"\|"already_initialized", "created": [...]}` |
| `scan` | Classify sources as new/modified/deleted | vault path | `{"version": 1, "vault": "...", "stats": {...}, "new": [...], "modified": [...], "deleted": [...]}` |
| `plan` | Split pending sources (new+modified) into batches; write task report to `wiki/_archived/ingest-tasks.md` | vault path, `--batch-size` (default 20) | `{"ok": true, "total": N, "batch_size": N, "report": "...", "batches": [{"id": 1, "status": "pending", "count": N, "items": [...]}]}` |
| `batch-done` | Mark a round complete after verifying every doc in it was `cache-put` | vault path, `--batch` | `{"ok": true, "batch": N, "remaining": [...], "complete": bool}` or `{"error": "batch_incomplete", "missing": [...]}` |
| `cache-get` | Query cache entry | source relative path | `{"path": "...", "sha256": "...", ...}` or `{"path": "...", "status": "absent"}` |
| `cache-put` | Record ingest completion | source path, topic list | `{"ok": true, "path": "...", "sha256": "..."}`; topic paths outside `wiki/topics/` → `{"error": "invalid_topic_path"}` |
| `cleanup` | Remove deleted sources from topics | vault path | `{"removed": N, "archived": M, "details": [...], "errors": [...]}` |
| `status` | Wiki health metrics (read-only) | vault path | `{"vault": "...", "sources_tracked": N, "topics_total": N, "index_exists": bool, "index_topics": N, "index_stale": bool, "index_errors": [...], "batch": {...}\|null, "quality_distribution": {...}, "featured_count": N, "aliases_count": N, "backlinks_max": N, "gaps_count": N, "wanted_count": N, "stale_count": N, "site_exists": bool, "site_stale": bool, ...}` |
| `index` | Rebuild `wiki/.wiki-index.json` from topic frontmatter (no `.base` written) | vault path | `{"ok": true, "topics": N, "errors": [...]}` |
| `normalize-source-type` | Rewrite each topic's `source_type` frontmatter to its `sources[]` file format (in place; no-source topics skipped) | vault path | `{"ok": true, "changed": [{"path": "...", "source_type": "..."}], "skipped": N, "errors": [...]}` |
| `gen-base` | Rebuild the index, then write Obsidian Bases views (index + master table) | vault path, `--name` | `{"ok": true, "prefix": "...", "written": [...]}` |
| `save-report` | Register an Agent-authored research report under `wiki/queries/`, ensure `kind: query`, log it | name, vault path | `{"ok": true, "path": "queries/<name>.md", "kind": "query"}` |
| `gen-canvas` | Generate per-topic JSON Canvas 1.0 graph(s) under `wiki/graphs/` from the index (topic center + `sources[]` ring + 1-hop neighbor topics) | vault path, `--topic <name>` or `--all` | `{"ok": true, "path": "wiki/graphs/<name>.canvas", "nodes": N, "edges": M}` or `{"ok": true, "written": [...], "count": K}` |
| `gen-home` | Build/refresh the `wiki/index.md` skeleton + one managed "工作区" block (Dataview card grid when detected, else static list); refreshes **only** the managed block on re-run (agent prose preserved); never touches `index.base` | vault path, `--cards auto\|on\|off` (default auto), `--no-rest` | `{"ok": true, "path": "wiki/index.md", "cards": bool, "write_via": "rest\|atomic"}` |
| `extract-authors` | Raw 作者 row per topic source note (read-only) | vault path | `{"ok": true, "topics": {"<topic>.md": [{"src": "...", "file": "...", "authors": "..."}]}}` |
| `aggregate-authors` | Deduplicated first author per topic for frontmatter backfill (read-only) | vault path | `{"ok": true, "authors": {"<topic>.md": ["作者1", ...]}}` |
| `quality` | Compute quality tier distribution and metrics per topic (read-only) | vault path | `{"ok": true, "tiers": {"<topic>.md": {"tier": "...", "metrics": {...}}}, "distribution": {"stub": N, ...}, "errors": [...]}` |
| `coverage` | Identify covered sources vs gaps (read-only) | vault path | `{"ok": true, "covered": N, "gaps": [{"path": "..."}], "coverage_ratio": 0.0-1.0}` |
| `worklist` | Get maintenance worklists: `wanted` (broken link targets ranked by demand) and `stale` (low-quality or index-stale topics) for bounded enrichment (read-only) | vault path | `{"ok": true, "wanted": [{"target": "...", "inbound": N, "linked_from": [...]}], "stale": [{"path": "...", "tier": "...", "reason": "low_tier"\|"index_stale"}]}` |
| `gen-site` | Generate self-contained static HTML site under `wiki/site/` (optional; requires `markdown` package; degrades gracefully to escaped plaintext if absent) | vault path | `{"ok": true, "pages": N, "out": "wiki/site", "degraded": bool, "errors": [...]}` |

## Agent Workflow

### Intent Routing

**Before any action, classify the user request into one of two modes. Default to Answer mode.**

| Trigger Signal | Mode | Action | Output |
|---|---|---|---|
| User is **asking / seeking explanation / requesting lookup** on a topic ("what is…", "compare…", "help me find…") — and **NOT** requesting wiki building | **Answer (default)** | Follow **Hybrid Retrieval Protocol** to answer → optionally `save-report` as a report | `wiki/queries/<name>.md` (kind: query), **does NOT create/modify topics** |
| User **explicitly** requests "build / import / ingest / update / maintain wiki", or "create topics from these notes", or points to a vault/directory to be ingested | **Ingest/Maintain** | Follow **Standard / Batched Ingest** or **Bounded Enrichment** | `wiki/topics/<name>.md` (kind: topic) |

**Rules**:
- **Reports are the default output**. A regular question **never** triggers topic generation — unless the user explicitly requests wiki building/maintenance, or explicitly says "make it a topic page".
- **Topics are only produced in Ingest/Maintain mode**: when ingesting source notes, batch ingesting, or maintaining/enriching existing topics.
- When uncertain which mode applies, treat as **Answer** and produce a report directly; confirm if wiki building is actually needed.
- Answer mode can **read** topics/index for retrieval (read-only), but **does NOT write** topics.

### Standard Ingest Loop

1. **Scan**: Run `scan` to get new/modified/deleted sources
2. **Process each source**:
   - For `new`/`modified`: Read source → generate/update **enriched** topic pages → `cache-put`
   - For `deleted`: Run `cleanup` (handles topic frontmatter update and archival)
3. **Refresh retrieval index**: Run `index` to rebuild `wiki/.wiki-index.json` from topic frontmatter
4. **Refresh views**: Run `gen-base` to (re)write the Bases views (this also rebuilds the index), then update `wiki/index.md` with topic summaries and embed `![[index.base#主题总览]]`
5. **Log**: Append to `wiki/log.md`

### Batched Ingest (large vaults)

To avoid loading the whole vault at once, process sources in bounded rounds:

1. **Plan**: Run `plan --batch-size 20` once. It scans, splits the pending sources into rounds of at most N, and writes a checklist report to `wiki/_archived/ingest-tasks.md`.
2. **Process one round**: Read **only** the docs in the current batch, author/update their topic pages, and `cache-put` each one. Do **not** read ahead into later batches.
3. **Confirm the round**: Run `batch-done --batch <id>`. It refuses (`batch_incomplete`, listing `missing` docs) until every doc in the batch is cached, then marks the batch `[x]` and returns `remaining` batch ids.
4. **Repeat** for each `remaining` batch until `complete` is `true`.
5. **Finish**: Run `cleanup` (if any deletions), then `gen-base`, and log as usual.

`status` reports batch progress under `batch`. Re-running `plan` re-derives batches from the current scan — already-ingested docs drop out automatically.

### Bounded Enrichment Loop

After initial ingest, maintain topics incrementally **without scanning the entire vault**:

1. **Check worklist**: Run `worklist` for two bounded queues: `wanted` (broken wikilink targets ranked by inbound demand) and `stale` (low-quality `stub`/`basic` or index-stale topics)

   **Understanding `wanted` (Broken Wikilinks)**: These are wikilink targets referenced by `wiki/topics/` pages but not yet created as dedicated topic pages. **Not an error** — most point to source notes in the vault root or other directories outside `wiki/`. They work as jump links in Obsidian; the "broken" label only means no dedicated topic page exists. **Use as demand signal**: `inbound` count shows reference frequency → prioritize high-demand sources (≥3) for enrichment.

2. **Pick one page**: Select a single target from `wanted` (create new topic) or `stale` (enrich existing)
3. **Enrich the page**: Read relevant sources, author/update the topic body and frontmatter
4. **Re-index**: Run `index` (recomputes quality tiers, backlinks, alias resolution)
5. **Repeat**: Run `worklist` again for the updated queue

One page per iteration keeps context bounded; as topics improve, they drop out of `stale` automatically. `status` reports `wanted_count` and `stale_count` for progress tracking.

### Quality Tiering

Topics get a five-tier rating (`stub` / `basic` / `standard` / `rich` / `premium`) from **structural metrics** of the markdown body (sections, evidence lines, script-fair prose weight, images, lead sentence — see `references/topic-authoring.md` for metric definitions).

**Effective prose with source grounding**: `effective_prose = prose_weight + 500 × unique_source_count` — each deduplicated source reference adds a grounding bonus.

**Tier gates** (top-down first-match):
- **premium**: sections ≥ 6 AND effective_prose ≥ 3000 AND evidence_lines ≥ 3
- **rich**: sections ≥ 4 AND effective_prose ≥ 1500 AND (evidence_lines ≥ 1 OR has_image)
- **standard**: sections ≥ 2 AND effective_prose ≥ 600
- **basic**: (effective_prose ≥ 200 AND prose_weight > 0) OR sections ≥ 1
- **stub**: otherwise

**Usage**: `quality` reports per-topic metrics and tier distribution; `worklist` flags `stub`/`basic` topics as `stale`; `index` recomputes tiers on every rebuild. The formula is deterministic and monotonic — `quality` and `index` apply the same source-grounding bonus.

### Authors Backfill

When source notes carry a `作者:` metadata row: `aggregate-authors` resolves each topic's `sources` to root notes and returns the **deduplicated first author** per topic (read-only). Write the returned lists into each topic's `authors` frontmatter, then rebuild via `index`/`gen-base`. Use `extract-authors` to inspect raw rows when a result looks off.

### Report Capture (research reports)

Persist valuable Agent research reports as **first-class, cross-linkable wiki nodes**. Capture is
**passive**: the Agent authors the page, then registers it — the CLI writes no prose. This is the
default landing spot for **Answer mode** output.

1. **Author the page** directly under `wiki/queries/<name>.md`, with topic-compatible frontmatter (`title`, `sources` [may be empty], `last_updated`, optional `summary`/`keywords`). Preserve any `[[wikilinks]]`/`![[embeds]]` verbatim.
2. **Register it**: run `save-report <name>`. The CLI ensures the `kind: query` discriminator (directory-derived), appends a log entry, and emits the page path. `<name>` is sanitized to its final path component with `.md` ensured.
3. **Re-ingest / cross-link**: run `index` (or `gen-base`) to pick the page up into the retrieval index under `queries`. To relate a report to a topic, add a `[[wikilink]]` in either page body — relations are surfaced by `gen-canvas`.

The CLI touches only `wiki/queries/` and `wiki/log.md`; an uninitialized wiki → `wiki_not_initialized`, a missing page → `capture_not_found`, and unparseable frontmatter fails with no write and no log entry.

#### Web Augmentation & Citations (Supplement when information is insufficient)

When the vault's sources are **insufficient** to answer fully, supplement with web search — and **always cite**:

1. **Exhaust the vault first**: route via the Hybrid Retrieval Protocol and ground in `sources[]`. Go to the web only for gaps the vault cannot fill.
2. **Search the web**: use the `websearch` if available. For pages, prefer `defuddle parse <url> --md`. **Do NOT fetch PDF links** — record the URL and link text only.
3. **Cite every external claim**: inline citation per statement, plus a closing `## 参考来源` section listing each source as `- [标题](URL)` in citation order. Never present web-derived facts without an attributable URL.
4. **Mark provenance**: keep vault-grounded and web-supplemented content distinguishable (e.g. `> 来源：网络检索`). Never fabricate — if neither vault nor web yields an answer, say so explicitly.

### Optional Static HTML Export

`gen-site` generates a self-contained static site under `wiki/site/` for **local offline browsing** — export is opt-in; Obsidian remains the primary interface. Optional `markdown` package; degrades gracefully to escaped plaintext when absent. Skipped topics are reported in `errors`. Design system, themes, page anatomy, and determinism guarantees: see `references/site-export.md`.

**Workflow**:
1. Run `gen-site` to generate/refresh the site
2. Check `status` for `site_exists` and `site_stale` (true if any topic is newer than the site)
3. Open `wiki/site/index.html` directly (fully offline)

### Knowledge Graph (Canvas)

`gen-canvas` renders a deterministic **JSON Canvas 1.0** subgraph per topic under `wiki/graphs/<topic>.canvas`, consumed purely from the retrieval index:

- **Scope**: the topic at visual center, one node per `sources[]` entry on an inner ring, and one node per **1-hop neighbor topic** on an outer ring.
- **Neighbor rule**: topics sharing ≥1 `sources[]` entry ∪ topics the target's body `[[wikilinks]]` resolve to ∪ topics whose `[[wikilinks]]` resolve back (by topic-stem), excluding the target.
- **Layout**: closed-form radial — no randomness; ring radii scale with member count. A vault-file source becomes a clickable `file` node; an `http(s)://` source becomes a `link` node.
- The canvas is a derived, hand-editable artifact, never written back into frontmatter; `status.graphs_stale` flags topics newer than (or missing) their canvas. Rebuild the index first so neighbors are current.

### Homepage (gen-home)

`gen-home` builds the `wiki/index.md` **skeleton** plus **one managed "workspace" block** (delimited by `<!-- agent-wiki:auto start … -->` / `<!-- … end -->` markers): the script owns the skeleton and managed block; the **agent** writes the semantic prose (regroup topics, fill range, author the relationship narrative). Cards render as a Dataview grid when detected (`--cards auto|on|off`), else a static list.

**Re-run semantics (never clobber)**: markers present → only the managed block is refreshed (agent prose preserved byte-for-byte); content without markers → block appended; empty/placeholder → full skeleton. `index.base` is never touched.

Three layout templates (academic / dashboard / magazine) are bundled under `templates/home/` in the skill directory — copy one into `{vault}/wiki/index.md` and fill the `_待补充_` placeholders, keeping the auto markers intact.

Details (cards detection, Obsidian Local REST API write-through for open-editor safety, optional CSS): see `references/homepage.md`. REST env vars: `AGENT_WIKI_OBSIDIAN_API_KEY` (+ optional `AGENT_WIKI_OBSIDIAN_API_URL`, default `https://127.0.0.1:27124`; TLS verification skipped only for loopback hosts) — see `.env.example`.

### Hybrid Retrieval Protocol

Answer questions in two passes — route cheaply, then ground precisely:

1. **Route** (fast): Read `wiki/.wiki-index.json` and use indexed fields to identify likely-relevant topics:
   - **Alias resolution**: Check `alias_index` first (maps alternative names → canonical topic keys)
   - **Primary fields**: `title`, `keywords`, `summary`, `source_type`, `sources` paths
   - **Ranking signals**: `quality_tier` (premium/rich/standard prioritized), `backlinks` (popularity/centrality), `featured` flag
   - **Do not** read every topic file during routing

2. **Ground** (deep): For detailed evidence, methods, paper data, or comparisons:
   - Follow each topic's `sources` entries to read the **original notes**
   - Check topics with high `backlinks` counts for cross-references
   - Use `coverage` to verify completeness (identify gaps in source coverage)

3. **Conflict rule**: If an indexed `summary` conflicts with source content, the **source note is authoritative**; correct the topic and rebuild the index on the next ingest pass.

4. **Disambiguation**: When `alias_index` lookup fails or returns conflicts, consult `.wiki-aliases.json` for manual disambiguation mappings. Conflicts are reported but never auto-resolved.

The index is a derived cache: topic frontmatter is the single source of truth. `index`/`gen-base` regenerate it from `wiki/topics/*.md`; `status` reports `index_stale` read-only and never rebuilds.

### Enriched Topic Authoring

For paper-like sources, populate the common frontmatter fields and write concise body sections for key paper data, experimental methods, technical routes, research trends, and source-grounded evidence **when the source supports them**. If a source lacks a dimension, **omit the field or mark the section unavailable — never fabricate**. Preserve existing wikilinks/embeds verbatim; never modify source notes or attachments.

**Every topic body MUST open with a single positioning sentence** (定位句) before the first `##` heading — plain paragraph, no heading/list/quote.

The optional frontmatter `type` field (concept/method/paper/person/event/place/overview) selects a recommended section structure — taxonomy, per-type section templates, and the conflict-recording convention: see `references/topic-authoring.md`.

### URL Fetching Rules

- Use `grok-search` or `exa` skills if available
- **PDF links**: Do NOT fetch (`.pdf` extension or `Content-Type: application/pdf`) — record URL and link text only

### Obsidian Wikilink Preservation

- Preserve `[[note]]` wikilinks and `![[image.png]]` embeds verbatim in topic bodies
- In frontmatter `sources: []`, use relative paths (no `[[...]]` wrap)

## Integration with Obsidian Skills

- **Source reading**: prefer `obsidian read file="..."` (captures unsaved editor buffers); fall back to direct file read
- **URL fetching**: `defuddle parse <url> --md` (replaces WebFetch for token efficiency)
- **Frontmatter updates**: prefer `obsidian property:set name="..." value="..." file="..."`; fall back to direct YAML rewrite
- **Dynamic index (Bases)**: run `gen-base` to write the two `.base` views deterministically; embed via `![[index.base#主题总览]]`. View columns, faceting, and fallback: see `references/index-schema.md`

## Wiki Structure

```
{vault}/
├── <name>.base             # Source master table (Bases, at vault root)
└── wiki/
    ├── index.md             # Homepage skeleton (gen-home); agent fills prose, cards auto-render
    ├── index.base           # Topic overview view (Bases)
    ├── log.md               # Append-only log
    ├── topics/              # Topic pages (LLM-written)
    │   └── 量子叠加原理.md
    ├── queries/             # Captured research reports (kind: query)
    ├── graphs/              # Generated JSON Canvas graphs (<topic>.canvas)
    ├── site/                # Optional static HTML export (gen-site)
    ├── _archived/{date}/    # Orphaned topics
    ├── .wiki-cache.json     # Incremental cache
    ├── .wiki-index.json     # Derived retrieval index (normalized metadata)
    └── .wiki-url-cache/     # External URL snapshots (optional)
```

### Topic Page Frontmatter Contract

`title`, `sources`, and `last_updated` are required/compatible; the remaining fields are optional, Agent-authored, and normalized into `wiki/.wiki-index.json`. `source_type` is **auto-derived** from `sources[]` file formats (never hand-edit; run `normalize-source-type`):

```yaml
---
title: 量子叠加原理
type: concept                 # optional page kind
aliases: ["叠加原理"]          # optional alternative names
featured: true                # optional emphasis flag (strict boolean)
sources:
  - "物理/量子力学/态叠加.md"
last_updated: 2026-06-04T15:30:00
summary: 一句话主题摘要，用于索引快速路由。
keywords: ["叠加态", "波函数"]
---
```

Full field list (`year_start`/`year_end`, `authors`, `institutions`, `methods`, `technical_routes`, `research_trends`), the derived `source_type` category table, the complete `.wiki-index.json` schema, and the capture-page contract: see `references/index-schema.md`.

### Scope Boundaries

This skill **includes** research-report capture (`save-report`) and Canvas knowledge-graph generation (`gen-canvas`). Two boundaries hold: the CLI makes **no embedded LLM API calls** (all page prose is Agent-authored; the CLI only places, registers, indexes, or renders derived artifacts), and classification/visualization **never physically reorganizes** topic/query files into per-category folders — they stay flat under `wiki/topics/` and `wiki/queries/`.

## Notes

- All paths in cache and frontmatter use NFC-normalized POSIX separators
- Derived topic paths are constrained to `wiki/topics/` — `cache-put` rejects and `cleanup` reports out-of-bounds entries (`invalid_topic_path`)
- Concurrent safety: single-process assumption; cache writes are atomic
- Topic pages: Agent should merge with existing content, not overwrite
- No LLM API calls embedded in CLI; all content generation by main Agent
