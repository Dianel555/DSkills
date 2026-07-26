"""Tests for grok-search CLI: Config + Tavily + commands."""
import sys
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def reset_config_singleton(monkeypatch):
    """Reset Config singleton state and clear env vars between tests."""
    for k in [
        "GROK_API_URL", "GROK_API_KEY", "GROK_MODEL", "GROK_DEBUG",
        "TAVILY_API_URL", "TAVILY_API_KEY", "TAVILY_ENABLED",
        "GROK_RETRY_MAX_ATTEMPTS", "GROK_RETRY_MULTIPLIER", "GROK_RETRY_MAX_WAIT",
    ]:
        monkeypatch.delenv(k, raising=False)
    import groksearch_cli
    groksearch_cli.Config._instance = None
    yield
    groksearch_cli.Config._instance = None


# ============================================================================
# Task 1.1: retry_* properties
# ============================================================================

class TestRetryConfig:
    def test_default_retry_values(self):
        from groksearch_cli import Config
        cfg = Config()
        assert cfg.retry_max_attempts == 3
        assert cfg.retry_multiplier == 1.0
        assert cfg.retry_max_wait == 10

    def test_env_overrides_retry(self, monkeypatch):
        monkeypatch.setenv("GROK_RETRY_MAX_ATTEMPTS", "5")
        monkeypatch.setenv("GROK_RETRY_MULTIPLIER", "2.5")
        monkeypatch.setenv("GROK_RETRY_MAX_WAIT", "20")
        from groksearch_cli import Config
        cfg = Config()
        assert cfg.retry_max_attempts == 5
        assert cfg.retry_multiplier == 2.5
        assert cfg.retry_max_wait == 20


# ============================================================================
# Task 1.2: tavily_* config properties
# ============================================================================

class TestTavilyConfig:
    def test_tavily_api_url_default(self):
        from groksearch_cli import Config
        assert Config().tavily_api_url == "https://api.tavily.com"

    def test_tavily_api_url_override(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_URL", "https://custom.tavily/v2")
        from groksearch_cli import Config
        assert Config().tavily_api_url == "https://custom.tavily/v2"

    def test_tavily_api_key_unset_returns_none(self):
        from groksearch_cli import Config
        assert Config().tavily_api_key is None

    def test_tavily_api_key_set(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-abc123")
        from groksearch_cli import Config
        assert Config().tavily_api_key == "tvly-abc123"

    def test_tavily_enabled_default_true(self):
        from groksearch_cli import Config
        assert Config().tavily_enabled is True

    def test_tavily_enabled_false(self, monkeypatch):
        monkeypatch.setenv("TAVILY_ENABLED", "false")
        from groksearch_cli import Config
        assert Config().tavily_enabled is False


# ============================================================================
# Task 1.3-1.4: _apply_model_suffix and grok_model integration
# ============================================================================

class TestModelSuffix:
    def test_openrouter_appends_online(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GROK_API_URL", "https://openrouter.ai/api/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        monkeypatch.setenv("GROK_MODEL", "grok-4-fast")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        from groksearch_cli import Config
        assert Config().grok_model == "grok-4-fast:online"

    def test_openrouter_with_existing_online_no_double(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GROK_API_URL", "https://openrouter.ai/api/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        monkeypatch.setenv("GROK_MODEL", "grok-4-fast:online")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        from groksearch_cli import Config
        assert Config().grok_model == "grok-4-fast:online"

    def test_non_openrouter_no_suffix(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        monkeypatch.setenv("GROK_MODEL", "grok-4-fast")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        from groksearch_cli import Config
        assert Config().grok_model == "grok-4-fast"


# ============================================================================
# Task 1.5: get_config_info exposes Tavily fields
# ============================================================================

class TestConfigInfoOutput:
    def test_get_config_info_includes_tavily_fields(self, monkeypatch):
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-grok-secret")
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-secretkey1234")
        from groksearch_cli import Config
        info = Config().get_config_info()
        assert "TAVILY_API_URL" in info
        assert "TAVILY_ENABLED" in info
        assert "TAVILY_API_KEY" in info
        # Masked
        assert info["TAVILY_API_KEY"] != "tvly-secretkey1234"
        assert "tvly" in info["TAVILY_API_KEY"]
        assert "1234" in info["TAVILY_API_KEY"]

    def test_get_config_info_tavily_unset_label(self, monkeypatch):
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        from groksearch_cli import Config
        info = Config().get_config_info()
        assert info["TAVILY_API_KEY"] in ("Not configured", "未配置")


# ============================================================================
# Task 2: Tavily call functions
# ============================================================================

class TestTavilyCallFunctions:
    @pytest.mark.asyncio
    async def test_call_tavily_search_returns_none_when_no_key(self):
        from groksearch_cli import _call_tavily_search
        result = await _call_tavily_search("query", max_results=3)
        assert result is None

    @pytest.mark.asyncio
    async def test_call_tavily_search_returns_results(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "results": [
                {"title": "Test", "url": "https://example.com", "content": "Body", "score": 0.9}
            ]
        })

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_search("test query", max_results=3)
        assert result == [
            {"title": "Test", "url": "https://example.com", "content": "Body", "score": 0.9}
        ]
        # Verify body
        call_args = mock_client.post.call_args
        body = call_args.kwargs["json"]
        assert body["query"] == "test query"
        assert body["max_results"] == 3
        assert body["search_depth"] == "advanced"
        assert body["include_raw_content"] is False
        assert body["include_answer"] is False

    @pytest.mark.asyncio
    async def test_call_tavily_search_exception_returns_none(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network"))

        async def _get_client():
            return mock_client
        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_search("q")
        assert result is None

    @pytest.mark.asyncio
    async def test_call_tavily_extract_returns_content(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "results": [{"raw_content": "# Page\nContent here"}]
        })
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client
        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_extract("https://example.com")
        assert result == "# Page\nContent here"
        body = mock_client.post.call_args.kwargs["json"]
        assert body == {"urls": ["https://example.com"], "format": "markdown"}

    @pytest.mark.asyncio
    async def test_call_tavily_extract_no_key_returns_none(self):
        from groksearch_cli import _call_tavily_extract
        result = await _call_tavily_extract("https://example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_call_tavily_map_returns_json_string(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "base_url": "https://docs.python.org",
            "results": ["https://docs.python.org/3"],
            "response_time": 1.2,
        })
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client
        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_map(
            "https://docs.python.org", instructions="api docs",
            max_depth=2, max_breadth=10, limit=20, timeout=60
        )
        data = json.loads(result)
        assert data["base_url"] == "https://docs.python.org"
        body = mock_client.post.call_args.kwargs["json"]
        assert body["url"] == "https://docs.python.org"
        assert body["max_depth"] == 2
        assert body["max_breadth"] == 10
        assert body["limit"] == 20
        assert body["timeout"] == 60
        assert body["instructions"] == "api docs"

    @pytest.mark.asyncio
    async def test_call_tavily_map_no_key_returns_error_string(self):
        from groksearch_cli import _call_tavily_map
        result = await _call_tavily_map(
            "https://x.com", instructions="", max_depth=1,
            max_breadth=20, limit=50, timeout=150
        )
        assert "TAVILY_API_KEY" in result


# ============================================================================
# Task 3: web_search --extra-sources merging
# ============================================================================

class TestWebSearchExtraSources:
    @pytest.mark.asyncio
    async def test_extra_sources_merges_results(self, monkeypatch, capsys):
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        async def fake_grok_search(*args, **kwargs):
            return json.dumps([
                {"title": "Grok1", "url": "https://a.com", "description": "A"},
            ])
        async def fake_tavily(query, max_results=6):
            return [
                {"title": "Tav1", "url": "https://a.com", "content": "dup"},
                {"title": "Tav2", "url": "https://b.com", "content": "B"},
            ]

        monkeypatch.setattr(groksearch_cli.GrokSearchProvider, "search", fake_grok_search)
        monkeypatch.setattr(groksearch_cli, "_call_tavily_search", fake_tavily)

        args = MagicMock(query="test", platform="", min_results=3, max_results=10,
                         extra_sources=2, raw=False)
        await groksearch_cli.cmd_web_search(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        urls = [d["url"] for d in data]
        assert "https://a.com" in urls
        assert "https://b.com" in urls
        # Tavily-marked entries
        providers = [d.get("provider") for d in data]
        assert "tavily" in providers
        # Grok url should appear only once (dedup)
        assert urls.count("https://a.com") == 1

    @pytest.mark.asyncio
    async def test_extra_sources_zero_no_tavily_call(self, monkeypatch, capsys):
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        called = {"tavily": 0}
        async def fake_grok_search(*a, **kw):
            return json.dumps([{"title": "G", "url": "https://g.com", "description": "G"}])
        async def fake_tavily(*a, **kw):
            called["tavily"] += 1
            return None

        monkeypatch.setattr(groksearch_cli.GrokSearchProvider, "search", fake_grok_search)
        monkeypatch.setattr(groksearch_cli, "_call_tavily_search", fake_tavily)

        args = MagicMock(query="test", platform="", min_results=3, max_results=10,
                         extra_sources=0, raw=False)
        await groksearch_cli.cmd_web_search(args)
        assert called["tavily"] == 0

    @pytest.mark.asyncio
    async def test_extra_sources_tavily_failure_does_not_block(self, monkeypatch, capsys):
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        async def fake_grok_search(*a, **kw):
            return json.dumps([{"title": "G", "url": "https://g.com", "description": "G"}])
        async def fake_tavily(*a, **kw):
            return None  # simulate failure

        monkeypatch.setattr(groksearch_cli.GrokSearchProvider, "search", fake_grok_search)
        monkeypatch.setattr(groksearch_cli, "_call_tavily_search", fake_tavily)

        args = MagicMock(query="t", platform="", min_results=3, max_results=10,
                         extra_sources=3, raw=False)
        await groksearch_cli.cmd_web_search(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert any(d["url"] == "https://g.com" for d in data)


# ============================================================================
# Task 4: web_fetch --via {grok|tavily}
# ============================================================================

class TestWebFetchViaTavily:
    @pytest.mark.asyncio
    async def test_via_tavily_calls_extract(self, monkeypatch, capsys):
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        async def fake_extract(url):
            return f"# Extracted: {url}"
        monkeypatch.setattr(groksearch_cli, "_call_tavily_extract", fake_extract)

        args = MagicMock(url="https://example.com", out=None, via="tavily")
        await groksearch_cli.cmd_web_fetch(args)
        out = capsys.readouterr().out
        assert "Extracted: https://example.com" in out

    @pytest.mark.asyncio
    async def test_via_tavily_no_key_errors(self, monkeypatch, capsys):
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        args = MagicMock(url="https://example.com", out=None, via="tavily")
        with pytest.raises(SystemExit) as exc:
            await groksearch_cli.cmd_web_fetch(args)
        assert exc.value.code != 0

    @pytest.mark.asyncio
    async def test_via_grok_default_path(self, monkeypatch, capsys):
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        async def fake_fetch(self, url):
            return f"GROK FETCH: {url}"
        monkeypatch.setattr(groksearch_cli.GrokSearchProvider, "fetch", fake_fetch)

        args = MagicMock(url="https://example.com", out=None, via="grok")
        await groksearch_cli.cmd_web_fetch(args)
        out = capsys.readouterr().out
        assert "GROK FETCH" in out


# ============================================================================
# Task 5: web_map subcommand
# ============================================================================

class TestWebMap:
    @pytest.mark.asyncio
    async def test_web_map_command_calls_tavily_map(self, monkeypatch, capsys):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli
        groksearch_cli.Config._instance = None

        captured = {}
        async def fake_map(url, instructions, max_depth, max_breadth, limit, timeout):
            captured.update(locals())
            return json.dumps({"base_url": url, "results": [], "response_time": 0.5})
        monkeypatch.setattr(groksearch_cli, "_call_tavily_map", fake_map)

        args = MagicMock(url="https://docs.python.org", instructions="api",
                         max_depth=2, max_breadth=15, limit=30, timeout=120)
        await groksearch_cli.cmd_web_map(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["base_url"] == "https://docs.python.org"
        assert captured["max_depth"] == 2
        assert captured["max_breadth"] == 15
        assert captured["limit"] == 30
        assert captured["timeout"] == 120

    def test_web_map_argparse_registered(self):
        import groksearch_cli
        # Build parser to verify subcommand registration
        from io import StringIO
        old_stderr = sys.stderr
        sys.stderr = StringIO()
        try:
            with pytest.raises(SystemExit):
                # Trigger parser to print help on a known subcommand
                old_argv = sys.argv
                sys.argv = ["groksearch_cli", "web_map", "--help"]
                try:
                    groksearch_cli.main()
                except SystemExit as e:
                    # argparse prints help and exits 0
                    if e.code != 0:
                        raise
                    raise
                finally:
                    sys.argv = old_argv
        finally:
            sys.stderr = old_stderr
