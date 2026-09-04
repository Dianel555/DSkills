import http.client
import ssl
import urllib.error
import urllib.request

import pytest
from agent_wiki import obsidian_api

# Transport failures that available()/put_file() must swallow into a False return.
# Covers an OSError subclass (timeout), an SSLError, a URLError, and an
# http.client.HTTPException (which is *not* an OSError subclass).
_TRANSPORT_EXCEPTIONS = [
    urllib.error.URLError("refused"),
    TimeoutError("timed out"),
    ssl.SSLError("bad cert"),
    http.client.BadStatusLine("garbage"),
]


class _FakeResp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("AGENT_WIKI_OBSIDIAN_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_WIKI_OBSIDIAN_API_URL", raising=False)


def test_available_false_without_key():
    assert obsidian_api.available() is False


def test_put_file_false_without_key():
    assert obsidian_api.put_file("a.md", "x") is False


def test_available_true_when_key_and_server_ok(monkeypatch):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "secret")
    captured = {}

    def fake_urlopen(req, timeout=None, context=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        return _FakeResp(200)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert obsidian_api.available() is True
    assert captured["url"] == "https://127.0.0.1:27124/"
    assert captured["auth"] == "Bearer secret"


@pytest.mark.parametrize("exc", _TRANSPORT_EXCEPTIONS)
def test_available_false_on_transport_error(monkeypatch, exc):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "secret")

    def boom(req, timeout=None, context=None):
        raise exc

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert obsidian_api.available() is False


def test_put_file_builds_put_request(monkeypatch):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    captured = {}

    def fake_urlopen(req, timeout=None, context=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = req.data
        captured["ctype"] = req.get_header("Content-type")
        captured["auth"] = req.get_header("Authorization")
        return _FakeResp(204)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    ok = obsidian_api.put_file("文献阅读记录/wiki/index.md", "# hi\n")
    assert ok is True
    assert captured["method"] == "PUT"
    assert captured["url"].startswith("https://127.0.0.1:27124/vault/")
    assert "%E6%96%87%E7%8C%AE" in captured["url"]  # Chinese path percent-encoded
    assert "/" in captured["url"].split("/vault/", 1)[1]  # path separators preserved
    assert captured["body"] == b"# hi\n"
    assert "text/markdown" in captured["ctype"]
    assert captured["auth"] == "Bearer k"


def test_put_file_false_on_http_error(monkeypatch):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")

    def boom(req, timeout=None, context=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert obsidian_api.put_file("a.md", "x") is False


@pytest.mark.parametrize("exc", _TRANSPORT_EXCEPTIONS)
def test_put_file_false_on_transport_error(monkeypatch, exc):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")

    def boom(req, timeout=None, context=None):
        raise exc

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert obsidian_api.put_file("a.md", "x") is False


def test_http_url_uses_no_ssl_context(monkeypatch):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_URL", "http://127.0.0.1:27123")
    seen = {}

    def fake_urlopen(req, timeout=None, context=None):
        seen["context"] = context
        return _FakeResp(200)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert obsidian_api.available() is True
    assert seen["context"] is None  # plain http -> no TLS context


def test_https_localhost_uses_unverified_context(monkeypatch):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    seen = {}

    def fake_urlopen(req, timeout=None, context=None):
        seen["context"] = context
        return _FakeResp(200)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert obsidian_api.available() is True
    assert seen["context"] is not None  # self-signed loopback -> unverified TLS


def test_https_remote_host_keeps_verified_context(monkeypatch):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_URL", "https://example.com:27124")
    seen = {}

    def fake_urlopen(req, timeout=None, context=None):
        seen["context"] = context
        return _FakeResp(200)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert obsidian_api.available() is True
    assert seen["context"] is None  # non-loopback HTTPS keeps default cert verification


def test_trailing_slash_in_url_is_normalized(monkeypatch):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_URL", "https://127.0.0.1:27124/")
    captured = {}

    def fake_urlopen(req, timeout=None, context=None):
        captured["url"] = req.full_url
        return _FakeResp(200)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    obsidian_api.available()
    assert captured["url"] == "https://127.0.0.1:27124/"  # no double slash
