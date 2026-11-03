"""Candidate regression tests for slow synchronous upload and batching."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import indexer
import pathspec
import pytest
from indexer import Indexer, IndexUploadError

IndexUploadOutcomeUnknownError = getattr(indexer, "IndexUploadOutcomeUnknownError", IndexUploadError)


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def fake_clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(
        indexer, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep, time=lambda: 0.0)
    )
    return clock


def install_transport(monkeypatch, handler):
    real_client = httpx.Client
    timeouts = []

    def factory(**kwargs):
        timeouts.append(kwargs.get("timeout"))
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(indexer.httpx, "Client", factory)
    return timeouts


def status(request, unknown=None, pending=None):
    return httpx.Response(
        200,
        request=request,
        json={
            "unknown_blob_names": unknown or [],
            "nonindexed_blob_names": pending or [],
            "checkpoint_not_found": False,
        },
    )


@pytest.mark.parametrize("outcome", ["read", "write", "disconnect", "502", "503", "429"])
def test_ambiguous_upload_waits_until_ready_without_resending(tmp_path, monkeypatch, fake_clock, outcome):
    payload = {"blobs": [{"path": "one.py", "content": "x=1\n"}]}
    name = Indexer._hash_blob("one.py", "x=1\n")
    uploads, statuses = [], []

    def handler(request):
        if request.url.path == "/batch-upload":
            uploads.append(json.loads(request.content))
            if outcome == "read":
                raise httpx.ReadTimeout("response lost", request=request)
            if outcome == "write":
                raise httpx.WriteTimeout("send interrupted", request=request)
            if outcome == "disconnect":
                raise httpx.RemoteProtocolError("lost response", request=request)
            return httpx.Response(int(outcome), request=request)
        statuses.append(json.loads(request.content))
        if len(statuses) == 1:
            return status(request, unknown=[name])
        if len(statuses) == 2:
            return status(request, pending=[name])
        return status(request)

    timeouts = install_transport(monkeypatch, handler)
    monkeypatch.setenv("ACE_UPLOAD_READ_TIMEOUT_SECONDS", "340")
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx:
        assert idx._upload_batch_with_retry({}, payload)
    assert uploads == [payload]
    assert len(statuses) == 3
    assert fake_clock.now == (7 if outcome == "429" else 2)
    assert timeouts[0].read == 340
    assert timeouts[0].connect == 15
    assert timeouts[0].write == 60


@pytest.mark.parametrize("kind", ["unknown", "pending", "unsupported", "invalid", "foreign", "transport"])
def test_unresolved_upload_is_explicit_and_never_replayed(tmp_path, monkeypatch, fake_clock, kind):
    payload = {"blobs": [{"path": "one.py", "content": "x=1\n"}]}
    name = Indexer._hash_blob("one.py", "x=1\n")
    uploads = []
    monkeypatch.setattr(indexer, "UPLOAD_RECONCILE_TIMEOUT", 2.0)

    def handler(request):
        if request.url.path == "/batch-upload":
            uploads.append(1)
            raise httpx.ReadTimeout("response lost", request=request)
        if kind == "unknown":
            return status(request, unknown=[name])
        if kind == "pending":
            return status(request, pending=[name])
        if kind == "unsupported":
            return httpx.Response(404, request=request)
        if kind == "transport":
            raise httpx.ReadTimeout("status lost", request=request)
        if kind == "foreign":
            return status(request, pending=["foreign"])
        return httpx.Response(200, request=request, json={"unknown_blob_names": []})

    install_transport(monkeypatch, handler)
    with (
        Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx,
        pytest.raises(IndexUploadOutcomeUnknownError, match="unknown"),
    ):
        idx._upload_batch_with_retry({}, payload)
    assert len(uploads) == 1


@pytest.mark.parametrize("error", [httpx.UnsupportedProtocol, httpx.LocalProtocolError])
def test_invalid_local_status_protocol_is_not_reclassified_as_unknown(tmp_path, monkeypatch, error):
    def handler(request):
        raise error("invalid local protocol")

    install_transport(monkeypatch, handler)
    with (
        Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx,
        pytest.raises(IndexUploadError, match="local protocol") as caught,
    ):
        idx._upload_status({}, ["0" * 64], 2.0)
    assert not isinstance(caught.value, IndexUploadOutcomeUnknownError)


@pytest.mark.parametrize("error", [httpx.ConnectTimeout, httpx.ConnectError, httpx.PoolTimeout])
def test_not_connected_may_retry_with_finite_budget(tmp_path, monkeypatch, fake_clock, error):
    payload = {"blobs": [{"path": "one.py", "content": "x=1\n"}]}
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if len(calls) == 1:
            raise error("no connection", request=request)
        return httpx.Response(200, request=request, json={"blob_names": [Indexer._hash_blob("one.py", "x=1\n")]})

    install_transport(monkeypatch, handler)
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx:
        assert idx._upload_batch_with_retry({}, payload)
    assert calls == ["/batch-upload", "/batch-upload"]
    assert fake_clock.now == 1


@pytest.mark.parametrize(
    "name,value",
    [
        ("ACE_UPLOAD_READ_TIMEOUT_SECONDS", "NaN"),
        ("ACE_UPLOAD_READ_TIMEOUT_SECONDS", "inf"),
        ("ACE_UPLOAD_READ_TIMEOUT_SECONDS", "0"),
        ("ACE_UPLOAD_READ_TIMEOUT_SECONDS", "-1"),
        ("ACE_UPLOAD_READ_TIMEOUT_SECONDS", "bad"),
        ("ACE_UPLOAD_BATCH_COUNT", "31"),
        ("ACE_UPLOAD_BATCH_COUNT", "0"),
        ("ACE_UPLOAD_BATCH_COUNT", "1.5"),
        ("ACE_UPLOAD_BATCH_BYTES", "1048577"),
        ("ACE_UPLOAD_BATCH_BYTES", "-1"),
    ],
)
def test_bad_upload_settings_fail_before_post(tmp_path, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, request=request, json={"blob_names": []})

    install_transport(monkeypatch, handler)
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx, pytest.raises(IndexUploadError, match=name):
        if name == "ACE_UPLOAD_READ_TIMEOUT_SECONDS":
            idx._upload_batch_with_retry({}, {"blobs": []})
        else:
            idx._make_batches([{"path": "x.py", "content": "x"}])
    assert calls == []


def test_runtime_settings_enforce_content_bytes_and_count(tmp_path, monkeypatch):
    blobs = [{"path": f"{i}.py", "content": "中a"} for i in range(5)]  # 4 UTF-8 bytes each
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx:
        monkeypatch.setenv("ACE_UPLOAD_BATCH_COUNT", "2")
        monkeypatch.setenv("ACE_UPLOAD_BATCH_BYTES", "8")
        assert [len(batch) for batch in idx._make_batches(blobs)] == [2, 2, 1]
        monkeypatch.setenv("ACE_UPLOAD_BATCH_COUNT", "30")
        monkeypatch.setenv("ACE_UPLOAD_BATCH_BYTES", "7")
        assert [len(batch) for batch in idx._make_batches(blobs)] == [1, 1, 1, 1, 1]
        monkeypatch.setenv("ACE_UPLOAD_BATCH_BYTES", "3")
        with pytest.raises(IndexUploadError, match="ACE_UPLOAD_BATCH_BYTES"):
            idx._make_batches(blobs)


@pytest.mark.parametrize("method", ["get_blob_names", "force_rebuild"])
def test_unknown_outcome_is_visible_and_never_published(tmp_path, monkeypatch, method):
    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx:

        def unresolved(*args, **kwargs):
            raise IndexUploadOutcomeUnknownError("Upload outcome is unknown; check server status before rerunning")

        monkeypatch.setattr(idx, "_upload_batch_with_retry", unresolved)
        with pytest.raises(IndexUploadOutcomeUnknownError, match="unknown"):
            getattr(idx, method)()
        assert idx._index is None
        assert not idx.index_path.exists()


def test_delayed_http_upload_completes_without_a_second_post(tmp_path, monkeypatch):
    import http.server
    import threading
    import time

    state = {"posts": 0, "ready": False}
    lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.path == "/batch-upload":
                with lock:
                    state["posts"] += 1
                time.sleep(0.3)
                with lock:
                    state["ready"] = True
                result = {"blob_names": []}
            else:
                names = json.loads(body)["blobs"]["added_blobs"]
                with lock:
                    is_ready = state["ready"]
                result = {
                    "unknown_blob_names": [],
                    "nonindexed_blob_names": [] if is_ready else names,
                    "checkpoint_not_found": False,
                }
            raw = json.dumps(result).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except OSError:
                pass  # A timed-out client can close before the server finishes.

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("ACE_UPLOAD_READ_TIMEOUT_SECONDS", "0.05")
    monkeypatch.setattr(indexer, "UPLOAD_RECONCILE_INTERVAL", 0.02)
    monkeypatch.setattr(indexer, "UPLOAD_RECONCILE_TIMEOUT", 3.0)
    try:
        with Indexer(str(tmp_path), f"http://127.0.0.1:{server.server_port}", "dummy") as idx:
            assert idx._upload_batch_with_retry({}, {"blobs": [{"path": "x.py", "content": "x=1"}]})
        assert state["posts"] == 1
        assert state["ready"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_accepted_response_without_blob_acknowledgement_fails(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(202, request=request, json={})

    install_transport(monkeypatch, handler)
    with (
        Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx,
        pytest.raises(IndexUploadOutcomeUnknownError, match="unknown"),
    ):
        idx._upload_batch_with_retry({}, {"blobs": [{"path": "x.py", "content": "x"}]})
    assert calls == ["/batch-upload"]


@pytest.mark.parametrize("error", [httpx.UnsupportedProtocol, httpx.LocalProtocolError])
def test_invalid_local_protocol_fails_without_status_poll(tmp_path, monkeypatch, fake_clock, error):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/batch-upload":
            raise error("invalid local request", request=request)
        return status(request)

    install_transport(monkeypatch, handler)
    with (
        Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx,
        pytest.raises(IndexUploadError, match="protocol"),
    ):
        idx._upload_batch_with_retry({}, {"blobs": [{"path": "x.py", "content": "x"}]})
    assert calls == ["/batch-upload"]


@pytest.mark.parametrize(
    "header,wait",
    [
        ("2.5", 2.5),
        ("100000", 30.0),
        ("-3", 0.0),
        ("bad", 5.0),
        ("NaN", 5.0),
        ("Thu, 01 Jan 1970 00:00:09 GMT", 9.0),
        ("Wed, 01 Jan 2099 00:00:00 GMT", 30.0),
    ],
)
def test_rate_limit_waits_before_reconciliation(tmp_path, monkeypatch, fake_clock, header, wait):
    calls = []

    def handler(request):
        calls.append((request.url.path, fake_clock.now))
        if request.url.path == "/batch-upload":
            return httpx.Response(429, request=request, headers={"Retry-After": header})
        return status(request)

    install_transport(monkeypatch, handler)
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx:
        assert idx._upload_batch_with_retry({}, {"blobs": [{"path": "x.py", "content": "x"}]})
    assert calls == [("/batch-upload", 0.0), ("/agents/blob-status", wait)]


@pytest.mark.parametrize("entry", ["package", "cli", "direct"])
def test_upload_settings_load_at_runtime_from_skill_env(tmp_path, entry):
    skill = tmp_path / "skill"
    source_scripts = Path(__file__).resolve().parent.parent / "scripts"
    shutil.copytree(source_scripts, skill / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    (skill / ".env").write_text(
        "ACE_UPLOAD_READ_TIMEOUT_SECONDS=450\nACE_UPLOAD_BATCH_COUNT=1\nACE_UPLOAD_BATCH_BYTES=8\n",
        encoding="utf-8",
    )
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
    env["ACE_UPLOAD_BATCH_COUNT"] = "2"  # process environment overrides the .env value
    env["PYTHONPATH"] = os.pathsep.join(
        (
            str(skill if entry == "package" else skill / "scripts"),
            str(Path(pathspec.__file__).resolve().parent.parent),
        )
    )
    setup = {
        "package": "import scripts; from scripts import indexer",
        "cli": "import ace_cli; import indexer",
        "direct": "import indexer; from utils import load_env; load_env()",
    }[entry]
    program = (
        setup
        + """\nimport json, sys\nwith indexer.Indexer(sys.argv[1], "", "") as idx:\n    batches = idx._make_batches([{"path": str(i), "content": "abcd"} for i in range(3)])\nprint(json.dumps([indexer._upload_config_number("ACE_UPLOAD_READ_TIMEOUT_SECONDS", 300.0), [len(b) for b in batches]]))\n"""
    )
    result = subprocess.run(
        [sys.executable, "-c", program, str(tmp_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == [450.0, [2, 1]]
