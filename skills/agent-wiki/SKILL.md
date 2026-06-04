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
| `status` | Wiki health metrics | vault path | `{"vault": "...", "sources_tracked": N, "topics_total": N, ...}` |

## Agent Workflow

### Standard Ingest Loop

1. **Scan**: Run `scan` to get new/modified/deleted sources
2. **Process each source**:
   - For `new`/`modified`: Read source → generate/update topic pages → `cache-put`
   - For `deleted`: Run `cleanup` (handles topic frontmatter update and archival)
3. **Refresh index**: Update `wiki/index.md` with topic summaries
4. **Log**: Append to `wiki/log.md`

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

### Dynamic Index
- **Primary**: Generate `index.base` (Obsidian Bases view) for sortable/filterable topic table
- **Fallback**: Generate markdown table in `index.md` if obsidian-bases plugin not detected

## Wiki Structure

```
{vault}/wiki/
├── index.md             # Auto-maintained topic directory
├── log.md               # Append-only log
├── topics/              # Topic pages (LLM-written)
│   └── 量子叠加原理.md
├── _archived/{date}/    # Orphaned topics
├── .wiki-cache.json     # Incremental cache
└── .wiki-url-cache/     # External URL snapshots (optional)
```

### Topic Page Frontmatter Contract

```yaml
---
title: 量子叠加原理
sources:
  - "物理/量子力学/态叠加.md"
  - "物理/量子力学/双缝实验.md"
last_updated: 2026-06-04T15:30:00
---
```

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
