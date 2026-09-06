# Structured Index & Frontmatter Schema Reference

Loaded on demand from SKILL.md. Full schema of `wiki/.wiki-index.json` and the
frontmatter contracts it normalizes.

## Structured Index (`wiki/.wiki-index.json`)

Derived retrieval cache; **frontmatter is the single source of truth** — the index and `.base` files
are regenerated from it and are never written back into topic files. The Obsidian Bases plugin renders
`.base` views by reading topic frontmatter **directly**, not this JSON.

- Top-level: `version` (int `2`), `generated_at` (UTC ISO-8601 derived from the max page mtime across
  the topics and queries directories, not wall-clock), `topics` (keyed by NFC POSIX path relative to `wiki/topics/`),
  `queries` (captured reports, keyed by NFC POSIX path relative to `wiki/`, e.g.
  `queries/<name>.md`), and `alias_index` (derived NFC alias→topic key map for routing). Topic counts stay clean: `index` reports only the topic count.
- **Topic entries** include: `path`, `title`, `sources[]`, `last_updated`,
  `year_start` (int|null), `year_end` (int|null), `authors[]`,
  `source_type` (derived), `institutions[]`, `methods[]`, `technical_routes[]`, `research_trends[]`, `summary`
  (≤1000 chars), `keywords[]`, `kind` (`topic`), `links[]` (parsed from body),
  `mtime_ns` (int, source file mtime — drives `--incremental` reuse on rebuild), `link_records[]` (target, label, fragment, embed, syntax from the shared parser), and optional academic identity fields `citekey`, `doi`, `library_id`, `review_status`, `reviewed_at`, plus **extended fields**:
  - `type` (string, default `""`) — page kind from frontmatter (orthogonal to derived `source_type`)
  - `aliases` (array, default `[]`) — order-preserved alternative names from frontmatter
  - `quality_tier` (string enum) — derived tier (`stub`/`basic`/`standard`/`rich`/`premium`)
  - `featured` (boolean, default `false`) — emphasis flag (strict boolean coercion)
  - `backlinks` (int ≥ 0) — distinct inbound linker count across all pages
- **Query entries** preserve the topic-only schema boundary (no `type`/quality/backlinks fields); they include the same base fields, optional academic identity fields, parsed `link_records[]`, and `kind` (`query`). Query aliases are not added to the canonical topic alias index; use `keywords` for report discovery.
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

## Full Topic Frontmatter Example

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
citekey: schrodinger1926       # optional stable key from the literature manager
doi: 10.1000/example            # optional DOI; never inferred from a title
library_id: zotero:ABC123       # optional library/item identifier
review_status: needs_review     # optional: needs_review / reviewed / superseded
reviewed_at: 2026-06-04          # optional manual verification date
---
```

## Capture Page Frontmatter Contract

Query (report) pages use the **same frontmatter contract as topics** (`title`, `sources` [may be
empty], `last_updated`, optional `summary`/`keywords`, auto-derived `source_type`) plus a `kind`
discriminator that the CLI sets from the directory (`query` for `wiki/queries/`). They are indexed
under the `queries` object and can be cross-linked into topics with body `[[wikilinks]]`.

## Bases Views (gen-base)

- `wiki/index.base` — topic overview (主题 / 来源数 / 更新日期) plus per-dimension faceted table views (按作者 / 按机构 / 按方法 / 按来源类型 / 按年份) read from frontmatter; embed via `![[index.base#主题总览]]`
- `{agent-wiki scope}/<name>.base` — source master table (文献 / 年份 / 标签); year parsed from a leading `(YYYY…)` filename, `标签` from source `tags` frontmatter
- Filter folders are auto-resolved relative to the registered Obsidian vault root (the dir containing `.obsidian`), while topic/source paths remain relative to the selected agent-wiki scope; child scopes therefore do not collide
- **Virtual classification**: Bases renders one row per file and cannot unroll a list-valued property into per-value folders; dimensions are surfaced as filterable columns in the faceted views, and topic files stay flat under `wiki/topics/` (never moved or duplicated)
- **Fallback**: Generate a markdown table in `index.md` if the obsidian-bases plugin is unavailable
