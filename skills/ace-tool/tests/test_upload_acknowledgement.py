"""An HTTP 200 must confirm every uploaded blob before it enters the cache."""

import json

import httpx
import pytest
from indexer import Indexer, IndexUploadError
from templates import INDEX_DIR, INDEX_FILE


@pytest.mark.parametrize("response_kind", ["missing", "empty", "short", "duplicate", "mismatch", "invalid-type", "malformed-json"])
def test_unacknowledged_upload_never_becomes_cached(tmp_path, monkeypatch, response_kind):
    (tmp_path / "first.py").write_text("one = 1\n", encoding="utf-8")
    (tmp_path / "second.py").write_text("two = 2\n", encoding="utf-8")

    def handler(request):
        sent = json.loads(request.content)["blobs"]
        names = [Indexer._hash_blob(item["path"], item["content"]) for item in sent]
        response = {
            "missing": {},
            "empty": {"blob_names": []},
            "short": {"blob_names": names[:1]},
            "duplicate": {"blob_names": [names[0], names[0]]},
            "mismatch": {"blob_names": [names[0], "other-id"]},
            "invalid-type": {"blob_names": "not-a-list"},
        }
        if response_kind == "malformed-json":
            return httpx.Response(200, text="not json", request=request)
        return httpx.Response(200, json=response[response_kind], request=request)

    real_client = httpx.Client
    monkeypatch.setattr("indexer.httpx.Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler)))
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as indexer:
        with pytest.raises(ValueError, match="upload"):
            indexer.get_blob_names()
        assert not (tmp_path / INDEX_DIR / INDEX_FILE).exists()


def test_reordered_matching_acknowledgements_are_accepted(tmp_path, monkeypatch):
    for name in ("first.py", "second.py"):
        (tmp_path / name).write_text(f"name = {name!r}\n", encoding="utf-8")

    def handler(request):
        sent = json.loads(request.content)["blobs"]
        names = [Indexer._hash_blob(item["path"], item["content"]) for item in sent]
        return httpx.Response(200, json={"blob_names": list(reversed(names))}, request=request)

    real_client = httpx.Client
    monkeypatch.setattr("indexer.httpx.Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler)))
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as indexer:
        names = indexer.get_blob_names()
        assert len(names) == 2
        assert (tmp_path / INDEX_DIR / INDEX_FILE).exists()


def test_partial_upload_failure_does_not_return_stale_entries_or_commit_cache(tmp_path, monkeypatch):
    (tmp_path / "deleted.py").write_text("old = 1\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("old = 2\n", encoding="utf-8")
    with Indexer(str(tmp_path), "", "") as initial:
        stale_names = set(initial.get_blob_names())
    cache = tmp_path / INDEX_DIR / INDEX_FILE
    before = cache.read_bytes()
    (tmp_path / "deleted.py").unlink()
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    for number in range(31):
        (tmp_path / f"new_{number}.py").write_text(f"value = {number}\n", encoding="utf-8")

    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as indexer:
        batches = []
        def fail_second(headers, payload):
            batches.append(payload["blobs"])
            return len(batches) != 2

        monkeypatch.setattr(indexer, "_upload_batch_with_retry", fail_second)
        with pytest.raises(ValueError, match="upload"):
            indexer.get_blob_names()
        assert [len(batch) for batch in batches] == [30, 1]
        assert cache.read_bytes() == before

        # Reusing this instance must rescan/re-upload, not treat its failed
        # candidate state as a successful cached index.
        batches.clear()
        monkeypatch.setattr(indexer, "_upload_batch_with_retry", lambda headers, payload: batches.append(payload["blobs"]) or True)
        names = indexer.get_blob_names()
        assert [len(batch) for batch in batches] == [30, 1]
        assert len(names) == 31
        assert not (set(names) & stale_names)


def test_upload_http_error_is_explicit_and_does_not_leave_candidate_cached(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("value = 1\n", encoding="utf-8")
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as indexer:
        response = httpx.Response(400, request=httpx.Request("POST", "https://example.invalid/batch-upload"))
        def fail(*args):
            raise httpx.HTTPStatusError("bad request", request=response.request, response=response)
        monkeypatch.setattr(indexer, "_upload_batch_with_retry", fail)
        with pytest.raises(IndexUploadError, match="upload"):
            indexer.get_blob_names()
        assert indexer._index is None
        assert not (tmp_path / INDEX_DIR / INDEX_FILE).exists()


def test_upload_stops_after_failed_batch(tmp_path, monkeypatch):
    for number in range(61):
        (tmp_path / f"new_{number}.py").write_text(f"value = {number}\n", encoding="utf-8")
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as indexer:
        calls = []
        monkeypatch.setattr(indexer, "_upload_batch_with_retry", lambda headers, payload: calls.append(payload) or False)
        with pytest.raises(ValueError, match="upload"):
            indexer.get_blob_names()
        assert len(calls) == 1
