# Topic Authoring Reference

Loaded on demand from SKILL.md. Covers the topic `type` taxonomy, per-type section
templates, and authoring conventions.

## Type Field (Page Kind)

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

## Lead Sentence Rule (定位句)

**Every topic body MUST open with a single positioning sentence** (定位句) before the first `##` heading:
- Concisely states what/who/where the topic is
- No heading, no list, no quote block — plain paragraph
- Example: `量子叠加原理是量子力学的核心原理，描述量子态可以同时处于多个本征态的线性组合。`

The CLI computes a read-only `has_lead` metric (quality metrics) but **never authors prose**.

## Per-Type Section Templates

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

## Conflict/Contradiction Convention

When source notes **disagree on a fact** (different values, contradictory claims):
- **Do NOT silently pick one** — record the disagreement
- Create a dedicated `## ⚠️ 矛盾` (conflict) section listing each variant with its source
- Example:
  ```markdown
  ## ⚠️ 矛盾

  - 来源 A.md 称实验于 1926 年完成
  - 来源 B.md 称实验于 1927 年完成
  ```

## Quality Metrics Detail

Metrics computed from the markdown body (all read-only):
- `sections`: count of level-2 to level-6 ATX headings (`##` to `######`), excluding level-1 title
- `evidence_lines`: count of blockquote lines (starting with `> `)
- `prose_weight`: script-aware prose measure combining CJK ideographs and Latin words
  - CJK characters (East Asian Width W/F, Unicode category L/N): weighted ×10
  - Latin/other word runs: weighted ×16
  - Ratio calibrated so equivalent-information content in CJK and Latin tier equally
- `cjk_chars`, `latin_words`: component counts (transparency)
- `prose_chars`: raw NFC character count (retained for transparency)
- `has_image`: boolean, true if body contains Obsidian (`![[image.ext]]`) or Markdown (`![](url)`) image embeds
- `has_lead`: boolean, true if first non-blank line after optional level-1 heading is a paragraph (not heading/list/quote/table/image-only)

Tiers are **monotonic** in all dimensions (adding prose, sections, evidence, images, or
sources never lowers tier). The formula is **deterministic** and **script-fair**: CJK and
Latin content of equivalent information density receive the same tier.
