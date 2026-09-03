"""Source file scanning and classification."""

from __future__ import annotations

import fnmatch
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from . import cache as cache_mod
from . import config

EXCLUDED_DIRS = {"wiki", ".obsidian", "attachments", ".git", ".trash"}


def _ignore_patterns(vault: Path) -> list[str]:
    ignore = vault / ".wikiignore"
    if not ignore.exists():
        return []
    return [line.strip() for line in ignore.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]


def _ignored(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel + "/", pattern) for pattern in patterns)


def _excluded(rel: str, patterns: list[str]) -> bool:
    parts = rel.split("/")
    return any(part in EXCLUDED_DIRS for part in parts) or _ignored(rel, patterns)


def _collect_sources(vault: str | Path) -> tuple[list[Path], list[dict[str, str]]]:
    root = Path(vault).resolve()
    patterns = _ignore_patterns(root)
    found: list[Path] = []
    skipped: list[dict[str, str]] = []
    for path in root.rglob("*.md"):
        rel = config.to_rel_posix(path, root)
        if _excluded(rel, patterns):
            continue
        if path.is_symlink():
            skipped.append({"path": rel, "error": "skipped_symlink"})
            continue
        found.append(path)
    found.sort(key=lambda p: config.to_rel_posix(p, root))
    skipped.sort(key=lambda item: item["path"])
    return found, skipped


def walk_sources(vault: str | Path) -> Iterator[Path]:
    yield from _collect_sources(vault)[0]


def _item(path: Path, vault: Path, derived_topics: list[str] | None = None, *, cached_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    st = path.stat()
    mtime_ns, size = st.st_mtime_ns, st.st_size

    if cached_entry is not None:
        cached_mtime_ns = cached_entry.get("mtime_ns")
        cached_size = cached_entry.get("size")
        if cached_mtime_ns is not None and cached_mtime_ns == mtime_ns and cached_size == size:
            return {
                "path": config.to_rel_posix(path, vault),
                "size": size,
                "mtime_ns": mtime_ns,
                "derived_topics": derived_topics or [],
                "signature_match": True,
            }

    sha256 = cache_mod.sha256_file(path)
    return {
        "path": config.to_rel_posix(path, vault),
        "sha256": sha256,
        "size": size,
        "mtime_ns": mtime_ns,
        "derived_topics": derived_topics or [],
    }


def classify(vault: str | Path, cache_data: dict[str, Any], *, collect: Callable[[Path], tuple[list[Path], list[dict[str, str]]]] | None = None) -> dict[str, Any]:
    root = Path(vault).resolve()
    sources = cache_data.get("sources", {})
    result: dict[str, Any] = {"new": [], "modified": [], "unchanged": [], "deleted": [], "errors": [], "skipped_symlinks": []}

    if collect is None:
        source_paths, skipped = _collect_sources(root)
    else:
        source_paths, skipped = collect(root)
    result["skipped_symlinks"] = skipped
    result["errors"].extend(skipped)

    current_paths: dict[str, Path] = {}
    for path in source_paths:
        rel = config.to_rel_posix(path, root)
        if rel in current_paths:
            result["fatal"] = {"error": "normalized_path_collision", "path": rel}
            result["new"] = []
            result["modified"] = []
            result["unchanged"] = []
            result["deleted"] = []
            return result
        current_paths[rel] = path

    for rel, path in current_paths.items():
        cached = sources.get(rel)
        try:
            item = _item(path, root, cached.get("derived_topics", []) if cached else [], cached_entry=cached)
        except OSError:
            result["errors"].append({"path": rel, "error": "unreadable"})
            continue
        if cached is None:
            result["new"].append(item)
        elif item.get("signature_match"):
            result["unchanged"].append(item)
        elif item["sha256"] != cached.get("sha256"):
            result["modified"].append(item)
        else:
            result["unchanged"].append(item)

    for rel, cached in sorted(sources.items()):
        normalized = config.normalize_relpath(rel)
        if normalized not in current_paths:
            result["deleted"].append({"path": normalized, "derived_topics": cached.get("derived_topics", [])})
    return result


def format_report(classified: dict[str, Any], vault: str | Path) -> dict[str, Any]:
    if "fatal" in classified:
        fatal_value = classified["fatal"]
        if isinstance(fatal_value, dict):
            return fatal_value
        return {"error": str(fatal_value)}
    return {
        "version": 1,
        "vault": str(Path(vault).resolve()),
        "stats": {
            "total_sources": len(classified.get("new", [])) + len(classified.get("modified", [])) + len(classified.get("unchanged", [])),
            "new": len(classified.get("new", [])),
            "modified": len(classified.get("modified", [])),
            "unchanged": len(classified.get("unchanged", [])),
            "deleted": len(classified.get("deleted", [])),
            "skipped_symlinks": len(classified.get("skipped_symlinks", [])),
            "errors": len(classified.get("errors", [])),
        },
        "new": classified.get("new", []),
        "modified": classified.get("modified", []),
        "deleted": classified.get("deleted", []),
        "errors": classified.get("errors", []),
    }
