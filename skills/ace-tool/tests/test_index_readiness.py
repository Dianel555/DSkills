"""Retrieval must not confuse asynchronous indexing with an empty result."""

import time
from types import SimpleNamespace

import httpx
import pytest
from client import AceToolClient
from indexer import Indexer, IndexUploadError


def _status(unknown=(), pending=(), checkpoint_not_found=False):
    return {
        "unknown_blob_names": list(unknown),
        "nonindexed_blob_names": list(pending),
        "checkpoint_not_found": checkpoint_not_found,
    }


class FakeIndexer:
    instances = []
    initial = ["old"]
    rebuilt = ["fresh"]

    def __init__(self, *args):
        self.rebuilds = 0
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get_blob_names(self):
        return list(self.initial)

    def force_rebuild(self):
        self.rebuilds += 1
        return list(self.rebuilt)


@pytest.fixture
def fake_indexer(monkeypatch):
    FakeIndexer.instances = []
    FakeIndexer.initial = ["old"]
    FakeIndexer.rebuilt = ["fresh"]
    monkeypatch.setattr("client.Indexer", FakeIndexer)
    return FakeIndexer


def test_pending_index_is_polled_before_retrieval(fake_indexer, monkeypatch):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    calls = []
    statuses = iter([_status(pending=["old"]), _status()])

    def post(url, payload, **kwargs):
        calls.append((url, payload))
        if url.endswith("/agents/blob-status"):
            return next(statuses)
        assert url.endswith("/agents/codebase-retrieval")
        return {"formatted_retrieval": "ready result"}

    monkeypatch.setattr(client, "_post_json", post)
    monkeypatch.setattr("client.time", SimpleNamespace(monotonic=time.monotonic, sleep=lambda seconds: None), raising=False)
    result = client._remote_search("workspace", "query")

    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["blob-status", "blob-status", "codebase-retrieval"]
    assert calls[0][1]["blobs"]["added_blobs"] == ["old"]
    assert result["results"] == "ready result"


def test_unknown_blob_rebuilds_once_then_waits_for_new_names(fake_indexer, monkeypatch):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    statuses = iter([_status(unknown=["old"]), _status(pending=["fresh"]), _status()])
    calls = []

    def post(url, payload, **kwargs):
        calls.append((url, list(payload["blobs"]["added_blobs"])))
        if url.endswith("/agents/blob-status"):
            return next(statuses)
        return {"formatted_retrieval": "ready"}

    monkeypatch.setattr(client, "_post_json", post)
    monkeypatch.setattr("client.time", SimpleNamespace(monotonic=time.monotonic, sleep=lambda seconds: None), raising=False)
    assert client._remote_search("workspace", "query")["results"] == "ready"
    assert fake_indexer.instances[0].rebuilds == 1
    assert [names for _, names in calls] == [["old"], ["fresh"], ["fresh"], ["fresh"]]


def test_unknown_blob_after_rebuild_fails_without_loop(fake_indexer, monkeypatch):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    statuses = iter([_status(unknown=["old"]), _status(unknown=["fresh"])])
    monkeypatch.setattr(client, "_post_json", lambda *args, **kwargs: next(statuses))
    with pytest.raises(ValueError, match="unknown"):
        client._remote_search("workspace", "query")
    assert fake_indexer.instances[0].rebuilds == 1


def test_gc_between_ready_and_retrieval_rebuilds_and_checks_readiness_again(fake_indexer, monkeypatch):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    calls = []
    request = httpx.Request("POST", "https://example.invalid/agents/codebase-retrieval")
    response = httpx.Response(400, text="unknown blobs", request=request)

    def post(url, payload, **kwargs):
        calls.append((url, list(payload["blobs"]["added_blobs"])))
        if url.endswith("/agents/blob-status"):
            return _status()
        if sum(endpoint.endswith("/agents/codebase-retrieval") for endpoint, _ in calls) == 1:
            raise httpx.HTTPStatusError("unknown blobs", request=request, response=response)
        return {"formatted_retrieval": "recovered"}

    monkeypatch.setattr(client, "_post_json", post)
    assert client._remote_search("workspace", "query")["results"] == "recovered"
    assert fake_indexer.instances[0].rebuilds == 1
    assert [names for _, names in calls] == [["old"], ["old"], ["fresh"], ["fresh"]]


def test_unknown_on_retrieval_retry_is_explicit_and_not_locally_suppressed(fake_indexer, monkeypatch):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    request = httpx.Request("POST", "https://example.invalid/agents/codebase-retrieval")
    response = httpx.Response(400, text="unknown blobs", request=request)
    def post(url, payload, **kwargs):
        if url.endswith("/agents/blob-status"):
            return _status()
        raise httpx.HTTPStatusError("unknown blobs", request=request, response=response)
    monkeypatch.setattr(client, "_post_json", post)
    monkeypatch.setattr(client, "_local_search", lambda *args: pytest.fail("unresolved unknown blob was hidden"))
    with pytest.raises(ValueError, match="unknown"):
        client.search_context("workspace", "query")
    assert fake_indexer.instances[0].rebuilds == 1


def test_pending_timeout_is_explicit_and_not_retried_or_locally_suppressed(fake_indexer, monkeypatch):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    calls = []
    clock = [0.0]
    monkeypatch.setattr("client.READINESS_TIMEOUT", 2.0, raising=False)
    monkeypatch.setattr("client.READINESS_POLL_INTERVAL", 1.0, raising=False)
    monkeypatch.setattr(
        "client.time",
        SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds)),
        raising=False,
    )

    def post(url, payload, **kwargs):
        calls.append(url)
        assert url.endswith("/agents/blob-status")
        return _status(pending=["old"])

    monkeypatch.setattr(client, "_post_json", post)
    monkeypatch.setattr(client, "_local_search", lambda *args: pytest.fail("readiness failure was hidden"))
    with pytest.raises(ValueError, match="(?i)(timeout|timed out)"):
        client.search_context("workspace", "query")
    assert len(calls) == 2
    assert clock[0] == 2.0


@pytest.mark.parametrize("response", [None, {}, {"unknown_blob_names": [], "nonindexed_blob_names": "pending", "checkpoint_not_found": False}, _status(unknown=["unrequested"]), _status(checkpoint_not_found=True)])
def test_malformed_or_invalid_status_cannot_be_treated_as_ready(fake_indexer, monkeypatch, response):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    calls = []
    monkeypatch.setattr(client, "_post_json", lambda url, payload, **kwargs: calls.append(url) or response)
    with pytest.raises(ValueError, match="(?i)(readiness|status|checkpoint)"):
        client._remote_search("workspace", "query")
    assert len(calls) == 1


def test_unsupported_status_endpoint_is_explicit_error(fake_indexer, monkeypatch):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    response = httpx.Response(404, request=httpx.Request("POST", "https://example.invalid/agents/blob-status"))
    def post(*args, **kwargs):
        raise httpx.HTTPStatusError("not found", request=response.request, response=response)
    monkeypatch.setattr(client, "_post_json", post)
    monkeypatch.setattr(client, "_local_search", lambda *args: pytest.fail("unsupported status was hidden"))
    with pytest.raises(ValueError, match="(?i)(readiness|status|unsupported)"):
        client.search_context("workspace", "query")


def test_empty_scope_never_sends_unscoped_retrieval(fake_indexer, monkeypatch):
    fake_indexer.initial = []
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    monkeypatch.setattr(client, "_post_json", lambda *args, **kwargs: pytest.fail("empty workspace must not call the server"))
    result = client._remote_search("workspace", "query")
    assert result["results"] == ""
    assert result["blob_count"] == 0


def test_cached_unchanged_blobs_are_still_checked_for_readiness(tmp_path, monkeypatch):
    (tmp_path / "example.py").write_text("def cached(): pass\n", encoding="utf-8")
    with Indexer(str(tmp_path), "", "") as indexer:
        cached = indexer.get_blob_names()
    assert cached
    monkeypatch.setattr(Indexer, "_upload_pending", lambda *args: pytest.fail("unchanged file reuploaded"))
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    calls = []
    def post(url, payload, **kwargs):
        calls.append((url, payload["blobs"]["added_blobs"]))
        return _status() if url.endswith("/agents/blob-status") else {"formatted_retrieval": "cached result"}
    monkeypatch.setattr(client, "_post_json", post)
    assert client._remote_search(str(tmp_path), "cached")["results"] == "cached result"
    assert [names for _, names in calls] == [cached, cached]
    assert calls[0][0].endswith("/agents/blob-status")


def test_ready_response_arriving_after_deadline_is_not_accepted(fake_indexer, monkeypatch):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    clock = [0.0]
    monkeypatch.setattr("client.READINESS_TIMEOUT", 2.0, raising=False)
    monkeypatch.setattr("client.time", SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda _: None), raising=False)
    def post(url, payload, **kwargs):
        assert url.endswith("/agents/blob-status")
        clock[0] = 2.1
        return _status()
    monkeypatch.setattr(client, "_post_json", post)
    with pytest.raises(ValueError, match="(?i)(timeout|timed out)"):
        client._remote_search("workspace", "query")


def test_unknown_rebuild_to_empty_scope_does_not_send_retrieval(fake_indexer, monkeypatch):
    fake_indexer.rebuilt = []
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    calls = []
    def post(url, payload, **kwargs):
        calls.append(url)
        assert url.endswith("/agents/blob-status")
        return _status(unknown=["old"])
    monkeypatch.setattr(client, "_post_json", post)
    result = client._remote_search("workspace", "query")
    assert result["blob_count"] == 0
    assert len(calls) == 1
    assert fake_indexer.instances[0].rebuilds == 1


def test_legacy_enhancement_rejects_empty_project_scope(fake_indexer, monkeypatch):
    fake_indexer.initial = []
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: pytest.fail("sent an unscoped request"))
    with pytest.raises(ValueError, match="(?i)(empty|no indexable)"):
        client._call_old_endpoint("hello", [], "workspace")


def test_index_command_waits_for_readiness_before_reporting(fake_indexer, monkeypatch, capsys):
    import ace_cli
    fake_indexer.root = "workspace"
    fake_indexer._index = SimpleNamespace(last_indexed=0)
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    calls = []
    monkeypatch.setattr(client, "_post_json", lambda url, payload, **kwargs: calls.append(url) or _status())
    monkeypatch.setattr(ace_cli, "AceToolClient", lambda *args: client)
    monkeypatch.setattr(ace_cli, "Indexer", fake_indexer)
    args = SimpleNamespace(api_url=None, token=None, endpoint=None, project_root="workspace")
    ace_cli.cmd_index(args)
    assert len(calls) == 1 and calls[0].endswith("/agents/blob-status")
    assert '"total_blobs": 1' in capsys.readouterr().out


def test_enhancement_retrieval_does_not_hide_readiness_failure(fake_indexer, monkeypatch):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    monkeypatch.setattr(client, "_post_json", lambda *args, **kwargs: {})
    with pytest.raises(ValueError, match="(?i)(readiness|status)"):
        client._get_retrieval_context("workspace", "query")
    with pytest.raises(ValueError, match="(?i)(readiness|status)"):
        client._get_blob_names("workspace")


def test_upload_failure_is_not_silently_replaced_by_local_search(monkeypatch):
    client = AceToolClient(base_url="https://example.invalid", token="dummy")
    def fail(*args):
        raise IndexUploadError("upload failed")
    monkeypatch.setattr(client, "_remote_search", fail)
    monkeypatch.setattr(client, "_local_search", lambda *args: pytest.fail("upload failure was hidden"))
    with pytest.raises(IndexUploadError):
        client.search_context("workspace", "query")
