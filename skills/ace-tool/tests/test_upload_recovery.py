"""Cross-process recovery must not replay previously accepted uploads."""

import hashlib
import http.server
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from indexer import Indexer

WORKER = r"""
import json, os, sys, time, traceback
from pathlib import Path
import indexer
from secure_fs import SafeFile

indexer.UPLOAD_RECONCILE_TIMEOUT = 3.0
indexer.UPLOAD_RECONCILE_INTERVAL = 0.01
indexer.UPLOAD_UNKNOWN_GRACE = 0.05
if os.environ.get("TEST_DELAY_LOCK_INITIALIZATION"):
    original_write = SafeFile.write_bytes
    def delayed_marker_write(self, data):
        if data in (b"windows\n", b"posix\n"):
            (Path(os.environ["TEST_PROJECT"]) / ".ace-test-lock-initializing").write_text("ready")
            time.sleep(0.75)
        return original_write(self, data)
    SafeFile.write_bytes = delayed_marker_write
if os.environ.get("TEST_EXIT_BEFORE_INDEX_SAVE"):
    indexer.Indexer._save_index = lambda self: os._exit(74)
if os.environ.get("TEST_EXIT_BEFORE_POST"):
    original_post = indexer.httpx.Client.post
    def exit_before_post(self, url, *args, **kwargs):
        if str(url).endswith("/batch-upload"):
            os._exit(73)
        return original_post(self, url, *args, **kwargs)
    indexer.httpx.Client.post = exit_before_post
try:
    with indexer.Indexer(os.environ["TEST_PROJECT"], os.environ["TEST_SERVER"], os.environ["TEST_TOKEN"]) as idx:
        names = idx.force_rebuild() if os.environ.get("TEST_REBUILD") else idx.get_blob_names()
except indexer.IndexUploadError as exc:
    traceback.print_exception(exc, file=sys.stderr)
    print(type(exc).__name__, str(exc))
    sys.exit(8)
print(json.dumps(names))
"""


class Backend:
    def __init__(self):
        self.lock = threading.Lock()
        self.uploads = []
        self.upload_scopes = []
        self.ready = set()
        self.scoped_ready = {}
        self.fail_upload_attempts = 0
        self.fail_status = False
        self.status_code = 200
        self.status_calls = 0
        self.status_auths = []
        self.pending_cycles = 0
        self.delay_first = False
        self.delay_second = False
        self.first_started = threading.Event()
        self.second_started = threading.Event()
        self.release_first = threading.Event()
        backend = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                code = 200
                if self.path.endswith("/batch-upload"):
                    scope = self.path.removesuffix("/batch-upload")
                    names = [hashlib.sha256((b["path"] + b["content"]).encode()).hexdigest() for b in body["blobs"]]
                    with backend.lock:
                        backend.uploads.extend(b["path"] for b in body["blobs"])
                        backend.upload_scopes.append(scope)
                        ready = backend.scoped_ready.setdefault(scope, set()) if scope else backend.ready
                        ready.update(names)
                        count = len(backend.uploads)
                        fail = count <= backend.fail_upload_attempts
                        delay = (backend.delay_first and count == 1) or (backend.delay_second and count == 2)
                    if count >= 2:
                        backend.second_started.set()
                    if delay:
                        if count == 1:
                            backend.first_started.set()
                        backend.release_first.wait(10)
                    code = 503 if fail else 200
                    response = {"blob_names": names}
                elif self.path.endswith("/agents/blob-status"):
                    scope = self.path.removesuffix("/agents/blob-status")
                    names = body["blobs"]["added_blobs"]
                    with backend.lock:
                        backend.status_calls += 1
                        backend.status_auths.append(self.headers.get("Authorization"))
                        fail = backend.fail_status
                        ready = backend.scoped_ready.setdefault(scope, set()) if scope else backend.ready
                        unknown = [name for name in names if name not in ready]
                        pending = [name for name in names if name in ready] if backend.pending_cycles else []
                        if backend.pending_cycles:
                            backend.pending_cycles -= 1
                    code = 503 if fail else backend.status_code
                    response = {
                        "unknown_blob_names": unknown,
                        "nonindexed_blob_names": pending,
                        "checkpoint_not_found": False,
                    }
                else:
                    code = 404
                    response = {}
                raw = json.dumps(response).encode()
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except OSError:
                    pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.release_first.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def backend():
    service = Backend()
    try:
        yield service
    finally:
        service.close()


def worker_env(
    root,
    backend,
    *,
    crash=False,
    crash_before_save=False,
    delay_lock=False,
    token="test-token",
    rebuild=False,
    prefix="",
):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("ACE_", "AUGMENT_", "PROMPT_ENHANCER_", "TEST_"))
    }
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(scripts), env.get("PYTHONPATH", ""))))
    env.update(
        {
            "TEST_PROJECT": str(root),
            "TEST_SERVER": backend.url + prefix,
            "TEST_TOKEN": token,
            "ACE_UPLOAD_BATCH_COUNT": "1",
        }
    )
    if crash:
        env["TEST_EXIT_BEFORE_POST"] = "1"
    if crash_before_save:
        env["TEST_EXIT_BEFORE_INDEX_SAVE"] = "1"
    if delay_lock:
        env["TEST_DELAY_LOCK_INITIALIZATION"] = "1"
    if rebuild:
        env["TEST_REBUILD"] = "1"
    return env


def run_worker(
    root, backend, *, crash=False, crash_before_save=False, token="test-token", rebuild=False, prefix="", timeout=15
):
    return subprocess.run(
        [sys.executable, "-c", WORKER],
        env=worker_env(
            root, backend, crash=crash, crash_before_save=crash_before_save, token=token, rebuild=rebuild, prefix=prefix
        ),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_partial_batches_recover_in_new_process_without_reupload(tmp_path, backend):
    (tmp_path / "first.py").write_text("first = 1\n", encoding="utf-8")
    (tmp_path / "second.py").write_text("second = 2\n", encoding="utf-8")
    backend.delay_second = True
    first = subprocess.Popen(
        [sys.executable, "-c", WORKER],
        env=worker_env(tmp_path, backend),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert backend.second_started.wait(10)
        first.terminate()
        first.communicate(timeout=10)
    finally:
        backend.release_first.set()
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5)
    assert len(backend.uploads) == 2
    second = run_worker(tmp_path, backend)
    assert second.returncode == 0, second.stderr
    assert len(json.loads(second.stdout)) == 2
    assert len(backend.uploads) == 2


def test_existing_instance_reloads_index_after_another_process_updates_it(tmp_path, backend, monkeypatch):
    monkeypatch.setenv("ACE_UPLOAD_BATCH_COUNT", "1")
    path = tmp_path / "one.py"
    path.write_text("value = 1\n", encoding="utf-8")
    with Indexer(str(tmp_path), backend.url, "test-token") as indexer:
        indexer.get_blob_names()
        path.write_text("value = 234567\n", encoding="utf-8")
        other = run_worker(tmp_path, backend)
        assert other.returncode == 0, other.stderr
        assert indexer.get_blob_names() == json.loads(other.stdout)
    assert backend.uploads == ["one.py", "one.py"]


def test_crash_before_post_checks_status_then_retries_automatically(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    first = run_worker(tmp_path, backend, crash=True)
    assert first.returncode == 73
    assert backend.uploads == []

    second = run_worker(tmp_path, backend)
    assert second.returncode == 0, second.stderr
    assert backend.status_calls >= 1
    assert backend.uploads == ["one.py"]


def test_crash_after_server_acceptance_is_reconciled_without_reupload(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    backend.delay_first = True
    first = subprocess.Popen(
        [sys.executable, "-c", WORKER],
        env=worker_env(tmp_path, backend),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert backend.first_started.wait(10)
        first.terminate()
        first.communicate(timeout=10)
    finally:
        backend.release_first.set()
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5)
    second = run_worker(tmp_path, backend)
    assert second.returncode == 0, second.stderr
    assert len(json.loads(second.stdout)) == 1
    assert backend.uploads == ["one.py"]


def test_crash_after_ack_before_index_save_does_not_reupload(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    first = run_worker(tmp_path, backend, crash_before_save=True)
    assert first.returncode == 74
    assert backend.uploads == ["one.py"]
    second = run_worker(tmp_path, backend)
    assert second.returncode == 0, second.stderr
    assert backend.status_calls >= 1
    assert backend.uploads == ["one.py"]


@pytest.mark.parametrize("accepted_before_crash", [False, True])
def test_ordinary_restart_recovers_uncertain_rebuild_with_unchanged_cache(tmp_path, backend, accepted_before_crash):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    first = run_worker(tmp_path, backend)
    assert first.returncode == 0, first.stderr
    backend.ready.clear()
    if accepted_before_crash:
        backend.delay_second = True
        rebuild = subprocess.Popen(
            [sys.executable, "-c", WORKER],
            env=worker_env(tmp_path, backend, rebuild=True),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert backend.second_started.wait(10)
            rebuild.terminate()
            rebuild.communicate(timeout=10)
        finally:
            backend.release_first.set()
            if rebuild.poll() is None:
                rebuild.kill()
                rebuild.wait(timeout=5)
    else:
        rebuild = run_worker(tmp_path, backend, rebuild=True, crash=True)
        assert rebuild.returncode == 73
    before = backend.status_calls
    result = run_worker(tmp_path, backend)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == json.loads(first.stdout)
    assert backend.status_calls > before
    assert backend.uploads == ["one.py", "one.py"]
    journal = json.loads((tmp_path / ".ace-tool" / "upload-journal.json").read_text(encoding="utf-8"))
    assert not any(records for records in journal["services"].values())


def test_uncertain_rebuild_never_reuploads_a_newly_ignored_file(tmp_path, backend):
    (tmp_path / "private.py").write_text("private = True\n", encoding="utf-8")
    assert run_worker(tmp_path, backend).returncode == 0
    backend.ready.clear()
    assert run_worker(tmp_path, backend, rebuild=True, crash=True).returncode == 73
    (tmp_path / ".gitignore").write_text("private.py\n", encoding="utf-8")
    result = run_worker(tmp_path, backend)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
    assert backend.uploads == ["private.py"]


def test_acknowledged_blob_removed_by_server_is_uploaded_again(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    assert run_worker(tmp_path, backend).returncode == 0
    backend.ready.clear()
    result = run_worker(tmp_path, backend, rebuild=True)
    assert result.returncode == 0, result.stderr
    assert backend.uploads == ["one.py", "one.py"]


def test_pending_blob_waits_for_readiness_without_reupload(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    assert run_worker(tmp_path, backend, crash_before_save=True).returncode == 74
    backend.pending_cycles = 2
    result = run_worker(tmp_path, backend)
    assert result.returncode == 0, result.stderr
    assert backend.status_calls >= 3
    assert backend.uploads == ["one.py"]


def test_unavailable_status_triggers_bounded_automatic_retry(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    backend.fail_upload_attempts = 1
    backend.fail_status = True
    result = run_worker(tmp_path, backend)
    assert result.returncode == 0, result.stderr
    assert backend.uploads == ["one.py", "one.py"]


def test_retry_budget_survives_process_restart(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    backend.fail_upload_attempts = 100
    backend.fail_status = True
    first = run_worker(tmp_path, backend)
    assert first.returncode == 8
    assert len(backend.uploads) == 3
    second = run_worker(tmp_path, backend)
    assert second.returncode == 8
    assert len(backend.uploads) == 3


def test_acknowledged_history_is_bounded_without_losing_uncertain_attempts(tmp_path, backend, monkeypatch):
    import upload_recovery
    from secure_fs import AuthorizedRoot
    from upload_recovery import RecoveryBudgetExhaustedError, UploadRecovery

    monkeypatch.setattr(upload_recovery, "MAX_JOURNAL_BYTES", 1000)
    guard = AuthorizedRoot(tmp_path)
    recovery = UploadRecovery(tmp_path, guard, backend.url, "test-token")
    uncertain = hashlib.sha256(b"uncertain").hexdigest()
    try:
        with recovery.locked():
            recovery.load()
            for _ in range(3):
                recovery.before_send([uncertain])
            for i in range(30):
                name = hashlib.sha256(f"completed-{i}".encode()).hexdigest()
                recovery.before_send([name])
                recovery.acknowledge([name])
            assert recovery.records()[uncertain] == {"state": "may", "attempts": 3}
            with pytest.raises(RecoveryBudgetExhaustedError):
                recovery.before_send([uncertain])
    finally:
        guard.close()
    assert (tmp_path / ".ace-tool" / "upload-journal.json").stat().st_size < 1000


def test_unresolved_journal_at_capacity_blocks_post_without_losing_evidence(tmp_path, backend, monkeypatch):
    import upload_recovery
    from indexer import IndexUploadError
    from secure_fs import AuthorizedRoot
    from upload_recovery import UploadRecovery

    uncertain = hashlib.sha256(b"uncertain-before-capacity").hexdigest()
    guard = AuthorizedRoot(tmp_path)
    recovery = UploadRecovery(tmp_path, guard, backend.url, "test-token")
    try:
        with recovery.locked():
            recovery.load()
            recovery.before_send([uncertain])
    finally:
        guard.close()
    journal = tmp_path / ".ace-tool" / "upload-journal.json"
    before = journal.read_bytes()
    monkeypatch.setattr(upload_recovery, "MAX_JOURNAL_BYTES", len(before))
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    with (
        Indexer(str(tmp_path), backend.url, "test-token") as indexer,
        pytest.raises(IndexUploadError, match="size limit"),
    ):
        indexer.get_blob_names()
    assert backend.uploads == []
    assert journal.read_bytes() == before


def test_reappearing_blob_is_rechecked_after_acknowledgement_compaction(tmp_path, backend, monkeypatch):
    import indexer as indexer_module

    monkeypatch.setattr(indexer_module, "UPLOAD_UNKNOWN_GRACE", 0.01)
    monkeypatch.setattr(indexer_module, "UPLOAD_RECONCILE_INTERVAL", 0.01)
    path = tmp_path / "one.py"
    first_content = "value = 1\n"
    path.write_text(first_content, encoding="utf-8")
    with Indexer(str(tmp_path), backend.url, "test-token") as indexer:
        first_name = indexer.get_blob_names()[0]
        path.write_text("value = 123456\n", encoding="utf-8")
        indexer.get_blob_names()
        journal = json.loads((tmp_path / ".ace-tool" / "upload-journal.json").read_text(encoding="utf-8"))
        assert all(first_name not in records for records in journal["services"].values())
        path.write_text(first_content, encoding="utf-8")
        assert indexer.get_blob_names() == [first_name]
    assert backend.uploads == ["one.py", "one.py"]


@pytest.mark.parametrize("failure", ["401", "403", "tls", "unsupported"])
def test_definitive_upload_failure_does_not_exhaust_attempt_budget(tmp_path, backend, monkeypatch, failure):
    import ssl

    import httpx
    import indexer as indexer_module
    from indexer import IndexUploadError

    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(indexer_module, "UPLOAD_UNKNOWN_GRACE", 0.01)
    monkeypatch.setattr(indexer_module, "UPLOAD_RECONCILE_INTERVAL", 0.01)
    original = httpx.Client.post

    def reject_upload(self, url, **kwargs):
        if str(url).endswith("/agents/blob-status"):
            return original(self, url, **kwargs)
        if failure in {"401", "403"}:
            return httpx.Response(int(failure), request=httpx.Request("POST", url))
        if failure == "tls":
            raise httpx.ConnectError("synthetic TLS failure") from ssl.SSLCertVerificationError()
        raise httpx.UnsupportedProtocol("synthetic protocol failure")

    with monkeypatch.context() as patch:
        patch.setattr(httpx.Client, "post", reject_upload)
        with Indexer(str(tmp_path), backend.url, "test-token") as indexer:
            for _ in range(3):
                with pytest.raises(IndexUploadError):
                    indexer.get_blob_names()
    result = run_worker(tmp_path, backend)
    assert result.returncode == 0, result.stderr
    assert backend.uploads == ["one.py"]


def test_local_protocol_error_preserves_possible_sent_attempt(tmp_path, backend, monkeypatch):
    import httpx
    from indexer import IndexUploadError

    content = "value = 1\n"
    (tmp_path / "one.py").write_text(content, encoding="utf-8")
    name = Indexer._hash_blob("one.py", content)
    original = httpx.Client.post

    def fail_after_server_accepts(self, url, **kwargs):
        response = original(self, url, **kwargs)
        if str(url).endswith("/batch-upload"):
            raise httpx.LocalProtocolError("synthetic ambiguous local protocol failure")
        return response

    with monkeypatch.context() as patch:
        patch.setattr(httpx.Client, "post", fail_after_server_accepts)
        with Indexer(str(tmp_path), backend.url, "test-token") as indexer, pytest.raises(IndexUploadError):
            indexer.get_blob_names()
    journal = json.loads((tmp_path / ".ace-tool" / "upload-journal.json").read_text(encoding="utf-8"))
    assert next(iter(journal["services"].values()))[name] == {"state": "may", "attempts": 1}
    result = run_worker(tmp_path, backend)
    assert result.returncode == 0, result.stderr
    assert backend.uploads == ["one.py"]


def test_rejected_retry_preserves_earlier_uncertain_attempt(tmp_path, backend, monkeypatch):
    import ssl

    import httpx
    import indexer as indexer_module
    from indexer import IndexUploadError
    from secure_fs import AuthorizedRoot
    from upload_recovery import UploadRecovery

    content = "value = 1\n"
    (tmp_path / "one.py").write_text(content, encoding="utf-8")
    name = Indexer._hash_blob("one.py", content)
    guard = AuthorizedRoot(tmp_path)
    recovery = UploadRecovery(tmp_path, guard, backend.url, "test-token")
    try:
        with recovery.locked():
            recovery.load()
            recovery.before_send([name])
    finally:
        guard.close()
    monkeypatch.setattr(indexer_module, "UPLOAD_UNKNOWN_GRACE", 0.01)
    monkeypatch.setattr(indexer_module, "UPLOAD_RECONCILE_INTERVAL", 0.01)
    original = httpx.Client.post

    def fail_tls(self, url, **kwargs):
        if str(url).endswith("/agents/blob-status"):
            return original(self, url, **kwargs)
        raise httpx.ConnectError("synthetic TLS failure") from ssl.SSLCertVerificationError()

    monkeypatch.setattr(httpx.Client, "post", fail_tls)
    with Indexer(str(tmp_path), backend.url, "test-token") as indexer, pytest.raises(IndexUploadError):
        indexer.get_blob_names()
    journal = json.loads((tmp_path / ".ace-tool" / "upload-journal.json").read_text(encoding="utf-8"))
    record = next(iter(journal["services"].values()))[name]
    assert record == {"state": "may", "attempts": 1}


def test_cached_scope_is_rechecked_on_service_change(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    first = run_worker(tmp_path, backend)
    assert first.returncode == 0, first.stderr
    other = Backend()
    try:
        second = run_worker(tmp_path, other)
        assert second.returncode == 0, second.stderr
        assert other.uploads == ["one.py"]
    finally:
        other.close()


def test_same_origin_service_prefix_change_rechecks_cached_blobs(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    assert run_worker(tmp_path, backend, prefix="/service-a").returncode == 0
    second = run_worker(tmp_path, backend, prefix="/service-b")
    assert second.returncode == 0, second.stderr
    assert backend.upload_scopes == ["/service-a", "/service-b"]


def test_exhausted_retry_budget_does_not_block_other_service_prefix(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    backend.fail_upload_attempts = 3
    backend.fail_status = True
    assert run_worker(tmp_path, backend, prefix="/service-a").returncode == 8
    backend.fail_status = False
    second = run_worker(tmp_path, backend, prefix="/service-b")
    assert second.returncode == 0, second.stderr
    assert backend.upload_scopes == ["/service-a"] * 3 + ["/service-b"]
    backend.fail_status = True
    assert run_worker(tmp_path, backend, prefix="/service-a").returncode == 8
    assert backend.upload_scopes == ["/service-a"] * 3 + ["/service-b"]


def test_equivalent_service_prefixes_share_cache(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    assert run_worker(tmp_path, backend, prefix="/service-a/").returncode == 0
    result = run_worker(tmp_path, backend, prefix="/service-a")
    assert result.returncode == 0, result.stderr
    assert backend.upload_scopes == ["/service-a"]


@pytest.mark.parametrize("prefix", ["/test-token", "/%74est-token"])
def test_configured_token_is_rejected_in_url_path(tmp_path, backend, prefix):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    result = run_worker(tmp_path, backend, prefix=prefix)
    assert result.returncode == 8
    assert "test-token" not in result.stderr
    assert backend.uploads == []
    assert not (tmp_path / ".ace-tool" / "upload-journal.json").exists()


def test_tls_certificate_failure_during_status_does_not_trigger_reupload(tmp_path, backend, monkeypatch):
    import ssl

    import httpx
    from indexer import IndexUploadError

    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    assert run_worker(tmp_path, backend, crash=True).returncode == 73
    calls = []

    def fail_tls(self, url, **kwargs):
        calls.append(str(url))
        raise httpx.ConnectError("synthetic TLS failure") from ssl.SSLCertVerificationError()

    monkeypatch.setattr(httpx.Client, "post", fail_tls)
    with Indexer(str(tmp_path), backend.url, "test-token") as indexer, pytest.raises(IndexUploadError, match="TLS"):
        indexer.get_blob_names()
    assert len(calls) == 1 and calls[0].endswith("/agents/blob-status")
    assert backend.uploads == []


def test_tls_certificate_failure_during_upload_is_not_retried(tmp_path, backend, monkeypatch):
    import ssl

    import httpx
    from indexer import IndexUploadError

    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    calls = []
    original = httpx.Client.post

    def fail_tls(self, url, **kwargs):
        calls.append(str(url))
        if str(url).endswith("/batch-upload"):
            raise httpx.ConnectError("synthetic TLS failure") from ssl.SSLCertVerificationError()
        return original(self, url, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", fail_tls)
    with Indexer(str(tmp_path), backend.url, "test-token") as indexer, pytest.raises(IndexUploadError, match="TLS"):
        indexer.get_blob_names()
    assert [url.rsplit("/", 1)[-1] for url in calls] == ["blob-status", "batch-upload"]
    assert backend.uploads == []


def test_rebuild_checks_status_with_current_credentials(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    assert run_worker(tmp_path, backend, token="old-test-token").returncode == 0
    backend.status_code = 403
    result = run_worker(tmp_path, backend, token="new-test-token", rebuild=True)
    assert result.returncode == 8
    assert backend.status_auths[-1].endswith("new-test-token")
    assert backend.uploads == ["one.py"]


def test_journal_does_not_store_token_or_file_content(tmp_path, backend):
    content = "SYNTHETIC_CONTENT_NOT_FOR_JOURNAL\n"
    token = "synthetic-test-token-not-for-journal"
    (tmp_path / "one.py").write_text(content, encoding="utf-8")
    result = run_worker(tmp_path, backend, token=token)
    assert result.returncode == 0, result.stderr
    journal = (tmp_path / ".ace-tool" / "upload-journal.json").read_bytes()
    assert content.encode() not in journal
    assert token.encode() not in journal
    assert hashlib.sha256(token.encode()).hexdigest().encode() not in journal


def test_corrupt_journal_blocks_upload_without_erasing_evidence(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    state = tmp_path / ".ace-tool"
    state.mkdir()
    journal = state / "upload-journal.json"
    journal.write_bytes(b"not valid json")
    result = run_worker(tmp_path, backend)
    assert result.returncode == 8
    assert backend.uploads == []
    assert journal.read_bytes() == b"not valid json"


@pytest.mark.parametrize("method", ["get_blob_names", "force_rebuild"])
def test_bad_timeout_does_not_consume_a_persisted_attempt(tmp_path, backend, monkeypatch, method):
    from indexer import IndexUploadError

    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setenv("ACE_UPLOAD_READ_TIMEOUT_SECONDS", "invalid")
    with Indexer(str(tmp_path), backend.url, "test-token") as indexer:
        for _ in range(3):
            with pytest.raises(IndexUploadError, match="ACE_UPLOAD_READ_TIMEOUT_SECONDS"):
                getattr(indexer, method)()
    assert backend.uploads == []
    assert not (tmp_path / ".ace-tool" / "upload-journal.json").exists()
    result = run_worker(tmp_path, backend)
    assert result.returncode == 0, result.stderr
    assert backend.uploads == ["one.py"]


def test_journal_sync_failure_prevents_post_and_next_run_reconciles(tmp_path, backend, monkeypatch):
    from indexer import IndexUploadError

    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    with Indexer(str(tmp_path), backend.url, "test-token") as indexer:

        def fail_sync(*args):
            raise OSError("synthetic sync failure")

        monkeypatch.setattr(indexer._guard, "sync_directory", fail_sync)
        with pytest.raises(IndexUploadError, match="persist"):
            indexer.get_blob_names()
    assert backend.uploads == []
    result = run_worker(tmp_path, backend)
    assert result.returncode == 0, result.stderr
    assert backend.status_calls >= 1
    assert backend.uploads == ["one.py"]


def test_other_platform_lock_marker_is_rejected(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    marker = b"posix\n" if os.name == "nt" else b"windows\n"
    (tmp_path / ".ace-tool.lock").write_bytes(marker)
    result = run_worker(tmp_path, backend)
    assert result.returncode == 8
    assert backend.uploads == []
    assert (tmp_path / ".ace-tool.lock").read_bytes() == marker


def test_other_platform_partial_marker_is_never_accepted(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    marker = b"posix\n" if os.name == "nt" else b"windows\n"
    path = tmp_path / ".ace-tool.lock"
    path.write_bytes(marker[:1])

    def finish_marker():
        time.sleep(0.3)
        path.write_bytes(marker)

    writer = threading.Thread(target=finish_marker)
    writer.start()
    try:
        result = run_worker(tmp_path, backend)
    finally:
        writer.join(timeout=5)
    assert result.returncode == 8
    assert backend.uploads == []
    assert path.read_bytes() == marker


def test_abandoned_empty_lock_marker_is_rejected_within_deadline(tmp_path, monkeypatch):
    import upload_recovery
    from secure_fs import AuthorizedRoot
    from upload_recovery import RecoveryStateError, UploadRecovery

    (tmp_path / ".ace-tool.lock").write_bytes(b"")
    monkeypatch.setattr(upload_recovery, "LOCK_MARKER_INIT_SECONDS", 0.2)
    guard = AuthorizedRoot(tmp_path)
    start = time.monotonic()
    try:
        with (
            pytest.raises(RecoveryStateError, match="incomplete"),
            UploadRecovery(tmp_path, guard, "http://127.0.0.1:12345").locked(),
        ):
            pytest.fail("empty marker was accepted")
    finally:
        guard.close()
    assert time.monotonic() - start < 2


@pytest.mark.skipif(os.name != "posix", reason="FIFOs require POSIX")
@pytest.mark.parametrize("target", ["lock", "journal"])
def test_fifo_recovery_state_is_rejected_without_hanging(tmp_path, backend, target):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    if target == "lock":
        fifo = tmp_path / ".ace-tool.lock"
    else:
        (tmp_path / ".ace-tool").mkdir()
        fifo = tmp_path / ".ace-tool" / "upload-journal.json"
    os.mkfifo(fifo)
    result = run_worker(tmp_path, backend, timeout=5)
    assert result.returncode == 8
    assert backend.uploads == []


@pytest.mark.skipif(os.name == "nt", reason="file symlinks may require elevation on Windows")
@pytest.mark.parametrize("target", ["lock", "journal"])
def test_linked_recovery_state_is_not_followed(tmp_path, backend, target):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    outside = tmp_path.parent / f"outside-{tmp_path.name}-{target}"
    outside.write_bytes(b"keep unchanged")
    if target == "lock":
        (tmp_path / ".ace-tool.lock").symlink_to(outside)
    else:
        (tmp_path / ".ace-tool").mkdir()
        (tmp_path / ".ace-tool" / "upload-journal.json").symlink_to(outside)
    result = run_worker(tmp_path, backend)
    assert result.returncode == 8
    assert backend.uploads == []
    assert outside.read_bytes() == b"keep unchanged"


@pytest.mark.skipif(os.name == "nt", reason="directory symlinks may require elevation on Windows")
def test_linked_state_directory_is_not_used(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    outside = tmp_path.parent / f"outside-state-{tmp_path.name}"
    outside.mkdir()
    (tmp_path / ".ace-tool").symlink_to(outside, target_is_directory=True)
    result = run_worker(tmp_path, backend)
    assert result.returncode == 8
    assert backend.uploads == []
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("target", ["lock", "journal"])
def test_hardlinked_recovery_state_is_rejected(tmp_path, backend, target):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    outside = tmp_path.parent / f"hardlink-{tmp_path.name}-{target}"
    outside.write_bytes(b"keep unchanged")
    if target == "lock":
        link = tmp_path / ".ace-tool.lock"
    else:
        (tmp_path / ".ace-tool").mkdir()
        link = tmp_path / ".ace-tool" / "upload-journal.json"
    try:
        os.link(outside, link)
    except OSError as exc:
        pytest.skip(f"hard links unavailable: {exc}")
    result = run_worker(tmp_path, backend)
    assert result.returncode == 8
    assert backend.uploads == []
    assert outside.read_bytes() == b"keep unchanged"


@pytest.mark.skipif(os.name == "nt", reason="Windows holds a sharing-protected lock anchor")
def test_replaced_lock_anchor_is_detected(tmp_path):
    from secure_fs import AuthorizedRoot
    from upload_recovery import RecoveryStateError, UploadRecovery

    guard = AuthorizedRoot(tmp_path)
    try:
        recovery = UploadRecovery(tmp_path, guard, "http://127.0.0.1:12345")
        with recovery.locked():
            replacement = tmp_path / "replacement.lock"
            replacement.write_bytes(b"posix\n")
            os.replace(replacement, tmp_path / ".ace-tool.lock")
            with pytest.raises(RecoveryStateError, match="replaced"):
                recovery.verify_anchor()
    finally:
        guard.close()


def test_concurrent_process_waits_for_lock_initialization(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    first = subprocess.Popen(
        [sys.executable, "-c", WORKER],
        env=worker_env(tmp_path, backend, delay_lock=True),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    second = None
    try:
        marker = tmp_path / ".ace-test-lock-initializing"
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        second = subprocess.Popen(
            [sys.executable, "-c", WORKER],
            env=worker_env(tmp_path, backend),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        first_stdout, first_stderr = first.communicate(timeout=15)
        second_stdout, second_stderr = second.communicate(timeout=15)
    finally:
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5)
        if second is not None and second.poll() is None:
            second.kill()
            second.wait(timeout=5)
    assert first.returncode == 0, (first_stdout, first_stderr)
    assert second.returncode == 0, (second_stdout, second_stderr)
    assert backend.uploads == ["one.py"]


def test_concurrent_processes_do_not_submit_the_same_batch(tmp_path, backend):
    (tmp_path / "one.py").write_text("value = 1\n", encoding="utf-8")
    backend.delay_first = True
    env = worker_env(tmp_path, backend)
    first = subprocess.Popen(
        [sys.executable, "-c", WORKER], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    second = None
    try:
        assert backend.first_started.wait(10)
        second = subprocess.Popen(
            [sys.executable, "-c", WORKER], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        backend.second_started.wait(2)
        backend.release_first.set()
        first_stdout, first_stderr = first.communicate(timeout=15)
        second_stdout, second_stderr = second.communicate(timeout=15)
    finally:
        backend.release_first.set()
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5)
        if second is not None and second.poll() is None:
            second.kill()
            second.wait(timeout=5)
    assert first.returncode == 0, (first_stdout, first_stderr)
    assert second.returncode == 0, (second_stdout, second_stderr)
    assert backend.uploads == ["one.py"]
