"""CLI subcommand implementations."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, NoReturn

from . import (
    authors,
    bases,
    batch,
    boundary,
    cache,
    canvas,
    cleanup,
    config,
    coverage,
    frontmatter,
    home,
    keywords,
    plugins,
    quality,
    scanner,
    site,
    source_type,
    wiki_index,
    worklist,
)
from .boundary import BoundaryError


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def fail(payload: dict[str, Any], code: int = 1) -> NoReturn:
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def verbose(args: argparse.Namespace, message: str) -> None:
    """Print progress message to stderr if --verbose flag is set."""
    if getattr(args, "verbose", False):
        print(f"[agent-wiki] {message}", file=sys.stderr)


def _vault(args: argparse.Namespace) -> Path:
    return config.resolve_vault(getattr(args, "vault", None))


def _parse_topics(value: str | None) -> list[str]:
    if not value:
        return []
    return [config.normalize_relpath(part) for part in (item.strip() for item in value.split(",")) if part]


def _writable_mode(path: Path) -> bool:
    try:
        st = boundary.stat(path)
    except BoundaryError:
        return False
    return st is None or bool(st.st_mode & stat.S_IWRITE)


def _ensure_wiki_writable(vault: Path) -> None:
    root = config.wiki_root(vault)
    parent = root if root.exists() else vault
    if not _writable_mode(parent):
        fail({"error": "wiki_not_writable"}, 1)
    for path in (root, root / "index.md", root / "log.md", config.cache_path(vault)):
        if not _writable_mode(path):
            fail({"error": "wiki_not_writable"}, 1)


def cmd_init(args: argparse.Namespace) -> None:
    vault = _vault(args)
    _ensure_wiki_writable(vault)
    root = config.wiki_root(vault)
    existed = root.exists()
    created: list[str] = []

    root.mkdir(parents=True, exist_ok=True)
    for directory in (
        config.topics_dir(vault),
        config.archive_dir(vault),
        config.queries_dir(vault),
        config.graphs_dir(vault),
    ):
        if not boundary.exists(directory):
            boundary.ensure_directory(directory)
            created.append(config.to_rel_posix(directory, vault))

    index = root / "index.md"
    if not boundary.exists(index):
        boundary.write_text(index, "# Wiki Index\n\n")
        created.append(config.to_rel_posix(index, vault))

    log = root / "log.md"
    if not boundary.exists(log):
        boundary.write_text(
            log, f"# Wiki Log\n\n## [{date.today().isoformat()}] init | wiki created\n"
        )
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


def cmd_scan(args: argparse.Namespace) -> None:
    vault = _vault(args)
    verbose(args, f"Scanning vault: {vault}")
    classified = scanner.classify(vault, cache.load(vault))
    verbose(args, f"Found {len(classified.get('new', []))} new, {len(classified.get('modified', []))} modified, {len(classified.get('deleted', []))} deleted")
    report = scanner.format_report(classified, vault)
    if "error" in report:
        fail(report, 1)
    emit(report)


def cmd_plan(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)

    # Check for resume flag
    resume = getattr(args, "resume", False)
    existing_state = batch.load_state(vault)

    if resume:
        if not existing_state:
            fail({"error": "no_existing_plan", "hint": "no batch state to resume"}, 1)
        verbose(args, "Resuming existing batch plan...")
        state = existing_state
    else:
        if existing_state:
            verbose(args, "Overwriting existing batch plan...")
        size = args.batch_size
        if size <= 0:
            fail({"error": "invalid_batch_size", "batch_size": size}, 1)
        state = batch.build_plan(vault, size)
        batch.save_state(vault, state)

    batch.write_report(vault, state)
    emit({
        "ok": True,
        "total": state["total"],
        "batch_size": state["batch_size"],
        "report": state["report"],
        "resumed": resume,
        "batches": [
            {"id": item["id"], "status": item["status"], "count": len(item["items"]), "items": item["items"]}
            for item in state["batches"]
        ],
    })


def cmd_batch_done(args: argparse.Namespace) -> None:
    vault = _vault(args)
    state = batch.load_state(vault)
    if state is None:
        fail({"error": "no_batch_plan", "hint": "run plan first"}, 1)
    target = next((item for item in state["batches"] if item["id"] == args.batch), None)
    if target is None:
        fail({"error": "batch_not_found", "batch": args.batch}, 1)
    tracked = cache.load(vault).get("sources", {})
    missing = [item for item in target["items"] if not batch.is_ingested(vault, item, tracked)]
    if missing:
        fail({"error": "batch_incomplete", "batch": args.batch, "missing": missing}, 1)
    target["status"] = "done"
    batch.save_state(vault, state)
    batch.write_report(vault, state)
    remaining = [item["id"] for item in state["batches"] if item["status"] != "done"]
    emit({"ok": True, "batch": args.batch, "status": "done", "remaining": remaining, "complete": not remaining})


def cmd_extract_authors(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.topics_dir(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)
    emit({"ok": True, "topics": authors.extract(vault)})


def cmd_aggregate_authors(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.topics_dir(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)
    emit({"ok": True, "authors": authors.aggregate(authors.extract(vault))})


def cmd_cache_get(args: argparse.Namespace) -> None:
    vault = _vault(args)
    rel = config.normalize_relpath(args.path)
    entry = cache.load(vault).get("sources", {}).get(rel)
    if not entry:
        emit({"path": rel, "status": "absent"})
        return
    payload = {"path": rel}
    payload.update(entry)
    emit(payload)


def cmd_cache_put(args: argparse.Namespace) -> None:
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

    topics = _parse_topics(args.topics)
    for topic_rel in topics:
        try:
            config.topic_path(vault, topic_rel)
        except ValueError:
            fail({"error": "invalid_topic_path", "path": topic_rel}, 1)
    cache.upsert(data, rel, sha, after[0], after[1], topics)
    try:
        cache.save(vault, data, expected_signature=signature)
    except cache.CacheNotWritableError:
        fail({"error": "cache_not_writable"}, 1)
    except cache.CacheConflictError:
        fail({"error": "cache_conflict", "path": rel}, 1)
    except cache.CacheReplaceError:
        fail({"error": "cache_replace_failed"}, 1)
    emit({"ok": True, "path": rel, "sha256": sha})


def _append_log(vault: Path, category: str, action: str, path: str) -> None:
    log = config.wiki_root(vault) / "log.md"
    boundary.append_text(
        log, f"## [{date.today().isoformat()}] {category} | {action} | {path}\n"
    )


def _path_reachable(path: Path) -> bool:
    """True when ``path`` names an existing, non-link object."""
    try:
        with boundary.open_read(path):
            return True
    except FileNotFoundError:
        return False
    except boundary.BoundaryError as exc:
        return not exc.is_link  # a link is "absent" here; other refusals are present
    except OSError:
        return True  # unreadable is not deleted


def _path_is_link(path: Path) -> bool:
    try:
        boundary.open_read(path)
    except boundary.BoundaryError as exc:
        return exc.is_link
    except OSError:
        return False
    return False


def cmd_cleanup(args: argparse.Namespace) -> None:
    vault = _vault(args)
    data, signature = cache.load_with_signature(vault)
    sources = data.get("sources", {})
    removed = 0
    archived = 0
    details: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for rel, entry in list(sources.items()):
        source = config.source_path(vault, rel)
        if _path_reachable(source):
            continue
        if _path_is_link(source):
            # A link (dangling or external) is not a deleted source: pruning its
            # topics or archiving them on that basis could destroy real content.
            source_cleaned = False
            errors.append({"path": rel, "error": "skipped_link"})
            continue
        source_cleaned = True
        for topic_rel in entry.get("derived_topics", []):
            try:
                topic = config.topic_path(vault, topic_rel)
            except ValueError:
                source_cleaned = False
                errors.append({"path": config.normalize_relpath(topic_rel), "error": "invalid_topic_path"})
                continue
            if not topic.exists():
                continue
            try:
                has_sources = cleanup.remove_source_from_topic(topic, rel)
                if has_sources:
                    details.append({"action": "removed_source", "path": config.normalize_relpath(topic_rel), "source": rel})
                    _append_log(vault, "cleanup", "removed_source", config.normalize_relpath(topic_rel))
                else:
                    archived_path = cleanup.archive_topic(topic, config.archive_dir(vault), date.today())
                    archived += 1
                    archived_rel = config.to_rel_posix(archived_path, vault)
                    details.append({"action": "archived", "path": archived_rel, "source": rel})
                    _append_log(vault, "cleanup", "archived", archived_rel)
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


def _safe_md_name(value: str) -> str:
    """Sanitize a capture/topic name to a single ``<name>.md`` component."""
    safe = Path(config.normalize_relpath(value)).name
    return safe if safe.endswith(".md") else safe + ".md"


def _capture(args: argparse.Namespace, dir_func: Callable[[Path], Path], kind: str, action: str) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)
    directory = dir_func(vault)
    safe = _safe_md_name(args.name)
    target = directory / safe
    rel = config.normalize_relpath(f"{directory.name}/{safe}")
    if not target.is_file():
        fail({"error": "capture_not_found", "path": rel}, 1)
    try:
        meta, body = frontmatter.parse(boundary.read_text(target))
    except (UnicodeDecodeError, frontmatter.FrontmatterError, BoundaryError):
        fail({"error": "capture_parse_failed", "path": rel}, 1)
    if meta.get("kind") != kind:
        meta["kind"] = kind
        config.atomic_write_text(target, frontmatter.dump(meta, body))
    _append_log(vault, "capture", action, rel)
    emit({"ok": True, "path": rel, "kind": kind})


def cmd_save_report(args: argparse.Namespace) -> None:
    _capture(args, config.queries_dir, "query", "save_report")


def _rebuild_index(vault: Path, *, incremental: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        data, errors = wiki_index.rebuild(vault, incremental=incremental)
    except wiki_index.NormalizedPathCollisionError as exc:
        fail({"error": "normalized_path_collision", "path": exc.path}, 1)
    try:
        wiki_index.save_index(vault, data)
    except wiki_index.IndexWriteError:
        fail({"error": "index_write_failed"}, 1)
    return data, errors


def _index_stale(vault: Path, index_file: Path) -> bool:
    index_stat = boundary.stat(index_file)
    if index_stat is None:
        return True
    index_mtime = index_stat.st_mtime_ns
    for root in (config.topics_dir(vault), config.queries_dir(vault)):
        try:
            stale = any(
                (st := entry.stat()) is not None and st.st_mtime_ns > index_mtime
                for entry in boundary.entries(root, suffix=".md")
            )
        except BoundaryError:
            return True
        if stale:
            return True
    return False


def _graphs_stale(vault: Path) -> bool:
    topics = boundary.entries(config.topics_dir(vault), suffix=".md")
    if not topics:
        return False
    graphs_root = config.graphs_dir(vault)
    for topic in topics:
        graph = graphs_root / (topic.path.stem + ".canvas")
        graph_stat = boundary.stat(graph)
        if graph_stat is None or (
            (topic_stat := topic.stat()) is not None
            and topic_stat.st_mtime_ns > graph_stat.st_mtime_ns
        ):
            return True
    return False


def cmd_index(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)
    incremental = getattr(args, "incremental", False)
    verbose(args, f"Building index (incremental={incremental})...")
    data, errors = _rebuild_index(vault, incremental=incremental)
    verbose(args, f"Index built: {len(data['topics'])} topics, {len(errors)} errors")
    emit({"ok": True, "topics": len(data["topics"]), "errors": errors})


def cmd_normalize_source_type(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.topics_dir(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)
    result = source_type.backfill(vault)
    emit({"ok": True, **result})


def cmd_status(args: argparse.Namespace) -> None:
    vault = _vault(args)
    data = cache.load(vault)
    topics_root = config.topics_dir(vault)
    archive_root = config.archive_dir(vault)
    topics = [entry.path for entry in boundary.entries(topics_root, suffix=".md")]
    report_file = batch.report_path(vault)
    archived_topics = [
        entry.path
        for entry in boundary.walk(archive_root)
        if entry.path.suffix == ".md" and entry.path != report_file
    ]
    queries_root = config.queries_dir(vault)
    graphs_root = config.graphs_dir(vault)
    queries_total = len(boundary.entries(queries_root, suffix=".md"))
    graphs_count = len(boundary.entries(graphs_root, suffix=".canvas"))
    errors = []
    orphaned = 0

    for topic in topics:
        try:
            parsed = frontmatter.parse(boundary.read_text(topic))
        except (UnicodeDecodeError, OSError, frontmatter.FrontmatterError):
            parsed = None
        if parsed is None:
            errors.append({"path": config.to_rel_posix(topic, vault), "error": "frontmatter_parse_failed"})
            continue
        meta, _ = parsed
        if meta.get("sources") == []:
            orphaned += 1

    log = config.wiki_root(vault) / "log.md"
    last_log = ""
    if boundary.exists(log):
        lines = [
            line.strip()
            for line in boundary.read_text(log, encoding="utf-8").splitlines()
            if line.strip()
        ]
        last_log = lines[-1] if lines else ""

    index_file = config.index_path(vault)
    index_exists = boundary.exists(index_file)
    index_topics = 0
    raw_index: Any = None
    if index_exists:
        try:
            raw_index = json.loads(boundary.read_text(index_file, encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            raw_index = None
        if isinstance(raw_index, dict) and isinstance(raw_index.get("topics"), dict):
            index_topics = len(raw_index["topics"])
    try:
        _index_data, index_errors = wiki_index.rebuild(vault)
    except wiki_index.NormalizedPathCollisionError as exc:
        _index_data = {}
        index_errors = [{"path": exc.path, "error": "normalized_path_collision"}]
    # Stale when any page is newer than the index file, or when the indexed page
    # set differs from disk (a deleted topic leaves no newer mtime behind).
    index_stale = _index_stale(vault, index_file) or not isinstance(raw_index, dict) or any(
        set(raw_index.get(key) or {}) != set(_index_data.get(key) or {}) for key in ("topics", "queries")
    )

    # Compute quality metrics from in-memory rebuild
    quality_distribution = {"stub": 0, "basic": 0, "standard": 0, "rich": 0, "premium": 0}
    featured_count = 0
    aliases_count = len(_index_data.get("alias_index", {}))
    backlinks_max = 0

    for _topic_key, topic_entry in _index_data.get("topics", {}).items():
        tier = topic_entry.get("quality_tier", "stub")
        quality_distribution[tier] = quality_distribution.get(tier, 0) + 1

        if topic_entry.get("featured", False):
            featured_count += 1

        backlinks_count = topic_entry.get("backlinks", 0)
        if backlinks_count > backlinks_max:
            backlinks_max = backlinks_count

    # Coverage / worklist reuse the index built above; failures are reported, not hidden.
    index_arg = _index_data or None
    gaps_count = wanted_count = stale_count = review_count = 0
    try:
        gaps_count = len(coverage.compute_coverage(vault, index_arg).get("gaps", []))
    except (ValueError, OSError) as exc:
        errors.append({"error": "coverage_failed", "detail": str(exc)})
    try:
        worklist_result = worklist.compute_worklist(vault, index_arg)
        wanted_count = len(worklist_result.get("wanted", []))
        stale_count = len(worklist_result.get("stale", []))
        review_count = len(worklist_result.get("review", []))
    except (ValueError, OSError) as exc:
        errors.append({"error": "worklist_failed", "detail": str(exc)})

    # Check site status
    site_dir = config.wiki_root(vault) / "site"
    site_index = site_dir / "index.html"
    site_stat = boundary.stat(site_index)
    site_exists = site_stat is not None
    site_stale = False
    pages = topics + [entry.path for entry in boundary.entries(queries_root, suffix=".md")]
    if site_exists and pages:
        site_mtime = site_stat.st_mtime_ns if site_stat else 0
        # Site is stale if any exported topic/report is newer.
        site_stale = any(
            st is not None and st.st_mtime_ns > site_mtime
            for st in (boundary.stat(page) for page in pages)
        )
    # A generation that reported errors leaves no completion stamp, so a partial site
    # is always stale no matter how recent its index.html looks.
    if site_exists and not boundary.exists(site_dir / "_complete"):
        site_stale = True

    cache_file = config.cache_path(vault)
    batch_state = batch.load_state(vault)
    cache_stat = boundary.stat(cache_file)
    index_stat = boundary.stat(index_file)
    batch_summary = None
    if batch_state:
        batches = batch_state.get("batches", [])
        done = sum(1 for item in batches if item.get("status") == "done")
        batch_summary = {
            "planned": batch_state.get("total", 0),
            "batch_size": batch_state.get("batch_size"),
            "batches_total": len(batches),
            "batches_done": done,
            "batches_pending": len(batches) - done,
        }
    emit({
        "vault": str(vault),
        "sources_tracked": len(data.get("sources", {})),
        "topics_total": len(topics),
        "topics_orphaned": orphaned,
        "topics_archived": len(archived_topics),
        "queries_total": queries_total,
        "graphs_count": graphs_count,
        "graphs_stale": _graphs_stale(vault),
        "cache_size_bytes": cache_stat.st_size if cache_stat else 0,
        "last_log_entry": last_log,
        "errors": errors,
        "index_exists": index_exists,
        "index_size_bytes": index_stat.st_size if index_stat else 0,
        "index_topics": index_topics,
        "index_stale": index_stale,
        "index_errors": index_errors,
        "batch": batch_summary,
        "quality_distribution": quality_distribution,
        "featured_count": featured_count,
        "aliases_count": aliases_count,
        "backlinks_max": backlinks_max,
        "gaps_count": gaps_count,
        "wanted_count": wanted_count,
        "stale_count": stale_count,
        "review_count": review_count,
        "site_exists": site_exists,
        "site_stale": site_stale,
    })


def cmd_gen_base(args: argparse.Namespace) -> None:
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
        config.atomic_write_text(path, content)
        written.append(config.to_rel_posix(path, vault))
    emit({"ok": True, "prefix": prefix, "written": written})


def _rebuild_index_in_memory(vault: Path) -> dict[str, Any]:
    try:
        data, _errors = wiki_index.rebuild(vault)
    except wiki_index.NormalizedPathCollisionError as exc:
        fail({"error": "normalized_path_collision", "path": exc.path}, 1)
    return data


def _render_canvas(vault: Path, data: dict[str, Any], prefix: str, key: str) -> dict[str, Any]:
    graph = canvas.build_canvas(key, data, prefix)
    path = config.graphs_dir(vault) / (Path(key).stem + ".canvas")
    try:
        canvas.write_canvas(path, graph)
    except canvas.CanvasWriteError:
        fail({"error": "canvas_write_failed", "path": config.to_rel_posix(path, vault)}, 1)
    return {"path": config.to_rel_posix(path, vault), "nodes": len(graph["nodes"]), "edges": len(graph["edges"])}


def cmd_gen_canvas(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)
    data = _rebuild_index_in_memory(vault)
    prefix = bases.obsidian_prefix(vault)
    if args.all:
        written = [_render_canvas(vault, data, prefix, key) for key in sorted(data["topics"])]
        emit({"ok": True, "written": written, "count": len(written)})
        return
    safe = _safe_md_name(args.topic)
    if safe not in data["topics"]:
        fail({"error": "topic_not_found", "topic": safe}, 1)
    emit({"ok": True, **_render_canvas(vault, data, prefix, safe)})


def _obsidian_index_relpath(vault: Path) -> str:
    """Obsidian-vault-root-relative POSIX path of ``wiki/index.md``."""
    prefix = bases.obsidian_prefix(vault)
    return "/".join(part for part in (prefix, "wiki", "index.md") if part)


def _resolve_cards(mode: str, vault: Path) -> bool:
    """Whether to emit the dynamic dataviewjs card block. ``auto`` detects
    Dataview + its JS queries; ``on``/``off`` force the choice."""
    if mode == "on":
        return True
    if mode == "off":
        return False
    return plugins.cards_available(vault)


def cmd_gen_home(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)
    cards = _resolve_cards(getattr(args, "cards", "auto"), vault)
    index_file = config.wiki_root(vault) / "index.md"
    existing = boundary.read_text(index_file) if boundary.exists(index_file) else None
    text = home.merge(existing, vault, cards)
    if getattr(args, "emit_only", False):
        # No write: the agent holds an MCP channel this subprocess cannot reach,
        # so it performs the conditional write itself from this payload.
        emit({
            "ok": True,
            "path": "wiki/index.md",
            "cards": cards,
            "write_via": "none",
            "obsidian_path": _obsidian_index_relpath(vault),
            "content": text,
        })
        return
    config.atomic_write_text(index_file, text)
    emit({"ok": True, "path": "wiki/index.md", "cards": cards, "write_via": "atomic"})


def cmd_quality(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)

    topics_dir = config.topics_dir(vault)
    if not boundary.exists(topics_dir):
        emit({"ok": True, "tiers": {}, "distribution": dict.fromkeys(["stub", "basic", "standard", "rich", "premium"], 0), "errors": []})
        return

    tiers = {}
    distribution = {"stub": 0, "basic": 0, "standard": 0, "rich": 0, "premium": 0}
    errors = []

    for entry in boundary.entries(topics_dir, suffix=".md"):
        rel = entry.name
        try:
            text = entry.read_text()
        except (UnicodeDecodeError, OSError):
            errors.append({"path": rel, "error": "topic_decode_failed"})
            continue

        try:
            meta, body = frontmatter.parse(text)
        except frontmatter.FrontmatterError:
            errors.append({"path": rel, "error": "frontmatter_parse_failed"})
            continue

        metrics = quality.compute_metrics(body)
        sources = meta.get("sources")
        items = sources if isinstance(sources, list) else [] if sources is None else [sources]
        unique_sources = len({config.normalize_relpath(str(item)) for item in items})
        tier = quality.compute_tier(body, source_count=unique_sources, metrics=metrics)

        tiers[rel] = {"tier": tier, "metrics": metrics}
        distribution[tier] += 1

    emit({"ok": True, "tiers": tiers, "distribution": distribution, "errors": errors})


def cmd_coverage(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)

    try:
        result = coverage.compute_coverage(vault)
    except ValueError as exc:
        fail({"error": str(exc)}, 1)

    emit(result)


def cmd_keywords(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)

    try:
        result = keywords.compute_keywords(vault)
    except ValueError as exc:
        fail({"error": str(exc)}, 1)

    emit(result)


def cmd_worklist(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)

    try:
        result = worklist.compute_worklist(vault)
    except ValueError as exc:
        fail({"error": str(exc)}, 1)

    emit({"ok": True, **result})


def cmd_gen_site(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)

    verbose(args, "Generating static site...")
    try:
        result = site.generate_site(vault)
        verbose(args, f"Generated {result.get('pages', 0)} pages")
    except ValueError as exc:
        fail({"error": str(exc)}, 1)

    emit(result)
