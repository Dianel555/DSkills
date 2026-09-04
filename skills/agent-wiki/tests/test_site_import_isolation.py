"""Tests for site.py import isolation and optional markdown dependency."""

import importlib
import sys
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

import pytest
from agent_wiki import config, frontmatter


@pytest.fixture(autouse=True)
def _restore_site():
    """Reimport a clean agent_wiki.site after each test.

    These tests deliberately reimport site under a patched ``markdown`` to
    exercise the optional dependency. A fresh reimport via importlib (not
    ``from agent_wiki import site``, which would return the stale package
    attribute) keeps them independent of execution order.
    """
    yield
    sys.modules.pop("agent_wiki.site", None)
    importlib.import_module("agent_wiki.site")


def _topic(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    """Create a topic with frontmatter and body."""
    topics = config.topics_dir(vault)
    topics.mkdir(parents=True, exist_ok=True)
    path = topics / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def _init(vault: Path) -> None:
    """Initialize wiki structure."""
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)


def test_core_imports_without_markdown():
    """Core agent_wiki modules import successfully without markdown package."""
    # Simulate markdown not available
    with patch.dict(sys.modules, {'markdown': None}):
        # These should all import successfully (core stays PyYAML-only)
        from agent_wiki import config, coverage, frontmatter, quality, wiki_index, worklist

        # Verify they imported
        assert config is not None
        assert frontmatter is not None
        assert wiki_index is not None
        assert quality is not None
        assert coverage is not None
        assert worklist is not None


def test_site_module_imports_without_markdown():
    """site.py imports successfully when markdown is absent (graceful degradation)."""
    # Simulate markdown not available and force a true reimport (not the stale attr).
    with patch.dict(sys.modules, {'markdown': None}, clear=False):
        sys.modules.pop('agent_wiki.site', None)
        site = importlib.import_module('agent_wiki.site')

        # Should have MARKDOWN_AVAILABLE = False
        assert not site.MARKDOWN_AVAILABLE


def test_site_degrades_to_escaped_plaintext_without_markdown(tmp_path):
    """site.generate_site uses escaped plaintext when markdown is absent."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "## Heading\n\nSome **bold** text.")

    # Force reimport with markdown unavailable
    with patch.dict(sys.modules, {'markdown': None}, clear=False):
        sys.modules.pop('agent_wiki.site', None)
        site = importlib.import_module('agent_wiki.site')

        result = site.generate_site(tmp_path)

        assert result["ok"] is True
        assert result["degraded"] is True  # Degraded mode flag
        assert result["pages"] >= 1

        # Check output exists
        site_dir = config.wiki_root(tmp_path) / "site"
        assert site_dir.exists()
        assert (site_dir / "index.html").exists()


def test_site_with_markdown_available(tmp_path):
    """site.generate_site uses markdown when available."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "## Heading\n\nSome **bold** text.")

    # Ensure markdown is available (or skip if not installed)
    if find_spec("markdown") is None:
        pytest.skip("markdown package not installed")

    # Import site fresh (should detect markdown is available)
    sys.modules.pop('agent_wiki.site', None)
    site = importlib.import_module('agent_wiki.site')

    # Verify MARKDOWN_AVAILABLE is True
    assert site.MARKDOWN_AVAILABLE, "markdown should be available"

    result = site.generate_site(tmp_path)

    assert result["ok"] is True
    assert result["degraded"] is False  # Not degraded when markdown available
    assert result["pages"] >= 1
