import pytest
from agent_wiki import frontmatter


def test_parse_without_frontmatter_returns_body_unchanged():
    text = "# Title\n\nBody\n"

    assert frontmatter.parse(text) == ({}, text)


def test_parse_yaml_frontmatter_preserves_body():
    text = "---\ntitle: Café\nsources:\n  - 笔记/a.md\n---\n\n# Body\n[[链接]]\n"

    meta, body = frontmatter.parse(text)

    assert meta == {"title": "Café", "sources": ["笔记/a.md"]}
    assert body == "# Body\n[[链接]]\n"


def test_dump_frontmatter_preserves_body():
    body = "# Body\n\n![[image.png]]\n"

    dumped = frontmatter.dump({"title": "Café", "sources": []}, body)

    assert dumped.startswith("---\n")
    assert "title: Café\n" in dumped
    assert dumped.endswith(body)
    assert "\n---\n\n# Body" in dumped


def test_parse_multiline_string_value():
    text = "---\nsummary: |\n  line 1\n  line 2\n---\n\nBody"

    meta, body = frontmatter.parse(text)

    assert meta["summary"] == "line 1\nline 2\n"
    assert body == "Body"


def test_parse_malformed_frontmatter_raises():
    with pytest.raises(frontmatter.FrontmatterError):
        frontmatter.parse("---\nkey: [\n---\nBody")
