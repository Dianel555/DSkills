"""Regression tests for diagnose fixes: URL consistency, unknown-blobs self-heal, cache hierarchy."""

import gzip
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ace_cli  # noqa: E402
from client import AceToolClient, build_api_url  # noqa: E402
from indexer import Indexer, IndexRebuildError, ProjectIndex  # noqa: E402
from templates import INDEX_DIR, INDEX_FILE  # noqa: E402
from utils import build_api_url as utils_build_api_url  # noqa: E402


def _write_index(root: Path):
    p = root / INDEX_DIR / INDEX_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump({"entries": {}, "last_indexed": 1.0}, f)
    return p


# --- Problem 1: URL construction consistency ---

def test_build_api_url_lives_in_utils_and_reexported():
    assert build_api_url is utils_build_api_url


@pytest.mark.parametrize("base,path,expected", [
    ("https://api.example.com", "/v1/messages", "https://api.example.com/v1/messages"),
    ("https://api.example.com/v1", "/v1/messages", "https://api.example.com/v1/messages"),
    ("https://proxy.com/v1beta", "/v1/messages", "https://proxy.com/v1beta/messages"),
    ("https://api.example.com/vertex", "/v1/messages", "https://api.example.com/vertex/v1/messages"),
    ("https://api.example.com", "v1/messages", "https://api.example.com/v1/messages"),
    ("https://api.example.com/v1/", "/v1/messages", "https://api.example.com/v1/messages"),
    ("https://h/v1", "/batch-upload", "https://h/v1/batch-upload"),
])
def test_build_api_url_version_handling(base, path, expected):
    assert build_api_url(base, path) == expected


def test_upload_url_uses_build_api_url(tmp_path, monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, **kw):
            captured["url"] = url
            return FakeResp()

    monkeypatch.setattr("indexer.httpx.Client", FakeClient)
    idx = Indexer(str(tmp_path), "https://h/v1", "tok")
    assert idx._upload_batch_with_retry({}, {"blobs": []})
    assert captured["url"] == build_api_url("https://h/v1", "/batch-upload")


# --- Problem 2: 400 unknown blobs self-heal ---

def test_unknown_blobs_triggers_rebuild_and_single_retry(monkeypatch):
    c = AceToolClient(base_url="https://h", token="tok")
    calls = {"post": 0, "rebuild": 0}

    monkeypatch.setattr("client.Indexer.__init__", lambda self, *a, **k: None)
    monkeypatch.setattr("client.Indexer.get_blob_names", lambda self: ["stale"])

    def fake_rebuild(self):
        calls["rebuild"] += 1
        return ["fresh"]

    monkeypatch.setattr("client.Indexer.force_rebuild", fake_rebuild, raising=False)

    def fake_post(url, payload, *, headers, provider="API", timeout=None):
        calls["post"] += 1
        if calls["post"] == 1:
            resp = httpx.Response(400, text="unknown blobs: ['stale']")
            raise httpx.HTTPStatusError("400 Bad Request", request=None, response=resp)
        assert payload["blobs"]["added_blobs"] == ["fresh"]
        return {"formatted_retrieval": "ok"}

    monkeypatch.setattr(c, "_post_json", fake_post)

    result = c._remote_search("/proj", "query")
    assert result["results"] == "ok"
    assert calls["rebuild"] == 1
    assert calls["post"] == 2


def test_unknown_blobs_no_infinite_retry(monkeypatch):
    c = AceToolClient(base_url="https://h", token="tok")
    calls = {"post": 0}

    monkeypatch.setattr("client.Indexer.__init__", lambda self, *a, **k: None)
    monkeypatch.setattr("client.Indexer.get_blob_names", lambda self: ["stale"])
    monkeypatch.setattr("client.Indexer.force_rebuild", lambda self: ["fresh"], raising=False)

    def fake_post(url, payload, *, headers, provider="API", timeout=None):
        calls["post"] += 1
        resp = httpx.Response(400, text="unknown blobs")
        raise httpx.HTTPStatusError("400 Bad Request", request=None, response=resp)

    monkeypatch.setattr(c, "_post_json", fake_post)

    with pytest.raises(httpx.HTTPStatusError):
        c._remote_search("/proj", "query")
    assert calls["post"] == 2


def test_other_400_errors_not_swallowed(monkeypatch):
    c = AceToolClient(base_url="https://h", token="tok")
    calls = {"post": 0, "rebuild": 0}

    monkeypatch.setattr("client.Indexer.__init__", lambda self, *a, **k: None)
    monkeypatch.setattr("client.Indexer.get_blob_names", lambda self: ["a"])
    monkeypatch.setattr("client.Indexer.force_rebuild", lambda self: calls.__setitem__("rebuild", calls["rebuild"] + 1) or [], raising=False)

    def fake_post(url, payload, *, headers, provider="API", timeout=None):
        calls["post"] += 1
        resp = httpx.Response(400, text="malformed request")
        raise httpx.HTTPStatusError("400 Bad Request", request=None, response=resp)

    monkeypatch.setattr(c, "_post_json", fake_post)

    with pytest.raises(httpx.HTTPStatusError):
        c._remote_search("/proj", "query")
    assert calls["post"] == 1
    assert calls["rebuild"] == 0


# --- Problem 3: cache hierarchy ---

def test_child_inherits_nearest_ancestor_cache(tmp_path):
    parent = tmp_path / "parent"
    child = parent / "sub"
    child.mkdir(parents=True)
    _write_index(parent)

    idx = Indexer(str(child), "https://h", "tok")
    assert idx.root == parent.resolve()
    assert idx.index_path == parent.resolve() / INDEX_DIR / INDEX_FILE


def test_own_cache_preferred_over_ancestor(tmp_path):
    parent = tmp_path / "p2"
    child = parent / "sub"
    child.mkdir(parents=True)
    _write_index(parent)
    _write_index(child)

    idx = Indexer(str(child), "https://h", "tok")
    assert idx.root == child.resolve()


def test_no_cache_anywhere_uses_project_root(tmp_path):
    proj = tmp_path / "fresh"
    proj.mkdir()

    idx = Indexer(str(proj), "https://h", "tok")
    assert idx.root == proj.resolve()


def test_nearest_ancestor_wins_over_farther(tmp_path):
    outer = tmp_path / "repo"
    nearest = outer / "packages"
    child = nearest / "service"
    child.mkdir(parents=True)
    _write_index(outer)
    _write_index(nearest)

    idx = Indexer(str(child), "https://h", "tok")
    assert idx.root == nearest.resolve()


def test_home_cache_not_inherited(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _write_index(tmp_path)
    proj = tmp_path / "work" / "proj"
    proj.mkdir(parents=True)

    idx = Indexer(str(proj), "https://h", "tok")
    assert idx.root == proj.resolve()


def test_parent_indexing_absorbs_child_cache(tmp_path):
    root = tmp_path / "proj"
    sub = root / "pkg"
    sub.mkdir(parents=True)
    (root / "m.py").write_text("a = 1\n", encoding="utf-8")
    (sub / "n.py").write_text("b = 2\n", encoding="utf-8")
    _write_index(root)
    _write_index(sub)

    idx = Indexer(str(root), "", "")  # empty base_url: upload step is a no-op
    names = idx.get_blob_names()

    assert not (sub / INDEX_DIR).exists()
    assert (root / INDEX_DIR / INDEX_FILE).exists()
    assert len(names) == 2


# --- Review fixes: absorb boundaries, retry amplification, CLI transparency ---

def test_child_cache_kept_when_root_never_saves_index(tmp_path):
    root = tmp_path / "empty-root"
    sub = root / "pkg"
    sub.mkdir(parents=True)
    _write_index(sub)  # only a child cache, no eligible source files anywhere

    idx = Indexer(str(root), "", "")
    names = idx.get_blob_names()

    assert names == []
    assert not (root / INDEX_DIR / INDEX_FILE).exists()
    assert (sub / INDEX_DIR / INDEX_FILE).exists()


def test_ignored_subtree_cache_not_absorbed(tmp_path):
    root = tmp_path / "proj2"
    ignored = root / "legacy"
    ignored.mkdir(parents=True)
    (root / "m.py").write_text("a = 1\n", encoding="utf-8")
    (ignored / "old.py").write_text("z = 9\n", encoding="utf-8")
    (root / ".gitignore").write_text("legacy/\n", encoding="utf-8")
    _write_index(ignored)

    idx = Indexer(str(root), "", "")
    names = idx.get_blob_names()

    assert (ignored / INDEX_DIR / INDEX_FILE).exists()  # not covered by parent scan
    assert len(names) == 1  # only m.py


def test_force_rebuild_raises_on_upload_failure(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    idx = Indexer(str(tmp_path), "https://h", "tok")
    monkeypatch.setattr(idx, "_upload_pending", lambda: False)

    with pytest.raises(IndexRebuildError):
        idx.force_rebuild()


def test_rebuild_failure_not_retried_by_enhance(monkeypatch):
    monkeypatch.delenv("PROMPT_ENHANCER_ENDPOINT", raising=False)
    monkeypatch.delenv("ACE_ENHANCER_ENDPOINT", raising=False)
    c = AceToolClient(base_url="https://h", token="tok", endpoint="claude")
    calls = {"n": 0}

    def fake_third_party(prompt, history, project_root=None):
        calls["n"] += 1
        raise IndexRebuildError("rebuild upload failed")

    monkeypatch.setattr(c, "_call_third_party_api", fake_third_party)

    with pytest.raises(IndexRebuildError):
        c.enhance_prompt("p", "", "/proj")
    assert calls["n"] == 1  # ValueError subclass: excluded from tenacity retry


def test_cmd_index_reports_effective_root(tmp_path, monkeypatch, capsys):
    parent = tmp_path / "top"
    child = parent / "sub"
    child.mkdir(parents=True)
    _write_index(parent)

    monkeypatch.setattr(
        ace_cli, "AceToolClient",
        lambda *a: SimpleNamespace(base_url="https://h", token="tok"),
    )

    def fake_names(self):
        self._index = ProjectIndex()
        return []

    monkeypatch.setattr(ace_cli.Indexer, "get_blob_names", fake_names)

    ace_cli.cmd_index(SimpleNamespace(api_url=None, token=None, endpoint=None, project_root=str(child)))
    out = json.loads(capsys.readouterr().out)
    assert out["effective_root"] == str(parent.resolve())
    assert out["project_root"] == str(child)


# --- Concurrency race: tolerate-and-converge (absorb vs concurrent child save) ---

def test_save_index_tolerates_dir_deleted_mid_write(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    idx = Indexer(str(tmp_path), "", "")
    idx._load_index()
    idx._scan_and_update()

    real_mkdir = Path.mkdir

    def mkdir_then_vanish(self, *a, **k):
        real_mkdir(self, *a, **k)
        shutil.rmtree(self)  # concurrent ancestor absorbs the dir right after mkdir

    monkeypatch.setattr(Path, "mkdir", mkdir_then_vanish)

    assert idx._save_index() is False  # abandoned, not crashed
    assert not idx.index_path.exists()


def test_save_index_returns_true_on_success(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    idx = Indexer(str(tmp_path), "", "")
    idx._load_index()
    idx._scan_and_update()

    assert idx._save_index() is True
    assert idx.index_path.is_file()


def test_no_absorb_when_save_abandoned(tmp_path, monkeypatch):
    root = tmp_path / "proj3"
    sub = root / "pkg"
    sub.mkdir(parents=True)
    (root / "m.py").write_text("a = 1\n", encoding="utf-8")
    (sub / "n.py").write_text("b = 2\n", encoding="utf-8")
    _write_index(root)
    _write_index(sub)

    idx = Indexer(str(root), "", "")
    monkeypatch.setattr(idx, "_save_index", lambda: False)  # own cache absorbed by grandparent
    idx.get_blob_names()

    assert (sub / INDEX_DIR / INDEX_FILE).exists()  # no cascading deletion


def test_force_rebuild_skips_absorb_when_save_abandoned(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "n.py").write_text("b = 2\n", encoding="utf-8")
    _write_index(sub)

    idx = Indexer(str(tmp_path), "", "")
    monkeypatch.setattr(idx, "_save_index", lambda: False)
    names = idx.force_rebuild()  # upload is a no-op (empty base_url) -> success

    assert names  # in-memory result still returned
    assert (sub / INDEX_DIR / INDEX_FILE).exists()


def test_absorb_skips_child_on_rmtree_failure(tmp_path, monkeypatch):
    root = tmp_path / "proj4"
    sub = root / "pkg"
    sub.mkdir(parents=True)
    (root / "m.py").write_text("a = 1\n", encoding="utf-8")
    (sub / "n.py").write_text("b = 2\n", encoding="utf-8")
    _write_index(root)
    _write_index(sub)

    def locked_rmtree(p):
        raise PermissionError(13, "file in use")  # Windows open-handle / racy delete

    monkeypatch.setattr("indexer.shutil.rmtree", locked_rmtree)
    idx = Indexer(str(root), "", "")
    names = idx.get_blob_names()  # must not raise

    assert (sub / INDEX_DIR / INDEX_FILE).exists()  # skipped, retried next run
    assert len(names) == 2


def test_save_index_tmp_is_per_process(tmp_path, monkeypatch):
    captured = {}
    real_replace = Path.replace

    def spy_replace(self, target):
        captured["tmp"] = self.name
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy_replace)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    idx = Indexer(str(tmp_path), "", "")
    idx._load_index()
    idx._scan_and_update()

    assert idx._save_index() is True
    assert captured["tmp"] == f"{INDEX_FILE}.{os.getpid()}.tmp"  # no shared-name torn writes
    assert list((tmp_path / INDEX_DIR).glob("*.tmp")) == []  # renamed away, no litter


def test_save_index_retries_transient_replace_permission_error(tmp_path, monkeypatch):
    attempts = {"n": 0}
    real_replace = Path.replace

    def briefly_locked_replace(self, target):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise PermissionError(5, "target open in a concurrent reader")  # WinError 5
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", briefly_locked_replace)
    monkeypatch.setattr("indexer.time.sleep", lambda s: None)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    idx = Indexer(str(tmp_path), "", "")
    idx._load_index()
    idx._scan_and_update()

    assert idx._save_index() is True
    assert attempts["n"] == 2
    assert idx.index_path.is_file()


def test_save_index_propagates_persistent_permission_error(tmp_path, monkeypatch):
    def always_locked_replace(self, target):
        raise PermissionError(5, "acl denies write")

    monkeypatch.setattr(Path, "replace", always_locked_replace)
    monkeypatch.setattr("indexer.time.sleep", lambda s: None)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    idx = Indexer(str(tmp_path), "", "")
    idx._load_index()
    idx._scan_and_update()

    with pytest.raises(PermissionError):  # genuine ACL problems must surface
        idx._save_index()
