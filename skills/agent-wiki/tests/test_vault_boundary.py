"""Regression checks: vault reads and writes must never cross a directory link.

A directory link (POSIX symlink or Windows junction) planted inside the vault must not
let the tool read, publish, write or delete anything outside the vault. Windows can
create junctions without any privilege, so these tests run everywhere; the leaf-file
symlink cases are skipped on Windows because creating them needs elevation.
"""

import argparse
import contextlib
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from agent_wiki import (
    authors,
    boundary,
    cache,
    cleanup,
    commands,
    config,
    frontmatter,
    scanner,
    site,
    wiki_index,
)

# Windows only lets an elevated (or Developer Mode) process create file symlinks.
requires_file_symlink = pytest.mark.skipif(
    os.name == "nt", reason="file symlinks need elevation or Developer Mode on Windows"
)


def _link(link: Path, target: Path, *, directory: bool = True) -> None:
    if os.name == "nt":
        if not directory:
            pytest.skip("file symlinks need elevation or Developer Mode on Windows")
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=directory)


def _init(vault: Path) -> None:
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)


def _init_wiki_only(vault: Path) -> None:
    """Create wiki/ so a link can take the place of one of its children."""
    config.wiki_root(vault).mkdir(parents=True, exist_ok=True)


def _topic(vault: Path, name: str, meta: dict, body: str = "Content.") -> Path:
    path = config.topics_dir(vault) / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def test_scan_ignores_linked_directory(tmp_path):
    """A linked directory must be skipped, not crash the scan (rglob follows it)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "notes").mkdir()
    (vault / "notes" / "real.md").write_text("real note\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("SECRET_OUTSIDE\n", encoding="utf-8")
    _link(vault / "linked", outside)

    result = scanner.classify(vault, {"sources": {}})

    assert [item["path"] for item in result["new"]] == ["notes/real.md"]


def test_site_generation_does_not_write_outside_through_linked_site_dir(tmp_path):
    vault = tmp_path / "vault"
    _init(vault)
    _topic(vault, "topic.md", {"title": "Topic"})
    outside = tmp_path / "site-outside"
    outside.mkdir()
    _link(config.wiki_root(vault) / "site", outside)

    result = site.generate_site(vault)

    assert list(outside.iterdir()) == []
    assert result["ok"] is False


def test_site_pruning_does_not_delete_external_html(tmp_path):
    vault = tmp_path / "vault"
    _init(vault)
    _topic(vault, "topic.md", {"title": "Topic"})
    outside = tmp_path / "site-outside"
    outside.mkdir()
    victim = outside / "victim.html"
    victim.write_text("<html>keep me</html>", encoding="utf-8")
    _link(config.wiki_root(vault) / "site", outside)

    site.generate_site(vault)

    assert victim.is_file()


def test_held_directory_pins_its_own_and_ancestor_paths(tmp_path):
    """A held output directory must not be replaceable by a link mid-run.

    On POSIX the descriptor already names the real directory, so this only asserts that
    the writes keep landing in the object that was verified. On Windows the handle is
    opened without FILE_SHARE_DELETE and must additionally stop anybody (including this
    process) from renaming the directory or any of its ancestors into a link.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "wiki" / "site").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    boundary.bind(vault)
    site_dir = config.wiki_root(vault) / "site"

    with boundary.fs_for(vault).open_directory(site_dir) as handle:
        if os.name == "nt":
            # The whole ancestor chain must be pinned while the handle is held.
            for target, destination in (
                (site_dir, tmp_path / "site-moved"),
                (vault / "wiki", tmp_path / "wiki-moved"),
                (vault, tmp_path / "vault-moved"),
            ):
                with pytest.raises(OSError):
                    target.rename(destination)
                assert not destination.exists()
            # ... so planting a link where the real directory still is must fail too.
            with pytest.raises(OSError):
                _link(site_dir, outside)
            assert list(outside.iterdir()) == []
        handle.write_atomic("index.html", "<html>real</html>")
        if os.name == "posix":
            # Rename even though index.html exists: rmdir would fail on this
            # nonempty directory and silently leave the test's swap unexercised.
            moved = tmp_path / "site-moved"
            site_dir.rename(moved)
            site_dir.symlink_to(outside, target_is_directory=True)
            handle.write_atomic("second.html", "still authorized")
            assert (moved / "second.html").read_text(encoding="utf-8") == "still authorized"
            assert list(outside.iterdir()) == []
            assert not (outside / "index.html").exists()

    if os.name == "nt":
        assert (site_dir / "index.html").read_text(encoding="utf-8") == "<html>real</html>"
        assert list(outside.iterdir()) == []


def test_site_generation_survives_site_dir_replaced_mid_run(tmp_path, monkeypatch):
    """Swapping wiki/site for a link between the check and the writes must not
    redirect the output outside the vault."""
    vault = tmp_path / "vault"
    _init(vault)
    _topic(vault, "topic.md", {"title": "Topic"})
    site_dir = config.wiki_root(vault) / "site"
    outside = tmp_path / "site-outside"
    outside.mkdir()
    swapped = False
    real_write_atomic = boundary.DirectoryHandle.write_atomic

    def swap_then_write(handle, name, data):
        nonlocal swapped
        if not swapped:
            # The publication handle is already open. POSIX: the validated descriptor
            # still refers to the real directory, so this swap is visible only to later
            # *path* operations. Windows: the held handle refuses the removal.
            with contextlib.suppress(OSError):
                site_dir.rename(tmp_path / "site-moved")
                _link(site_dir, outside)
            swapped = True
        return real_write_atomic(handle, name, data)

    monkeypatch.setattr(boundary.DirectoryHandle, "write_atomic", swap_then_write)

    site.generate_site(vault)

    assert swapped
    assert list(outside.iterdir()) == []
    published_dir = tmp_path / "site-moved" if os.name == "posix" else site_dir
    assert (published_dir / "index.html").exists()


def test_site_does_not_publish_topics_from_linked_topics_dir(tmp_path):
    vault = tmp_path / "vault"
    _init_wiki_only(vault)
    outside = tmp_path / "outside-topics"
    outside.mkdir()
    (outside / "secret.md").write_text(
        frontmatter.dump({"title": "Secret"}, "SECRET_OUTSIDE"), encoding="utf-8"
    )
    _link(config.topics_dir(vault), outside)

    site.generate_site(vault)

    site_dir = config.wiki_root(vault) / "site"
    pages = list(site_dir.glob("*.html")) if site_dir.exists() else []
    assert all("SECRET_OUTSIDE" not in page.read_text(encoding="utf-8") for page in pages)


@requires_file_symlink
def test_site_does_not_publish_outside_topic_file(tmp_path):
    vault = tmp_path / "vault"
    _init(vault)
    outside = tmp_path / "outside-topics"
    outside.mkdir()
    (outside / "secret.md").write_text(
        frontmatter.dump({"title": "Secret"}, "SECRET_OUTSIDE"), encoding="utf-8"
    )
    _link(config.topics_dir(vault) / "linked.md", outside / "secret.md", directory=False)

    site.generate_site(vault)

    site_dir = config.wiki_root(vault) / "site"
    pages = list(site_dir.glob("*.html")) if site_dir.exists() else []
    assert all("SECRET_OUTSIDE" not in page.read_text(encoding="utf-8") for page in pages)


def test_authors_does_not_read_outside_topic(tmp_path):
    vault = tmp_path / "vault"
    _init_wiki_only(vault)
    (vault / "note.md").write_text("| 作者 | Alice |\n", encoding="utf-8")
    outside = tmp_path / "outside-topics"
    outside.mkdir()
    (outside / "paper.md").write_text(
        frontmatter.dump({"title": "Paper", "sources": ["note.md"]}, "body"), encoding="utf-8"
    )
    _link(config.topics_dir(vault), outside)

    extracted = authors.extract(vault)

    assert extracted == {}


@requires_file_symlink
def test_authors_does_not_read_outside_note(tmp_path):
    vault = tmp_path / "vault"
    _init(vault)
    _topic(vault, "paper.md", {"title": "Paper", "sources": ["note.md"]})
    outside = tmp_path / "outside-notes"
    outside.mkdir()
    (outside / "note.md").write_text("| 作者 | Mallory |\n", encoding="utf-8")
    _link(vault / "note.md", outside / "note.md", directory=False)

    extracted = authors.extract(vault)

    assert extracted == {"paper.md": [{"src": "note.md", "file": None, "authors": ""}]}


def test_index_does_not_read_topics_from_linked_topics_dir(tmp_path):
    vault = tmp_path / "vault"
    _init_wiki_only(vault)
    outside = tmp_path / "outside-topics"
    outside.mkdir()
    (outside / "secret.md").write_text(
        frontmatter.dump({"title": "Secret"}, "SECRET_OUTSIDE"), encoding="utf-8"
    )
    _link(config.topics_dir(vault), outside)

    data, _errors = wiki_index.rebuild(vault)

    assert "SECRET_OUTSIDE" not in str(data)
    assert "secret.md" not in data.get("topics", {})


def test_deepest_registered_vault_wins_over_a_shallower_one(tmp_path):
    """A shallower root registered later must not widen a nested vault's boundary."""
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    # Bound in this order on purpose: the shallower root is the most recent one.
    boundary.bind(inner)
    boundary.bind(outer)

    assert boundary._anchor_for(inner / "note.md") == inner
    assert boundary._anchor_for(outer / "note.md") == outer


def test_append_does_not_follow_a_linked_leaf(tmp_path):
    """Appending must never write the caller's data into a file outside the vault.

    The log is the one append path in the tool, and it lives in the wiki directory
    where an attacker can plant a link. ``append_atomic`` opens the leaf without
    following it, so the outside target must keep its original bytes.
    """
    vault = tmp_path / "vault"
    _init_wiki_only(vault)
    outside = tmp_path / "outside-log"
    outside.mkdir()
    victim = outside / "log.md"
    victim.write_text("ORIGINAL", encoding="utf-8")
    log = config.wiki_root(vault) / "log.md"
    _link(log, victim, directory=False)

    with pytest.raises(OSError):
        boundary.append_text(log, "## entry\n")

    assert victim.read_text(encoding="utf-8") == "ORIGINAL"
    assert "entry" not in victim.read_text(encoding="utf-8")


def test_append_accumulates_instead_of_overwriting(tmp_path):
    """The descriptor must be opened in append mode.

    Without it the first write of each run lands at offset 0 and the log silently
    keeps only the newest entry, which is how a repeated ``save-report`` call lost
    every earlier entry.
    """
    vault = tmp_path / "vault"
    _init_wiki_only(vault)
    log = config.wiki_root(vault) / "log.md"
    boundary.write_text(log, "## header\n")
    boundary.append_text(log, "## first\n")
    boundary.append_text(log, "## second\n")

    assert log.read_text(encoding="utf-8") == "## header\n## first\n## second\n"


def test_directory_handle_refuses_names_that_are_not_a_single_component(tmp_path):
    """A leaf name must never carry a separator, parent reference or stream."""
    vault = tmp_path / "vault"
    _init_wiki_only(vault)
    wiki = config.wiki_root(vault)
    names = ["", ".", "..", "../escape.md", "sub/escape.md", "..\\escape.md"]
    if os.name == "nt":
        names += ["C:escape.md", "log.md:stream"]
    with boundary.fs_for(wiki).open_directory(wiki) as handle:
        for name in names:
            with pytest.raises(boundary.BoundaryError):
                handle.write_atomic(name, b"x")
            with pytest.raises(boundary.BoundaryError):
                handle.append_atomic(name, b"x")
            with pytest.raises(boundary.BoundaryError):
                handle.unlink(name)


def test_cleanup_does_not_treat_a_linked_source_as_deleted(tmp_path, capsys):
    """A source whose path is a link must be skipped, not cleaned up as a deletion.

    ``cleanup`` used to resolve the cached source path with ``Path.resolve()`` and
    crash on the ``ValueError`` that a link outside the vault produces, and a
    path-based existence check can mistake a refused read for a deleted file. The
    cached entry and the topic that references it must both survive untouched.
    """
    vault = tmp_path / "vault"
    _init(vault)
    outside = tmp_path / "outside-sources"
    outside.mkdir()
    (outside / "secret.md").write_text("SECRET", encoding="utf-8")
    topic = _topic(vault, "paper.md", {"title": "Paper", "sources": ["note.md"]})
    cache.save(vault, {"sources": {"note.md": {"sha256": "x", "size": 6, "mtime_ns": 1, "derived_topics": ["paper.md"]}}})
    _link(vault / "note.md", outside)

    before = topic.read_text(encoding="utf-8")
    with redirect_stdout(io.StringIO()):
        commands.cmd_cleanup(argparse.Namespace(vault=str(vault)))

    assert topic.read_text(encoding="utf-8") == before
    assert sorted(p.name for p in outside.iterdir()) == ["secret.md"]
    assert "note.md" in cache.load(vault).get("sources", {})


@pytest.mark.parametrize("target", ["wiki/graphs", "wiki"])
def test_directory_creation_is_refused_below_a_link(tmp_path, target):
    """Creating a missing directory must not reach through a link.

    ``write_canvas`` and ``save_index`` used ``path.parent.mkdir(parents=True)``,
    which is an unguarded creation: when the parent does not exist yet and an
    ancestor of it is a link, the directory is created outside the vault before
    the write itself is refused. The directory must be created through the
    boundary, which refuses the link instead of creating anything outside.

    The ``wiki/graphs`` variant is the one that isolates the creation defect:
    reverting ``ensure_directory`` back to ``mkdir`` makes ``outside-wiki-graphs``
    contain a ``nested`` directory. The ``wiki`` variant asserts the same boundary
    but passes either way, because ``wiki`` already exists as a link and ``mkdir``
    with ``exist_ok=True`` is a no-op there.
    """
    import agent_wiki.canvas as canvas
    import agent_wiki.wiki_index as wiki_index

    vault = tmp_path / "vault"
    outside = tmp_path / ("outside-" + target.replace("/", "-"))
    outside.mkdir()
    if target == "wiki":
        vault.mkdir()
    else:
        _init(vault)
    _link(vault / target, outside)

    if target == "wiki":
        with pytest.raises(wiki_index.IndexWriteError):
            wiki_index.save_index(vault, wiki_index.empty_schema())
    else:
        with pytest.raises(canvas.CanvasWriteError):
            canvas.write_canvas(vault / "wiki" / "graphs" / "nested" / "graph.canvas", {"nodes": [], "edges": []})

    assert outside.is_dir()
    assert list(outside.iterdir()) == []


def test_walk_refuses_a_linked_start_directory(tmp_path):
    """``boundary.walk`` must verify the start directory before enumerating it.

    A link planted at the walk root would otherwise list external names as if
    they were vault files, and the scanner would then hash/track them.
    """
    vault = tmp_path / "vault"
    _init(vault)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("external", encoding="utf-8")
    _link(vault / "linked", outside)

    with pytest.raises(boundary.BoundaryError):
        list(boundary.walk(vault / "linked", include_links=True))
    # The vault root itself still walks fine.
    assert list(boundary.walk(vault)) == []


def test_archive_moves_the_latest_source_version(tmp_path, monkeypatch):
    """A replacement before the atomic move is archived intact, never discarded."""
    from datetime import date

    vault = tmp_path / "vault"
    _init(vault)
    archive = config.archive_dir(vault)
    topic = vault / "t.md"
    topic.write_text("old", encoding="utf-8")

    real_move = boundary.DirectoryHandle.move_to

    def sneaky_move(handle, name, destination, new_name):
        topic.write_text("NEWER", encoding="utf-8")
        return real_move(handle, name, destination, new_name)

    monkeypatch.setattr(boundary.DirectoryHandle, "move_to", sneaky_move)
    cleanup.archive_topic(topic, archive, date(2026, 11, 2))
    assert not topic.exists()
    assert (archive / "2026-11-02" / "t.md").read_text(encoding="utf-8") == "NEWER"


def test_archive_preserves_both_even_for_an_identical_target(tmp_path):
    """An existing target never authorizes deleting a separate source object."""
    from datetime import date

    vault = tmp_path / "vault"
    _init(vault)
    archive = config.archive_dir(vault)
    topic = vault / "t.md"
    topic.write_text("same", encoding="utf-8")

    first = cleanup.archive_topic(topic, archive, date(2026, 11, 2))
    assert first == config.archive_dir(vault) / "2026-11-02" / "t.md"
    assert not topic.exists()

    topic.write_text("same", encoding="utf-8")
    with pytest.raises(cleanup.TopicError, match="archive_target_conflict"):
        cleanup.archive_topic(topic, archive, date(2026, 11, 2))
    assert topic.read_text(encoding="utf-8") == "same"
    assert first.read_text(encoding="utf-8") == "same"


def test_cleanup_reports_a_dangling_linked_source(tmp_path, capsys):
    """A dangling link standing where a source was is not a deleted source."""
    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "gone.md").write_text("x", encoding="utf-8")
    _init(vault)
    config.wiki_root(vault).mkdir(parents=True, exist_ok=True)
    data = {"sources": {"note.md": {"sha256": "x", "size": 1, "mtime_ns": 1, "derived_topics": ["paper.md"]}}}
    cache.save(vault, data)
    _link(vault / "note.md", outside / "gone.md")

    os.remove(outside / "gone.md")  # now the junction dangles
    out = io.StringIO()
    with redirect_stdout(out):
        commands.cmd_cleanup(argparse.Namespace(vault=str(vault)))

    assert "note.md" in cache.load(vault).get("sources", {})
    payload = json.loads(out.getvalue())
    assert {"path": "note.md", "error": "skipped_link"} in payload["errors"]


def test_site_without_a_completion_stamp_is_stale(tmp_path):
    """An incomplete generation must not present itself as fresh."""
    vault = tmp_path / "vault"
    _init(vault)
    _topic(vault, "a.md", {"type": "concept"})
    result = site.generate_site(vault)
    assert result["complete"] is True
    site_dir = config.wiki_root(vault) / "site"
    assert (site_dir / "_complete").exists()

    # Now a run with an unreadable topic: no new stamp may be written.
    (config.topics_dir(vault) / "b.md").write_bytes(b"\xef\xbb\xbf" + b"\xff\xfe\xff")
    result = site.generate_site(vault)
    assert result["errors"] and result["complete"] is False


def test_the_facade_reuses_one_vault_fs_per_root(tmp_path):
    """Facade calls share a VaultFS so POSIX root descriptors are not leaked."""
    vault = tmp_path / "vault"
    _init(vault)
    boundary.bind(vault)
    probe = vault / "x.md"
    probe.write_text("x", encoding="utf-8")
    boundary.read_text(probe)
    boundary.stat(probe)
    from agent_wiki.boundary import _FS_CACHE, _fs_for

    assert _fs_for(probe) is _fs_for(probe)
    assert vault.resolve() in _FS_CACHE or any(
        root in _FS_CACHE for root in [vault]
    )


def test_write_text_closes_its_directory_handle(tmp_path, monkeypatch):
    """Single-component facade writes must not leak the root directory handle."""
    vault = tmp_path / "vault"
    _init(vault)
    closed = []
    real_close = boundary.DirectoryHandle.close

    def tracking_close(self):
        closed.append(self.path.name)
        real_close(self)

    monkeypatch.setattr(boundary.DirectoryHandle, "close", tracking_close)
    boundary.write_text(vault / "y.md", "y")
    assert (vault / "y.md").read_text(encoding="utf-8") == "y"
    # The root handle opened for the single-component write must be closed.
    assert closed.count("vault") >= 1


def test_site_stale_stamp_is_removed_by_an_incomplete_run(tmp_path):
    """A failing generation must retract the previous _complete stamp.

    Otherwise a partial site hides behind the stamp of an older complete run and
    status keeps reporting it as fresh.
    """
    vault = tmp_path / "vault"
    _init(vault)
    _topic(vault, "a.md", {"type": "concept"})
    site_dir = config.wiki_root(vault) / "site"

    assert site.generate_site(vault)["complete"] is True
    assert (site_dir / "_complete").exists()

    (config.topics_dir(vault) / "b.md").write_bytes(b"\xff\xfe\xff")
    result = site.generate_site(vault)
    assert result["complete"] is False
    assert not (site_dir / "_complete").exists()

    os.remove(config.topics_dir(vault) / "b.md")
    assert site.generate_site(vault)["complete"] is True
    assert (site_dir / "_complete").exists()


def test_archive_conflict_keeps_a_concurrently_edited_source(tmp_path, monkeypatch):
    """A conflict preserves a newer source without comparing stale byte snapshots."""
    from datetime import date

    vault = tmp_path / "vault"
    _init(vault)
    archive = config.archive_dir(vault)
    topic = vault / "t.md"
    topic.write_text("old", encoding="utf-8")
    target_dir = archive / "2026-11-02"
    target_dir.mkdir(parents=True)
    (target_dir / "t.md").write_text("old", encoding="utf-8")

    real_move = boundary.DirectoryHandle.move_to

    def sneaky_move(handle, name, destination, new_name):
        topic.write_text("NEWER", encoding="utf-8")
        return real_move(handle, name, destination, new_name)

    monkeypatch.setattr(boundary.DirectoryHandle, "move_to", sneaky_move)
    with pytest.raises(cleanup.TopicError) as excinfo:
        cleanup.archive_topic(topic, archive, date(2026, 11, 2))
    assert excinfo.value.code == "archive_target_conflict"
    assert topic.read_text(encoding="utf-8") == "NEWER"
    assert (target_dir / "t.md").read_text(encoding="utf-8") == "old"


def test_archive_does_not_clobber_a_target_that_appears_mid_publish(tmp_path, monkeypatch):
    """A different same-day target appearing between check and publish must win.

    Publication used to replace, so a concurrent archiver's completed target was
    overwritten by this run's bytes. The no-clobber claim must detect the loser
    and apply the conflict policy instead.
    """
    from datetime import date

    vault = tmp_path / "vault"
    _init(vault)
    archive = config.archive_dir(vault)
    topic = vault / "t.md"
    topic.write_text("mine", encoding="utf-8")
    theirs = "theirs"

    real_method = boundary.DirectoryHandle.move_to

    def sneaky_move(self, name, destination, new_name):
        target = destination.path / new_name
        target.write_text(theirs, encoding="utf-8")
        return real_method(self, name, destination, new_name)

    monkeypatch.setattr(boundary.DirectoryHandle, "move_to", sneaky_move)
    with pytest.raises(cleanup.TopicError) as excinfo:
        cleanup.archive_topic(topic, archive, date(2026, 11, 2))
    assert excinfo.value.code == "archive_target_conflict"
    # The concurrent winner's content survived, and the source is kept for reconciliation.
    assert (archive / "2026-11-02" / "t.md").read_text(encoding="utf-8") == theirs
    assert topic.read_text(encoding="utf-8") == "mine"


def test_scan_reports_an_ignore_file_that_cannot_be_inspected(tmp_path, monkeypatch):
    """An ignore-file inspection failure must warn, not abort classification."""
    vault = tmp_path / "vault"
    _init(vault)
    (vault / "a.md").write_text("note\n", encoding="utf-8")
    (vault / ".wikiignore").write_text("a.md\n", encoding="utf-8")

    real_exists = boundary.exists

    def denied_exists(path):
        if path.name == ".wikiignore":
            raise PermissionError(13, "access denied", str(path))
        return real_exists(path)

    monkeypatch.setattr(boundary, "exists", denied_exists)
    result = scanner.classify(vault, {})
    assert {"path": ".wikiignore", "error": "ignore_unreadable"} in result["skipped_symlinks"]
    # The scan itself still classifies the note (rules not applied, but not aborted).
    assert len(result["new"]) == 1
    assert result["new"][0]["path"] == "a.md"
