"""Generate Obsidian Bases (.base) files for the wiki.

Two deterministic files (the two-file output contract):
  * index.base   — topic overview plus per-dimension faceted table views
                   (authors, institutions, methods, source_type) read from
                   topic frontmatter over wiki/topics
  * <name>.base  — source master table (year parsed from a leading
                   "(YYYY...)" filename prefix, tags column from frontmatter)

Filter folder paths are Obsidian-vault-relative (the directory containing
``.obsidian``), discovered by walking up from the agent-wiki vault.
"""

from __future__ import annotations

from pathlib import Path

from . import config


def obsidian_prefix(vault: str | Path) -> str:
    """Folder path from the Obsidian vault root (dir holding ``.obsidian``) down
    to ``vault``, POSIX-style. Empty when ``vault`` is itself the root or no
    vault is found above it."""
    vault = Path(vault).expanduser().resolve()
    current = vault
    while True:
        if (current / ".obsidian").is_dir():
            rel = vault.relative_to(current).as_posix()
            return "" if rel == "." else config.normalize_relpath(rel)
        if current.parent == current:
            return ""
        current = current.parent


def _folder(prefix: str, *parts: str) -> str:
    segments = [prefix, *parts] if prefix else list(parts)
    return "/".join(seg for seg in segments if seg)


def build_index_base(prefix: str = "") -> str:
    topics = _folder(prefix, "wiki", "topics")
    return f"""filters:
  and:
    - file.inFolder("{topics}")
    - file.ext == "md"
formulas:
  source_count: if(sources, sources.length, 0)
properties:
  file.basename:
    displayName: 主题
  formula.source_count:
    displayName: 来源数
  last_updated:
    displayName: 更新日期
  year_start:
    displayName: 起始年
  year_end:
    displayName: 截止年
  authors:
    displayName: 作者
  institutions:
    displayName: 机构
  methods:
    displayName: 方法
  source_type:
    displayName: 来源类型
  featured:
    displayName: 精选
views:
  - type: table
    name: 主题总览
    order:
      - file.basename
      - formula.source_count
      - last_updated
    summaries:
      formula.source_count: Sum
    columnSize:
      file.basename: 360
  - type: table
    name: 精选
    filters:
      and:
        - featured == true
    order:
      - file.basename
      - formula.source_count
      - last_updated
  - type: table
    name: 按作者
    order:
      - authors
      - file.basename
      - source_type
  - type: table
    name: 按机构
    order:
      - institutions
      - file.basename
      - source_type
  - type: table
    name: 按方法
    order:
      - methods
      - file.basename
      - source_type
  - type: table
    name: 按来源类型
    order:
      - source_type
      - file.basename
      - authors
  - type: table
    name: 按年份
    order:
      - year_start
      - year_end
      - file.basename
      - source_type
  - type: cards
    name: 卡片视图
    order:
      - file.basename
      - formula.source_count
      - last_updated
"""


def build_master_base(prefix: str = "") -> str:
    include = f'    - file.inFolder("{prefix}")\n' if prefix else ""
    wiki = _folder(prefix, "wiki")
    return f"""filters:
  and:
{include}    - file.ext == "md"
    - not:
        - file.inFolder("{wiki}")
formulas:
  year: 'file.basename.split("(").slice(1, 2).join("").slice(0, 4)'
properties:
  file.basename:
    displayName: 文献
  formula.year:
    displayName: 年份
  tags:
    displayName: 标签
views:
  - type: table
    name: 全部文献
    order:
      - formula.year
      - file.basename
      - tags
    columnSize:
      file.basename: 640
  - type: cards
    name: 卡片
    order:
      - file.basename
      - formula.year
      - tags
"""
