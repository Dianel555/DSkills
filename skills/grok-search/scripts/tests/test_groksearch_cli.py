"""Tests for grok-search CLI: Config + Tavily + commands."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def reset_config_singleton(monkeypatch):
    """Reset Config singleton state and clear env vars between tests."""
    for k in [
        "GROK_API_URL",
        "GROK_API_KEY",
        "GROK_MODEL",
        "GROK_DEBUG",
        "TAVILY_API_URL",
        "TAVILY_API_KEY",
        "TAVILY_ENABLED",
        "TAVILY_SEARCH_DEPTH",
        "TAVILY_CHUNKS_PER_SOURCE",
        "TAVILY_INCLUDE_ANSWER",
        "TAVILY_EXTRACT_TIMEOUT",
        "TAVILY_EXTRACT_DEPTH",
        "TAVILY_TOPIC",
        "TAVILY_TIME_RANGE",
        "TAVILY_INCLUDE_DOMAINS",
        "TAVILY_EXCLUDE_DOMAINS",
        "TAVILY_INCLUDE_DOMAINS_MODE",
        "TAVILY_INCLUDE_USAGE",
        "TAVILY_CRAWL_TIMEOUT",
        "TAVILY_CRAWL_MAX_DEPTH",
        "TAVILY_CRAWL_MAX_BREADTH",
        "TAVILY_CRAWL_LIMIT",
        "TAVILY_CRAWL_ALLOW_EXTERNAL",
        "TAVILY_CRAWL_SELECT_PATHS",
        "TAVILY_CRAWL_EXCLUDE_PATHS",
        "TAVILY_RESEARCH_MODEL",
        "TAVILY_RESEARCH_CITATION_FORMAT",
        "TAVILY_RESEARCH_OUTPUT_LENGTH",
        "TAVILY_RESEARCH_TIMEOUT",
        "TAVILY_RESEARCH_POLL_INTERVAL",
        "GROK_RETRY_MAX_ATTEMPTS",
        "GROK_RETRY_MULTIPLIER",
        "GROK_RETRY_MAX_WAIT",
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

    def test_search_tuning_defaults(self):
        from groksearch_cli import Config

        cfg = Config()
        assert cfg.tavily_search_depth == "advanced"
        assert cfg.tavily_chunks_per_source == 3
        assert cfg.tavily_include_answer is False
        assert cfg.tavily_extract_timeout == 30.0

    def test_search_tuning_env_overrides(self, monkeypatch):
        monkeypatch.setenv("TAVILY_SEARCH_DEPTH", "ultra-fast")
        monkeypatch.setenv("TAVILY_CHUNKS_PER_SOURCE", "5")
        monkeypatch.setenv("TAVILY_INCLUDE_ANSWER", "advanced")
        monkeypatch.setenv("TAVILY_EXTRACT_TIMEOUT", "45")
        from groksearch_cli import Config

        cfg = Config()
        assert cfg.tavily_search_depth == "ultra-fast"
        assert cfg.tavily_chunks_per_source == 5
        assert cfg.tavily_include_answer == "advanced"
        assert cfg.tavily_extract_timeout == 45.0

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("false", False),
            ("0", False),
            ("no", False),
            ("", False),
            ("true", "basic"),
            ("1", "basic"),
            ("basic", "basic"),
            ("advanced", "advanced"),
        ],
    )
    def test_include_answer_aliases(self, monkeypatch, raw, expected):
        monkeypatch.setenv("TAVILY_INCLUDE_ANSWER", raw)
        from groksearch_cli import Config

        value = Config().tavily_include_answer
        assert value == expected
        # Tavily rejects the string "false" with a 400 — the disabled state must be boolean.
        if expected is False:
            assert value is False

    def test_invalid_search_depth_rejected(self, monkeypatch):
        monkeypatch.setenv("TAVILY_SEARCH_DEPTH", "deep")
        from groksearch_cli import Config

        with pytest.raises(ValueError, match="TAVILY_SEARCH_DEPTH"):
            _ = Config().tavily_search_depth

    def test_invalid_include_answer_rejected(self, monkeypatch):
        monkeypatch.setenv("TAVILY_INCLUDE_ANSWER", "maybe")
        from groksearch_cli import Config

        with pytest.raises(ValueError, match="TAVILY_INCLUDE_ANSWER"):
            _ = Config().tavily_include_answer

    def test_filter_defaults(self):
        from groksearch_cli import Config

        cfg = Config()
        assert cfg.tavily_topic == "general"
        assert cfg.tavily_time_range == ""
        assert cfg.tavily_include_domains == []
        assert cfg.tavily_exclude_domains == []
        assert cfg.tavily_include_domains_mode == "filter"
        assert cfg.tavily_include_usage is False
        assert cfg.tavily_extract_depth == "basic"

    def test_domain_lists_parsed_from_csv(self, monkeypatch):
        monkeypatch.setenv("TAVILY_INCLUDE_DOMAINS", "reuters.com, bloomberg.com ,")
        monkeypatch.setenv("TAVILY_EXCLUDE_DOMAINS", "espn.com")
        from groksearch_cli import Config

        cfg = Config()
        assert cfg.tavily_include_domains == ["reuters.com", "bloomberg.com"]
        assert cfg.tavily_exclude_domains == ["espn.com"]

    def test_chunks_per_source_out_of_range_rejected(self, monkeypatch):
        # Live API: "chunks_per_source must be an integer between 1 and 5, or 'auto'"
        monkeypatch.setenv("TAVILY_CHUNKS_PER_SOURCE", "6")
        from groksearch_cli import Config

        with pytest.raises(ValueError, match="TAVILY_CHUNKS_PER_SOURCE"):
            _ = Config().tavily_chunks_per_source

    @pytest.mark.parametrize(
        "var,value",
        [
            ("TAVILY_TOPIC", "bogus"),
            ("TAVILY_TIME_RANGE", "decade"),
            ("TAVILY_INCLUDE_DOMAINS_MODE", "strict"),
            ("TAVILY_EXTRACT_DEPTH", "deep"),
        ],
    )
    def test_invalid_filter_values_surface_in_config_info(self, monkeypatch, var, value):
        """A bad tuning value must be reported in the dump, not crash it."""
        monkeypatch.setenv(var, value)
        from groksearch_cli import Config

        info = Config().get_config_info()
        assert var in info
        assert "❌" in info[var], f"{var} should be flagged as invalid"

    def test_domains_mode_omitted_without_include_domains(self, monkeypatch):
        """include_domains_mode alone is a 400 — it must not be sent unless domains are set."""
        import asyncio

        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_INCLUDE_DOMAINS_MODE", "boost")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"results": []})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        asyncio.run(groksearch_cli._call_tavily_search("q"))
        body = mock_client.post.call_args.kwargs["json"]
        assert "include_domains_mode" not in body
        assert "include_domains" not in body
        # Unset optional filters must be omitted entirely, not sent as empty values.
        assert "topic" in body and body["topic"] == "general"
        assert "time_range" not in body
        assert "include_usage" not in body

    def test_filters_included_when_configured(self, monkeypatch):
        import asyncio

        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_INCLUDE_DOMAINS", "reuters.com,bloomberg.com")
        monkeypatch.setenv("TAVILY_INCLUDE_DOMAINS_MODE", "boost")
        monkeypatch.setenv("TAVILY_EXCLUDE_DOMAINS", "espn.com")
        monkeypatch.setenv("TAVILY_TIME_RANGE", "month")
        monkeypatch.setenv("TAVILY_INCLUDE_USAGE", "true")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"results": []})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        asyncio.run(groksearch_cli._call_tavily_search("q"))
        body = mock_client.post.call_args.kwargs["json"]
        assert body["include_domains"] == ["reuters.com", "bloomberg.com"]
        assert body["include_domains_mode"] == "boost"
        assert body["exclude_domains"] == ["espn.com"]
        assert body["time_range"] == "month"
        assert body["include_usage"] is True

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

    @pytest.mark.parametrize(
        "var,raw",
        [
            ("TAVILY_CRAWL_TIMEOUT", "abc"),
            ("TAVILY_CRAWL_TIMEOUT", "500"),
            ("TAVILY_CRAWL_TIMEOUT", "nan"),
            ("TAVILY_CRAWL_LIMIT", "0"),
            ("TAVILY_EXTRACT_TIMEOUT", "61"),
            ("TAVILY_RESEARCH_POLL_INTERVAL", "-1"),
        ],
    )
    def test_numeric_tuning_out_of_range_rejected(self, monkeypatch, var, raw):
        """Numeric tuning must reject non-finite / out-of-range values with a named error."""
        monkeypatch.setenv(var, raw)
        from groksearch_cli import Config

        prop = {
            "TAVILY_CRAWL_TIMEOUT": "tavily_crawl_timeout",
            "TAVILY_CRAWL_LIMIT": "tavily_crawl_limit",
            "TAVILY_EXTRACT_TIMEOUT": "tavily_extract_timeout",
            "TAVILY_RESEARCH_POLL_INTERVAL": "tavily_research_poll_interval",
        }[var]
        with pytest.raises(ValueError, match=var):
            _ = getattr(Config(), prop)


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

    def test_get_config_info_invalid_value_is_per_key(self, monkeypatch):
        """One bad tuning value must flag only its own key, not the whole tuning block."""
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        monkeypatch.setenv("TAVILY_TOPIC", "bogus")
        from groksearch_cli import Config

        info = Config().get_config_info()
        assert "❌" in info["TAVILY_TOPIC"]
        assert info["TAVILY_SEARCH_DEPTH"] == "advanced"
        assert info["TAVILY_CRAWL_LIMIT"] == 50


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
        mock_response.json = MagicMock(
            return_value={"results": [{"title": "Test", "url": "https://example.com", "content": "Body", "score": 0.9}]}
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_search("test query", max_results=3)
        assert result == [{"title": "Test", "url": "https://example.com", "content": "Body", "score": 0.9}]
        # Verify body
        call_args = mock_client.post.call_args
        body = call_args.kwargs["json"]
        assert body["query"] == "test query"
        assert body["max_results"] == 3
        assert body["search_depth"] == "advanced"
        assert body["chunks_per_source"] == 3
        assert body["include_raw_content"] is False
        assert body["include_answer"] is False

    @pytest.mark.asyncio
    async def test_search_body_uses_tuning_config(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_SEARCH_DEPTH", "ultra-fast")
        monkeypatch.setenv("TAVILY_CHUNKS_PER_SOURCE", "5")
        monkeypatch.setenv("TAVILY_INCLUDE_ANSWER", "advanced")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"results": []})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        await groksearch_cli._call_tavily_search("q")
        body = mock_client.post.call_args.kwargs["json"]
        assert body["search_depth"] == "ultra-fast"
        assert body["chunks_per_source"] == 5
        assert body["include_answer"] == "advanced"

    @pytest.mark.asyncio
    async def test_call_tavily_search_exception_returns_none(self, monkeypatch, capsys):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.NetworkError("network"))

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_search("q")
        assert result is None
        captured = capsys.readouterr()
        # Contract: the message must disclose retry exhaustion, not read as a first-attempt failure.
        assert "after 3 attempts" in captured.err
        assert "network" in captured.err

    @pytest.mark.asyncio
    async def test_call_tavily_search_retries_persistent_network_error(self, monkeypatch, capsys):
        """A network error that survives every retry reports exhaustion, not a transient failure."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        attempts = {"n": 0}
        mock_client = AsyncMock()

        async def _post(*a, **kw):
            attempts["n"] += 1
            raise httpx.ConnectError("persistent")

        mock_client.post = _post

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_search("q")
        assert result is None
        assert attempts["n"] == 3, "all retry attempts must be made before reporting"
        err = capsys.readouterr().err
        assert "3 attempts" in err

    @pytest.mark.asyncio
    async def test_call_tavily_search_429_reports_after_retries(self, monkeypatch, capsys):
        """429 is in RETRYABLE_STATUS_CODES, so it is retried before being reported."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        attempts = {"n": 0}
        mock_client = AsyncMock()

        async def _post(*a, **kw):
            attempts["n"] += 1
            req = httpx.Request("POST", "https://api.tavily.com/search")
            raise httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, request=req))

        mock_client.post = _post

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_search("q")
        assert result is None
        assert attempts["n"] == 3
        err = capsys.readouterr().err
        assert "quota exceeded" in err
        assert "3 attempts" in err

    @pytest.mark.asyncio
    async def test_call_tavily_search_non_retryable_401_never_claims_retries(self, monkeypatch, capsys):
        """401/403/400/432 are attempted exactly once — claiming '(after N attempts)' would be false."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        attempts = {"n": 0}
        mock_client = AsyncMock()

        async def _post(*a, **kw):
            attempts["n"] += 1
            req = httpx.Request("POST", "https://api.tavily.com/search")
            raise httpx.HTTPStatusError("401", request=req, response=httpx.Response(401, request=req))

        mock_client.post = _post

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_search("q")
        assert result is None
        assert attempts["n"] == 1, "401 is not retryable and must not enter the retry loop"
        err = capsys.readouterr().err
        assert "TAVILY_API_KEY invalid or missing" in err
        assert "attempts" not in err, "a single-attempt fatal error must not be labelled as retry-exhausted"

    @pytest.mark.asyncio
    async def test_call_tavily_search_reports_intermediate_retries(self, monkeypatch, capsys):
        """Intermediate attempts must be visible: a 3-attempt failure must not look like a 1-attempt one."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        mock_client = AsyncMock()

        async def _post(*a, **kw):
            raise httpx.ConnectError("persistent")

        mock_client.post = _post

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        await groksearch_cli._call_tavily_search("q")
        err = capsys.readouterr().err
        assert "attempt 1 failed" in err
        assert "attempt 2 failed" in err
        # The final attempt fails without scheduling another retry, so no "attempt 3 failed" progress line.
        assert "attempt 3 failed" not in err

    @pytest.mark.asyncio
    async def test_call_tavily_extract_returns_content(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"results": [{"raw_content": "# Page\nContent here"}]})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_extract("https://example.com")
        assert result == "# Page\nContent here"
        body = mock_client.post.call_args.kwargs["json"]
        assert body["urls"] == ["https://example.com"]
        assert body["format"] == "markdown"
        # Tavily's own timeout (API range 1.0-60.0) must be sent, not left to the default.
        assert body["timeout"] == 30.0
        # The HTTP client must outlast Tavily's timeout so Tavily's error wins over ours.
        client_timeout = mock_client.post.call_args.kwargs["timeout"]
        assert client_timeout.read > body["timeout"]

    @pytest.mark.asyncio
    async def test_call_tavily_extract_timeout_configurable(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_EXTRACT_TIMEOUT", "55")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"results": [{"raw_content": "x"}]})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        await groksearch_cli._call_tavily_extract("https://example.com")
        body = mock_client.post.call_args.kwargs["json"]
        assert body["timeout"] == 55.0

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
        mock_response.json = MagicMock(
            return_value={
                "base_url": "https://docs.python.org",
                "results": ["https://docs.python.org/3"],
                "response_time": 1.2,
            }
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_map(
            "https://docs.python.org", instructions="api docs", max_depth=2, max_breadth=10, limit=20, timeout=60
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
            "https://x.com", instructions="", max_depth=1, max_breadth=20, limit=50, timeout=150
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
            return json.dumps(
                [
                    {"title": "Grok1", "url": "https://a.com", "description": "A"},
                ]
            )

        async def fake_tavily(query, max_results=6):
            return [
                {"title": "Tav1", "url": "https://a.com", "content": "dup"},
                {"title": "Tav2", "url": "https://b.com", "content": "B"},
            ]

        monkeypatch.setattr(groksearch_cli.GrokSearchProvider, "search", fake_grok_search)
        monkeypatch.setattr(groksearch_cli, "_call_tavily_search", fake_tavily)

        args = MagicMock(query="test", platform="", min_results=3, max_results=10, extra_sources=2, raw=False)
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

        args = MagicMock(query="test", platform="", min_results=3, max_results=10, extra_sources=0, raw=False)
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

        args = MagicMock(query="t", platform="", min_results=3, max_results=10, extra_sources=3, raw=False)
        await groksearch_cli.cmd_web_search(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert any(d["url"] == "https://g.com" for d in data)
        # Requested-but-unavailable extra sources must be disclosed, not silently dropped.
        assert "Tavily extra sources were requested" in captured.err
        assert data[0].get("degraded") == "tavily_unavailable"
        # The disclosure must not inject a synthetic element into the results array.
        assert all(d.get("url") for d in data)

    @pytest.mark.asyncio
    async def test_extra_sources_zero_not_marked_degraded(self, monkeypatch, capsys):
        """No degradation marker when Tavily was never requested."""
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        async def fake_grok_search(*a, **kw):
            return json.dumps([{"title": "G", "url": "https://g.com", "description": "G"}])

        monkeypatch.setattr(groksearch_cli.GrokSearchProvider, "search", fake_grok_search)

        args = MagicMock(query="t", platform="", min_results=3, max_results=10, extra_sources=0, raw=False)
        await groksearch_cli.cmd_web_search(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "degraded" not in data[0]
        assert "Tavily extra sources" not in captured.err


# ============================================================================
# Task 4: web_fetch --via {grok|tavily}
# ============================================================================


class TestGrokStreamingPreference:
    @pytest.mark.asyncio
    async def test_search_uses_streaming_request(self, monkeypatch):
        monkeypatch.setenv("GROK_API_URL", "https://api.example/v1")
        from groksearch.provider import GrokSearchProvider

        provider = GrokSearchProvider("https://api.example/v1", "sk-test", "grok-test")
        execute_stream = AsyncMock(return_value="# Example")
        execute_non_stream = AsyncMock(side_effect=AssertionError("search must not start with a non-streaming request"))
        monkeypatch.setattr(provider, "_execute_stream", execute_stream)
        monkeypatch.setattr(provider, "_execute_non_stream", execute_non_stream)

        result = await provider.search("example")

        assert result == "# Example"
        execute_stream.assert_awaited_once()
        execute_non_stream.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_uses_streaming_request(self, monkeypatch):
        monkeypatch.setenv("GROK_API_URL", "https://api.example/v1")
        from groksearch.provider import GrokSearchProvider

        provider = GrokSearchProvider("https://api.example/v1", "sk-test", "grok-test")
        execute_stream = AsyncMock(return_value="# Example")
        execute_non_stream = AsyncMock(side_effect=AssertionError("fetch must not start with a non-streaming request"))
        monkeypatch.setattr(provider, "_execute_stream", execute_stream)
        monkeypatch.setattr(provider, "_execute_non_stream", execute_non_stream)

        result = await provider.fetch("https://example.com")

        assert result == "# Example"
        execute_stream.assert_awaited_once()
        execute_non_stream.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stream_failure_falls_back_to_non_stream(self, monkeypatch):
        monkeypatch.setenv("GROK_API_URL", "https://api.example/v1")
        from groksearch.provider import GrokSearchProvider

        provider = GrokSearchProvider("https://api.example/v1", "sk-test", "grok-test")
        calls = []

        async def execute_stream(payload):
            calls.append("stream")
            raise httpx.ReadTimeout("stream failed")

        async def execute_non_stream(payload):
            calls.append("non-stream")
            return "fallback"

        monkeypatch.setattr(provider, "_execute_stream", execute_stream)
        monkeypatch.setattr(provider, "_execute_non_stream", execute_non_stream)

        result = await provider.fetch("https://example.com")

        assert result == "fallback"
        assert calls == ["stream", "non-stream"]

    @pytest.mark.asyncio
    async def test_empty_stream_falls_back_to_non_stream(self, monkeypatch):
        monkeypatch.setenv("GROK_API_URL", "https://api.example/v1")
        from groksearch.provider import GrokSearchProvider

        provider = GrokSearchProvider("https://api.example/v1", "sk-test", "grok-test")
        execute_stream = AsyncMock(return_value="")
        execute_non_stream = AsyncMock(return_value="fallback")
        monkeypatch.setattr(provider, "_execute_stream", execute_stream)
        monkeypatch.setattr(provider, "_execute_non_stream", execute_non_stream)

        result = await provider.search("example")

        assert result == "fallback"
        execute_stream.assert_awaited_once()
        execute_non_stream.assert_awaited_once()


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

        args = MagicMock(
            url="https://docs.python.org", instructions="api", max_depth=2, max_breadth=15, limit=30, timeout=120
        )
        await groksearch_cli.cmd_web_map(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["base_url"] == "https://docs.python.org"
        assert captured["max_depth"] == 2
        assert captured["max_breadth"] == 15
        assert captured["limit"] == 30
        assert captured["timeout"] == 120

    def test_web_map_argparse_registered(self):
        # Build parser to verify subcommand registration
        from io import StringIO

        import groksearch_cli

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


# ============================================================================
# Task 6: web_crawl + web_research
# ============================================================================


class TestWebCrawl:
    @pytest.mark.asyncio
    async def test_crawl_command_passes_options(self, monkeypatch, capsys):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        captured = {}

        async def fake_crawl(url, instructions, max_depth, max_breadth, limit, timeout, select_paths, exclude_paths):
            captured.update(locals())
            return json.dumps({"base_url": url, "results": [], "response_time": 1.0})

        monkeypatch.setattr(groksearch_cli, "_call_tavily_crawl", fake_crawl)

        args = MagicMock(
            url="https://docs.python.org",
            instructions="api",
            max_depth=2,
            max_breadth=10,
            limit=20,
            timeout=60,
            select_paths="/docs/.*",
            exclude_paths="/blog/.*",
        )
        await groksearch_cli.cmd_web_crawl(args)
        data = json.loads(capsys.readouterr().out)
        assert data["base_url"] == "https://docs.python.org"
        assert captured["max_depth"] == 2
        assert captured["limit"] == 20
        assert captured["select_paths"] == "/docs/.*"

    @pytest.mark.asyncio
    async def test_crawl_body_uses_config_defaults(self, monkeypatch):
        """Options default to the configured values when not passed on the CLI."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_CRAWL_MAX_DEPTH", "3")
        monkeypatch.setenv("TAVILY_CRAWL_LIMIT", "25")
        monkeypatch.setenv("TAVILY_CRAWL_ALLOW_EXTERNAL", "false")
        monkeypatch.setenv("TAVILY_CRAWL_SELECT_PATHS", "/docs/.*,/api/.*")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"base_url": "u", "results": []})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        await groksearch_cli._call_tavily_crawl("https://x.com")
        body = mock_client.post.call_args.kwargs["json"]
        assert body["max_depth"] == 3
        assert body["limit"] == 25
        assert body["allow_external"] is False
        # CSV config must reach the API as a real list, not a raw string.
        assert body["select_paths"] == ["/docs/.*", "/api/.*"]
        assert "include_usage" not in body  # False is omitted

    @pytest.mark.asyncio
    async def test_crawl_no_key_returns_config_error(self):
        from groksearch_cli import _call_tavily_crawl

        result = await _call_tavily_crawl("https://x.com")
        assert "TAVILY_API_KEY" in result

    def test_crawl_argparse_registered(self):
        import groksearch_cli

        parser = groksearch_cli.build_parser()
        args = parser.parse_args(["web_crawl", "--url", "https://x.com"])
        assert args.url == "https://x.com"
        assert args.max_depth is None  # falls back to config


class TestWebResearch:
    @pytest.mark.asyncio
    async def test_research_polls_until_completed(self, monkeypatch, capsys):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_POLL_INTERVAL", "0")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        posted = {}

        class FakeResponse:
            def __init__(self, payload, status=200):
                self._payload = payload
                self.status_code = status

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        states = [{"status": "in_progress"}, {"status": "completed", "content": "Answer", "sources": []}]

        class FakeClient:
            async def post(self, url, **kw):
                posted.update(kw.get("json") or {})
                return FakeResponse({"request_id": "req-1", "status": "pending"})

            async def get(self, url, **kw):
                return FakeResponse(states.pop(0))

        async def _get_client():
            return FakeClient()

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_research("What is Tavily?")
        data = json.loads(result)
        assert data["status"] == "completed"
        assert data["content"] == "Answer"
        assert posted["input"] == "What is Tavily?"

    @pytest.mark.asyncio
    async def test_research_body_uses_config(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_MODEL", "pro")
        monkeypatch.setenv("TAVILY_RESEARCH_CITATION_FORMAT", "apa")
        monkeypatch.setenv("TAVILY_RESEARCH_OUTPUT_LENGTH", "long")
        monkeypatch.setenv("TAVILY_RESEARCH_POLL_INTERVAL", "0")
        monkeypatch.setenv("TAVILY_INCLUDE_DOMAINS", "reuters.com")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        posted = {}

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeClient:
            async def post(self, url, **kw):
                posted.update(kw.get("json") or {})
                return FakeResponse({"request_id": "r"})

            async def get(self, url, **kw):
                return FakeResponse({"status": "completed", "content": ""})

        async def _get_client():
            return FakeClient()

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        await groksearch_cli._call_tavily_research("q")
        assert posted["model"] == "pro"
        assert posted["citation_format"] == "apa"
        assert posted["output_length"] == "long"
        assert posted["include_domains"] == ["reuters.com"]

    @pytest.mark.asyncio
    async def test_research_timeout_returns_request_id(self, monkeypatch):
        """A task that never finishes must return its request_id, not hang."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_TIMEOUT", "0")
        monkeypatch.setenv("TAVILY_RESEARCH_POLL_INTERVAL", "0")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeClient:
            async def post(self, url, **kw):
                return FakeResponse({"request_id": "req-slow"})

            async def get(self, url, **kw):
                return FakeResponse({"status": "in_progress"})

        async def _get_client():
            return FakeClient()

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        data = json.loads(await groksearch_cli._call_tavily_research("q"))
        assert data["status"] == "timeout"
        assert data["request_id"] == "req-slow"

    @pytest.mark.asyncio
    async def test_research_rejected_task_reports_response(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"detail": {"error": "bad input"}}

        class FakeClient:
            async def post(self, url, **kw):
                return FakeResponse()

        async def _get_client():
            return FakeClient()

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        data = json.loads(await groksearch_cli._call_tavily_research("q"))
        assert "error" in data

    def test_research_argparse_registered(self):
        import groksearch_cli

        parser = groksearch_cli.build_parser()
        args = parser.parse_args(["web_research", "--input", "What is Tavily?"])
        assert args.input == "What is Tavily?"
        assert args.model is None  # falls back to config
        assert args.output_schema is None

    @pytest.mark.asyncio
    async def test_research_poll_network_error_keeps_request_id(self, monkeypatch):
        """A poll failure after task creation must return JSON with request_id, not a bare string."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_POLL_INTERVAL", "0")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"request_id": "r"}

        class FakeClient:
            async def post(self, url, **kw):
                return FakeResponse()

            async def get(self, url, **kw):
                raise httpx.ConnectError("poll dropped")

        async def _get_client():
            return FakeClient()

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        data = json.loads(await groksearch_cli._call_tavily_research("q"))
        assert data["request_id"] == "r"
        assert data["status"] == "poll_error"
        assert "poll dropped" in data["error"]

    @pytest.mark.asyncio
    async def test_research_poll_budget_bounds_sleep(self, monkeypatch):
        """The poll interval must be clamped to the remaining budget so a large interval cannot overshoot."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_TIMEOUT", "0")
        monkeypatch.setenv("TAVILY_RESEARCH_POLL_INTERVAL", "30")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"request_id": "r"}

        class FakeClient:
            async def post(self, url, **kw):
                return FakeResponse()

            async def get(self, url, **kw):
                raise AssertionError("must not poll after the budget is spent")

        async def _get_client():
            return FakeClient()

        async def _sleep(seconds):
            # With budget 0 the clamped sleep must be 0, not the configured 30s interval.
            assert seconds == 0

        import asyncio

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)
        monkeypatch.setattr(asyncio, "sleep", _sleep)

        data = json.loads(await groksearch_cli._call_tavily_research("q"))
        assert data["status"] == "timeout"
        assert data["request_id"] == "r"

    @pytest.mark.asyncio
    async def test_research_invalid_model_returns_json_error(self, monkeypatch, capsys):
        """An invalid research tuning env surfaces as a JSON error, not a bare traceback."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_MODEL", "huge")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        with pytest.raises(SystemExit) as excinfo:
            await groksearch_cli.cmd_web_research(
                MagicMock(input="q", model=None, output_length=None, citation_format=None, output_schema=None)
            )
        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        data = json.loads(err)
        assert "TAVILY_RESEARCH_MODEL" in data["error"]


VALID_SCHEMA = {
    "properties": {
        "company": {"type": "string", "description": "The company name"},
        "metrics": {
            "type": "array",
            "description": "Key metrics",
            "items": {"type": "string"},
        },
    },
    "required": ["company"],
}


class TestResearchOutputSchema:
    def test_valid_schema_passes_validation(self):
        from groksearch_cli import _validate_output_schema

        assert _validate_output_schema(VALID_SCHEMA) is None

    @pytest.mark.parametrize(
        "schema,needle",
        [
            ({"properties": {}}, "non-empty 'properties'"),
            ({"type": "object"}, "non-empty 'properties'"),
            ({"properties": {"a": {"description": "d"}}}, "needs a type"),
            ({"properties": {"a": {"type": "blob", "description": "d"}}}, "needs a type"),
            ({"properties": {"a": {"type": "string"}}}, "needs a description"),
            ({"properties": {"a": {"type": "array", "description": "d"}}}, "needs 'items'"),
            ({"properties": {"a": {"type": "object", "description": "d"}}}, "needs non-empty 'properties'"),
            (
                {"properties": {"a": {"type": "string", "description": "d"}}, "required": ["b"]},
                "not present in properties",
            ),
            ({"properties": {"a": {"type": "string", "description": "d"}}, "required": []}, "non-empty array"),
        ],
    )
    def test_invalid_schemas_rejected_with_reason(self, schema, needle):
        """Rejecting locally is cheaper than a 400 round-trip; the message must name the fault."""
        from groksearch_cli import _validate_output_schema

        error = _validate_output_schema(schema)
        assert error and needle in error

    def test_nested_object_validated(self):
        from groksearch_cli import _validate_output_schema

        schema = {
            "properties": {
                "financials": {
                    "type": "object",
                    "description": "breakdown",
                    "properties": {"income": {"type": "string"}},  # missing description
                }
            }
        }
        assert "income" in _validate_output_schema(schema)

    @pytest.mark.asyncio
    async def test_output_schema_sent_in_body(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_POLL_INTERVAL", "0")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        posted = {}

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeClient:
            async def post(self, url, **kw):
                posted.update(kw.get("json") or {})
                return FakeResponse({"request_id": "r"})

            async def get(self, url, **kw):
                return FakeResponse({"status": "completed", "content": {"company": "Acme"}})

        async def _get_client():
            return FakeClient()

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_research("q", output_schema=VALID_SCHEMA)
        assert posted["output_schema"] == VALID_SCHEMA
        # Structured output arrives as an object in `content`, not a string.
        assert json.loads(result)["content"] == {"company": "Acme"}

    @pytest.mark.asyncio
    async def test_invalid_output_schema_stops_before_any_request(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        called = {"post": 0}

        class FakeClient:
            async def post(self, url, **kw):
                called["post"] += 1
                raise AssertionError("must not call the API with an invalid schema")

        async def _get_client():
            return FakeClient()

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_research(
            "q", output_schema={"properties": {"a": {"type": "string"}}}
        )
        assert result.startswith("Configuration error:")
        assert called["post"] == 0

    @pytest.mark.asyncio
    async def test_schema_loaded_from_file(self, monkeypatch, tmp_path):
        schema_file = tmp_path / "schema.json"
        schema_file.write_text(json.dumps(VALID_SCHEMA), encoding="utf-8")
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_POLL_INTERVAL", "0")
        monkeypatch.setenv("TAVILY_RESEARCH_OUTPUT_SCHEMA", str(schema_file))
        import groksearch_cli

        groksearch_cli.Config._instance = None

        posted = {}

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeClient:
            async def post(self, url, **kw):
                posted.update(kw.get("json") or {})
                return FakeResponse({"request_id": "r"})

            async def get(self, url, **kw):
                return FakeResponse({"status": "completed", "content": {}})

        async def _get_client():
            return FakeClient()

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        await groksearch_cli._call_tavily_research("q")
        assert posted["output_schema"] == VALID_SCHEMA

    @pytest.mark.asyncio
    async def test_missing_schema_file_reports_config_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_OUTPUT_SCHEMA", str(tmp_path / "nope.json"))
        import groksearch_cli

        groksearch_cli.Config._instance = None

        result = await groksearch_cli._call_tavily_research("q")
        assert result.startswith("Configuration error:")
        assert "nope.json" in result

    @pytest.mark.asyncio
    async def test_malformed_schema_file_reports_config_error(self, monkeypatch, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_OUTPUT_SCHEMA", str(bad))
        import groksearch_cli

        groksearch_cli.Config._instance = None

        result = await groksearch_cli._call_tavily_research("q")
        assert result.startswith("Configuration error:")
        assert "not valid JSON" in result

    @pytest.mark.asyncio
    async def test_no_schema_means_omitted_from_body(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_RESEARCH_POLL_INTERVAL", "0")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        posted = {}

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeClient:
            async def post(self, url, **kw):
                posted.update(kw.get("json") or {})
                return FakeResponse({"request_id": "r"})

            async def get(self, url, **kw):
                return FakeResponse({"status": "completed", "content": "text"})

        async def _get_client():
            return FakeClient()

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        await groksearch_cli._call_tavily_research("q")
        assert "output_schema" not in posted


class TestTavilyUsageInResults:
    @pytest.mark.asyncio
    async def test_usage_lifted_into_first_result(self, monkeypatch, capsys):
        """include_usage must reach the merged array without adding a pseudo-result."""
        monkeypatch.setenv("GROK_API_URL", "https://api.x.ai/v1")
        monkeypatch.setenv("GROK_API_KEY", "sk-test")
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        async def fake_grok_search(*a, **kw):
            return json.dumps([{"title": "G", "url": "https://g.com", "description": "G"}])

        async def fake_tavily(*a, **kw):
            return [
                {"title": "T", "url": "https://t.com", "content": "C", "score": 0.9},
                {"usage": {"credits": 2}},
            ]

        monkeypatch.setattr(groksearch_cli.GrokSearchProvider, "search", fake_grok_search)
        monkeypatch.setattr(groksearch_cli, "_call_tavily_search", fake_tavily)

        args = MagicMock(query="t", platform="", min_results=3, max_results=10, extra_sources=2, raw=False)
        await groksearch_cli.cmd_web_search(args)
        data = json.loads(capsys.readouterr().out)
        assert data[0]["tavily_usage"] == {"credits": 2}
        # The usage entry must never appear as a result element.
        assert all(d.get("url") for d in data)
        assert len(data) == 2

    def test_usage_marker_not_treated_as_result(self):
        from groksearch_cli import merge_search_results

        grok = json.dumps([{"title": "G", "url": "https://g.com", "description": "G"}])
        merged = merge_search_results(
            grok,
            [{"title": "T", "url": "https://t.com", "content": "C"}, {"usage": {"credits": 1}}],
            tavily_requested=True,
        )
        assert merged[0]["tavily_usage"] == {"credits": 1}
        assert len(merged) == 2
        assert not any(d.get("title") == "" for d in merged)

    def test_no_usage_key_when_disabled(self):
        from groksearch_cli import merge_search_results

        grok = json.dumps([{"title": "G", "url": "https://g.com", "description": "G"}])
        merged = merge_search_results(
            grok, [{"title": "T", "url": "https://t.com", "content": "C"}], tavily_requested=True
        )
        assert "tavily_usage" not in merged[0]

    @pytest.mark.asyncio
    async def test_search_includes_usage_entry_when_enabled(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_INCLUDE_USAGE", "true")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(
            return_value={
                "results": [{"title": "T", "url": "https://t.com", "content": "C"}],
                "usage": {"credits": 2},
            }
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_search("q")
        assert result[-1] == {"usage": {"credits": 2}}
        assert mock_client.post.call_args.kwargs["json"]["include_usage"] is True

    @pytest.mark.asyncio
    async def test_search_preserves_usage_on_empty_results(self, monkeypatch):
        """Credits spent on an empty search must still surface the usage entry."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setenv("TAVILY_INCLUDE_USAGE", "true")
        import groksearch_cli

        groksearch_cli.Config._instance = None

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"results": [], "usage": {"credits": 2}})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        async def _get_client():
            return mock_client

        monkeypatch.setattr(groksearch_cli, "get_http_client", _get_client)

        result = await groksearch_cli._call_tavily_search("q")
        assert result == [{"usage": {"credits": 2}}]
