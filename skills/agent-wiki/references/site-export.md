# Static HTML Export (gen-site) Reference

Loaded on demand from SKILL.md. Covers the design system, page anatomy, and
determinism/safety guarantees of `gen-site`.

Pages embed the **"Oriental Editorial Atlas"** design system (rice-paper / ink / cinnabar)
entirely inline, so each file works offline by double-click. The export is for **local
browsing** of your own notes; Obsidian remains the primary interface.

## Requirements

- Optional `markdown` package (pinned for determinism)
- Degrades gracefully: if `markdown` is absent, the body is exported as HTML-escaped plaintext (TOC and link resolution are skipped); page chrome still renders

## Themes

Three palettes via a `data-theme` attribute — `shan-shui` (宣纸 light, default), `hu-yan` (护眼米色 warm eye-care), `mo-ye` (墨夜 dark). The initial theme follows `prefers-color-scheme`; a header toggle cycles and persists the choice in `localStorage`; all motion respects `prefers-reduced-motion`.

## Page Anatomy

**Topic/report page**: responsive three-zone layout with semantic landmarks — `<nav>` 文献目录 (heading-derived table of contents with scroll-spy) / `<main><article>` 知识舆图 / `<aside>` 资料信息 (frontmatter identity, review status, and source links). A clear return-to-index link and compact provenance block appear before the body. Skip-to-content link, visible focus rings, ≥44px targets; the main reading column remains primary until a measured wide-screen breakpoint. `[[wikilinks]]`, standard Markdown internal links, heading fragments, and local image embeds use the shared resolver; links stay literal inside code and ambiguous targets are inert with a reason. Code/tables/blockquotes/footnotes are styled within the design tokens.

**Index (`index.html`)**: header band + 精选 (featured) section + per-`type` card sections (empty type → "未分类"), with inline client-side search/filter over title, authors, years, aliases/keywords, summary, and literature identifiers. Topics and captured reports are server-rendered and navigable with JavaScript disabled (progressive enhancement).

## Determinism & Safety

- Byte-identical output for fixed inputs and markdown version; all inline JS/CSS are static literals (no `Date.now`/`Math.random`/`fetch`/network)
- No wall-clock timestamps — the footer shows the index `generated_at`
- Clean topic-named filenames: `sanitize(stem).html` with no hash suffix (CJK preserved); collisions are disambiguated with numeric suffixes (`-2`, `-3`, …) in NFC key order
- Automatic pruning: each `gen-site` run removes orphaned HTML files (from renamed/deleted topics or old naming schemes), keeping only current output
- Atomic writes, **write-only under `wiki/site/`** — never modifies sources, topics, `.base`, or `.canvas`; `index.html` is written last so `site_stale` stays correct
- Markdown output is passed through a small HTML element/attribute allowlist; only relative, `http`, `https`, and `mailto` URLs survive. Imported note HTML is rendered as data, not executable markup; degraded mode remains fully escaped.
- Topics that fail to decode/parse are skipped and reported in the result's `errors` list
