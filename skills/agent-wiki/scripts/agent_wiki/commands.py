"""CLI subcommand implementations."""

from __future__ import annotations

import json
import os
import stat
import sys
from datetime import date
from pathlib import Path

from . import bases, cache, cleanup, config, frontmatter, scanner, wiki_index


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def fail(payload: dict, code: int = 1) -> None:
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def _vault(args) -> Path:
    return config.resolve_vault(getattr(args, "vault", None))


def _parse_topics(value: str | None) -> list[str]:
    if not value:
        return []
    return [config.normalize_relpath(part) for part in (item.strip() for item in value.split(",")) if part]


def _writable_mode(path: Path) -> bool:
    return not path.exists() or bool(path.stat().st_mode & stat.S_IWRITE)


def _ensure_wiki_writable(vault: Path) -> None:
    root = config.wiki_root(vault)
    parent = root if root.exists() else vault
    if not _writable_mode(parent):
        fail({"error": "wiki_not_writable"}, 1)
    for path in (root, root / "index.md", root / "log.md", config.cache_path(vault)):
        if not _writable_mode(path):
            fail({"error": "wiki_not_writable"}, 1)


def cmd_init(args) -> None:
    vault = _vault(args)
    _ensure_wiki_writable(vault)
    root = config.wiki_root(vault)
    existed = root.exists()
    created: list[str] = []

    root.mkdir(parents=True, exist_ok=True)
    for directory in (config.topics_dir(vault), config.archive_dir(vault), config.url_cache_dir(vault)):
        if not directory.exists():
            directory.mkdir(parents=True)
            created.append(config.to_rel_posix(directory, vault))

    index = root / "index.md"
    if not index.exists():
        index.write_text("# Wiki Index\n\n", encoding="utf-8")
        created.append(config.to_rel_posix(index, vault))

    log = root / "log.md"
    if not log.exists():
        log.write_text(f"# Wiki Log\n\n## [{date.today().isoformat()}] init | wiki created\n", encoding="utf-8")
        created.append(config.to_rel_posix(log, vault))

    cache_file = config.cache_path(vault)
    if not cache_file.exists():
        cache.save(vault, cache.empty_schema())
        created.append(config.to_rel_posix(cache_file, vault))

    index_file = config.index_path(vault)
    if not index_file.exists():
        wiki_index.save_index(vault, wiki_index.empty_schema())
        created.append(config.to_rel_posix(index_file, vault))

    emit({"status": "already_initialized" if existed else "ok", "created": created})


def cmd_scan(args) -> None:
    vault = _vault(args)
    classified = scanner.classify(vault, cache.load(vault))
    report = scanner.format_report(classified, vault)
    if "error" in report:
        fail(report, 1)
    emit(report)


def cmd_cache_get(args) -> None:
    vault = _vault(args)
    rel = config.normalize_relpath(args.path)
    entry = cache.load(vault).get("sources", {}).get(rel)
    if not entry:
        emit({"path": rel, "status": "absent"})
        return
    payload = {"path": rel}
    payload.update(entry)
    emit(payload)


def cmd_cache_put(args) -> None:
    vault = _vault(args)
    rel = config.normalize_relpath(args.path)
    source = config.source_path(vault, rel)
    if not source.is_file():
        fail({"error": "source not found", "path": rel}, 1)

    data, signature = cache.load_with_signature(vault)
    before = cache.stat_signature(source)
    sha = cache.sha256_file(source)
    after = cache.stat_signature(source)
    if before != after:
        fail({"error": "source_changed_during_hash", "path": rel}, 1)

    cache.upsert(data, rel, sha, after[0], after[1], _parse_topics(args.topics))
    try:
        cache.save(vault, data, expected_signature=signature)
    except cache.CacheNotWritableError:
        fail({"error": "cache_not_writable"}, 1)
    except cache.CacheConflictError:
        fail({"error": "cache_conflict", "path": rel}, 1)
    except cache.CacheReplaceError:
        fail({"error": "cache_replace_failed"}, 1)
    emit({"ok": True, "path": rel, "sha256": sha})


def _append_log(vault: Path, action: str, path: str) -> None:
    log = config.wiki_root(vault) / "log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"## [{date.today().isoformat()}] cleanup | {action} | {path}\n")


def cmd_cleanup(args) -> None:
    vault = _vault(args)
    data, signature = cache.load_with_signature(vault)
    sources = data.get("sources", {})
    removed = 0
    archived = 0
    details: list[dict] = []
    errors: list[dict] = []

    for rel, entry in list(sources.items()):
        source = config.source_path(vault, rel)
        if source.exists():
            continue
        source_cleaned = True
        for topic_rel in entry.get("derived_topics", []):
            topic = config.topics_dir(vault) / config.normalize_relpath(topic_rel)
            if not topic.exists():
                continue
            try:
                has_sources = cleanup.remove_source_from_topic(topic, rel)
                if has_sources:
                    details.append({"action": "removed_source", "path": config.normalize_relpath(topic_rel), "source": rel})
                    _append_log(vault, "removed_source", config.normalize_relpath(topic_rel))
                else:
                    archived_path = cleanup.archive_topic(topic, config.archive_dir(vault), date.today())
                    archived += 1
                    archived_rel = config.to_rel_posix(archived_path, vault)
                    details.append({"action": "archived", "path": archived_rel, "source": rel})
                    _append_log(vault, "archived", archived_rel)
            except cleanup.TopicError as exc:
                source_cleaned = False
                errors.append({"path": config.normalize_relpath(topic_rel), "error": exc.code})
            except OSError:
                source_cleaned = False
                errors.append({"path": config.normalize_relpath(topic_rel), "error": "topic_update_failed"})
        if source_cleaned:
            cache.remove(data, rel)
            removed += 1
    cache.save(vault, data, expected_signature=signature)
    emit({"removed": removed, "archived": archived, "details": details, "errors": errors})


def _topic_meta(path: Path) -> tuple[dict, str] | None:
    try:
        return frontmatter.parse(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, frontmatter.FrontmatterError):
        return None


def _rebuild_index(vault: Path) -> tuple[dict, list[dict]]:
    try:
        data, errors = wiki_index.rebuild(vault)
    except wiki_index.NormalizedPathCollision as exc:
        fail({"error": "normalized_path_collision", "path": exc.path}, 1)
    try:
        wiki_index.save_index(vault, data)
    except wiki_index.IndexWriteError:
        fail({"error": "index_write_failed"}, 1)
    return data, errors


def _index_stale(vault: Path, index_file: Path) -> bool:
    if not index_file.exists():
        return True
    index_mtime = index_file.stat().st_mtime_ns
    topics_root = config.topics_dir(vault)
    if not topics_root.exists():
        return False
    return any(topic.stat().st_mtime_ns > index_mtime for topic in topics_root.glob("*.md"))


def cmd_index(args) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)
    data, errors = _rebuild_index(vault)
    emit({"ok": True, "topics": len(data["topics"]), "errors": errors})


def cmd_status(args) -> None:
    vault = _vault(args)
    data = cache.load(vault)
    topics_root = config.topics_dir(vault)
    archive_root = config.archive_dir(vault)
    topics = list(topics_root.glob("*.md")) if topics_root.exists() else []
    archived_topics = list(archive_root.glob("**/*.md")) if archive_root.exists() else []
    errors = []
    orphaned = 0

    for topic in topics:
        parsed = _topic_meta(topic)
        if parsed is None:
            errors.append({"path": config.to_rel_posix(topic, vault), "error": "frontmatter_parse_failed"})
            continue
        meta, _ = parsed
        if meta.get("sources") == []:
            orphaned += 1

    log = config.wiki_root(vault) / "log.md"
    last_log = ""
    if log.exists():
        lines = [line.strip() for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        last_log = lines[-1] if lines else ""

    index_file = config.index_path(vault)
    index_exists = index_file.exists()
    index_topics = 0
    if index_exists:
        try:
            raw_index = json.loads(index_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            raw_index = None
        if isinstance(raw_index, dict) and isinstance(raw_index.get("topics"), dict):
            index_topics = len(raw_index["topics"])
    try:
        _index_data, index_errors = wiki_index.rebuild(vault)
    except wiki_index.NormalizedPathCollision as exc:
        index_errors = [{"path": exc.path, "error": "normalized_path_collision"}]

    cache_file = config.cache_path(vault)
    emit({
        "vault": str(vault),
        "sources_tracked": len(data.get("sources", {})),
        "topics_total": len(topics),
        "topics_orphaned": orphaned,
        "topics_archived": len(archived_topics),
        "cache_size_bytes": cache_file.stat().st_size if cache_file.exists() else 0,
        "last_log_entry": last_log,
        "errors": errors,
        "index_exists": index_exists,
        "index_size_bytes": index_file.stat().st_size if index_exists else 0,
        "index_topics": index_topics,
        "index_stale": _index_stale(vault, index_file),
        "index_errors": index_errors,
    })


def cmd_gen_base(args) -> None:
    vault = _vault(args)
    root = config.wiki_root(vault)
    if not root.exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)
    _rebuild_index(vault)
    prefix = bases.obsidian_prefix(vault)
    name = Path(args.name).name or "sources.base"
    if not name.endswith(".base"):
        name += ".base"
    targets = [
        (root / "index.base", bases.build_index_base(prefix)),
        (vault / name, bases.build_master_base(prefix)),
    ]
    for path, _content in targets:
        if not _writable_mode(path):
            fail({"error": "base_not_writable", "path": config.to_rel_posix(path, vault)}, 1)
    written: list[str] = []
    for path, content in targets:
        path.write_text(content, encoding="utf-8")
        written.append(config.to_rel_posix(path, vault))
    emit({"ok": True, "prefix": prefix, "written": written})
