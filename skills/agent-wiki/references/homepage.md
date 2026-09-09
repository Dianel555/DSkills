# Homepage (gen-home) Reference

Loaded on demand from SKILL.md. Covers layout templates, the managed cards block,
re-run semantics, the MCP write path, and the optional CSS snippet.

## Layout Templates

Three reference templates are bundled under `templates/home/` in the skill directory. Each provides a complete `index.md` skeleton with a Dataview-managed 工作区 card block — pick one, paste into `wiki/index.md`, and let the agent fill the `_待补充_` placeholders.

| Template | Style | Key Features |
|----------|-------|-------------|
| `academic.md` | Formal, citation-focused | Bases embed → grouped topic list → narrative relationship graph |
| `dashboard.md` | Metrics-first, compact | KPI callout → Bases callouts → table navigation → relationship summary |
| `magazine.md` | Editorial, visually rich | Quote导语 → Bases embed → callout速览 → quote脉络 |

> **Usage**: Copy a template into `{vault}/wiki/index.md`, replace `_待补充_` with agent-authored prose, and keep the `<!-- agent-wiki:auto … -->` block intact so `gen-home` can refresh cards on re-run without clobbering your content.

## Skeleton + Managed Cards

`gen-home` deterministically builds the `wiki/index.md` **skeleton**, not a finished page: an
Obsidian-native frame (overview line, the Bases embed `![[index.base#主题总览]]`, a 主题导航 table
scaffold with auto-filled 主题/篇数 and `_待补充_` 范围 cells, and a 关系图谱 placeholder) plus **one
managed "工作区" block** delimited by `<!-- agent-wiki:auto start … -->` / `<!-- … end -->`. The
**division of labor**: the script owns the skeleton and the managed block; the **agent** writes the
semantic prose (regroup topics, fill 范围, author the relationship narrative); the **cards** are the
one-click scriptable part.

**Cards (Dataview auto-detection)**: the managed block renders captured reports / graphs
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
preserved.

## Write Decision Chain (MCP → file)

`wiki/index.md` is the one wiki file users keep open in an Obsidian tab, so an external `os.replace`
can race the editor buffer. It is written through the most conflict-safe channel available:

1. **MCP** (preferred): if an Obsidian MCP server is connected, probe the target with `vault_get_document_map` to capture its `version`, render the content with `gen-home --emit-only`, then apply it with `vault_patch` (`targetType: heading`, `target: null`, `operation: replace`, `ifMatch: <version>`) so an open editor tab is never blindly replaced. `--emit-only` returns `write_via: "none"` plus `obsidian_path` (root-relative, scope prefix included) and `content`; it never touches disk.
2. **Atomic file write**: otherwise run plain `gen-home`; it writes via same-directory temp file + `os.replace` and reports `write_via: "atomic"`.

Never do both for the same write — pick the first available and stop. Only `index.md` gets the MCP treatment; canvas/capture/index files stay atomic.

## Optional Homepage CSS

The `gen-home` skeleton adds the Obsidian `cssclasses: [agent-wiki-home]` property. The scope keeps this optional styling local to the generated home page. For typography/palette polish,
the user may add this **optional** CSS snippet (Settings → Appearance → CSS snippets) — pure
progressive enhancement, safe to omit:

```css
/* agent-wiki homepage — optional progressive enhancement */
.agent-wiki-home .markdown-preview-view,
.agent-wiki-home .markdown-rendered {
  --aw-ink: #475569;          /* slate body ink (light) */
  --aw-accent: #2563eb;       /* blue accent */
}
.theme-dark .agent-wiki-home .markdown-preview-view,
.theme-dark .agent-wiki-home .markdown-rendered {
  --aw-ink: #cbd5e1;          /* lighten ink in dark mode for ≥4.5:1 contrast */
  --aw-accent: #60a5fa;
}
.agent-wiki-home .markdown-rendered h1,
.agent-wiki-home .markdown-rendered h2 {
  font-family: "Crimson Pro", var(--font-text), serif;
  letter-spacing: 0.01em;
}
.agent-wiki-home .markdown-rendered p,
.agent-wiki-home .markdown-rendered li,
.agent-wiki-home .markdown-rendered .callout {
  font-family: "Atkinson Hyperlegible", var(--font-text), sans-serif;
  color: var(--aw-ink);
  line-height: 1.6;           /* 8px vertical rhythm at default size */
}
.agent-wiki-home .markdown-rendered .callout { margin: 8px 0; padding: 8px 12px; }   /* 4/8px spacing */
.agent-wiki-home .markdown-rendered a { color: var(--aw-accent); }
```

The palette (`#475569` ink / `#2563EB` accent), Crimson Pro + Atkinson Hyperlegible pairing, and
4/8px spacing rhythm are delivered via Obsidian CSS variables so themes still control the chrome;
dark-mode variants keep text contrast at ≥4.5:1.
