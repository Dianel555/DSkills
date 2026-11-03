"""Offline regression checks for the project upload boundary."""

import gzip
import json
import os
import sys
from pathlib import Path

import pytest

# Windows only lets an elevated (or Developer Mode) process create file symlinks, so the
# leaf-link checks run on POSIX and on Linux CI; junctions cover directories on Windows.
requires_file_symlink = pytest.mark.skipif(
    os.name == "nt", reason="file symlinks need elevation or Developer Mode on Windows"
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from indexer import Indexer  # noqa: E402
from secure_fs import AuthorizedRoot, UnsafePathError  # noqa: E402
from templates import INDEX_DIR, INDEX_FILE  # noqa: E402


def _directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def _record_uploads(indexer, monkeypatch):
    uploads = []

    def capture(headers, payload):
        uploads.extend(payload["blobs"])
        return True

    monkeypatch.setattr(indexer, "_upload_batch_with_retry", capture)
    return uploads


def test_ancestor_cache_does_not_expand_requested_upload_root(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    project = parent / "project"
    project.mkdir(parents=True)
    (parent / "outside.py").write_text("outside_dummy = 1\n", encoding="utf-8")
    (project / "inside.py").write_text("inside_dummy = 1\n", encoding="utf-8")
    cache = parent / INDEX_DIR / INDEX_FILE
    cache.parent.mkdir()
    with gzip.open(cache, "wt", encoding="utf-8") as f:
        json.dump({"entries": {}, "last_indexed": 0}, f)
    indexer = Indexer(str(project), "https://example.invalid", "dummy")
    uploads = _record_uploads(indexer, monkeypatch)

    indexer.get_blob_names()

    assert indexer.root == project.resolve()
    assert {blob["path"] for blob in uploads} == {"inside.py"}


def test_parent_index_does_not_remove_child_project_cache(tmp_path):
    parent = tmp_path / "parent"
    child = parent / "project"
    child.mkdir(parents=True)
    (parent / "file.py").write_text("inside_parent = 1\n", encoding="utf-8")
    cache = child / INDEX_DIR / INDEX_FILE
    cache.parent.mkdir()
    with gzip.open(cache, "wt", encoding="utf-8") as f:
        json.dump({"entries": {}, "last_indexed": 0}, f)

    Indexer(str(parent), "", "").get_blob_names()

    assert cache.is_file()


def test_directory_link_never_uploads_external_content(tmp_path, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / "inside.py").write_text("inside_dummy = 1\n", encoding="utf-8")
    (outside / "private.py").write_text("outside_dummy = 1\n", encoding="utf-8")
    _directory_link(project / "linked", outside)
    indexer = Indexer(str(project), "https://example.invalid", "dummy")
    uploads = _record_uploads(indexer, monkeypatch)

    indexer.get_blob_names()

    assert {blob["path"] for blob in uploads} == {"inside.py"}
    assert all("outside_dummy" not in blob["content"] for blob in uploads)


def test_directory_swap_after_enumeration_does_not_upload_external_content(tmp_path, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    inside = project / "package"
    inside.mkdir(parents=True)
    outside.mkdir()
    (inside / "module.py").write_text("inside_dummy = 1\n", encoding="utf-8")
    (outside / "module.py").write_text("outside_dummy = 1\n", encoding="utf-8")
    indexer = Indexer(str(project), "https://example.invalid", "dummy")
    uploads = _record_uploads(indexer, monkeypatch)
    original_walk = indexer._walk_files
    swapped = False

    def walk_then_swap():
        # Enumeration finishes before any file is read, so the swap lands exactly in
        # the window between discovering a name and opening it.
        yield from original_walk()
        inside.rename(project / "original-package")
        _directory_link(inside, outside)

    def counting_walk():
        nonlocal swapped
        yield from walk_then_swap()
        swapped = True

    monkeypatch.setattr(indexer, "_walk_files", counting_walk)
    indexer.get_blob_names()

    assert swapped
    assert all("outside_dummy" not in blob["content"] for blob in uploads)


@requires_file_symlink
def test_leaf_symlink_is_not_uploaded(tmp_path, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / "inside.py").write_text("inside_dummy = 1\n", encoding="utf-8")
    (outside / "private.py").write_text("outside_dummy = 1\n", encoding="utf-8")
    link = project / "linked.py"
    link.symlink_to(outside / "private.py")
    indexer = Indexer(str(project), "https://example.invalid", "dummy")
    uploads = _record_uploads(indexer, monkeypatch)

    indexer.get_blob_names()

    assert {blob["path"] for blob in uploads} == {"inside.py"}


@requires_file_symlink
def test_linked_ignore_file_is_not_followed(tmp_path, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / "inside.py").write_text("inside_dummy = 1\n", encoding="utf-8")
    # The ignore rules of another directory must not decide what we index.
    (outside / ".aceignore").write_text("inside.py\n", encoding="utf-8")
    (project / ".aceignore").symlink_to(outside / ".aceignore")
    indexer = Indexer(str(project), "https://example.invalid", "dummy")
    uploads = _record_uploads(indexer, monkeypatch)

    indexer.get_blob_names()

    assert {blob["path"] for blob in uploads} == {"inside.py"}


@requires_file_symlink
def test_linked_index_cache_is_not_loaded(tmp_path, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir(parents=True)
    outside.mkdir()
    (project / "inside.py").write_text("inside_dummy = 1\n", encoding="utf-8")
    # A cache placed outside the root must never contribute entries.
    foreign = outside / INDEX_FILE
    with gzip.open(foreign, "wt", encoding="utf-8") as f:
        json.dump(
            {
                "entries": {
                    "deadbeef": {
                        "path": "../../outside/private.py",
                        "blob_name": "deadbeef",
                        "mtime": 1.0,
                        "size": 1,
                    }
                },
                "last_indexed": 1.0,
            },
            f,
        )
    (project / INDEX_DIR).mkdir()
    (project / INDEX_DIR / INDEX_FILE).symlink_to(foreign)
    indexer = Indexer(str(project), "", "")

    names = indexer.get_blob_names()

    assert names and all("private.py" not in name for name in names)
    assert all("private.py" not in e.path for e in indexer._index.entries.values())


def test_oversized_index_cache_is_rebuilt_not_decompressed(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "inside.py").write_text("inside_dummy = 1\n", encoding="utf-8")
    cache = project / INDEX_DIR / INDEX_FILE
    cache.parent.mkdir()
    # Decompression bomb: tiny compressed, far past the load cap once inflated, and
    # otherwise valid JSON so a naive loader would happily adopt the foreign entry.
    pad = "x" * (72 * 1024 * 1024)  # well past indexer.MAX_INDEX_BYTES (64 MiB)
    payload = (
        '{"entries": {"bomb": {"path": "../../outside/private.py", "blob_name": "bomb",'
        ' "mtime": 1.0, "size": 1}}, "last_indexed": 1.0, "pad": "' + pad + '"}'
    ).encode("utf-8")
    cache.write_bytes(gzip.compress(payload, compresslevel=9))
    indexer = Indexer(str(project), "", "")

    names = indexer.get_blob_names()

    assert names  # rebuilt from the real files
    assert any(e.path == "inside.py" for e in indexer._index.entries.values())
    assert all("private.py" not in e.path for e in indexer._index.entries.values())
    assert cache.stat().st_size < len(payload)  # cache replaced by a normal one


def test_save_index_refuses_cache_directory_link(tmp_path, monkeypatch):
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / "inside.py").write_text("inside_dummy = 1\n", encoding="utf-8")
    _directory_link(project / INDEX_DIR, outside)
    indexer = Indexer(str(project), "", "")

    indexer.get_blob_names()

    assert indexer._save_index() is False
    assert not (outside / INDEX_FILE).exists()
    assert not (outside / f"{INDEX_FILE}.{os.getpid()}.tmp").exists()


def test_open_for_write_creates_nothing_outside_through_a_linked_parent(tmp_path):
    """Creating through a link must be refused *before* the file exists.

    Checking the finished handle only discovers that the file landed outside the
    root; by then it is already there and has to be cleaned up.
    """
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    _directory_link(project / INDEX_DIR, outside)

    guard = AuthorizedRoot(project)
    try:
        with pytest.raises(UnsafePathError), guard.open_for_write((INDEX_DIR, f"{INDEX_FILE}.tmp")) as staging:
            staging.write_bytes(b"payload")
        assert list(outside.iterdir()) == []
        assert [p.name for p in project.iterdir()] == [INDEX_DIR]
    finally:
        guard.close()


def test_publish_refuses_to_write_through_a_linked_leaf(tmp_path):
    """The published leaf must be replaced, never followed."""
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    cache = project / INDEX_DIR
    cache.mkdir()
    (cache / INDEX_FILE).write_bytes(b"OLD")

    guard = AuthorizedRoot(project)
    try:
        with guard.open_for_write((INDEX_DIR, f"{INDEX_FILE}.staging")) as staging:
            staging.write_bytes(b"NEW")
        os.remove(cache / INDEX_FILE)
        _directory_link(cache / INDEX_FILE, outside)

        if os.name == "nt":
            with pytest.raises(UnsafePathError):
                guard.publish((INDEX_DIR, f"{INDEX_FILE}.staging"), (INDEX_DIR, INDEX_FILE))
            assert (cache / f"{INDEX_FILE}.staging").read_bytes() == b"NEW"
        else:
            # POSIX rename replaces the link entry, never its target.
            guard.publish((INDEX_DIR, f"{INDEX_FILE}.staging"), (INDEX_DIR, INDEX_FILE))
            assert not (cache / INDEX_FILE).is_symlink()
            assert (cache / INDEX_FILE).read_bytes() == b"NEW"
        assert list(outside.iterdir()) == []
    finally:
        guard.close()


def test_publish_refuses_a_temporary_replaced_by_a_link(tmp_path):
    """The temporary file must be reopened without following a planted link.

    ``publish`` reopens the temporary file by name in order to rename it by handle. If
    that reopen followed a link planted at the temporary name, the rename would move
    the outside target into the project instead of publishing our own bytes.

    The link used here is a junction because Windows only lets an elevated process (or
    Developer Mode) create a *file* symlink, which is the variant that would otherwise
    be followed. Access rules already refuse renaming a directory opened without
    FILE_FLAG_BACKUP_SEMANTICS, so the junction case is a regression guard rather than a
    demonstrated bypass; the symlink variant is what the OPEN_REPARSE_POINT flag closes.
    """
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    cache = project / INDEX_DIR
    cache.mkdir()
    (cache / INDEX_FILE).write_bytes(b"OLD")
    (outside / "victim.txt").write_bytes(b"OUTSIDE")

    guard = AuthorizedRoot(project)
    try:
        with guard.open_for_write((INDEX_DIR, f"{INDEX_FILE}.staging")) as staging:
            staging.write_bytes(b"NEW")
        # Replace the temporary with a link to the outside file.
        os.remove(cache / f"{INDEX_FILE}.staging")
        _directory_link(cache / f"{INDEX_FILE}.staging", outside / "victim.txt")

        if os.name == "nt":
            with pytest.raises(UnsafePathError):
                guard.publish((INDEX_DIR, f"{INDEX_FILE}.staging"), (INDEX_DIR, INDEX_FILE))
            assert (cache / INDEX_FILE).read_bytes() == b"OLD"
        else:
            # POSIX moves the symlink entry, not the outside file. The cache
            # reader must refuse that entry rather than consume outside bytes.
            guard.publish((INDEX_DIR, f"{INDEX_FILE}.staging"), (INDEX_DIR, INDEX_FILE))
            assert (cache / INDEX_FILE).is_symlink()
            with pytest.raises(UnsafePathError):
                guard.read_verified((INDEX_DIR, INDEX_FILE))
        assert (outside / "victim.txt").read_bytes() == b"OUTSIDE"
        assert sorted(p.name for p in outside.iterdir()) == ["victim.txt"]
    finally:
        guard.close()


def test_validate_refuses_colon_and_nul_components(tmp_path):
    """``C:escape`` (drive-relative) and ``file:stream`` (ADS) must be refused.

    On Windows a component like ``C:escape`` resolves against the C: current
    directory of that drive, and ``name:stream`` opens an NTFS alternate data
    stream; both can escape or alias the intended location, so both are rejected
    outright before any handle is opened. NUL truncates Win32 paths.
    """
    root = AuthorizedRoot(tmp_path)
    try:
        for bad in [("C:escape",), ("dir", "file:stream"), ("nul\x00name",)]:
            with pytest.raises(UnsafePathError):
                root.open_for_write(bad)
        for bad in [("C:escape",), ("nul\x00name",)]:
            with pytest.raises(UnsafePathError):
                root.open_verified(bad)
    finally:
        root.close()
    # Nothing may have been created anywhere by the refused writes.
    assert list(tmp_path.rglob("*")) == []


def test_indexer_context_closes_guard_on_failure(tmp_path, monkeypatch):
    closed = []
    real_close = AuthorizedRoot.close

    def close(guard):
        closed.append(guard)
        real_close(guard)

    monkeypatch.setattr(AuthorizedRoot, "close", close)
    with pytest.raises(RuntimeError, match="injected"), Indexer(str(tmp_path), "", "") as idx:
        guard = idx._guard
        raise RuntimeError("injected")
    assert closed == [guard]
    assert guard._dir_fd == -1


@pytest.mark.skipif(os.name != "nt", reason="Windows canonical mutation paths")
def test_windows_create_and_publish_keep_on_disk_case(tmp_path, monkeypatch):
    import secure_fs

    project = tmp_path / "MixedCase"
    project.mkdir()
    seen = []
    real_create = secure_fs._kernel32.CreateFileW

    def record(path, *args):
        if str(path).endswith("index.staging"):
            seen.append(str(path))
        return real_create(path, *args)

    monkeypatch.setattr(secure_fs._kernel32, "CreateFileW", record)
    guard = AuthorizedRoot(project)
    try:
        with guard.open_for_write(("index.staging",)) as staging:
            staging.write_bytes(b"safe")
        guard.publish(("index.staging",), ("index.json",))
        assert guard.read_verified(("index.json",)) == b"safe"
        assert len(seen) == 2  # creation and the publication reopen
        assert all("MixedCase" in path for path in seen)
    finally:
        guard.close()


def test_indexer_constructor_failure_closes_guard(tmp_path, monkeypatch):
    closed = []
    real_close = AuthorizedRoot.close

    def close(guard):
        closed.append(guard)
        real_close(guard)

    def fail(indexer):
        raise RuntimeError("injected constructor failure")

    monkeypatch.setattr(AuthorizedRoot, "close", close)
    monkeypatch.setattr(Indexer, "_load_ignore_patterns", fail)
    with pytest.raises(RuntimeError, match="constructor failure"):
        Indexer(str(tmp_path), "", "")
    assert len(closed) == 1
    assert closed[0]._dir_fd == -1


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor lifetime")
def test_repeated_client_indexing_does_not_leak_root_descriptors(tmp_path, monkeypatch):
    from client import AceToolClient, IndexReadinessError

    descriptors = Path("/proc/self/fd")
    if not descriptors.is_dir():
        pytest.skip("requires procfs descriptor counts")
    monkeypatch.setattr(Indexer, "get_blob_names", lambda self: [])
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    before = len(list(descriptors.iterdir()))
    for _ in range(50):
        with pytest.raises(IndexReadinessError, match="no indexable"):
            client._get_blob_names(str(tmp_path))
    monkeypatch.setattr(Indexer, "get_blob_names", lambda self: ["known"])
    monkeypatch.setattr(
        client,
        "_post_json",
        lambda *args, **kwargs: {
            "unknown_blob_names": [],
            "nonindexed_blob_names": [],
            "checkpoint_not_found": False,
        },
    )
    for _ in range(50):
        assert client._get_blob_names(str(tmp_path)) == ["known"]
    assert len(list(descriptors.iterdir())) <= before


@pytest.mark.skipif(os.name != "nt", reason="Windows junction alias regression")
@pytest.mark.parametrize("operation", ["create", "publish"])
def test_write_parent_junction_cannot_be_retargeted(tmp_path, monkeypatch, operation):
    project = tmp_path / "project"
    project.mkdir()
    real = project / "real"
    (real / "nested").mkdir(parents=True)
    alias = project / "alias"
    _directory_link(alias, real)
    outside = tmp_path / "outside"
    (outside / "nested").mkdir(parents=True)
    (real / "nested" / "temp").write_bytes(b"inside")
    (outside / "nested" / "temp").write_bytes(b"OUTSIDE")
    guard = AuthorizedRoot(project)
    real_open = guard._open_dir_handle

    def retarget(parts):
        handle = real_open(parts)
        os.rmdir(alias)
        _directory_link(alias, outside)
        return handle

    monkeypatch.setattr(guard, "_open_dir_handle", retarget)
    try:
        if operation == "create":
            with guard.open_for_write(("alias", "nested", "probe")) as output:
                output.write_bytes(b"new")
            assert (real / "nested" / "probe").read_bytes() == b"new"
        else:
            guard.publish(("alias", "nested", "temp"), ("alias", "nested", "published"))
            assert (real / "nested" / "published").read_bytes() == b"inside"
        assert (outside / "nested" / "temp").read_bytes() == b"OUTSIDE"
        assert sorted(p.name for p in (outside / "nested").iterdir()) == ["temp"]
    finally:
        guard.close()
