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

# Generate Obsidian Bases (.base) views: wiki/index.base + <name>.base master table
python scripts/agent_wiki_cli.py gen-base --name sources --vault /path/to/vault
```

**Vault Path Resolution**: Use `--vault PATH` or set environment variable `AGENT_WIKI_VAULT`.

## CLI Command Matrix

| Command | Purpose | Input | Output (JSON) |
|---------|---------|-------|---------------|
| `init` | Create wiki structure | vault path | `{"status": "ok"\|"already_initialized", "created": [...]}` |
| `scan` | Classify sources as new/modified/deleted | vault path | `{"version": 1, "vault": "...", "stats": {...}, "new": [...], "modified": [...], "deleted": [...]}` |
| `cache-get` | Query cache entry | source relative path | `{"path": "...", "sha256": "...", ...}` or `{"path": "...", "status": "absent"}` |
| `cache-put` | Record ingest completion | source path, topic list | `{"ok": true, "path": "...", "sha256": "..."}` |
| `cleanup` | Remove deleted sources from topics | vault path | `{"removed": N, "archived": M, "details": [...]}` |
| `status` | Wiki health metrics (read-only) | vault path | `{"vault": "...", "sources_tracked": N, "topics_total": N, "index_exists": bool, "index_topics": N, "index_stale": bool, "index_errors": [...], ...}` |
| `index` | Rebuild `wiki/.wiki-index.json` from topic frontmatter (no `.base` written) | vault path | `{"ok": true, "topics": N, "errors": [...]}` |
| `gen-base` | Rebuild the index, then write Obsidian Bases views (index + master table) | vault path, `--name` | `{"ok": true, "prefix": "...", "written": [...]}` |

## Agent Workflow

### Standard Ingest Loop

1. **Scan**: Run `scan` to get new/modified/deleted sources
2. **Process each source**:
   - For `new`/`modified`: Read source → generate/update **enriched** topic pages → `cache-put`
   - For `deleted`: Run `cleanup` (handles topic frontmatter update and archival)
3. **Refresh retrieval index**: Run `index` to rebuild `wiki/.wiki-index.json` from topic frontmatter
4. **Refresh views**: Run `gen-base` to (re)write the Bases views (this also rebuilds the index), then update `wiki/index.md` with topic summaries and embed `![[index.base#主题总览]]`
5. **Log**: Append to `wiki/log.md`

### Hybrid Retrieval Protocol

Answer questions in two passes — route cheaply, then ground precisely:

1. **Route** (fast): Read `wiki/.wiki-index.json` and use indexed `title`, `keywords`, `summary`,
   `source_type`, and `sources` paths to identify the likely-relevant topics — do **not** read every
   topic file.
2. **Ground** (deep): For detailed evidence, methods, paper data, or comparisons, follow each topic's
   `sources` entries and relevant backlinks to read the **original notes** before answering.
3. **Conflict rule**: If an indexed `summary` conflicts with source content, the **source note is
   authoritative**; correct the topic and rebuild the index on the next ingest pass.

The index is a derived cache: topic frontmatter is the single source of truth. `index`/`gen-base`
regenerate it from `wiki/topics/*.md`; `status` reports `index_stale` (any topic newer than the index)
read-only and never rebuilds.

### Enriched Topic Authoring

For paper-like sources, populate the common frontmatter fields and write concise body sections for
key paper data, experimental methods, technical routes, research trends, and source-grounded evidence
**when the source supports them**. If a source lacks a dimension, **omit the field or mark the section
unavailable — never fabricate**. Preserve existing wikilinks/embeds verbatim; never modify source notes
or attachments.

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
    ├── index.md             # Auto-maintained topic directory
    ├── index.base           # Topic overview view (Bases)
    ├── log.md               # Append-only log
    ├── topics/              # Topic pages (LLM-written)
    │   └── 量子叠加原理.md
    ├── _archived/{date}/    # Orphaned topics
    ├── .wiki-cache.json     # Incremental cache
    ├── .wiki-index.json     # Derived retrieval index (normalized metadata)
    └── .wiki-url-cache/     # External URL snapshots (optional)
```

### Topic Page Frontmatter Contract

`title`, `sources`, and `last_updated` are required/compatible. The remaining fields are optional,
Agent-authored, and normalized into `wiki/.wiki-index.json` (omit any the source doesn't support):

```yaml
---
title: 量子叠加原理
sources:
  - "物理/量子力学/态叠加.md"
  - "物理/量子力学/双缝实验.md"
last_updated: 2026-06-04T15:30:00
year_start: 1926             # earliest year across the topic's sources (omit for single-year topics)
year_end: 1935               # latest year across the topic's sources
authors: ["Schrödinger"]
source_type: paper            # recommended: paper|book|article|blog|dataset|web|other
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

- Top-level: `version` (int `1`), `generated_at` (UTC ISO-8601 derived from the max topic mtime, not
  wall-clock), `topics` (keyed by NFC POSIX path relative to `wiki/topics/`).
- Per-topic fields: `path`, `title`, `sources[]`, `last_updated`,
  `year_start` (int|null), `year_end` (int|null), `authors[]`,
  `source_type`, `institutions[]`, `methods[]`, `technical_routes[]`, `research_trends[]`, `summary`
  (≤1000 chars), `keywords[]`. Missing fields use null-or-empty defaults; list order is preserved (no
  dedup/reorder). `year_start`/`year_end` parse a 4-digit run from int or string, else null.
- Deterministic: identical topic inputs produce byte-identical JSON. Rebuilds skip and report malformed
  topics (`topic_decode_failed` / `frontmatter_parse_failed`) without blocking others.

### Out of Scope

Q&A/chat archive capture and Obsidian Canvas/graph generation are **not** part of this skill; they
remain future independent changes.


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
