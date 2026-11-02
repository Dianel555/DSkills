"""Final-review regressions: publication must not destroy newer data."""

import json
import os
from pathlib import Path

import pytest
from agent_wiki import boundary, cleanup, config, frontmatter, site


def _vault(tmp_path):
    vault = tmp_path / "vault"
    config.topics_dir(vault).mkdir(parents=True)
    return vault


def test_archive_refuses_even_an_identical_existing_target(tmp_path):
    vault = _vault(tmp_path)
    source = vault / "note.md"
    source.write_bytes(b"same")
    archive = config.archive_dir(vault)
    target = archive / "2026-11-02" / source.name
    target.parent.mkdir(parents=True)
    target.write_bytes(b"same")

    with pytest.raises(cleanup.TopicError, match="archive_target_conflict"):
        cleanup.archive_topic(source, archive, "2026-11-02")

    assert source.read_bytes() == target.read_bytes() == b"same"


def test_archive_does_not_delete_a_source_path_after_copying(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    source = vault / "note.md"
    source.write_bytes(b"original")

    def unsafe_unlink(path):
        # This is the unsafe check/use window: the path may now name a newer file.
        Path(path).write_bytes(b"new version")
        raise AssertionError("copy then path-unlink is not an identity-safe move")

    monkeypatch.setattr(boundary, "unlink", unsafe_unlink)
    target = cleanup.archive_topic(source, config.archive_dir(vault), "2026-11-02")
    assert target.read_bytes() == b"original"
    assert not source.exists()


def test_move_to_refuses_existing_destination_without_touching_either(tmp_path):
    vault = _vault(tmp_path)
    source = vault / "note.md"
    source.write_bytes(b"mine")
    dest_dir = vault / "archive"
    dest_dir.mkdir()
    target = dest_dir / source.name
    target.write_bytes(b"winner")
    fs = boundary.fs_for(source)

    with (
        fs.open_directory(vault) as src,
        fs.open_directory(dest_dir) as dst,
        pytest.raises(FileExistsError),
    ):
        src.move_to(source.name, dst, target.name)

    assert source.read_bytes() == b"mine"
    assert target.read_bytes() == b"winner"


def test_interrupted_site_generation_invalidates_previous_completion(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    topic = config.topics_dir(vault) / "note.md"
    topic.write_text(frontmatter.dump({"title": "Note", "sources": []}, "body"), encoding="utf-8")
    assert site.generate_site(vault)["complete"]
    stamp = config.wiki_root(vault) / "site" / "_complete"
    assert stamp.exists()

    def interrupted_write(self, name, data):
        raise OSError("simulated interrupted publication")

    monkeypatch.setattr(boundary.DirectoryHandle, "write_atomic", interrupted_write)
    with pytest.raises(OSError, match="simulated interrupted publication"):
        site.generate_site(vault)
    assert not stamp.exists()


def test_disappearing_page_does_not_get_a_completion_stamp(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    topic = config.topics_dir(vault) / "note.md"
    topic.write_text(frontmatter.dump({"title": "Note", "sources": []}, "body"), encoding="utf-8")
    real_exists = boundary.exists

    def disappeared(path):
        return False if Path(path) == topic else real_exists(path)

    monkeypatch.setattr(boundary, "exists", disappeared)
    result = site.generate_site(vault)
    assert result["complete"] is False
    assert any(e["error"] == "topic_missing" for e in result["errors"])
    assert not (config.wiki_root(vault) / "site" / "_complete").exists()


def test_alias_warning_does_not_mark_published_site_incomplete(tmp_path):
    vault = _vault(tmp_path)
    (config.topics_dir(vault) / "note.md").write_text(
        frontmatter.dump({"title": "Note", "sources": []}, "body"), encoding="utf-8"
    )
    (config.wiki_root(vault) / ".wiki-aliases.json").write_text(
        json.dumps({"ghost": "missing.md"}), encoding="utf-8"
    )
    result = site.generate_site(vault)
    assert any(error["error"] == "alias_target_missing" for error in result["errors"])
    assert result["complete"] is True
    assert (config.wiki_root(vault) / "site" / "_complete").is_file()


@pytest.mark.skipif(os.name != "nt", reason="Windows canonical path case")
def test_directory_mutation_path_keeps_on_disk_case(tmp_path):
    vault = _vault(tmp_path)
    mixed = vault / "MixedCase"
    mixed.mkdir()
    with boundary.fs_for(mixed).open_directory(mixed) as held:
        assert held.path.name == "MixedCase"
        held.write_atomic("note.md", "preserved")
    assert (mixed / "note.md").read_text(encoding="utf-8") == "preserved"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction alias regression")
@pytest.mark.parametrize("operation", ["write", "append", "unlink", "move"])
def test_held_directory_does_not_reuse_a_retargeted_junction(tmp_path, operation):
    import _winapi

    vault = _vault(tmp_path)
    real = vault / "real"
    (real / "nested").mkdir(parents=True)
    (real / "nested" / "victim.md").write_bytes(b"inside")
    outside = tmp_path / "outside"
    (outside / "nested").mkdir(parents=True)
    victim = outside / "nested" / "victim.md"
    victim.write_bytes(b"OUTSIDE")
    alias = vault / "alias"
    _winapi.CreateJunction(str(real), str(alias))
    fs = boundary.fs_for(vault)
    with fs.open_directory(alias / "nested") as held, fs.open_directory(vault) as dest:
        os.rmdir(alias)
        _winapi.CreateJunction(str(outside), str(alias))
        if operation == "write":
            held.write_atomic("probe.md", b"new")
        elif operation == "append":
            held.append_atomic("victim.md", b"more")
        elif operation == "unlink":
            held.unlink("victim.md")
        else:
            held.move_to("victim.md", dest, "moved.md")
    assert victim.read_bytes() == b"OUTSIDE"
    assert not (outside / "nested" / "probe.md").exists()
    if operation == "write":
        assert (real / "nested" / "probe.md").read_bytes() == b"new"
    elif operation == "append":
        assert (real / "nested" / "victim.md").read_bytes() == b"insidemore"
    elif operation == "move":
        assert (vault / "moved.md").read_bytes() == b"inside"


@pytest.mark.skipif(os.name != "posix", reason="POSIX atomic move availability")
def test_unsupported_atomic_move_never_copies_or_unlinks(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    source = vault / "note.md"
    source.write_bytes(b"keep")
    monkeypatch.setattr(boundary.ctypes, "CDLL", lambda *args, **kwargs: object())
    with pytest.raises(boundary.BoundaryError, match="unavailable"):
        cleanup.archive_topic(source, config.archive_dir(vault), "2026-11-02")
    assert source.read_bytes() == b"keep"
    assert not (config.archive_dir(vault) / "2026-11-02" / source.name).exists()
