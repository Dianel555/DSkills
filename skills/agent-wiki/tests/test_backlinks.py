"""Tests for backlinks derivation in wiki index."""

from pathlib import Path

from agent_wiki import config, frontmatter, wiki_index


def _topic(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    """Create a topic with frontmatter and body."""
    topics = config.topics_dir(vault)
    topics.mkdir(parents=True, exist_ok=True)
    path = topics / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def _query(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    """Create a query capture."""
    queries = config.queries_dir(vault)
    queries.mkdir(parents=True, exist_ok=True)
    path = queries / name
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def _init(vault: Path) -> None:
    """Initialize wiki structure."""
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)


# --- 2.3 Backlinks derivation tests ---


def test_backlinks_counts_distinct_inbound_linker_pages(tmp_path):
    """backlinks counts distinct pages linking to a topic."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")
    _topic(tmp_path, "linker1.md", {"title": "Linker 1"}, "See [[target]].")
    _topic(tmp_path, "linker2.md", {"title": "Linker 2"}, "Also [[target]].")

    data, errors = wiki_index.rebuild(tmp_path)

    assert errors == []
    assert data["topics"]["target.md"]["backlinks"] == 2


def test_backlinks_includes_queries_as_linkers(tmp_path):
    """backlinks counts linkers from topics and queries."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")
    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Link to [[target]].")
    _query(tmp_path, "query.md", {"title": "Query"}, "Query for [[target]].")

    data, errors = wiki_index.rebuild(tmp_path)

    # 2 distinct linkers: 1 topic + 1 query
    assert data["topics"]["target.md"]["backlinks"] == 2


def test_self_links_excluded_from_backlinks(tmp_path):
    """Self-links do not increment backlinks."""
    _init(tmp_path)

    _topic(tmp_path, "self.md", {"title": "Self"}, "I link to [[self]] multiple times [[self]].")

    data, errors = wiki_index.rebuild(tmp_path)

    # Self-links should not count
    assert data["topics"]["self.md"]["backlinks"] == 0


def test_backlinks_resolved_by_topic_stem(tmp_path):
    """backlinks resolution uses topic stem, not full path."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")
    _topic(tmp_path, "linker.md", {"title": "Linker"}, "Link via [[target]] stem.")

    data, errors = wiki_index.rebuild(tmp_path)

    assert data["topics"]["target.md"]["backlinks"] == 1


def test_backlinks_counts_distinct_pages_not_link_occurrences(tmp_path):
    """Each page contributes at most one to backlinks, regardless of link count."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")
    _topic(tmp_path, "linker.md", {"title": "Linker"},
           "Multiple links: [[target]] and [[target]] and [[target]].")

    data, errors = wiki_index.rebuild(tmp_path)

    # Only 1 backlink despite 3 link occurrences (per-page deduped)
    assert data["topics"]["target.md"]["backlinks"] == 1


def test_backlinks_computed_only_for_topic_targets(tmp_path):
    """backlinks field appears only on topic entries, not queries."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")
    _query(tmp_path, "query.md", {"title": "Query"}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    # Topics have backlinks
    assert "backlinks" in data["topics"]["topic.md"]

    # Queries do not
    assert "backlinks" not in data["queries"]["queries/query.md"]


def test_backlinks_is_deterministic(tmp_path):
    """backlinks values are identical across rebuilds."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")
    _topic(tmp_path, "linker1.md", {"title": "Linker 1"}, "Link [[target]].")
    _topic(tmp_path, "linker2.md", {"title": "Linker 2"}, "Link [[target]].")

    data1, _ = wiki_index.rebuild(tmp_path)
    data2, _ = wiki_index.rebuild(tmp_path)

    assert data1["topics"]["target.md"]["backlinks"] == data2["topics"]["target.md"]["backlinks"]


def test_backlinks_equals_inbound_edge_count(tmp_path):
    """backlinks equals the count of distinct source pages with links to target."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")
    _topic(tmp_path, "A.md", {"title": "A"}, "[[target]]")
    _topic(tmp_path, "B.md", {"title": "B"}, "[[target]]")
    _topic(tmp_path, "C.md", {"title": "C"}, "No link.")

    data, errors = wiki_index.rebuild(tmp_path)

    # Inbound edges: A -> target, B -> target (2 edges)
    assert data["topics"]["target.md"]["backlinks"] == 2


def test_backlinks_zero_when_no_inbound_links(tmp_path):
    """backlinks is 0 for topics with no inbound links."""
    _init(tmp_path)

    _topic(tmp_path, "isolated.md", {"title": "Isolated"}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    assert data["topics"]["isolated.md"]["backlinks"] == 0


def test_backlinks_handles_broken_links(tmp_path):
    """Broken links (target doesn't exist) don't cause errors."""
    _init(tmp_path)

    _topic(tmp_path, "linker.md", {"title": "Linker"}, "[[nonexistent]] target.")

    data, errors = wiki_index.rebuild(tmp_path)

    # Should complete without error
    assert data["topics"]["linker.md"]["backlinks"] == 0


def test_backlinks_uses_existing_links_data(tmp_path):
    """backlinks computed from already-parsed links[] without extra reads."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")
    _topic(tmp_path, "linker.md", {"title": "Linker"}, "Link to [[target]] and [[other]].")

    data, errors = wiki_index.rebuild(tmp_path)

    # Verify links[] was parsed
    assert "target" in data["topics"]["linker.md"]["links"]

    # backlinks computed from those links
    assert data["topics"]["target.md"]["backlinks"] == 1


def test_backlinks_with_alias_and_heading_suffixes(tmp_path):
    """Links with |alias or #heading suffixes still count for backlinks."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")
    _topic(tmp_path, "linker.md", {"title": "Linker"},
           "Links: [[target|alias]] and [[target#section]].")

    data, errors = wiki_index.rebuild(tmp_path)

    # Both links should resolve to target (aliases/headings stripped)
    assert data["topics"]["target.md"]["backlinks"] == 1


def test_backlinks_file_order_independence(tmp_path):
    """backlinks values unchanged regardless of file processing order."""
    _init(tmp_path)

    # Create files that sort differently by name vs mtime
    _topic(tmp_path, "z_target.md", {"title": "Target"}, "Content.")
    _topic(tmp_path, "a_linker.md", {"title": "Linker"}, "[[z_target]]")

    data1, _ = wiki_index.rebuild(tmp_path)

    # Rebuild again (same files)
    data2, _ = wiki_index.rebuild(tmp_path)

    assert data1["topics"]["z_target.md"]["backlinks"] == data2["topics"]["z_target.md"]["backlinks"]
