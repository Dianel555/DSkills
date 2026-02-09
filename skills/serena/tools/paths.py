"""Path resolution for Serena Tools configuration."""
import os
from pathlib import Path
from typing import Optional


class SerenaToolsPaths:
    """Manages configuration paths for Serena Tools wrapper."""

    def __init__(self):
        """Initialize path resolver."""
        pass

    def get_config_dir(self) -> Path:
        """Get configuration directory path.

        Returns ~/.serena or $SERENA_HOME if set.
        """
        serena_home = os.environ.get("SERENA_HOME")
        if serena_home:
            return Path(serena_home)
        return Path.home() / ".serena"

    def get_config_file_path(self) -> Path:
        """Get configuration file path.

        Returns <config_dir>/serena_config.yml
        """
        return self.get_config_dir() / "serena_config.yml"

    def ensure_config_exists(self) -> Path:
        """Ensure configuration file exists, creating it if necessary.

        Returns path to config file.
        """
        config_file = self.get_config_file_path()
        config_dir = config_file.parent

        # Create directory if it doesn't exist
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create default config if file doesn't exist
        if not config_file.exists():
            default_config = """# Serena Tools Configuration
# This file is auto-generated on first run

projects: []
web_dashboard:
  enabled: true
  host: "127.0.0.1"
  port: 8765
log_level: "INFO"
"""
            config_file.write_text(default_config)

        return config_file
