"""Vault health diagnostics (``doctor`` subcommand)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config, frontmatter, wiki_index


def _check(name: str, status: str, detail: str = "") -> dict[str, str]:
    if detail:
        return {"name": name, "status": status, "detail": detail}
    return {"name": name, "status": status}


def _topic_meta(path: Path) -> tuple[dict[str, Any], str] | None:
    try:
        return frontmatter.parse(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, OSError, frontmatter.FrontmatterError):
        return None


def run(vault: str | Path) -> dict[str, Any]:
    """Run health checks. Returns ``{ok, checks, summary}`` where ``ok`` is
    False when any check has ``error`` status (``warn`` does not fail)."""
    vault_path = Path(vault).resolve()
    checks: list[dict[str, str]] = []

    root = config.wiki_root(vault_path)
    if not root.exists():
        return {
            "ok": False,
            "checks": [_check("wiki_initialized", "error", "wiki/ missing — run init")],
            "summary": "1 problem",
        }
    checks.append(_check("wiki_initialized", "ok"))

    # Topics: parse failures and orphans (no sources)
    topics_dir = config.topics_dir(vault_path)
    topics = list(topics_dir.glob("*.md")) if topics_dir.exists() else []
    unreadable = 0
    orphans = 0
    for topic in topics:
        parsed = _topic_meta(topic)
        if parsed is None:
            unreadable += 1
            continue
        meta, _body = parsed
        if meta.get("sources") in (None, []):
            orphans += 1
    checks.append(_check("topics", "ok" if unreadable == 0 else "error",
                         f"{len(topics)} topics, {unreadable} unreadable"
                         if unreadable else f"{len(topics)} topics"))
    checks.append(_check("orphan_topics", "ok" if orphans == 0 else "warn",
                         f"{orphans} topics without sources" if orphans else ""))

    # Index: exists, parses, matches current files, no rebuild errors
    index = config.index_path(vault_path)
    if not index.exists():
        checks.append(_check("index", "error", "wiki/.wiki-index.json missing — run index"))
    else:
        try:
            raw_index = json.loads(index.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            raw_index = None
        if not isinstance(raw_index, dict):
            checks.append(_check("index", "error", "corrupted or non-object JSON — run index"))
        else:
            checks.append(_check("index", "ok"))
            try:
                _data, errors = wiki_index.rebuild(vault_path)
            except wiki_index.NormalizedPathCollisionError as exc:
                errors = [{"path": exc.path, "error": "normalized_path_collision"}]
                _data = {}
            checks.append(_check("index_consistent", "ok" if not errors else "error",
                                 f"{len(errors)} errors: {errors[:3]}" if errors else ""))
            # Fresh = the on-disk index content matches a fresh rebuild. Covers
            # topic/query deletion, query/alias edits — not just topic mtime.
            stale = (
                raw_index.get("topics") != _data.get("topics")
                or raw_index.get("queries") != _data.get("queries")
                or raw_index.get("alias_index") != _data.get("alias_index")
            )
            checks.append(_check("index_fresh", "ok" if not stale else "warn",
                                 "index out of date — run index" if stale else ""))

    # Cache: parses, and every tracked source still exists (no cache yet is a normal pre-scan state)
    cache_file = config.cache_path(vault_path)
    if not cache_file.exists():
        checks.append(_check("cache", "ok", "no cache file yet"))
    else:
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            data = None
        if not isinstance(data, dict):
            checks.append(_check("cache", "error", "corrupted or non-object JSON"))
        else:
            checks.append(_check("cache", "ok"))
            sources = data.get("sources", {})
            if not isinstance(sources, dict):
                checks.append(_check("cache_sources", "error", "sources is not an object"))
            else:
                missing = 0
                for rel in sources:
                    try:
                        if not config.source_path(vault_path, rel).exists():
                            missing += 1
                    except (ValueError, OSError):
                        missing += 1
                checks.append(_check("cache_sources", "ok" if missing == 0 else "warn",
                                     f"{missing} missing or invalid source paths — run cleanup" if missing else ""))

    problems = sum(1 for check in checks if check["status"] == "error")
    summary = f"{problems} problem{'s' if problems != 1 else ''}" if problems else "healthy"
    return {"ok": problems == 0, "checks": checks, "summary": summary}
