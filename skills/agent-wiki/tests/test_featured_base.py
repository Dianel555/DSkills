"""Tests for featured view in gen-base."""

import yaml
from pathlib import Path

from agent_wiki import bases, config, frontmatter


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


# --- 1.6 Featured view tests ---


def test_index_base_includes_featured_view():
    """index.base includes a 精选 (featured) view."""
    data = yaml.safe_load(bases.build_index_base(""))

    view_names = [v["name"] for v in data["views"]]
    assert "精选" in view_names


def test_featured_view_filters_by_featured_frontmatter():
    """Featured view uses featured property as filter."""
    data = yaml.safe_load(bases.build_index_base(""))

    views = {v["name"]: v for v in data["views"]}
    featured_view = views["精选"]

    # Should have a filter for featured property
    assert "featured" in str(featured_view)


def test_featured_view_preserves_two_file_contract(tmp_path):
    """gen-base still writes exactly two .base files."""
    import json
    import subprocess
    import sys

    ROOT = Path(__file__).resolve().parents[1]
    CLI = ROOT / "scripts" / "agent_wiki_cli.py"

    # Initialize
    subprocess.run([sys.executable, str(CLI), "init", "--vault", str(tmp_path)],
                   capture_output=True)

    # Create featured and non-featured topics
    _topic(tmp_path, "featured.md", {"title": "Featured", "featured": True}, "Content.")
    _topic(tmp_path, "normal.md", {"title": "Normal"}, "Content.")

    # Run gen-base
    result = subprocess.run(
        [sys.executable, str(CLI), "gen-base", "--vault", str(tmp_path)],
        capture_output=True, text=True
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)

    # Two-file contract preserved
    assert len(payload["written"]) == 2
    assert "wiki/index.base" in payload["written"]
    assert "sources.base" in payload["written"]


def test_featured_view_valid_yaml():
    """Featured view produces valid YAML structure."""
    data = yaml.safe_load(bases.build_index_base(""))

    views = {v["name"]: v for v in data["views"]}
    featured_view = views["精选"]

    # Basic structure
    assert "type" in featured_view
    assert "name" in featured_view
    assert "order" in featured_view

    # Valid table view
    assert featured_view["type"] == "table"


def test_featured_property_defined_in_properties():
    """featured property is defined in the properties section."""
    data = yaml.safe_load(bases.build_index_base(""))

    assert "featured" in data["properties"]
    assert "displayName" in data["properties"]["featured"]


def test_gen_base_works_with_zero_featured_topics(tmp_path):
    """gen-base succeeds when no topics are featured."""
    import json
    import subprocess
    import sys

    ROOT = Path(__file__).resolve().parents[1]
    CLI = ROOT / "scripts" / "agent_wiki_cli.py"

    # Initialize with no featured topics
    subprocess.run([sys.executable, str(CLI), "init", "--vault", str(tmp_path)],
                   capture_output=True)
    _topic(tmp_path, "normal.md", {"title": "Normal"}, "Content.")

    # Should succeed
    result = subprocess.run(
        [sys.executable, str(CLI), "gen-base", "--vault", str(tmp_path)],
        capture_output=True, text=True
    )

    assert result.returncode == 0

    # index.base should be valid YAML
    index_base = tmp_path / "wiki" / "index.base"
    data = yaml.safe_load(index_base.read_text(encoding="utf-8"))
    assert data is not None


def test_gen_base_works_with_many_featured_topics(tmp_path):
    """gen-base succeeds with multiple featured topics."""
    import json
    import subprocess
    import sys

    ROOT = Path(__file__).resolve().parents[1]
    CLI = ROOT / "scripts" / "agent_wiki_cli.py"

    # Initialize with multiple featured topics
    subprocess.run([sys.executable, str(CLI), "init", "--vault", str(tmp_path)],
                   capture_output=True)

    for i in range(5):
        _topic(tmp_path, f"featured_{i}.md", {"title": f"Featured {i}", "featured": True}, "Content.")

    # Should succeed
    result = subprocess.run(
        [sys.executable, str(CLI), "gen-base", "--vault", str(tmp_path)],
        capture_output=True, text=True
    )

    assert result.returncode == 0
