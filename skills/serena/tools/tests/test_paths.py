"""Tests for path resolution module."""
import os
from pathlib import Path
from unittest.mock import patch
import tempfile


def test_get_config_dir_default():
    """Test default config directory resolution."""
    from tools.paths import SerenaToolsPaths

    paths = SerenaToolsPaths()
    config_dir = paths.get_config_dir()

    # Should resolve to ~/.serena
    expected = Path.home() / ".serena"
    assert config_dir == expected


def test_get_config_dir_with_serena_home():
    """Test config directory with SERENA_HOME override."""
    from tools.paths import SerenaToolsPaths

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"SERENA_HOME": tmpdir}):
            paths = SerenaToolsPaths()
            config_dir = paths.get_config_dir()

            assert config_dir == Path(tmpdir)


def test_get_config_file_path():
    """Test config file path resolution."""
    from tools.paths import SerenaToolsPaths

    paths = SerenaToolsPaths()
    config_file = paths.get_config_file_path()

    # Should resolve to ~/.serena/serena_config.yml
    expected = Path.home() / ".serena" / "serena_config.yml"
    assert config_file == expected


def test_ensure_config_exists_creates_directory():
    """Test that ensure_config_exists creates config directory."""
    from tools.paths import SerenaToolsPaths

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"SERENA_HOME": tmpdir}):
            paths = SerenaToolsPaths()
            config_file = paths.ensure_config_exists()

            # Directory should be created
            assert config_file.parent.exists()
            assert config_file.parent.is_dir()


def test_ensure_config_exists_creates_file():
    """Test that ensure_config_exists creates config file if missing."""
    from tools.paths import SerenaToolsPaths

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"SERENA_HOME": tmpdir}):
            paths = SerenaToolsPaths()
            config_file = paths.ensure_config_exists()

            # Config file should be created
            assert config_file.exists()
            assert config_file.is_file()


def test_ensure_config_exists_preserves_existing():
    """Test that ensure_config_exists preserves existing config."""
    from tools.paths import SerenaToolsPaths

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"SERENA_HOME": tmpdir}):
            # Create existing config
            config_dir = Path(tmpdir)
            config_dir.mkdir(exist_ok=True)
            config_file = config_dir / "serena_config.yml"
            config_file.write_text("existing: config")

            paths = SerenaToolsPaths()
            result = paths.ensure_config_exists()

            # Should preserve existing content
            assert result.read_text() == "existing: config"
