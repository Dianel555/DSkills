"""Configuration singleton + .env loader for exa_cli."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

DEFAULT_API_URL = "https://api.exa.ai"


def load_dotenv(env_path: Optional[Path] = None) -> bool:
    """Load .env using a documented subset:

    - KEY=VALUE on a single line.
    - Outer single/double quotes around VALUE are stripped (no escape decoding).
    - Whole-line comments starting with `#` are ignored.
    - Inline comments, multi-line values, ${VAR} interpolation, and \\n escapes
      are NOT supported (the `#` after a value is preserved literally).
    - Existing process env vars are NOT overwritten.
    """
    search_paths = [env_path] if env_path else [
        Path.cwd() / ".env",
        Path.cwd() / "scripts" / ".env",
        Path(__file__).resolve().parent.parent / "scripts" / ".env",
    ]
    for path in search_paths:
        if path is None or not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        value = value[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = value
            return True
        except OSError:
            continue
    return False


class Config:
    _instance: Optional["Config"] = None

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._override_url = None
            cls._instance._override_key = None
            cls._instance._override_max_retry_wait = None
        return cls._instance

    @classmethod
    def _reset_for_testing(cls) -> None:
        cls._instance = None

    def set_overrides(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        max_retry_wait: Optional[int] = None,
    ) -> None:
        if api_url is not None:
            self._override_url = api_url
        if api_key is not None:
            self._override_key = api_key
        if max_retry_wait is not None:
            self._override_max_retry_wait = max_retry_wait

    @property
    def debug_enabled(self) -> bool:
        return os.getenv("EXA_DEBUG", "false").lower() in ("true", "1", "yes")

    @property
    def exa_api_url(self) -> str:
        if self._override_url:
            return self._override_url.rstrip("/")
        return os.getenv("EXA_API_URL", DEFAULT_API_URL).rstrip("/")

    @property
    def exa_api_key(self) -> str:
        if self._override_key:
            return self._override_key
        key = os.getenv("EXA_API_KEY")
        if not key:
            raise ValueError(
                "EXA_API_KEY not configured. Set environment variable or use --api-key"
            )
        return key

    @property
    def max_retry_wait(self) -> int:
        if self._override_max_retry_wait is not None:
            return self._override_max_retry_wait
        env_val = os.getenv("EXA_MAX_RETRY_WAIT")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed > 0:
                    return parsed
            except ValueError:
                pass
        return 60

    @staticmethod
    def mask_api_key(key: str) -> str:
        if not key or len(key) <= 8:
            return "***"
        return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"

    def get_config_info(self) -> dict:
        try:
            api_url = self.exa_api_url
            api_key_masked = self.mask_api_key(self.exa_api_key)
            config_status = "OK"
        except ValueError as exc:
            api_url = self.exa_api_url
            api_key_masked = "Not configured"
            config_status = f"Error: {exc}"
        return {
            "EXA_API_URL": api_url,
            "EXA_API_KEY": api_key_masked,
            "EXA_DEBUG": self.debug_enabled,
            "config_status": config_status,
        }
