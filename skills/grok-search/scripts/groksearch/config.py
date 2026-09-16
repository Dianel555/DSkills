import json
import math
import os
from pathlib import Path

from .env import load_dotenv

load_dotenv()


class Config:
    _instance = None
    _FALLBACK_MODEL = "grok-4-1-fast"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config_file = None
            cls._instance._cached_model = None
            cls._instance._override_url = None
            cls._instance._override_key = None
        return cls._instance

    @property
    def config_file(self) -> Path:
        if self._config_file is None:
            config_dir = Path.home() / ".config" / "grok-search"
            config_dir.mkdir(parents=True, exist_ok=True)
            self._config_file = config_dir / "config.json"
        return self._config_file

    def _load_config_file(self) -> dict:
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_config_file(self, config_data: dict) -> None:
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

    def set_overrides(self, api_url: str | None, api_key: str | None):
        self._override_url = api_url
        self._override_key = api_key

    @property
    def debug_enabled(self) -> bool:
        return os.getenv("GROK_DEBUG", "false").lower() in ("true", "1", "yes")

    @property
    def retry_max_attempts(self) -> int:
        return int(os.getenv("GROK_RETRY_MAX_ATTEMPTS", "3"))

    @property
    def retry_multiplier(self) -> float:
        return float(os.getenv("GROK_RETRY_MULTIPLIER", "1"))

    @property
    def retry_max_wait(self) -> int:
        return int(os.getenv("GROK_RETRY_MAX_WAIT", "10"))

    @property
    def tavily_enabled(self) -> bool:
        return os.getenv("TAVILY_ENABLED", "true").lower() in ("true", "1", "yes")

    @property
    def tavily_api_url(self) -> str:
        return os.getenv("TAVILY_API_URL", "https://api.tavily.com")

    @property
    def tavily_api_key(self) -> str | None:
        return os.getenv("TAVILY_API_KEY")

    @property
    def tavily_search_depth(self) -> str:
        depth = os.getenv("TAVILY_SEARCH_DEPTH", "advanced").lower()
        if depth not in ("advanced", "basic", "fast", "ultra-fast"):
            raise ValueError(f"Invalid TAVILY_SEARCH_DEPTH: {depth}. Use advanced/basic/fast/ultra-fast")
        return depth

    @property
    def tavily_chunks_per_source(self) -> int:
        # The API accepts 1-5 ("or 'auto'"), though the docs page still renders 1-3.
        chunks = int(os.getenv("TAVILY_CHUNKS_PER_SOURCE", "3"))
        if not 1 <= chunks <= 5:
            raise ValueError(f"Invalid TAVILY_CHUNKS_PER_SOURCE: {chunks}. API accepts 1-5")
        return chunks

    @property
    def tavily_topic(self) -> str:
        topic = os.getenv("TAVILY_TOPIC", "general").lower()
        if topic not in ("general", "news", "finance"):
            raise ValueError(f"Invalid TAVILY_TOPIC: {topic}. Use general/news/finance")
        return topic

    @property
    def tavily_time_range(self) -> str:
        value = os.getenv("TAVILY_TIME_RANGE", "").lower()
        if not value:
            return ""
        if value not in ("day", "week", "month", "year", "d", "w", "m", "y"):
            raise ValueError(f"Invalid TAVILY_TIME_RANGE: {value}. Use day/week/month/year")
        return value

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _bounded_float(name: str, default: float, low: float | None = None, high: float | None = None) -> float:
        raw = os.getenv(name, str(default))
        try:
            value = float(raw)
        except ValueError as e:
            raise ValueError(f"Invalid {name}: {raw!r}. Must be a number") from e
        if not math.isfinite(value) or (low is not None and value < low) or (high is not None and value > high):
            bounds = f"{low}-{high}" if high is not None else f">={low}"
            raise ValueError(f"Invalid {name}: {raw!r}. Must be {bounds}")
        return value

    @staticmethod
    def _positive_int(name: str, default: int) -> int:
        raw = os.getenv(name, str(default))
        try:
            value = int(raw)
        except ValueError as e:
            raise ValueError(f"Invalid {name}: {raw!r}. Must be an integer") from e
        if value < 1:
            raise ValueError(f"Invalid {name}: {raw!r}. Must be >= 1")
        return value

    @property
    def tavily_include_domains(self) -> list[str]:
        return self._split_csv(os.getenv("TAVILY_INCLUDE_DOMAINS", ""))

    @property
    def tavily_exclude_domains(self) -> list[str]:
        return self._split_csv(os.getenv("TAVILY_EXCLUDE_DOMAINS", ""))

    @property
    def tavily_include_domains_mode(self) -> str:
        value = os.getenv("TAVILY_INCLUDE_DOMAINS_MODE", "filter").lower()
        if value not in ("filter", "boost"):
            raise ValueError(f"Invalid TAVILY_INCLUDE_DOMAINS_MODE: {value}. Use filter/boost")
        return value

    @property
    def tavily_include_usage(self) -> bool:
        return os.getenv("TAVILY_INCLUDE_USAGE", "false").lower() in ("true", "1", "yes")

    @property
    def tavily_extract_depth(self) -> str:
        depth = os.getenv("TAVILY_EXTRACT_DEPTH", "basic").lower()
        if depth not in ("basic", "advanced"):
            raise ValueError(f"Invalid TAVILY_EXTRACT_DEPTH: {depth}. Use basic/advanced")
        return depth

    @property
    def tavily_include_answer(self) -> bool | str:
        """Return the value for Tavily's `include_answer`.

        The API accepts only True, False, 'basic' or 'advanced' — the string "false" is
        rejected with a 400, so the disabled state must be the boolean.
        """
        value = os.getenv("TAVILY_INCLUDE_ANSWER", "false").lower()
        if value in ("false", "0", "no", "none", ""):
            return False
        if value in ("true", "1", "yes", "basic"):
            return "basic"
        if value == "advanced":
            return "advanced"
        raise ValueError(f"Invalid TAVILY_INCLUDE_ANSWER: {value}. Use false/basic/advanced")

    @property
    def tavily_extract_timeout(self) -> float:
        return self._bounded_float("TAVILY_EXTRACT_TIMEOUT", 30.0, low=1.0, high=60.0)

    @property
    def tavily_crawl_timeout(self) -> float:
        return self._bounded_float("TAVILY_CRAWL_TIMEOUT", 150.0, low=10.0, high=150.0)

    @property
    def tavily_crawl_max_depth(self) -> int:
        return self._positive_int("TAVILY_CRAWL_MAX_DEPTH", 1)

    @property
    def tavily_crawl_max_breadth(self) -> int:
        return self._positive_int("TAVILY_CRAWL_MAX_BREADTH", 20)

    @property
    def tavily_crawl_limit(self) -> int:
        return self._positive_int("TAVILY_CRAWL_LIMIT", 50)

    @property
    def tavily_crawl_allow_external(self) -> bool:
        return os.getenv("TAVILY_CRAWL_ALLOW_EXTERNAL", "true").lower() in ("true", "1", "yes")

    @property
    def tavily_crawl_select_paths(self) -> list[str]:
        return self._split_csv(os.getenv("TAVILY_CRAWL_SELECT_PATHS", ""))

    @property
    def tavily_crawl_exclude_paths(self) -> list[str]:
        return self._split_csv(os.getenv("TAVILY_CRAWL_EXCLUDE_PATHS", ""))

    @property
    def tavily_research_model(self) -> str:
        model = os.getenv("TAVILY_RESEARCH_MODEL", "auto").lower()
        if model not in ("mini", "pro", "auto"):
            raise ValueError(f"Invalid TAVILY_RESEARCH_MODEL: {model}. Use mini/pro/auto")
        return model

    @property
    def tavily_research_citation_format(self) -> str:
        value = os.getenv("TAVILY_RESEARCH_CITATION_FORMAT", "numbered").lower()
        if value not in ("numbered", "mla", "apa", "chicago"):
            raise ValueError(f"Invalid TAVILY_RESEARCH_CITATION_FORMAT: {value}. Use numbered/mla/apa/chicago")
        return value

    @property
    def tavily_research_output_length(self) -> str:
        value = os.getenv("TAVILY_RESEARCH_OUTPUT_LENGTH", "standard").lower()
        if value not in ("short", "standard", "long"):
            raise ValueError(f"Invalid TAVILY_RESEARCH_OUTPUT_LENGTH: {value}. Use short/standard/long")
        return value

    @property
    def tavily_research_output_schema(self) -> str:
        """Path to a JSON Schema file; blank means unstructured text output."""
        return os.getenv("TAVILY_RESEARCH_OUTPUT_SCHEMA", "").strip()

    @property
    def tavily_research_timeout(self) -> float:
        return self._bounded_float("TAVILY_RESEARCH_TIMEOUT", 300.0, low=0.0)

    @property
    def tavily_research_poll_interval(self) -> float:
        return self._bounded_float("TAVILY_RESEARCH_POLL_INTERVAL", 5.0, low=0.0)

    @property
    def grok_api_url(self) -> str:
        if self._override_url:
            return self._override_url
        url = os.getenv("GROK_API_URL")
        if not url:
            raise ValueError("GROK_API_URL not configured. Set environment variable or use --api-url")
        return url.rstrip("/")

    @property
    def grok_api_key(self) -> str:
        if self._override_key:
            return self._override_key
        key = os.getenv("GROK_API_KEY")
        if not key:
            raise ValueError("GROK_API_KEY not configured. Set environment variable or use --api-key")
        return key

    def _apply_model_suffix(self, model: str) -> str:
        try:
            url = self.grok_api_url
        except ValueError:
            return model
        if "openrouter" in url and ":online" not in model:
            return f"{model}:online"
        return model

    @property
    def grok_model(self) -> str:
        if self._cached_model is not None:
            return self._cached_model
        config_data = self._load_config_file()
        file_model = config_data.get("model")
        if file_model:
            self._cached_model = self._apply_model_suffix(file_model)
            return self._cached_model
        env_model = os.getenv("GROK_MODEL")
        if env_model:
            self._cached_model = self._apply_model_suffix(env_model)
            return self._cached_model
        self._cached_model = self._apply_model_suffix(self._FALLBACK_MODEL)
        return self._cached_model

    def set_model(self, model: str) -> str:
        previous = self.grok_model
        config_data = self._load_config_file()
        config_data["model"] = model
        self._save_config_file(config_data)
        self._cached_model = self._apply_model_suffix(model)
        return previous

    @staticmethod
    def _mask_api_key(key: str) -> str:
        if not key or len(key) <= 8:
            return "***"
        return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"

    def get_config_info(self) -> dict:
        try:
            api_url = self.grok_api_url
            api_key_raw = self.grok_api_key
            api_key_masked = self._mask_api_key(api_key_raw)
            config_status = "✅ Configuration Complete"
        except ValueError as e:
            api_url = "Not configured"
            api_key_masked = "Not configured"
            config_status = f"❌ Error: {str(e)}"

        # A malformed tuning value raises ValueError on access; report it per-key instead
        # of breaking the whole config dump. Values are property names, resolved lazily.
        unset_when_empty = {
            "TAVILY_TIME_RANGE",
            "TAVILY_INCLUDE_DOMAINS",
            "TAVILY_EXCLUDE_DOMAINS",
            "TAVILY_CRAWL_SELECT_PATHS",
            "TAVILY_CRAWL_EXCLUDE_PATHS",
            "TAVILY_RESEARCH_OUTPUT_SCHEMA",
        }
        tuning_props = {
            "TAVILY_SEARCH_DEPTH": "tavily_search_depth",
            "TAVILY_CHUNKS_PER_SOURCE": "tavily_chunks_per_source",
            "TAVILY_INCLUDE_ANSWER": "tavily_include_answer",
            "TAVILY_EXTRACT_TIMEOUT": "tavily_extract_timeout",
            "TAVILY_EXTRACT_DEPTH": "tavily_extract_depth",
            "TAVILY_TOPIC": "tavily_topic",
            "TAVILY_TIME_RANGE": "tavily_time_range",
            "TAVILY_INCLUDE_DOMAINS": "tavily_include_domains",
            "TAVILY_EXCLUDE_DOMAINS": "tavily_exclude_domains",
            "TAVILY_INCLUDE_DOMAINS_MODE": "tavily_include_domains_mode",
            "TAVILY_INCLUDE_USAGE": "tavily_include_usage",
            "TAVILY_CRAWL_TIMEOUT": "tavily_crawl_timeout",
            "TAVILY_CRAWL_MAX_DEPTH": "tavily_crawl_max_depth",
            "TAVILY_CRAWL_MAX_BREADTH": "tavily_crawl_max_breadth",
            "TAVILY_CRAWL_LIMIT": "tavily_crawl_limit",
            "TAVILY_CRAWL_ALLOW_EXTERNAL": "tavily_crawl_allow_external",
            "TAVILY_CRAWL_SELECT_PATHS": "tavily_crawl_select_paths",
            "TAVILY_CRAWL_EXCLUDE_PATHS": "tavily_crawl_exclude_paths",
            "TAVILY_RESEARCH_MODEL": "tavily_research_model",
            "TAVILY_RESEARCH_CITATION_FORMAT": "tavily_research_citation_format",
            "TAVILY_RESEARCH_OUTPUT_LENGTH": "tavily_research_output_length",
            "TAVILY_RESEARCH_OUTPUT_SCHEMA": "tavily_research_output_schema",
            "TAVILY_RESEARCH_TIMEOUT": "tavily_research_timeout",
            "TAVILY_RESEARCH_POLL_INTERVAL": "tavily_research_poll_interval",
        }

        def _get(key: str, prop: str):
            try:
                value = getattr(self, prop)
            except ValueError as e:
                return f"❌ {e}"
            return "(unset)" if key in unset_when_empty and not value else value

        tuning = {k: _get(k, p) for k, p in tuning_props.items()}

        return {
            "GROK_API_URL": api_url,
            "GROK_API_KEY": api_key_masked,
            "GROK_MODEL": self.grok_model,
            "GROK_DEBUG": self.debug_enabled,
            "TAVILY_API_URL": self.tavily_api_url,
            "TAVILY_ENABLED": self.tavily_enabled,
            "TAVILY_API_KEY": self._mask_api_key(self.tavily_api_key) if self.tavily_api_key else "Not configured",
            **tuning,
            "config_status": config_status,
        }


config = Config()
