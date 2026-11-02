import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import indexer


@pytest.mark.parametrize("header", ["999999999", "NaN", "-50", "Wed, 01 Jan 2099 00:00:00 GMT"])
def test_rate_limit_delay_is_finite_bounded_and_not_used_after_last_attempt(tmp_path, monkeypatch, header):
    calls, sleeps = [], []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            calls.append(1)
            return SimpleNamespace(status_code=429, headers={"Retry-After": header})

    monkeypatch.setattr(indexer.httpx, "Client", Client)
    monkeypatch.setattr(indexer.time, "sleep", sleeps.append)
    idx = indexer.Indexer(str(tmp_path), "https://example.invalid", "dummy")
    assert not idx._upload_batch_with_retry({}, {}, max_retries=3)
    assert len(calls) == 3
    assert len(sleeps) == 2
    assert all(0 <= seconds <= 30 for seconds in sleeps)


def test_final_server_error_does_not_sleep(tmp_path, monkeypatch):
    sleeps = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            return SimpleNamespace(status_code=503)

    monkeypatch.setattr(indexer.httpx, "Client", Client)
    monkeypatch.setattr(indexer.time, "sleep", sleeps.append)
    idx = indexer.Indexer(str(tmp_path), "https://example.invalid", "dummy")
    assert not idx._upload_batch_with_retry({}, {}, max_retries=1)
    assert sleeps == []
