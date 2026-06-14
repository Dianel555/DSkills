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

## Execution

The skill provides a Python CLI with the following subcommands:

```bash
# Initialize wiki structure
python scripts/agent_wiki_cli.py init --vault /path/to/vault

# Scan for changed sources
python scripts/agent_wiki_cli.py scan --vault /path/to/vault

# Plan a batched ingest: split pending sources into rounds (default 20/round),
# writing a task report to wiki/_archived/ingest-tasks.md
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

# Register an Agent-authored conversation page (wiki/sessions/<name>.md) and tag kind: session
python scripts/agent_wiki_cli.py save-session <name> --vault /path/to/vault

# Register an Agent-authored research report (wiki/queries/<name>.md) and tag kind: query
python scripts/agent_wiki_cli.py save-report <name> --vault /path/to/vault

# Generate per-topic JSON Canvas knowledge graphs under wiki/graphs/ (one topic or all)
python scripts/agent_wiki_cli.py gen-canvas --topic <name> --vault /path/to/vault
python scripts/agent_wiki_cli.py gen-canvas --all --vault /path/to/vault

# Build/refresh the wiki/index.md skeleton + its managed "工作区" card block
# Cards auto-detect Dataview (--cards auto|on|off); index.md prefers the Obsidian Local REST API when configured, else atomic write (--no-rest forces atomic)
python scripts/agent_wiki_cli.py gen-home --vault /path/to/vault

# Extract raw 作者 rows from each topic's source notes (read-only)
python scripts/agent_wiki_cli.py extract-authors --vault /path/to/vault

# Deduplicated first-author list per topic, for frontmatter backfill (read-only)
python scripts/agent_wiki_cli.py aggregate-authors --vault /path/to/vault

# Compute quality tier distribution and per-topic metrics (read-only)
python scripts/agent_wiki_cli.py quality --vault /path/to/vault

# Identify covered sources vs gaps (read-only)
python scripts/agent_wiki_cli.py coverage --vault /path/to/vault

# Get maintenance worklists: wanted (broken links) and stale (low-quality/outdated) topics (read-only)
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
| `cache-put` | Record ingest completion | source path, topic list | `{"ok": true, "path": "...", "sha256": "..."}` |
| `cleanup` | Remove deleted sources from topics | vault path | `{"removed": N, "archived": M, "details": [...]}` |
| `status` | Wiki health metrics (read-only) | vault path | `{"vault": "...", "sources_tracked": N, "topics_total": N, "index_exists": bool, "index_topics": N, "index_stale": bool, "index_errors": [...], "batch": {...}\|null, "quality_distribution": {...}, "featured_count": N, "aliases_count": N, "backlinks_max": N, "gaps_count": N, "wanted_count": N, "stale_count": N, "site_exists": bool, "site_stale": bool, ...}` |
| `index` | Rebuild `wiki/.wiki-index.json` from topic frontmatter (no `.base` written) | vault path | `{"ok": true, "topics": N, "errors": [...]}` |
| `normalize-source-type` | Rewrite each topic's `source_type` frontmatter to its `sources[]` file format (in place; no-source topics skipped) | vault path | `{"ok": true, "changed": [{"path": "...", "source_type": "..."}], "skipped": N, "errors": [...]}` |
| `gen-base` | Rebuild the index, then write Obsidian Bases views (index + master table) | vault path, `--name` | `{"ok": true, "prefix": "...", "written": [...]}` |
| `save-session` | Register an Agent-authored conversation page under `wiki/sessions/`, ensure `kind: session`, log it (page authored by Agent; CLI writes no prose) | name, vault path | `{"ok": true, "path": "sessions/<name>.md", "kind": "session"}` or `{"error": "capture_not_found", "path": "..."}` |
| `save-report` | Register an Agent-authored research report under `wiki/queries/`, ensure `kind: query`, log it | name, vault path | `{"ok": true, "path": "queries/<name>.md", "kind": "query"}` |
| `gen-canvas` | Generate per-topic JSON Canvas 1.0 graph(s) under `wiki/graphs/` from the index (topic center + `sources[]` ring + 1-hop neighbor topics) | vault path, `--topic <name>` or `--all` | `{"ok": true, "path": "wiki/graphs/<name>.canvas", "nodes": N, "edges": M}` or `{"ok": true, "written": [...], "count": K}` |
| `gen-home` | Build/refresh the `wiki/index.md` skeleton + one managed "工作区" block (Dataview card grid when detected, else static list); refreshes **only** the managed block on re-run (agent prose preserved), appends it to an unmarked content-bearing index; never touches `index.base` | vault path, `--cards auto\|on\|off` (default auto), `--no-rest` | `{"ok": true, "path": "wiki/index.md", "cards": bool, "write_via": "rest\|atomic"}` |
| `extract-authors` | Raw 作者 row per topic source note (read-only) | vault path | `{"ok": true, "topics": {"<topic>.md": [{"src": "...", "file": "...", "authors": "..."}]}}` |
| `aggregate-authors` | Deduplicated first author per topic for frontmatter backfill (read-only) | vault path | `{"ok": true, "authors": {"<topic>.md": ["作者1", ...]}}` |
| `quality` | Compute quality tier distribution and metrics per topic (read-only) | vault path | `{"ok": true, "tiers": {"<topic>.md": {"tier": "...", "metrics": {...}}}, "distribution": {"stub": N, ...}, "errors": [...]}` |
| `coverage` | Identify covered sources vs gaps (read-only) | vault path | `{"ok": true, "covered": N, "gaps": [{"path": "..."}], "coverage_ratio": 0.0-1.0}` |
| `worklist` | Get maintenance worklists: `wanted` (broken link targets ranked by demand) and `stale` (low-quality or index-stale topics) for bounded enrichment (read-only) | vault path | `{"ok": true, "wanted": [{"target": "...", "inbound": N, "linked_from": [...]}], "stale": [{"path": "...", "tier": "...", "reason": "low_tier"\|"index_stale"}]}` |
| `gen-site` | Generate self-contained static HTML site under `wiki/site/` (optional; requires `markdown` package; degrades gracefully to escaped plaintext if absent; inline CSS; deterministic injective filenames) | vault path | `{"ok": true, "pages": N, "out": "wiki/site", "degraded": bool}` |

## Agent Workflow

### Standard Ingest Loop

1. **Scan**: Run `scan` to get new/modified/deleted sources
2. **Process each source**:
   - For `new`/`modified`: Read source → generate/update **enriched** topic pages → `cache-put`
   - For `deleted`: Run `cleanup` (handles topic frontmatter update and archival)
3. **Refresh retrieval index**: Run `index` to rebuild `wiki/.wiki-index.json` from topic frontmatter
4. **Refresh views**: Run `gen-base` to (re)write the Bases views (this also rebuilds the index), then update `wiki/index.md` with topic summaries and embed `![[index.base#主题总览]]`
5. **Log**: Append to `wiki/log.md`

### Batched Ingest (large vaults)

To avoid loading the whole vault at once, process sources in bounded rounds instead of
the single-pass loop above:

1. **Plan**: Run `plan --batch-size 20` once. It scans, splits the pending sources
   (`new` + `modified`) into rounds of at most N (default **20**), and writes a checklist
   report to `wiki/_archived/ingest-tasks.md`. The JSON lists each batch's `items`.
2. **Process one round**: Read **only** the docs in the current batch, author/update their
   topic pages, and `cache-put` each one. Do **not** read ahead into later batches.
3. **Confirm the round**: Run `batch-done --batch <id>`. It refuses (`batch_incomplete`,
   listing `missing` docs) until every doc in the batch is cached, then marks the batch
   `[x]` in the report and returns `remaining` batch ids.
4. **Repeat** for each `remaining` batch until `complete` is `true`.
5. **Finish**: Run `cleanup` (if any deletions), then `gen-base`, and log as usual.

`status` reports batch progress under `batch` (`batches_done`/`batches_pending`). Re-running
`plan` re-derives batches from the current scan — already-ingested docs drop out automatically.

### Bounded Enrichment Loop

After initial ingest, maintain and improve topics incrementally **without scanning the entire vault**:

1. **Check worklist**: Run `worklist` to get two bounded work queues:
   - `wanted`: broken wikilink targets ranked by demand (inbound link count)
   - `stale`: low-quality topics (`stub`/`basic` tier) or index-stale topics (modified after last index rebuild)
2. **Pick one page**: Select a single target from `wanted` (create new topic) or `stale` (enrich existing topic)
3. **Enrich the page**: Read relevant sources, author/update the topic body and frontmatter
4. **Re-index**: Run `index` to update the retrieval index (this recomputes quality tiers, backlinks, alias resolution)
5. **Repeat**: Run `worklist` again to get the updated work queue

**Key properties**:
- **No full-vault scan**: `worklist` reads only the index, not every source file
- **One page per iteration**: Bounded context, no state explosion
- **Automatic priority**: `wanted` ranks by link demand, `stale` identifies quality gaps
- **Self-correcting**: as topics improve (tier rises), they drop out of `stale` automatically

**Status metrics**: `status` reports `wanted_count` and `stale_count` for progress tracking.

### Authors Backfill

When source notes carry a `作者:` metadata row and topics accumulate too many / duplicate
authors, normalize them deterministically:

1. `aggregate-authors` resolves each topic's `sources` to the root notes, extracts the
   `作者:` row, and returns the **deduplicated first author** per topic (read-only).
2. Write the returned lists into each topic's `authors` frontmatter, then rebuild via
   `index`/`gen-base`. Use `extract-authors` to inspect the raw rows when a result looks off.

### Conversation & Report Capture

Persist valuable Agent conversations and research reports as **first-class, cross-linkable
wiki nodes**. Capture is **passive**: the Agent authors the page, then registers it — the CLI
writes no prose (mirroring `cache-put`).

1. **Author the page** directly under `wiki/sessions/<name>.md` (a conversation) or
   `wiki/queries/<name>.md` (a research report), with topic-compatible frontmatter
   (`title`, `sources` [may be empty], `last_updated`, optional `summary`/`keywords`).
   Preserve any `[[wikilinks]]`/`![[embeds]]` verbatim.
2. **Register it**: run `save-session <name>` or `save-report <name>`. The CLI ensures the
   `kind` discriminator (`session`/`query`, **directory-derived**), force-setting and atomically
   rewriting only when it is absent or wrong (a correctly-tagged page is left byte-unchanged),
   appends a `capture | save_session|save_report | <rel>` log entry, and emits the page path.
   `<name>` is sanitized to its final path component with `.md` ensured.
3. **Re-ingest / cross-link**: run `index` (or `gen-base`) to pick the page up into the
   retrieval index under the `sessions`/`queries` objects (with its `kind` and body `links[]`).
   To relate a capture to a topic, add a `[[wikilink]]` in either page body — neighbor/backlink
   relations are then derivable from the index and surfaced by `gen-canvas`.

The CLI touches only `wiki/sessions/`, `wiki/queries/`, and `wiki/log.md`; an uninitialized wiki
→ `wiki_not_initialized`, a missing page → `capture_not_found`, and unparseable frontmatter
fails with no write and no log entry. **Optional** ergonomics (documented, not required): a
session-stop hook or a slash command that authors the page then calls `save-session`. A stateless
CLI cannot observe the conversation itself, so this stays an Agent-driven step.

### Optional Static HTML Export

Generate a self-contained static site under `wiki/site/` for offline browsing or hosting. **Obsidian remains the primary interface** — export is opt-in only.

**Requirements**: 
- Optional `markdown` package (pinned for determinism)
- Degrades gracefully: if `markdown` is absent, exports plaintext (HTML-escaped) instead

**What gets exported**:
- One HTML page per topic with:
  - Frontmatter infobox sidebar (title, type, quality tier, featured marker, backlinks count)
  - Rendered markdown body (or escaped plaintext in degraded mode)
  - Inline CSS (no external dependencies)
- `index.html` listing all topics

**Determinism**:
- Byte-identical output for fixed inputs and markdown version
- No wall-clock timestamps (uses index `generated_at`)
- Injective filenames: `sanitize(stem)-<sha256[:8]>.html` (CJK preserved)

**Workflow**:
1. Run `gen-site` to generate/refresh the site
2. Check `status` for `site_exists` and `site_stale` (true if any topic is newer than site)
3. Deploy `wiki/site/` to a static host if desired

The export is **write-only under `wiki/site/`** — never modifies sources, topics, `.base`, or `.canvas` files.

### Knowledge Graph (Canvas)

`gen-canvas` renders a deterministic **JSON Canvas 1.0** subgraph per topic under
`wiki/graphs/<topic>.canvas`, consumed purely from the retrieval index:

- **Scope**: the topic at visual center, one node per `sources[]` entry on an inner ring, and one
  node per **1-hop neighbor topic** on an outer ring.
- **Neighbor rule**: topics sharing ≥1 `sources[]` entry with the target ∪ topics the target's
  body `[[wikilinks]]` resolve to ∪ topics whose `[[wikilinks]]` resolve back to the target
  (by topic-stem), excluding the target itself.
- **Layout**: closed-form radial — no randomness, no iteration; ring radii scale with member
  count so same-ring boxes never overlap. **Colors**: topic `4`, source `6`, neighbor `5`.
  A vault-file source becomes a clickable `file` node; an `http(s)://` source becomes a `link` node.
- Run `--topic <name>` for one canvas or `--all` for one per topic. The canvas is a derived,
  hand-editable artifact and is never written back into topic frontmatter; `status.graphs_stale`
  flags topics newer than (or missing) their canvas. Rebuild the index first so neighbors are current.

### Homepage Skeleton + Managed Cards

`gen-home` deterministically builds the `wiki/index.md` **skeleton**, not a finished page: an
Obsidian-native frame (overview line, the Bases embed `![[index.base#主题总览]]`, a 主题导航 table
scaffold with auto-filled 主题/篇数 and `_待补充_` 范围 cells, and a 关系图谱 placeholder) plus **one
managed "工作区" block** delimited by `<!-- agent-wiki:auto start … -->` / `<!-- … end -->`. The
**division of labor**: the script owns the skeleton and the managed block; the **agent** writes the
semantic prose (regroup topics, fill 范围, author the relationship narrative); the **cards** are the
one-click scriptable part.

**Cards (Dataview auto-detection)**: the managed block renders captured sessions / reports / graphs
as a centered, responsive **card grid** via a `dataviewjs` query when Dataview is installed *and* its
JavaScript Queries are enabled (read from `.obsidian/community-plugins.json` + `dataview/data.json`).
Otherwise it falls back to a static NFC-sorted Markdown list. `--cards auto` (default) follows
detection; `--cards on` forces the card grid; `--cards off` forces the static list. The grid fills
rows evenly and **centers the trailing row** (no sparse edges for any item count), using theme-variable
colors, hover/focus/press feedback and `prefers-reduced-motion` support. Cards are clickable internal
links; `.canvas` graphs are matched explicitly (Dataview's DQL does not index canvas, so the block
uses `app.vault.getFiles()`).

> **Prerequisite for cards**: Dataview → Settings → "Enable JavaScript Queries" must be on, or the
> `dataviewjs` block won't execute. Detection checks this flag; when off, gen-home emits the static
> list and its callout points the user to the toggle.

**Re-run semantics (never clobber)**: an empty/placeholder `index.md` gets the full skeleton; an index
that already has the markers gets **only the managed block refreshed** (agent prose outside the markers
is preserved byte-for-byte); a content-bearing index **without** markers gets the managed block
**appended** at the end (existing content untouched). Output is byte-identical for a fixed vault (no
timestamps). It **does not** modify `index.base` or create any `.base` file — `index.base` stays the
topic data provider and `index.md` the layout controller, so the two-file `gen-base` contract is
preserved. An optional CSS snippet (see *Optional Homepage CSS* below) adds typography/palette polish;
the skeleton reads correctly in default light/dark themes without it.

**Conflict-safe write (Obsidian open)**: `index.md` is the one wiki file users keep open in an
Obsidian tab, so an external `os.replace` can race the editor buffer. When the **Obsidian Local REST
API** plugin is configured (env vars below), gen-home writes `index.md` *through* Obsidian
(`PUT /vault/{path}`) so the editor buffer and disk update together; otherwise it falls back to the
normal atomic write. `write_via` in the output reports which path was taken (`rest` / `atomic`). Only
`index.md` uses this; canvas/capture/index files stay atomic. Pass `--no-rest` to always write
directly. Configure (key from Obsidian → Settings → Local REST API; read from the environment only,
never persisted — see `.env.example`):

```bash
export AGENT_WIKI_OBSIDIAN_API_KEY=<your-key>          # required to enable REST write
export AGENT_WIKI_OBSIDIAN_API_URL=https://127.0.0.1:27124  # optional, this is the default
```

The HTTPS endpoint uses a self-signed cert; agent-wiki skips TLS verification **only for loopback
hosts** (127.0.0.1/localhost/::1).

### Hybrid Retrieval Protocol

Answer questions in two passes — route cheaply, then ground precisely:

1. **Route** (fast): Read `wiki/.wiki-index.json` and use indexed fields to identify likely-relevant topics:
   - **Alias resolution**: Check `alias_index` first (maps alternative names → canonical topic keys)
   - **Primary fields**: `title`, `keywords`, `summary`, `source_type`, `sources` paths
   - **Ranking signals**: `quality_tier` (premium/rich/standard prioritized), `backlinks` (popularity/centrality), `featured` flag
   - **Do not** read every topic file during routing

2. **Ground** (deep): For detailed evidence, methods, paper data, or comparisons:
   - Follow each topic's `sources` entries to read the **original notes**
   - Check topics with high `backlinks` counts for cross-references and related concepts
   - Use `coverage` command to verify completeness (identify gaps in source coverage)

3. **Conflict rule**: If an indexed `summary` conflicts with source content, the **source note is authoritative**; correct the topic and rebuild the index on the next ingest pass.

4. **Disambiguation**: When `alias_index` lookup fails or returns conflicts, consult `.wiki-aliases.json` for manual disambiguation mappings. Conflicts are reported but never auto-resolved.

The index is a derived cache: topic frontmatter is the single source of truth. `index`/`gen-base` regenerate it from `wiki/topics/*.md`; `status` reports `index_stale` (any topic newer than the index) read-only and never rebuilds.

**Quality & Coverage Metrics**:
- `quality` command: Per-topic tier distribution and metrics (sections, evidence_lines, prose_chars, has_image, has_lead)
- `coverage` command: Identifies which sources are covered by topics vs gaps (uncovered sources)
- `status` extended fields: `quality_distribution`, `featured_count`, `aliases_count`, `backlinks_max`, `gaps_count`

### Enriched Topic Authoring

For paper-like sources, populate the common frontmatter fields and write concise body sections for
key paper data, experimental methods, technical routes, research trends, and source-grounded evidence
**when the source supports them**. If a source lacks a dimension, **omit the field or mark the section
unavailable — never fabricate**. Preserve existing wikilinks/embeds verbatim; never modify source notes
or attachments.

### Topic Type Taxonomy & Content Structure

#### Type Field (Page Kind)

The optional frontmatter `type` field describes the page kind and is **orthogonal** to the auto-derived `source_type` (file format):
- `type` = **page kind** (concept/method/paper/person/event/place/overview) — Agent-authored, optional
- `source_type` = **file format** (markdown/pdf/web/mixed) — **CLI-derived** from `sources[]`, never hand-edited

**Recommended `type` vocabulary** (stored as-is if outside this list, never rejected):
- `concept` — principles, definitions, theoretical constructs
- `method` — techniques, algorithms, protocols
- `paper` — research papers, publications
- `person` — researchers, authors, historical figures
- `event` — conferences, experiments, historical events
- `place` — institutions, labs, geographical locations
- `overview` — surveys, meta-analyses, literature reviews

#### Lead Sentence Rule (定位句)

**Every topic body MUST open with a single positioning sentence** (定位句) before the first `##` heading:
- Concisely states what/who/where the topic is
- No heading, no list, no quote block — plain paragraph
- Example: `量子叠加原理是量子力学的核心原理，描述量子态可以同时处于多个本征态的线性组合。`

The CLI computes a read-only `has_lead` metric (quality metrics) but **never authors prose**.

#### Per-Type Section Templates

Each `type` has a recommended priority-ordered section structure. Omit sections the source doesn't support.

**concept**:
1. `## 定义` (definition)
2. `## 核心原理` (core principles)
3. `## 应用场景` (applications)
4. `## 相关概念` (related concepts)
5. `## 历史发展` (historical development, if relevant)

**method**:
1. `## 原理` (principle/mechanism)
2. `## 步骤` (procedure/algorithm)
3. `## 参数` (parameters/configuration, if applicable)
4. `## 适用范围` (scope/constraints)
5. `## 案例` (examples/applications)

**paper**:
1. `## 研究问题` (research question)
2. `## 方法` (methods)
3. `## 主要发现` (key findings)
4. `## 技术路线` (technical routes, if applicable)
5. `## 局限性` (limitations, if stated)

**person**:
1. `## 基本信息` (affiliation, period)
2. `## 主要贡献` (key contributions)
3. `## 代表作` (notable works)
4. `## 合作者` (collaborators, if relevant)

**event**:
1. `## 背景` (context)
2. `## 经过` (proceedings/timeline)
3. `## 成果` (outcomes/impact)
4. `## 参与者` (participants, if relevant)

**place**:
1. `## 概况` (overview)
2. `## 研究方向` (research areas)
3. `## 主要成果` (notable achievements)
4. `## 关键人物` (key people, if relevant)

**overview**:
1. `## 范围` (scope/coverage)
2. `## 主要主题` (major themes)
3. `## 关键文献` (key references)
4. `## 研究趋势` (research trends)

#### Conflict/Contradiction Convention

When source notes **disagree on a fact** (different values, contradictory claims):
- **Do NOT silently pick one** — record the disagreement
- Create a dedicated `## ⚠️ 矛盾` (conflict) section listing each variant with its source
- Example:
  ```markdown
  ## ⚠️ 矛盾
  
  - 来源 A.md 称实验于 1926 年完成
  - 来源 B.md 称实验于 1927 年完成
  ```

### URL Fetching Rules

- Use `grok-search` or `exa` skills if available
- **PDF links**: Do NOT fetch (`.pdf` extension or `Content-Type: application/pdf`)
- Record URL and link text only in topic page

### Obsidian Wikilink Preservation

- Preserve `[[note]]` wikilinks verbatim in topic bodies
- Preserve `![[image.png]]` embeds verbatim
- In frontmatter `sources: []`, use relative paths (no `[[...]]` wrap)

## Integration with Obsidian Skills

### Source Reading
- **Primary**: `obsidian read file="..."` (captures unsaved editor buffers)
- **Fallback**: Direct file read (when Obsidian not running)

### URL Fetching
- **Mandatory**: `defuddle parse <url> --md` (replaces WebFetch for token efficiency)

### Frontmatter Updates
- **Preferred**: `obsidian property:set name="sources" value="[...]" file="..."` (surgical update)
- **Fallback**: Direct YAML rewrite

### Dynamic Index (Bases)
- Run `gen-base` to write two `.base` views deterministically (filter folders auto-resolved relative to the Obsidian vault root — the dir containing `.obsidian`):
  - `wiki/index.base` — topic overview (主题 / 来源数 / 更新日期) plus per-dimension faceted table views (按作者 / 按机构 / 按方法 / 按来源类型 / 按年份) read from frontmatter; embed via `![[index.base#主题总览]]`
  - `{vault}/<name>.base` — source master table (文献 / 年份 / 标签); year parsed from a leading `(YYYY…)` filename, `标签` from source `tags` frontmatter
- **Virtual classification**: Bases renders one row per file and cannot unroll a list-valued property into per-value folders; dimensions are surfaced as filterable columns in the faceted views, and topic files stay flat under `wiki/topics/` (never moved or duplicated)
- **Fallback**: Generate a markdown table in `index.md` if the obsidian-bases plugin is unavailable

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
    ├── sessions/            # Captured conversation pages (kind: session)
    ├── queries/             # Captured research reports (kind: query)
    ├── graphs/              # Generated JSON Canvas graphs (<topic>.canvas)
    ├── _archived/{date}/    # Orphaned topics
    ├── .wiki-cache.json     # Incremental cache
    ├── .wiki-index.json     # Derived retrieval index (normalized metadata)
    └── .wiki-url-cache/     # External URL snapshots (optional)
```

### Topic Page Frontmatter Contract

`title`, `sources`, and `last_updated` are required/compatible. The remaining fields are optional,
Agent-authored, and normalized into `wiki/.wiki-index.json` (omit any the source doesn't support).
`source_type` is the exception — it is **auto-derived** from `sources[]` file formats, not hand-authored:

```yaml
---
title: 量子叠加原理
type: concept                 # optional page kind (concept/method/paper/person/event/place/overview)
aliases: ["叠加原理", "态叠加"]  # optional alternative names
featured: true                # optional emphasis flag (strict boolean)
sources:
  - "物理/量子力学/态叠加.md"
  - "物理/量子力学/双缝实验.md"
last_updated: 2026-06-04T15:30:00
year_start: 1926             # earliest year across the topic's sources (omit for single-year topics)
year_end: 1935               # latest year across the topic's sources
authors: ["Schrödinger"]
source_type: markdown         # auto-derived from sources[] formats (do not hand-edit; run normalize-source-type)
institutions: ["University of Zurich"]
methods: ["wave mechanics"]
technical_routes: ["analytical solution"]
research_trends: ["quantum information"]
summary: 一句话主题摘要，用于索引快速路由（索引中截断至 1000 字符）。
keywords: ["叠加态", "波函数"]
---
```

### Structured Index (`wiki/.wiki-index.json`)

Derived retrieval cache; **frontmatter is the single source of truth** — the index and `.base` files
are regenerated from it and are never written back into topic files. The Obsidian Bases plugin renders
`.base` views by reading topic frontmatter **directly**, not this JSON.

- Top-level: `version` (int `1`), `generated_at` (UTC ISO-8601 derived from the max page mtime across
  all three directories, not wall-clock), `topics` (keyed by NFC POSIX path relative to `wiki/topics/`),
  `sessions` / `queries` (captured pages, keyed by NFC POSIX path relative to `wiki/`, e.g.
  `sessions/<name>.md`), and `alias_index` (derived NFC alias→topic key map for routing). Topic counts stay clean: `index` reports only the topic count.
- **Topic entries** include: `path`, `title`, `sources[]`, `last_updated`,
  `year_start` (int|null), `year_end` (int|null), `authors[]`,
  `source_type` (derived), `institutions[]`, `methods[]`, `technical_routes[]`, `research_trends[]`, `summary`
  (≤1000 chars), `keywords[]`, `kind` (`topic`), `links[]` (parsed from body), plus **extended fields**:
  - `type` (string, default `""`) — page kind from frontmatter (orthogonal to derived `source_type`)
  - `aliases` (array, default `[]`) — order-preserved alternative names from frontmatter
  - `quality_tier` (string enum) — derived tier (`stub`/`basic`/`standard`/`rich`/`premium`)
  - `featured` (boolean, default `false`) — emphasis flag (strict boolean coercion)
  - `backlinks` (int ≥ 0) — distinct inbound linker count across all pages
- **Session/query entries** preserve existing schema (no extended fields); they include the same base fields plus `kind` (`session`/`query`).
- Missing fields use null-or-empty defaults; list order is preserved (no dedup/reorder). `year_start`/`year_end` parse a 4-digit run from int or string, else null.
- `source_type` is **always derived from the source file formats** in `sources[]` (`.md`→`markdown`,
  `.pdf`→`pdf`, `.doc/.docx`→`word`, `.xls/.xlsx/.csv`→`spreadsheet`, `.ppt/.pptx`→`slides`, `.txt`→`text`,
  URL→`web`, else `other`; a topic spanning more than one format becomes `mixed`). Values are always
  lowercase ASCII categories. The frontmatter value is **ignored on rebuild** and treated as a materialized
  copy: run `normalize-source-type` once to rewrite it in place to the derived value (what Obsidian Bases
  reads directly); topics with no sources are skipped. Format discernibility requires `sources[]` to
  reference the original files (e.g. `paper.pdf`, `data.xlsx`); a vault of pure `.md` notes resolves to
  `markdown` for every topic.
- Deterministic: identical topic inputs produce byte-identical JSON. Rebuilds skip and report malformed
  topics (`topic_decode_failed` / `frontmatter_parse_failed`) without blocking others.

### Capture Page Frontmatter Contract

Session/query pages use the **same frontmatter contract as topics** (`title`, `sources` [may be
empty], `last_updated`, optional `summary`/`keywords`, auto-derived `source_type`) plus a `kind`
discriminator that the CLI sets from the directory (`session` for `wiki/sessions/`, `query` for
`wiki/queries/`). They are indexed under the `sessions`/`queries` objects and can be cross-linked
into topics with body `[[wikilinks]]`.

### Optional Homepage CSS

The `gen-home` skeleton renders correctly in default Obsidian themes. For typography/palette polish,
the user may add this **optional** CSS snippet (Settings → Appearance → CSS snippets) — pure
progressive enhancement, safe to omit:

```css
/* agent-wiki homepage — optional progressive enhancement */
.markdown-preview-view,
.markdown-rendered {
  --aw-ink: #475569;          /* slate body ink (light) */
  --aw-accent: #2563eb;       /* blue accent */
}
.theme-dark .markdown-preview-view,
.theme-dark .markdown-rendered {
  --aw-ink: #cbd5e1;          /* lighten ink in dark mode for ≥4.5:1 contrast */
  --aw-accent: #60a5fa;
}
.markdown-rendered h1,
.markdown-rendered h2 {
  font-family: "Crimson Pro", var(--font-text), serif;
  letter-spacing: 0.01em;
}
.markdown-rendered p,
.markdown-rendered li,
.markdown-rendered .callout {
  font-family: "Atkinson Hyperlegible", var(--font-text), sans-serif;
  color: var(--aw-ink);
  line-height: 1.6;           /* 8px vertical rhythm at default size */
}
.markdown-rendered .callout { margin: 8px 0; padding: 8px 12px; }   /* 4/8px spacing */
.markdown-rendered a { color: var(--aw-accent); }
```

The palette (`#475569` ink / `#2563EB` accent), Crimson Pro + Atkinson Hyperlegible pairing, and
4/8px spacing rhythm are delivered via Obsidian CSS variables so themes still control the chrome;
dark-mode variants keep text contrast at ≥4.5:1.

### Scope Boundaries

This skill **includes** conversation/report capture (`save-session`/`save-report`) and Obsidian
Canvas knowledge-graph generation (`gen-canvas`). Two boundaries still hold: the CLI makes **no
embedded LLM API calls** (all page prose is Agent-authored; the CLI only places, registers, indexes,
or renders derived artifacts), and classification/visualization **never physically reorganizes**
topic/session/query files into per-category folders — they stay flat under `wiki/topics/`,
`wiki/sessions/`, `wiki/queries/`.


## Example: Minimal Ingest

```python
# 1. Scan
result = run_cli("scan --vault /path/to/vault")
scan_data = json.loads(result.stdout)

# 2. Process new sources
for item in scan_data["new"]:
    source_content = read_source(item["path"])
    topic_name, topic_content = generate_topic(source_content)
    write_topic(f"wiki/topics/{topic_name}.md", topic_content)
    run_cli(f"cache-put {item['path']} --topics {topic_name}.md --vault /path/to/vault")

# 3. Process deleted sources
if scan_data["deleted"]:
    run_cli("cleanup --vault /path/to/vault")

# 4. Refresh index
topics = list_topics("wiki/topics/")
update_index("wiki/index.md", topics)
append_log("wiki/log.md", f"[{today}] ingest | processed {len(scan_data['new'])} new sources")
```

## Notes

- All paths in cache and frontmatter use NFC-normalized POSIX separators
- Concurrent safety: single-process assumption; cache writes are atomic
- Topic pages: Agent should merge with existing content, not overwrite
- No LLM API calls embedded in CLI; all content generation by main Agent
