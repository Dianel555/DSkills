"""Git-compatible ignore rules must protect both upload and local fallback."""

import gzip
import json
import os
import shutil
import subprocess

import pytest
from client import AceToolClient
from indexer import Indexer


def _make_file(root, relative, content="diagnostic_keyword = True\n"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _indexed_paths(root):
    with Indexer(str(root), "", "") as indexer:
        return {path.relative_to(root).as_posix() for path in indexer._walk_files()}


@pytest.mark.parametrize(
    ("patterns", "relative", "ignored"),
    [
        ("/secret/\n", "secret/a.py", True),
        ("/secret/\n", "nested/secret/a.py", False),
        ("generated/*\n!generated/keep.py\n", "generated/keep.py", False),
        ("generated/*\n!generated/keep.py\n", "generated/drop.py", True),
        ("build/\n!build/keep.py\n", "build/keep.py", True),
        ("*.py\n!keep.py\nkeep.py\n", "keep.py", True),
        ("*.py\n!keep.py\n*.py\n", "keep.py", True),
        ("src/**/gen.py\n", "src/a/b/gen.py", True),
        ("src/*.py\n", "src/a/b/gen.py", False),
        ("\\#report.py\n", "#report.py", True),
        ("\\!important.py\n", "!important.py", True),
        ("file.py   \n", "file.py", True),
    ],
)
def test_gitignore_pattern_semantics(tmp_path, patterns, relative, ignored):
    (tmp_path / ".gitignore").write_text(patterns, encoding="utf-8")
    _make_file(tmp_path, relative)

    assert (relative not in _indexed_paths(tmp_path)) is ignored

    # Git is the reference for ignore semantics, including ignored ancestors.
    if shutil.which("git"):
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True, capture_output=True)
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.ignorecase=false",
                "-c",
                "core.excludesFile=",
                "check-ignore",
                "--no-index",
                "-q",
                "--",
                relative,
            ],
            cwd=tmp_path,
            env=env,
            check=False,
            capture_output=True,
        )
        assert result.returncode in (0, 1), result.stderr.decode(errors="replace")
        assert (result.returncode == 0) is ignored


def test_nested_gitignore_overrides_parent_for_its_own_subtree(tmp_path):
    (tmp_path / ".gitignore").write_text("*.py\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / ".gitignore").write_text("!safe.py\nprivate.py\n", encoding="utf-8")
    for relative in ("nested/safe.py", "nested/private.py", "other/safe.py"):
        _make_file(tmp_path, relative)

    assert _indexed_paths(tmp_path) == {"nested/safe.py"}


def test_aceignore_is_an_additional_filter_and_cannot_reinclude_git_excluded_files(tmp_path):
    (tmp_path / ".gitignore").write_text("git_secret.py\n", encoding="utf-8")
    (tmp_path / ".aceignore").write_text("*.py\n!keep.py\n!git_secret.py\n", encoding="utf-8")
    for relative in ("git_secret.py", "ace_secret.py", "keep.py"):
        _make_file(tmp_path, relative)

    assert _indexed_paths(tmp_path) == {"keep.py"}


def test_local_fallback_uses_same_git_and_ace_ignore_filters(tmp_path):
    (tmp_path / ".gitignore").write_text("/git_secret.py\n", encoding="utf-8")
    (tmp_path / ".aceignore").write_text("ace_secret.py\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / ".gitignore").write_text("private.py\n", encoding="utf-8")
    for relative in ("git_secret.py", "ace_secret.py", "nested/private.py", "public.py"):
        _make_file(tmp_path, relative)

    client = AceToolClient(base_url="", token="")
    result = client._local_search(str(tmp_path), "diagnostic_keyword")
    assert [entry["file"] for entry in result["results"]] == ["public.py"]


@pytest.mark.parametrize("method", ["get_blob_names", "force_rebuild"])
@pytest.mark.parametrize("rule_source", ["root_git", "existing_nested_git", "new_nested_git", "root_ace"])
def test_repeated_indexing_refreshes_changed_ignore_rules(tmp_path, monkeypatch, method, rule_source):
    private = "src/private.py"
    _make_file(tmp_path, private)
    if rule_source == "existing_nested_git":
        (tmp_path / "src" / ".gitignore").write_text("", encoding="utf-8")
    uploads = []
    ready = set()
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as indexer:

        def upload(headers, payload):
            for blob in payload["blobs"]:
                uploads.append(blob["path"])
                ready.add(indexer._hash_blob(blob["path"], blob["content"]))
            return True

        monkeypatch.setattr(indexer, "_upload_batch_with_retry", upload)
        monkeypatch.setattr(indexer, "_upload_status", lambda headers, names, timeout: (set(names) - ready, set()))
        initial_names = indexer.get_blob_names()
        private_name = indexer._hash_blob(private, "diagnostic_keyword = True\n")
        assert private_name in initial_names and private in uploads
        uploads.clear()

        if rule_source in {"existing_nested_git", "new_nested_git"}:
            ignore_file, pattern = tmp_path / "src" / ".gitignore", "private.py\n"
        elif rule_source == "root_ace":
            ignore_file, pattern = tmp_path / ".aceignore", f"{private}\n"
        else:
            ignore_file, pattern = tmp_path / ".gitignore", f"{private}\n"
        ignore_file.write_text(pattern, encoding="utf-8")
        _make_file(tmp_path, "src/public.py")

        names = getattr(indexer, method)()
        cache = json.loads(gzip.decompress(indexer.index_path.read_bytes()))
        assert private_name not in names
        assert private not in uploads
        assert all(entry["path"] != private for entry in cache["entries"].values())
        assert "src/public.py" in uploads


def test_repeated_walk_refreshes_ignore_rules(tmp_path):
    _make_file(tmp_path, "src/private.py")
    with Indexer(str(tmp_path), "", "") as indexer:
        assert [p.relative_to(tmp_path).as_posix() for p in indexer._walk_files()] == ["src/private.py"]
        (tmp_path / "src" / ".gitignore").write_text("private.py\n", encoding="utf-8")
        assert list(indexer._walk_files()) == []


@pytest.mark.skipif(os.name == "nt", reason="file symlinks may require elevation on Windows")
def test_nested_gitignore_symlink_is_not_followed(tmp_path):
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    outside = tmp_path / "outside-ignore"
    outside.write_text("secret.py\n", encoding="utf-8")
    (nested / ".gitignore").symlink_to(outside)
    _make_file(root, "nested/secret.py")

    assert _indexed_paths(root) == {"nested/secret.py"}
