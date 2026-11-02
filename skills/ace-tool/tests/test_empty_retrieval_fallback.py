"""A successful but empty remote search must not suppress local results."""

import pytest
from client import AceToolClient, IndexReadinessError
from templates import NO_RELEVANT_CODE_CONTEXT

EMPTY_HEADER = "The following code sections were retrieved:"


def _client():
    return AceToolClient(base_url="https://example.invalid", token="dummy")


def _local_result(query="query"):
    return {"results": [{"file": "src/example.py", "score": 1}], "query": query, "mode": "local_fallback"}


@pytest.mark.parametrize("remote_text", ["", "   \n", None, EMPTY_HEADER, f"\n{EMPTY_HEADER}\n"])
def test_empty_remote_result_falls_back_locally(monkeypatch, remote_text):
    client = _client()
    monkeypatch.setattr(client, "_remote_search", lambda *args: {"results": remote_text, "mode": "remote"})
    local = _local_result()
    monkeypatch.setattr(client, "_local_search", lambda *args: local)
    assert client.search_context("workspace", "query") == local


@pytest.mark.parametrize("remote_text", ["matched code", f"{EMPTY_HEADER}\n\nsrc/example.py:1"])
def test_nonempty_remote_result_is_preserved(monkeypatch, remote_text):
    client = _client()
    remote = {"results": remote_text, "mode": "remote"}
    monkeypatch.setattr(client, "_remote_search", lambda *args: remote)
    monkeypatch.setattr(client, "_local_search", lambda *args: pytest.fail("nonempty result was discarded"))
    assert client.search_context("workspace", "query") == remote


def test_readiness_failure_does_not_trigger_empty_result_fallback(monkeypatch):
    client = _client()
    def fail(*args):
        raise IndexReadinessError("index timed out")
    monkeypatch.setattr(client, "_remote_search", fail)
    monkeypatch.setattr(client, "_local_search", lambda *args: pytest.fail("readiness failure was hidden"))
    with pytest.raises(IndexReadinessError, match="timed out"):
        client.search_context("workspace", "query")


def test_third_party_injection_formats_local_fallback_as_text(monkeypatch):
    client = _client()
    client.endpoint = "claude"
    monkeypatch.setattr(client, "_should_include_search_context", lambda: True)
    monkeypatch.setattr(client, "_remote_search", lambda *args: {"results": EMPTY_HEADER})
    monkeypatch.setattr(client, "_local_search", lambda *args: _local_result("original request"))
    prompt = client._maybe_inject_search_context("claude", "original request", "workspace")
    assert "<codebase_context>" in prompt
    assert "src/example.py" in prompt
    assert "<original_request>\noriginal request\n</original_request>" in prompt
    assert "'file':" not in prompt


def test_cloud_prompt_context_formats_local_fallback_as_text(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_remote_search", lambda *args: {"results": "   "})
    monkeypatch.setattr(client, "_local_search", lambda *args: _local_result())
    context = client._get_retrieval_context("workspace", "query")
    assert "<codebase-context>" in context
    assert "src/example.py" in context
    assert "'file':" not in context


def test_empty_local_fallback_uses_injection_placeholder(monkeypatch):
    client = _client()
    client.endpoint = "claude"
    monkeypatch.setattr(client, "_should_include_search_context", lambda: True)
    monkeypatch.setattr(client, "_remote_search", lambda *args: {"results": ""})
    monkeypatch.setattr(client, "_local_search", lambda *args: {"results": [], "mode": "local_fallback"})
    prompt = client._maybe_inject_search_context("claude", "query", "workspace")
    assert NO_RELEVANT_CODE_CONTEXT in prompt
