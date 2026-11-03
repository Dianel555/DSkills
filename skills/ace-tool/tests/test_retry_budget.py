"""Connection failures may be retried within the configured finite budget."""

import httpx
from indexer import Indexer


def test_connect_failure_retry_budget_and_no_final_sleep(tmp_path, monkeypatch):
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
            raise httpx.ConnectTimeout("connect failed")

    monkeypatch.setattr("indexer.httpx.Client", Client)
    monkeypatch.setattr("indexer.time.sleep", sleeps.append)
    with Indexer(str(tmp_path), "https://example.invalid", "dummy") as idx:
        assert not idx._upload_batch_with_retry({}, {"blobs": []}, max_retries=3)
    assert len(calls) == 3
    assert sleeps == [1, 2]
