import json
import os
from pathlib import Path
from typing import Optional

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
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_config_file(self, config_data: dict) -> None:
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

    def set_overrides(self, api_url: Optional[str], api_key: Optional[str]):
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
    def tavily_api_key(self) -> Optional[str]:
        return os.getenv("TAVILY_API_KEY")

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

        return {
            "GROK_API_URL": api_url,
            "GROK_API_KEY": api_key_masked,
            "GROK_MODEL": self.grok_model,
            "GROK_DEBUG": self.debug_enabled,
            "TAVILY_API_URL": self.tavily_api_url,
            "TAVILY_ENABLED": self.tavily_enabled,
            "TAVILY_API_KEY": self._mask_api_key(self.tavily_api_key) if self.tavily_api_key else "Not configured",
            "config_status": config_status,
        }


config = Config()
