"""Tests for clean topic-named HTML filenames (no hash suffix)."""

from pathlib import Path

import pytest
from agent_wiki import config, frontmatter, site


def _init(vault: Path) -> None:
    """Initialize wiki structure."""
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)


def _topic(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    """Create a topic with frontmatter and body."""
    topics = config.topics_dir(vault)
    topics.mkdir(parents=True, exist_ok=True)
    path = topics / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def test_site_slug_no_hash_suffix(tmp_path):
    """Topic pages use clean names: sanitize(stem).html (no hash)."""
    _init(tmp_path)

    _topic(tmp_path, "python-basics.md", {"title": "Python Basics"}, "Content.")

    result = site.generate_site(tmp_path)
    assert result["ok"] is True

    site_dir = config.wiki_root(tmp_path) / "site"
    html_files = [p.name for p in site_dir.glob("*.html") if p.name != "index.html"]

    # Should be named python-basics.html (no hash suffix)
    assert "python-basics.html" in html_files
    assert len(html_files) == 1

    # Should NOT contain any hash-suffixed files
    for fname in html_files:
        assert not any(fname.startswith(f"python-basics-{h}") for h in "0123456789abcdef")


def test_site_slug_collision_numeric_disambiguation(tmp_path):
    """Colliding sanitized names get -2, -3 suffixes in NFC key order."""
    _init(tmp_path)

    # Create topics that sanitize to the same name
    # "foo bar.md" and "foo  bar.md" (double space) both sanitize to "foo_bar"
    _topic(tmp_path, "foo bar.md", {"title": "Foo Bar 1"}, "Content 1.")
    _topic(tmp_path, "foo  bar.md", {"title": "Foo Bar 2"}, "Content 2.")

    result = site.generate_site(tmp_path)
    assert result["ok"] is True

    site_dir = config.wiki_root(tmp_path) / "site"
    html_files = sorted(p.name for p in site_dir.glob("*.html") if p.name != "index.html")

    # Should have disambiguated filenames
    # First key in NFC order gets bare name, second gets -2
    assert len(html_files) == 2
    assert "foo_bar.html" in html_files
    assert "foo_bar-2.html" in html_files


def test_site_prunes_orphaned_pages(tmp_path):
    """Site removes old HTML files not in current output set."""
    _init(tmp_path)

    # First run: create topic A
    _topic(tmp_path, "topic-a.md", {"title": "Topic A"}, "Content A.")
    site.generate_site(tmp_path)

    site_dir = config.wiki_root(tmp_path) / "site"
    assert (site_dir / "topic-a.html").exists()

    # Manually add orphaned file (simulates old hash-named or deleted topic)
    orphan = site_dir / "old-orphan-12345678.html"
    orphan.write_text("<html>orphan</html>", encoding="utf-8")

    # Second run: topic A still exists
    site.generate_site(tmp_path)

    # Current page should exist
    assert (site_dir / "topic-a.html").exists()
    assert (site_dir / "index.html").exists()

    # Orphan should be pruned
    assert not orphan.exists()


def test_site_slug_map_threaded_through_links(tmp_path):
    pytest.importorskip("markdown")
    """Internal wikilinks use the slug map (no hash in hrefs)."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Target content.")
    _topic(tmp_path, "source.md", {"title": "Source"}, "Link: [[target]]")

    site.generate_site(tmp_path)

    site_dir = config.wiki_root(tmp_path) / "site"
    source_html = (site_dir / "source.html").read_text(encoding="utf-8")

    # Link should use clean filename
    assert 'href="target.html"' in source_html
    # Should NOT contain hash
    assert not any(f'href="target-{h}' in source_html for h in "0123456789abcdef")
