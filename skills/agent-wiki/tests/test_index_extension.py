"""Tests for extended index entry schema (topic-only fields)."""

import json
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


# --- 1.5 Extended index schema tests ---


def test_topic_entry_includes_new_fields(tmp_path):
    """Topic entries include type, aliases, quality_tier, featured, backlinks."""
    _init(tmp_path)

    body = "## Section 1\n## Section 2\n\n" + ("Prose content. " * 50)
    _topic(tmp_path, "topic.md", {
        "title": "Topic",
        "sources": ["a.md"],
        "type": "concept",
        "aliases": ["Alias1", "Alias2"],
        "featured": True
    }, body)

    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["topic.md"]

    assert errors == []
    assert "type" in entry
    assert "aliases" in entry
    assert "quality_tier" in entry
    assert "featured" in entry
    assert "backlinks" in entry

    assert entry["type"] == "concept"
    assert entry["aliases"] == ["Alias1", "Alias2"]
    assert entry["quality_tier"] == "standard"  # Based on body metrics
    assert entry["featured"] is True
    assert entry["backlinks"] == 0  # No inbound links yet


def test_query_entry_does_not_include_new_fields(tmp_path):
    """Query entries preserve existing schema without new fields."""
    _init(tmp_path)

    _query(tmp_path, "query.md", {
        "title": "Query",
        "sources": ["c.md"]
    }, "Query content.")

    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["queries"]["queries/query.md"]

    assert errors == []
    # New fields should NOT appear on queries
    assert "type" not in entry
    assert "aliases" not in entry
    assert "quality_tier" not in entry
    assert "featured" not in entry
    assert "backlinks" not in entry


def test_existing_fields_preserved_in_extended_schema(tmp_path):
    """All existing fields remain unchanged in topic entries."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {
        "title": "Topic",
        "sources": ["source.pdf"],
        "last_updated": "2026-06-01",
        "year_start": 2020,
        "year_end": 2025,
        "authors": ["Author A", "Author B"],
        "institutions": ["MIT"],
        "methods": ["Method X"],
        "technical_routes": ["Route Y"],
        "research_trends": ["Trend Z"],
        "summary": "Summary text",
        "keywords": ["key1", "key2"]
    }, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["topic.md"]

    # All existing fields present
    assert entry["path"] == "topic.md"
    assert entry["title"] == "Topic"
    assert entry["sources"] == ["source.pdf"]
    assert entry["last_updated"] == "2026-06-01"
    assert entry["year_start"] == 2020
    assert entry["year_end"] == 2025
    assert entry["authors"] == ["Author A", "Author B"]
    assert entry["source_type"] == "pdf"  # Derived
    assert entry["institutions"] == ["MIT"]
    assert entry["methods"] == ["Method X"]
    assert entry["technical_routes"] == ["Route Y"]
    assert entry["research_trends"] == ["Trend Z"]
    assert entry["summary"] == "Summary text"
    assert entry["keywords"] == ["key1", "key2"]
    assert entry["kind"] == "topic"
    assert entry["links"] == []


def test_type_defaults_to_empty_string(tmp_path):
    """type field defaults to empty string when absent."""
    _init(tmp_path)

    _topic(tmp_path, "no_type.md", {"title": "No Type"}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["no_type.md"]

    assert entry["type"] == ""


def test_type_coerced_to_nfc_string(tmp_path):
    """type field is NFC-normalized."""
    _init(tmp_path)

    # NFD Unicode (decomposed form)
    _topic(tmp_path, "nfd.md", {"title": "NFD", "type": "café"}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["nfd.md"]

    # Should be normalized to NFC
    assert entry["type"] == "café"
    assert entry["type"] == "café"  # NFC form


def test_type_non_scalar_becomes_empty_string(tmp_path):
    """Non-scalar type values coerce to empty string."""
    _init(tmp_path)

    _topic(tmp_path, "list_type.md", {"title": "List", "type": ["concept", "method"]}, "Content.")
    _topic(tmp_path, "dict_type.md", {"title": "Dict", "type": {"main": "concept"}}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    assert data["topics"]["list_type.md"]["type"] == ""
    assert data["topics"]["dict_type.md"]["type"] == ""


def test_aliases_defaults_to_empty_list(tmp_path):
    """aliases field defaults to empty list when absent."""
    _init(tmp_path)

    _topic(tmp_path, "no_aliases.md", {"title": "No Aliases"}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["no_aliases.md"]

    assert entry["aliases"] == []


def test_aliases_preserves_order_and_does_not_dedupe(tmp_path):
    """aliases list preserves authored order without deduplication."""
    _init(tmp_path)

    _topic(tmp_path, "ordered.md", {
        "title": "Ordered",
        "aliases": ["Third", "First", "Second", "First"]  # Duplicate "First"
    }, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["ordered.md"]

    # Order preserved, duplicates NOT removed
    assert entry["aliases"] == ["Third", "First", "Second", "First"]


def test_featured_defaults_to_false(tmp_path):
    """featured field defaults to false when absent."""
    _init(tmp_path)

    _topic(tmp_path, "not_featured.md", {"title": "Not Featured"}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["not_featured.md"]

    assert entry["featured"] is False


def test_featured_strict_boolean_coercion(tmp_path):
    """featured field only true for YAML boolean true."""
    _init(tmp_path)

    _topic(tmp_path, "true.md", {"title": "True", "featured": True}, "Content.")
    _topic(tmp_path, "false.md", {"title": "False", "featured": False}, "Content.")
    _topic(tmp_path, "string.md", {"title": "String", "featured": "true"}, "Content.")
    _topic(tmp_path, "number.md", {"title": "Number", "featured": 1}, "Content.")
    _topic(tmp_path, "null.md", {"title": "Null", "featured": None}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    assert data["topics"]["true.md"]["featured"] is True
    assert data["topics"]["false.md"]["featured"] is False
    assert data["topics"]["string.md"]["featured"] is False  # String "true" is not boolean
    assert data["topics"]["number.md"]["featured"] is False  # Truthy number is not boolean
    assert data["topics"]["null.md"]["featured"] is False


def test_quality_tier_computed_from_body(tmp_path):
    """quality_tier is computed from body metrics, not frontmatter."""
    _init(tmp_path)

    stub_body = "Short."
    basic_body = "## Section\n\nSome content here."
    standard_body = "## S1\n## S2\n\n" + ("Prose content here. " * 40)  # Need >= 600 prose_chars

    _topic(tmp_path, "stub.md", {"title": "Stub"}, stub_body)
    _topic(tmp_path, "basic.md", {"title": "Basic"}, basic_body)
    _topic(tmp_path, "standard.md", {"title": "Standard"}, standard_body)

    data, errors = wiki_index.rebuild(tmp_path)

    assert data["topics"]["stub.md"]["quality_tier"] == "stub"
    assert data["topics"]["basic.md"]["quality_tier"] == "basic"
    assert data["topics"]["standard.md"]["quality_tier"] == "standard"


def test_backlinks_defaults_to_zero(tmp_path):
    """backlinks field defaults to 0 for topics with no inbound links."""
    _init(tmp_path)

    _topic(tmp_path, "isolated.md", {"title": "Isolated"}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)
    entry = data["topics"]["isolated.md"]

    assert entry["backlinks"] == 0


def test_index_determinism_preserved_with_new_fields(tmp_path):
    """Rebuilding twice produces byte-identical output."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {
        "title": "Topic",
        "sources": ["a.md"],
        "type": "concept",
        "aliases": ["Alias"],
        "featured": True
    }, "## Section\n\nContent.")

    data1, _ = wiki_index.rebuild(tmp_path)
    data2, _ = wiki_index.rebuild(tmp_path)

    # Serialize and compare
    json1 = wiki_index.serialize(data1)
    json2 = wiki_index.serialize(data2)

    assert json1 == json2


# --- 6.2 Property-based / invariant tests ---


def test_rebuild_determinism_across_file_order(tmp_path):
    """INVARIANT: rebuild is deterministic regardless of file creation order."""
    _init(tmp_path)

    # Create topics in one order
    _topic(tmp_path, "zzz.md", {"title": "ZZZ", "aliases": ["Last"]}, "Content Z.")
    _topic(tmp_path, "aaa.md", {"title": "AAA", "aliases": ["First"]}, "Content A.")
    _topic(tmp_path, "mmm.md", {"title": "MMM", "aliases": ["Mid"]}, "Content M.")

    data1, _ = wiki_index.rebuild(tmp_path)
    json1 = wiki_index.serialize(data1)

    # Rebuild again (same file order on disk, but order-independent logic)
    data2, _ = wiki_index.rebuild(tmp_path)
    json2 = wiki_index.serialize(data2)

    # Should be byte-identical
    assert json1 == json2

    # Keys should be sorted in output
    topics_keys = list(data1["topics"].keys())
    assert topics_keys == sorted(topics_keys)


def test_new_fields_only_on_topics_not_captures(tmp_path):
    """INVARIANT: new fields appear ONLY on topics, not queries."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {
        "title": "Topic",
        "type": "concept",
        "aliases": ["Alias"],
        "featured": True
    }, "## Section\n\nProse.")

    _query(tmp_path, "query.md", {
        "title": "Query",
        "sources": ["q.md"]
    }, "Query body.")

    data, _ = wiki_index.rebuild(tmp_path)

    topic_entry = data["topics"]["topic.md"]
    query_entry = data["queries"]["queries/query.md"]

    # Topic has new fields
    assert "type" in topic_entry
    assert "aliases" in topic_entry
    assert "quality_tier" in topic_entry
    assert "featured" in topic_entry
    assert "backlinks" in topic_entry

    # Query does NOT have new fields
    assert "type" not in query_entry
    assert "aliases" not in query_entry
    assert "quality_tier" not in query_entry
    assert "featured" not in query_entry
    assert "backlinks" not in query_entry


def test_alias_index_injectivity(tmp_path):
    """INVARIANT: alias_index is injective (one alias -> one target)."""
    _init(tmp_path)

    _topic(tmp_path, "topic1.md", {
        "title": "Topic 1",
        "aliases": ["Alias A", "Alias B"]
    }, "Content.")

    _topic(tmp_path, "topic2.md", {
        "title": "Topic 2",
        "aliases": ["Alias C", "Alias D"]
    }, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    assert errors == []
    alias_index = data.get("alias_index", {})

    # Each alias maps to exactly one target
    assert alias_index.get("Alias A") == "topic1.md"
    assert alias_index.get("Alias B") == "topic1.md"
    assert alias_index.get("Alias C") == "topic2.md"
    assert alias_index.get("Alias D") == "topic2.md"

    # No alias maps to multiple targets
    targets = set(alias_index.values())
    for target in targets:
        aliases_for_target = [a for a, t in alias_index.items() if t == target]
        # Each alias should appear exactly once in the index
        assert len(aliases_for_target) == len(set(aliases_for_target))


def test_alias_conflict_detection(tmp_path):
    """INVARIANT: alias conflicts reported, never auto-picked."""
    _init(tmp_path)

    # Two topics with same alias
    _topic(tmp_path, "topic1.md", {
        "title": "Topic 1",
        "aliases": ["SharedAlias"]
    }, "Content 1.")

    _topic(tmp_path, "topic2.md", {
        "title": "Topic 2",
        "aliases": ["SharedAlias"]
    }, "Content 2.")

    data, errors = wiki_index.rebuild(tmp_path)

    # Should report conflict
    conflict_errors = [e for e in errors if e.get("error") == "alias_conflict"]
    assert len(conflict_errors) == 1

    conflict = conflict_errors[0]
    assert conflict["alias"] == "SharedAlias"
    assert "candidates" in conflict
    # Candidates should be sorted
    candidates = conflict["candidates"]
    assert candidates == sorted(candidates)
    assert set(candidates) == {"topic1.md", "topic2.md"}

    # Conflicting alias should NOT appear in alias_index
    alias_index = data.get("alias_index", {})
    assert "SharedAlias" not in alias_index


def test_alias_target_missing_detection(tmp_path):
    """INVARIANT: alias pointing to nonexistent topic is reported."""
    _init(tmp_path)

    # Create alias map pointing to nonexistent topic
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(exist_ok=True)
    alias_map_path = wiki_dir / ".wiki-aliases.json"
    alias_map_path.write_text(json.dumps({"GhostAlias": "nonexistent.md"}), encoding="utf-8")

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    # Should report missing target
    missing_errors = [e for e in errors if e.get("error") == "alias_target_missing"]
    assert len(missing_errors) == 1

    missing = missing_errors[0]
    assert missing["alias"] == "GhostAlias"
    assert missing["target"] == "nonexistent.md"

    # Missing alias should NOT appear in alias_index
    alias_index = data.get("alias_index", {})
    assert "GhostAlias" not in alias_index


def test_alias_map_invalid_detection(tmp_path):
    """INVARIANT: malformed alias map is reported, not fatal."""
    _init(tmp_path)

    # Create malformed alias map
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(exist_ok=True)
    alias_map_path = wiki_dir / ".wiki-aliases.json"
    alias_map_path.write_text("not valid json {", encoding="utf-8")

    _topic(tmp_path, "topic.md", {
        "title": "Topic",
        "aliases": ["ValidAlias"]
    }, "Content.")

    data, errors = wiki_index.rebuild(tmp_path)

    # Should report invalid map
    invalid_errors = [e for e in errors if e.get("error") == "alias_map_invalid"]
    assert len(invalid_errors) == 1

    # Build should still succeed with frontmatter aliases
    alias_index = data.get("alias_index", {})
    assert alias_index.get("ValidAlias") == "topic.md"


def test_backlinks_equals_inbound_edge_count(tmp_path):
    """INVARIANT: backlinks == number of distinct inbound linker pages."""
    _init(tmp_path)

    # Create target topic
    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")

    # Create linkers
    _topic(tmp_path, "linker1.md", {"title": "Linker 1"}, "Link to [[target]].")
    _topic(tmp_path, "linker2.md", {"title": "Linker 2"}, "Link to [[target]] multiple [[target]] times.")
    _topic(tmp_path, "linker3.md", {"title": "Linker 3"}, "Link to [[target]].")

    # Create query linker
    _query(tmp_path, "query.md", {"title": "Query"}, "Query links [[target]].")

    # Create non-linker
    _topic(tmp_path, "other.md", {"title": "Other"}, "No links here.")

    data, errors = wiki_index.rebuild(tmp_path)

    assert errors == []
    target_entry = data["topics"]["target.md"]

    # Should count 4 distinct linkers: linker1, linker2, linker3, query
    # (multiple links from same page count as 1)
    assert target_entry["backlinks"] == 4

    # Manually count inbound edges
    linkers = set()
    for kind in ["topics", "queries"]:
        for page_key, page_entry in data.get(kind, {}).items():
            links = page_entry.get("links", [])
            if "target" in links:  # Stem match
                linkers.add(page_key)

    assert len(linkers) == target_entry["backlinks"]


def test_backlinks_self_links_excluded(tmp_path):
    """INVARIANT: self-links do not increment backlinks."""
    _init(tmp_path)

    _topic(tmp_path, "selflink.md", {"title": "Selflink"}, "I link to [[selflink]] myself.")

    data, errors = wiki_index.rebuild(tmp_path)

    assert errors == []
    entry = data["topics"]["selflink.md"]

    # Self-link should NOT count
    assert entry["backlinks"] == 0


def test_backlinks_deterministic_across_rebuild(tmp_path):
    """INVARIANT: backlinks values are deterministic across rebuilds."""
    _init(tmp_path)

    _topic(tmp_path, "target.md", {"title": "Target"}, "Content.")
    _topic(tmp_path, "linker1.md", {"title": "Linker 1"}, "[[target]]")
    _topic(tmp_path, "linker2.md", {"title": "Linker 2"}, "[[target]]")

    data1, _ = wiki_index.rebuild(tmp_path)
    data2, _ = wiki_index.rebuild(tmp_path)

    backlinks1 = data1["topics"]["target.md"]["backlinks"]
    backlinks2 = data2["topics"]["target.md"]["backlinks"]

    assert backlinks1 == backlinks2 == 2
