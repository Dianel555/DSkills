---
name: github-trending-analyzer
description: Crawl GitHub trending repositories, analyze with LLM for Chinese insights, categorize by themes, compute diffs against history, and generate Markdown reports. Default brief mode stops at trend analysis; optional detailed mode appends per-project analysis. Supports incremental gap-filling and selective re-analysis with caching.
---

# GitHub Trending Analyzer

A workflow protocol for tracking GitHub trending repositories with LLM-powered analysis. Fetches trending projects, enriches each with structured Chinese insights (what/analogy/help/who), classifies by themes, compares against historical snapshots, and generates reports in two modes — a compact brief (default) or a detailed report with per-project analysis (opt-in).

## Trigger Signals

- GitHub trending analysis
- Weekly tech trend report
- Repository discovery automation
- Incremental analysis refresh
- Theme-based repo categorization

## Preconditions

- HTTP access to github.com/trending (no auth required for public trending)
- LLM backend capable of JSON-structured output (for the 4-field analysis schema)
- File system access for memory cache and report output
- HTML parsing capability (regex or DOM parser)

## Strategy

Run the five-step pipeline in order.

### Step 1: Fetch trending HTML

Construct the URL with time range and optional language filter:
```
https://github.com/trending[/{language}]?since={daily|weekly|monthly}
```

Fetch with a browser User-Agent to avoid bot detection. Parse the HTML to extract:
- `name` (org/repo)
- `url` (full GitHub link)
- `desc` (one-line description from the page)
- `lang` (primary language)
- `stars` (total stargazers count)
- `today_stars` (increment for this period)

**Regex patterns** (reference from source):
- Project name: `<h2[^>]*>.*?<a href="/([^"]+)"`
- Description: `<p class="[^"]*col-9[^"]*"[^>]*>\s*(.*?)\s*</p>`
- Language: `<span itemprop="programmingLanguage">([^<]+)</span>`
- Stars: parse from `/stargazers` link text after stripping HTML tags
- Today increment: `([\d,]+)\s*stars?\s*(?:this|today)` (case-insensitive)

### Step 2: Batch LLM analysis

For each batch of 5 projects (to avoid token limits), send this prompt to your LLM:

```
Analyze the following {N} GitHub Trending projects. Output strict JSON array.
Each project needs 4 fields:
- what: What it is (≤30 Chinese characters)
- analogy: Life analogy (one sentence)
- help: What it helps you do (2 items, each ≤40 chars, array)
- who: Who needs it (one sentence, ≤30 chars)

Project list:
1. org/repo (Language) — description...
2. ...

Output ONLY the JSON array, no other text. Example:
[{"name":"org/repo","what":"...","analogy":"...","help":["...","..."],"who":"..."}]
```

**Parse the response**:
1. Strip markdown code fences (` ```json ` / ` ``` `)
2. Clean trailing commas: `,\s*([\]}])` → `\1`
3. Extract the JSON array via regex: `\[.*\]` (DOTALL)
4. Decode with `json.loads()` or equivalent
5. Match results back to projects by name suffix (case-insensitive)

**Fallback**: If array parsing fails, extract individual objects via bracket-counting and parse one by one.

**Deep mode** (optional): Use longer limits (what ≤50 chars, help 3 items) for richer analysis.

### Step 3: Theme classification

Load the bundled `theme_rules.json`. For each project:
1. Concatenate `name + " " + desc` and lowercase
2. Iterate themes by priority order
3. Check if any keyword from the theme appears in the text
4. Assign to first matching theme
5. Default to "🌐 其他" if no match

Result: `{theme_name: [projects...]}` dictionary.

### Step 4: Compute diff (optional)

Load `memory.json` from the workspace root (see Output Protocol). Schema:
```json
[
  {
    "date": "2026-06-19",
    "since": "weekly",
    "lang": "python",
    "repos": [{"name":"...", "url":"...", "desc":"...", "lang":"...", "stars":..., "today_stars":..., "analysis":{...}}]
  }
]
```

Compare current repos against the latest entry with the same `since` (and same `lang` filter):
- **new**: projects in current but not in last
- **hot**: projects in both
- **dropped**: projects in last but not in current
- **last_date**: baseline timestamp

### Step 5: Generate reports

Two report modes, driven by the bundled templates:

- **Brief (default)**: `report_template_brief.md` — stops at "💡 Trend Analysis". Always emitted.
- **Detailed (opt-in)**: `report_template_detailed.md` — the brief content plus a per-project "📋 Project Details" section with the 4-field analysis. Emitted only when the user asks for detail (or when `deep` analysis was run).

**Trend insight prompt** (used in the "Trend Analysis" section of both modes):
```
基于以下GitHub Trending项目摘要，用3-5句话分析当前最强技术趋势和驱动力：
{list of "name: what" for all projects}
```

Save under `reports/YYYY-MM-DD/` with a `{since}` suffix (`daily` / `weekly` / `monthly`), e.g. `trending_briefing_weekly.md`. Same-day re-runs of the same `since`+`lang` overwrite that report.

**Empty tables**: when a section (new/hot/dropped) has no rows, render the table header followed by a single `*none*` row; keep "Theme Breakdown" and "Trend Analysis" only if there are classified projects. On a first run (no memory baseline), omit the "Dropped Off" section rather than showing it empty.

## Constraints

### Core rules

1. **Batch size = 5** for LLM calls to avoid truncation. For 20 repos, make 4 separate calls.
2. **JSON-only LLM output**. The prompt explicitly forbids explanatory text. Parse defensively (strip fences, clean commas).
3. **Name matching is fuzzy**. Match by suffix (`org/repo` vs `repo`) and case-insensitive substring.
4. **Theme priority matters**. A project matching both "AI" and "Dev Tools" gets classified as "AI" (priority 1 < 4).
5. **Memory and daily repo JSON are upserted, not blindly overwritten or appended.** Key is `(date, since, lang)`. Same-key re-runs merge; other keys are added. Retain the 30 most recent distinct dates.

### Incremental modes (optional)

- **Gap-fill mode**: Load the matching memory entry (same `date`+`since`+`lang`, else latest with same `since`+`lang`) → detect repos without `analysis` → re-run LLM only for those → merge back into both `memory.json` and `repos/YYYY-MM-DD_repos.json` → regenerate reports.
- **Selective re-analysis**: User specifies project names (comma-separated, partial match) → find matching repos in memory → re-run LLM with optional deep mode → merge into memory and the day's repos JSON → regenerate reports.

Implementation hint: `detect_gaps(repos)` returns `[r for r in repos if not r.get('analysis')]`.

### Error handling

- **HTML fetch fails**: Retry once with 5s delay, then abort with clear error message.
- **LLM returns non-JSON**: Log warning, continue with raw description as fallback for that batch.
- **Memory file missing**: Treat as first run (no diff section in reports).

## Output Protocol

Write all artifacts under the **current working directory** (the consuming workspace). Never write into the skill package.

```
<cwd>/
├── repos/YYYY-MM-DD_repos.json
├── reports/YYYY-MM-DD/trending_briefing_{since}[_{lang}].md
├── reports/YYYY-MM-DD/trending_detailed_{since}[_{lang}].md   # opt-in
└── memory.json
```

`{since}` is `daily` | `weekly` | `monthly`. Append `_{lang}` only when a language filter was used (`python`, `go`, …). Date lives in the reports folder — do not repeat it in the report filename.

Create `repos/` and `reports/YYYY-MM-DD/` if missing. Same-day re-runs of the same `since`+`lang` overwrite that report file.

### `repos/YYYY-MM-DD_repos.json`

Day-level crawl cache. Incremental merge on every run:

```json
{
  "date": "2026-08-19",
  "updated_at": "2026-08-19T16:45:00+08:00",
  "snapshots": [
    {
      "since": "daily",
      "lang": "",
      "fetched_at": "2026-08-19T16:45:00+08:00",
      "repos": [{"name":"...","url":"...","desc":"...","lang":"...","stars":0,"today_stars":0,"analysis":{}}]
    }
  ]
}
```

Merge rules:
1. Load the file if it exists; otherwise start `{date, updated_at, snapshots: []}`.
2. Upsert the snapshot whose `(since, lang)` matches this run (`lang` is `""` when unfiltered).
3. Matching repos (case-insensitive `name`): overwrite crawl fields (`url`, `desc`, `lang`, `stars`, `today_stars`); keep existing `analysis` unless this run produced a new one.
4. Repos only in the new fetch are appended; repos only in the old snapshot are kept (a later `since` on the same day must not wipe another window).
5. Write atomically (temp file in the same directory, then replace).

### `memory.json`

Workspace-root history used by Step 4 diffs and gap-fill. Incremental merge:

1. Load the array if the file exists; missing or empty → first run (no diff / no Dropped Off).
2. Upsert by `(date, since, lang)`. Same key: apply the same per-repo merge as the day cache. New key: append.
3. After upsert, keep entries whose `date` is among the 30 most recent distinct dates (so one day with daily+weekly+monthly does not evict history).
4. Write atomically.

### Reports

1. **Brief (default)** (`reports/{date}/trending_briefing_{since}[_{lang}].md`): new/hot/dropped/themes + trend insight. Stops at "Trend Analysis" — no per-project blocks.
2. **Detailed (opt-in)** (`reports/{date}/trending_detailed_{since}[_{lang}].md`): brief content followed by one "📋 Project Details" block per project with the 4-field analysis. Only when the user requests detail.

**Console output** during execution:
- "Fetching {since} trending..." → "Got {N} projects"
- "LLM batch {i}/{total}..." → "✅ Batch complete: {n} items"
- "💾 Repos merged: {path}"
- "💾 Memory merged: {path}"
- "📄 Brief saved: {path}"
- "📄 Detailed saved: {path}" (only when detailed mode runs)
- (Gap-fill) "Coverage: {covered}/{total} ({pct}%)"

## Validation

Before emitting reports, confirm:

- All repos have `name`, `url`, `desc`, `lang`, `stars`, `today_stars` fields.
- At least one theme contains projects (not all "其他").
- LLM analysis covers ≥50% of projects (log warning if lower).
- Emitted report files are valid UTF-8 Markdown at the paths above.
- `YYYY-MM-DD_repos.json` and `memory.json` reload without error after the merge.

## Adapting and Extending

### Custom themes

Edit the bundled `theme_rules.json`:
- Add new themes with emoji prefix and priority
- Extend keyword lists for existing themes
- Adjust priority order to prefer certain classifications

### Alternative LLM schemas

The 4-field schema (what/analogy/help/who) is optimized for Chinese tech audiences. Adapt for other contexts:
- **English reports**: Change field names and prompt language
- **Different insights**: Replace "analogy" with "use cases" or "risks"
- **Richer detail**: Increase char limits in deep mode

### Different trending sources

The HTML parsing patterns are GitHub-specific. To adapt for other platforms (Hacker News, Product Hunt):
- Replace Step 1 fetch logic
- Adjust regex patterns for that site's DOM structure
- Keep Steps 2-5 unchanged (LLM + themes + diff + reports)

### Memory backends

The reference uses local JSON. For multi-agent or cloud deployments:
- Swap `load_memory()` / `save_memory()` with a DB or object storage client
- Maintain the same list-of-dicts schema
- Add concurrency locks if multiple agents run in parallel
