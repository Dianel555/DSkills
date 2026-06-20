---
name: GitHub Trending Analyzer
description: Crawl GitHub trending repositories, analyze with LLM for Chinese insights, categorize by themes, compute diffs against history, and generate briefing plus detailed reports in Markdown. Supports incremental gap-filling and selective re-analysis with caching.
---

# GitHub Trending Analyzer

A workflow protocol for tracking GitHub trending repositories with LLM-powered analysis. Fetches trending projects, enriches each with structured Chinese insights (what/analogy/help/who), classifies by themes, compares against historical snapshots, and generates dual-format reports (briefing + detailed).

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

If you maintain a memory cache (JSON file storing past runs):
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

Compare current repos against the latest entry with the same `since` value:
- **new**: projects in current but not in last
- **hot**: projects in both
- **dropped**: projects in last but not in current
- **last_date**: baseline timestamp

### Step 5: Generate reports

#### Briefing (compact, for quick scan)

Structure:
```markdown
# GitHub 热门趋势简报 - {date}

> 生成日期: {date}
> 来源: github.com/trending?since={since}
> 对比基准: {baseline_date}

## 🔥 新上榜
| 排名 | 项目 | 语言 | ⭐ Stars | 📈 今日新增 | 一句话说明 |

## ⭐ 持续热门
| 项目 | 语言 | ⭐ Stars | 📈 今日新增 | 为什么值得关注 |

## 📉 掉出榜单
| 项目 | 可能意味着什么 |

## 🎯 趋势主题
**{theme}** (N个): repo1(+stars), repo2(+stars), ...

## 💡 趋势解读
{LLM-generated trend insight based on all "what" summaries}
```

**Trend insight prompt**:
```
基于以下GitHub Trending项目摘要，用3-5句话分析当前最强技术趋势和驱动力：
{list of "name: what" for all projects}
```

#### Detailed (one section per project)

Structure:
```markdown
# GitHub 详细分析 - {date}

## {Project Name}

**Stars**: {total} (+{increment})  
**Language**: {lang}  
**URL**: {github_url}

### 这是什么
{analysis.what}

### 生活化类比
{analysis.analogy}

### 它能帮你做什么
1. {analysis.help[0]}
2. {analysis.help[1]}

### 谁需要它
{analysis.who}

---
```

Save both to files with date-stamped names (e.g. `trending_briefing_2026-06-19.md`).

## Constraints

### Core rules

1. **Batch size = 5** for LLM calls to avoid truncation. For 20 repos, make 4 separate calls.
2. **JSON-only LLM output**. The prompt explicitly forbids explanatory text. Parse defensively (strip fences, clean commas).
3. **Name matching is fuzzy**. Match by suffix (`org/repo` vs `repo`) and case-insensitive substring.
4. **Theme priority matters**. A project matching both "AI" and "Dev Tools" gets classified as "AI" (priority 1 < 4).
5. **Memory is append-only list**. Each run appends one entry. Keep last 30 to prevent unbounded growth.

### Incremental modes (optional)

- **Gap-fill mode**: Load the latest memory entry → detect repos without `analysis` field → re-run LLM only for those → merge back → regenerate reports.
- **Selective re-analysis**: User specifies project names (comma-separated, partial match) → find matching repos in memory → re-run LLM with optional deep mode → update memory → regenerate reports.

Implementation hint: `detect_gaps(repos)` returns `[r for r in repos if not r.get('analysis')]`.

### Error handling

- **HTML fetch fails**: Retry once with 5s delay, then abort with clear error message.
- **LLM returns non-JSON**: Log warning, continue with raw description as fallback for that batch.
- **Memory file missing**: Treat as first run (no diff section in reports).

## Output Protocol

Emit two Markdown files to a reports directory:

1. **Briefing** (`trending_briefing_{date}.md`): 4 sections (new/hot/dropped/themes) + trend insight.
2. **Detailed** (`trending_detailed_{date}.md`): One block per project with 4-field analysis.

Overwrite if file exists (same-day re-runs replace prior reports).

**Console output** during execution:
- "Fetching {since} trending..." → "Got {N} projects"
- "LLM batch {i}/{total}..." → "✅ Batch complete: {n} items"
- "📄 Briefing saved: {path}"
- "📄 Detailed saved: {path}"
- (Gap-fill) "Coverage: {covered}/{total} ({pct}%)"

## Validation

Before emitting reports, confirm:

- All repos have `name`, `url`, `desc`, `lang`, `stars`, `today_stars` fields.
- At least one theme contains projects (not all "其他").
- LLM analysis covers ≥50% of projects (log warning if lower).
- Both report files are valid UTF-8 Markdown.
- Memory JSON is valid (can be reloaded without error).

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
