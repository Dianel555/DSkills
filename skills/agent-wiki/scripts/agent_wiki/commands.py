"""CLI subcommand implementations."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import secrets
import stat
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, NoReturn

try:
    import yaml as yaml_module
except ImportError:
    yaml_module = None  # type: ignore[assignment]

from . import (
    authors,
    bases,
    batch,
    cache,
    canvas,
    cleanup,
    config,
    coverage,
    doctor,
    frontmatter,
    home,
    obsidian_api,
    plugins,
    quality,
    scanner,
    site,
    source_type,
    wiki_index,
    worklist,
)


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def emit_formatted(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    """Emit output in the requested format (json/yaml/table)."""
    fmt = getattr(args, "format", "json")

    if fmt == "yaml":
        if yaml_module is None:
            fail({"error": "yaml_not_available", "hint": "pip install PyYAML"}, 1)
        print(yaml_module.safe_dump(payload, allow_unicode=True, sort_keys=False))
    elif fmt == "table":
        _emit_table(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False))


def _emit_table(payload: dict[str, Any]) -> None:
    """Emit simple key-value table format."""
    if "error" in payload:
        print(f"ERROR: {payload.get('error')}", file=sys.stderr)
        if "hint" in payload:
            print(f"  Hint: {payload['hint']}", file=sys.stderr)
        return

    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            print(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            print(f"{key}: {value}")


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
    return not path.exists() or bool(path.stat().st_mode & stat.S_IWRITE)


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
        config.url_cache_dir(vault),
        config.queries_dir(vault),
        config.graphs_dir(vault),
    ):
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


def cmd_scan(args: argparse.Namespace) -> None:
    vault = _vault(args)
    verbose(args, f"Scanning vault: {vault}")
    classified = scanner.classify(vault, cache.load(vault))
    verbose(args, f"Found {len(classified.get('new', []))} new, {len(classified.get('modified', []))} modified, {len(classified.get('deleted', []))} deleted")
    report = scanner.format_report(classified, vault)
    if "error" in report:
        fail(report, 1)
    emit_formatted(args, report)


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
    emit_formatted(args, {
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
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"## [{date.today().isoformat()}] {category} | {action} | {path}\n")


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
        if source.exists():
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


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


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
        meta, body = frontmatter.parse(target.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, frontmatter.FrontmatterError):
        fail({"error": "capture_parse_failed", "path": rel}, 1)
    if meta.get("kind") != kind:
        meta["kind"] = kind
        _atomic_write_text(target, frontmatter.dump(meta, body))
    _append_log(vault, "capture", action, rel)
    emit({"ok": True, "path": rel, "kind": kind})


def cmd_save_report(args: argparse.Namespace) -> None:
    _capture(args, config.queries_dir, "query", "save_report")


def _topic_meta(path: Path) -> tuple[dict[str, Any], str] | None:
    try:
        return frontmatter.parse(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, frontmatter.FrontmatterError):
        return None


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
    if not index_file.exists():
        return True
    index_mtime = index_file.stat().st_mtime_ns
    for root in (config.topics_dir(vault), config.queries_dir(vault)):
        if root.exists() and any(p.stat().st_mtime_ns > index_mtime for p in root.glob("*.md")):
            return True
    return False


def _graphs_stale(vault: Path) -> bool:
    topics_root = config.topics_dir(vault)
    topics = list(topics_root.glob("*.md")) if topics_root.exists() else []
    if not topics:
        return False
    graphs_root = config.graphs_dir(vault)
    for topic in topics:
        graph = graphs_root / (topic.stem + ".canvas")
        if not graph.exists() or topic.stat().st_mtime_ns > graph.stat().st_mtime_ns:
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
    emit_formatted(args, {"ok": True, "topics": len(data["topics"]), "errors": errors})


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
    topics = list(topics_root.glob("*.md")) if topics_root.exists() else []
    report_file = batch.report_path(vault)
    archived_topics = [p for p in archive_root.glob("**/*.md") if p != report_file] if archive_root.exists() else []
    queries_root = config.queries_dir(vault)
    graphs_root = config.graphs_dir(vault)
    queries_total = len(list(queries_root.glob("*.md"))) if queries_root.exists() else 0
    graphs_count = len(list(graphs_root.glob("*.canvas"))) if graphs_root.exists() else 0
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
    except wiki_index.NormalizedPathCollisionError as exc:
        _index_data = {}
        index_errors = [{"path": exc.path, "error": "normalized_path_collision"}]

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

    # Compute coverage metrics
    try:
        coverage_result = coverage.compute_coverage(vault)
        gaps_count = len(coverage_result.get("gaps", []))
    except (ValueError, Exception):
        gaps_count = 0  # Graceful fallback

    # Compute worklist metrics
    try:
        worklist_result = worklist.compute_worklist(vault)
        wanted_count = len(worklist_result.get("wanted", []))
        stale_count = len(worklist_result.get("stale", []))
        review_count = len(worklist_result.get("review", []))
    except (ValueError, Exception):
        wanted_count = 0
        stale_count = 0
        review_count = 0

    # Check site status
    site_dir = config.wiki_root(vault) / "site"
    site_index = site_dir / "index.html"
    site_exists = site_index.exists()
    site_stale = False
    pages = topics + (list(queries_root.glob("*.md")) if queries_root.exists() else [])
    if site_exists and pages:
        try:
            site_mtime = site_index.stat().st_mtime_ns
            # Site is stale if any exported topic/report is newer.
            site_stale = any(page.stat().st_mtime_ns > site_mtime for page in pages)
        except OSError:
            pass

    cache_file = config.cache_path(vault)
    batch_state = batch.load_state(vault)
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
        "cache_size_bytes": cache_file.stat().st_size if cache_file.exists() else 0,
        "last_log_entry": last_log,
        "errors": errors,
        "index_exists": index_exists,
        "index_size_bytes": index_file.stat().st_size if index_exists else 0,
        "index_topics": index_topics,
        "index_stale": _index_stale(vault, index_file),
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
        path.write_text(content, encoding="utf-8")
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


_IDENTITY_MARKER_NAME = ".agent-wiki-vault-id.md"


def _bootstrap_vault_identity(vault: Path) -> obsidian_api.VaultIdentitySetupRequiredError:
    """Create a marker and return the env setup needed for the next run."""
    wiki = config.wiki_root(vault)
    token = secrets.token_urlsafe(24)
    marker_path: Path | None = None
    marker_name = _IDENTITY_MARKER_NAME
    for attempt in range(10):
        if attempt:
            marker_name = f".agent-wiki-vault-id-{token[:10]}.md"
        candidate = wiki / marker_name
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            token = secrets.token_urlsafe(24)
            continue
        marker_path = candidate
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as marker:
                marker.write(token)
        except BaseException:
            with contextlib.suppress(OSError):
                candidate.unlink()
            raise
        break
    if marker_path is None:
        raise OSError("could not create a unique vault identity marker")
    api_marker_path = "/".join(
        part for part in (bases.obsidian_prefix(vault), "wiki", marker_path.name) if part
    )
    return obsidian_api.VaultIdentitySetupRequiredError(
        {
            "AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH": api_marker_path,
            "AGENT_WIKI_OBSIDIAN_VAULT_ID": token,
        },
        config.to_rel_posix(marker_path, vault),
    )


def _write_index(
    vault: Path,
    text: str,
    use_rest: bool,
    expected_content: str | None = None,
) -> str:
    """Write ``wiki/index.md`` without falling back after an uncertain REST write.
    REST writes are verified against the intended target before replacement.
    No local fallback is used after a configured REST write is attempted."""
    if use_rest and expected_content is not None and obsidian_api.configured():
        if not obsidian_api.identity_configured():
            try:
                raise _bootstrap_vault_identity(vault)
            except OSError as exc:
                raise obsidian_api.WriteSafetyError("obsidian_vault_identity_setup_failed") from exc
        if obsidian_api.available():
            ok = obsidian_api.put_file(
                _obsidian_index_relpath(vault), text, expected_content=expected_content
            )
            if ok:
                return "rest"
            raise obsidian_api.WriteSafetyError("obsidian_write_failed")
    _atomic_write_text(config.wiki_root(vault) / "index.md", text)
    return "atomic"


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
    existing = index_file.read_text(encoding="utf-8") if index_file.exists() else None
    text = home.merge(existing, vault, cards)
    try:
        write_via = _write_index(
            vault, text, use_rest=not args.no_rest, expected_content=existing
        )
    except obsidian_api.VaultIdentitySetupRequiredError as exc:
        fail(
            {
                "error": exc.code,
                "env": exc.environment,
                "marker_file": exc.marker_file,
                "hint": "set the two generated environment variables, then retry; the marker is create-only",
            },
            1,
        )
    except obsidian_api.WriteSafetyError as exc:
        hint = "install a REST plugin with document-map version and conditional root PATCH support, or use --no-rest"
        if exc.code != "obsidian_conditional_write_unsupported":
            hint = "refresh the vault target and retry"
        fail({"error": exc.code, "hint": hint}, 1)
    emit({"ok": True, "path": "wiki/index.md", "cards": cards, "write_via": write_via})


def cmd_quality(args: argparse.Namespace) -> None:
    vault = _vault(args)
    if not config.wiki_root(vault).exists():
        fail({"error": "wiki_not_initialized", "hint": "run init first"}, 1)

    topics_dir = config.topics_dir(vault)
    if not topics_dir.exists():
        emit({"ok": True, "tiers": {}, "distribution": dict.fromkeys(["stub", "basic", "standard", "rich", "premium"], 0), "errors": []})
        return

    tiers = {}
    distribution = {"stub": 0, "basic": 0, "standard": 0, "rich": 0, "premium": 0}
    errors = []

    for path in sorted(topics_dir.glob("*.md")):
        rel = path.name
        try:
            text = path.read_text(encoding="utf-8-sig")
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
        tier = quality.compute_tier(body, source_count=unique_sources)

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
        verbose(args, f"Generated {result.get('pages_written', 0)} pages")
    except ValueError as exc:
        fail({"error": str(exc)}, 1)

    emit(result)


def cmd_doctor(args: argparse.Namespace) -> None:
    vault = _vault(args)
    verbose(args, f"Running health checks on: {vault}")
    emit_formatted(args, doctor.run(vault))
