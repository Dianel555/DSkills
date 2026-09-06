"""TDD regression tests for the academic/Obsidian evaluation roadmap."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest
from agent_wiki import commands, config, frontmatter, links, site, wiki_index, worklist


def _init(vault: Path) -> None:
    config.topics_dir(vault).mkdir(parents=True, exist_ok=True)


def _page(vault: Path, name: str, meta: dict, body: str = "x") -> Path:
    path = config.topics_dir(vault) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return path


def test_link_parser_preserves_fragments_embeds_and_ignores_code() -> None:
    refs = links.parse(
        "Outside [[Paper#Methods|method]] and [paper](Paper.md#Results).\n"
        "![[attachments/figure.png|300]]\n\n"
        "```md\n[[Not a relation]]\n```\n\n"
        "Inline `[[Also not a relation]]`."
    )

    assert [(ref.target, ref.fragment, ref.embed, ref.syntax) for ref in refs] == [
        ("Paper", "Methods", False, "wikilink"),
        ("Paper.md", "Results", False, "markdown"),
        ("attachments/figure.png", "", True, "wikilink"),
    ]


def test_link_parser_handles_markdown_boundaries_and_comments() -> None:
    refs = links.parse(
        "``code ` [[code-span]]`` [[real]]\n"
        "```md\n[[fenced]]\n``` not-a-close\n[[still-fenced]]\n```\n"
        "[[real-two]]\n<!-- [[comment]]\n[[comment-two]]\n[also-comment](Comment.md) -->\n"
        "`<!-- [[inline-comment]] -->` [[real-three]]\n"
        "[ref](https://example.org/Function_(mathematics))\n"
        "![pdf](<paper_(v1).pdf#page=3> \"title\")"
    )

    assert [(ref.target, ref.fragment, ref.embed, ref.syntax) for ref in refs] == [
        ("real", "", False, "wikilink"),
        ("real-two", "", False, "wikilink"),
        ("real-three", "", False, "wikilink"),
        ("https://example.org/Function_(mathematics)", "", False, "markdown"),
        ("paper_(v1).pdf", "page=3", True, "markdown"),
    ]
    inline = "`<!-- [[inline-comment]] -->`"
    assert links.rewrite(inline, lambda _ref: "BROKEN") == inline


def test_index_records_canonical_link_details_and_ignores_code(tmp_path: Path) -> None:
    _init(tmp_path)
    _page(
        tmp_path,
        "A.md",
        {"title": "A"},
        "[[B#Methods|method]] [B](B.md#Results)\n\n```md\n[[Fake]]\n```",
    )

    entry = wiki_index.rebuild(tmp_path)[0]["topics"]["A.md"]
    assert entry["links"] == ["B", "B.md"]
    assert entry["link_records"] == [
        {
            "target": "B",
            "label": "method",
            "fragment": "Methods",
            "embed": False,
            "syntax": "wikilink",
        },
        {
            "target": "B.md",
            "label": "B",
            "fragment": "Results",
            "embed": False,
            "syntax": "markdown",
        },
    ]


def test_incremental_rebuild_invalidates_old_index_schema(tmp_path: Path) -> None:
    _init(tmp_path)
    _page(tmp_path, "A.md", {"title": "A"}, "[B](B.md#Methods)")
    initial, _ = wiki_index.rebuild(tmp_path)
    old_entry = dict(initial["topics"]["A.md"])
    old_entry.pop("link_records", None)
    for field in ("citekey", "doi", "library_id", "review_status", "reviewed_at"):
        old_entry.pop(field, None)
    old_entry["links"] = []
    config.index_path(tmp_path).write_text(
        json.dumps({"version": 1, "topics": {"A.md": old_entry}, "queries": {}, "alias_index": {}}),
        encoding="utf-8",
    )

    rebuilt, _ = wiki_index.rebuild(tmp_path, incremental=True)

    assert rebuilt["version"] != 1
    assert rebuilt["topics"]["A.md"]["link_records"] == [
        {
            "target": "B.md",
            "label": "B",
            "fragment": "Methods",
            "embed": False,
            "syntax": "markdown",
        }
    ]


def test_incremental_rebuild_rejects_incomplete_current_entry(tmp_path: Path) -> None:
    _init(tmp_path)
    _page(tmp_path, "A.md", {"title": "A"}, "[B](B.md#Methods)")
    initial, _ = wiki_index.rebuild(tmp_path)
    incomplete = dict(initial["topics"]["A.md"])
    incomplete.pop("link_records")
    config.index_path(tmp_path).write_text(
        json.dumps(
            {
                "version": wiki_index.INDEX_VERSION,
                "topics": {"A.md": incomplete},
                "queries": {},
                "alias_index": {},
            }
        ),
        encoding="utf-8",
    )

    rebuilt, _ = wiki_index.rebuild(tmp_path, incremental=True)

    assert rebuilt["topics"]["A.md"]["link_records"]


def test_incremental_rebuild_rejects_malformed_current_entry(tmp_path: Path) -> None:
    _init(tmp_path)
    _page(tmp_path, "A.md", {"title": "A"}, "[[B]]")
    initial, _ = wiki_index.rebuild(tmp_path)
    malformed = dict(initial["topics"]["A.md"])
    malformed["aliases"] = 1
    config.index_path(tmp_path).write_text(
        json.dumps(
            {
                "version": wiki_index.INDEX_VERSION,
                "topics": {"A.md": malformed},
                "queries": {},
                "alias_index": {},
            }
        ),
        encoding="utf-8",
    )

    rebuilt, _ = wiki_index.rebuild(tmp_path, incremental=True)

    assert rebuilt["topics"]["A.md"]["aliases"] == []
    assert rebuilt["topics"]["A.md"]["link_records"]


def test_worklist_resolves_alias_and_does_not_report_code_links(tmp_path: Path) -> None:
    _init(tmp_path)
    _page(tmp_path, "A.md", {"title": "A"}, "[[Bee#Methods]]\n```md\n[[Missing]]\n```")
    _page(tmp_path, "B.md", {"title": "B", "aliases": ["Bee"]})

    result = worklist.compute_worklist(tmp_path)

    assert result["wanted"] == []
    assert result["unresolved"] == []


def test_canvas_resolves_alias_and_fragment_links(tmp_path: Path) -> None:
    _init(tmp_path)
    _page(tmp_path, "A.md", {"title": "A"}, "[[Bee#Methods]]")
    _page(tmp_path, "B.md", {"title": "B", "aliases": ["Bee"]})
    data, errors = wiki_index.rebuild(tmp_path)

    assert errors == []
    from agent_wiki import canvas

    assert canvas.neighbors("A.md", data) == {"B.md"}


def test_link_resolver_accepts_explicit_wiki_query_paths(tmp_path: Path) -> None:
    _init(tmp_path)
    _page(tmp_path, "A.md", {"title": "A"}, "[[wiki/queries/report]]")
    queries = config.queries_dir(tmp_path)
    queries.mkdir(parents=True, exist_ok=True)
    (queries / "report.md").write_text(frontmatter.dump({"title": "Report"}, "body"), encoding="utf-8")

    data, errors = wiki_index.rebuild(tmp_path)

    assert errors == []
    entry = data["topics"]["A.md"]
    resolution = links.resolve("wiki/queries/report", set(data["topics"]), set(data["queries"]), data["alias_index"])
    assert resolution.status == "resolved"
    assert resolution.key == "queries/report.md"
    assert links.from_entry(entry)[0].target == "wiki/queries/report"


def test_site_preserves_heading_fragment_and_renders_image_embed(tmp_path: Path) -> None:
    pytest.importorskip("markdown")
    _init(tmp_path)
    _page(tmp_path, "A.md", {"title": "A"}, "See [[B#Methods|methods]].\n\n![[attachments/figure.png]]")
    _page(tmp_path, "B.md", {"title": "B"}, "## Methods\n\nDetails")
    (tmp_path / "attachments").mkdir()
    (tmp_path / "attachments" / "figure.png").write_bytes(b"png")

    site.generate_site(tmp_path)
    rendered = (config.wiki_root(tmp_path) / "site" / "A.html").read_text(encoding="utf-8")

    assert 'href="B.html#h-methods"' in rendered
    assert 'src="../../attachments/figure.png"' in rendered
    assert '<span class="wikilink wikilink--missing"' not in rendered


def test_site_preserves_external_fragments_and_special_heading_ids(tmp_path: Path) -> None:
    pytest.importorskip("markdown")
    _init(tmp_path)
    _page(
        tmp_path,
        "A.md",
        {"title": "A"},
        "[[B#Methods & Results|internal]]\n\n"
        "[external](https://example.org/doc#section)\n\n"
        "[pdf](paper.pdf#page=3)",
    )
    _page(tmp_path, "B.md", {"title": "B"}, "## Methods & Results\n\nbody")

    site.generate_site(tmp_path)
    rendered_a = (config.wiki_root(tmp_path) / "site" / "A.html").read_text(encoding="utf-8")
    rendered_b = (config.wiki_root(tmp_path) / "site" / "B.html").read_text(encoding="utf-8")

    assert 'href="https://example.org/doc#section"' in rendered_a
    assert 'href="../../paper.pdf#page=3"' in rendered_a
    assert 'href="B.html#h-methods_&amp;_results"' in rendered_a
    assert 'id="h-methods_&amp;_results"' in rendered_b


def test_site_does_not_reinterpret_search_text_as_html(tmp_path: Path) -> None:
    _init(tmp_path)
    _page(tmp_path, "A.md", {"title": "<em>literal</em>"}, "Content")
    site.generate_site(tmp_path)
    rendered = (config.wiki_root(tmp_path) / "site" / "index.html").read_text(encoding="utf-8")

    assert "innerHTML" not in rendered


def test_site_sanitizes_raw_html_and_unsafe_urls(tmp_path: Path) -> None:
    pytest.importorskip("markdown")
    _init(tmp_path)
    _page(
        tmp_path,
        "A.md",
        {"title": "A"},
        '<script>alert("x")</script>\n\n<div onclick="alert(1)">safe text</div>\n\n[bad](javascript:alert(1))',
    )
    site.generate_site(tmp_path)
    rendered = (config.wiki_root(tmp_path) / "site" / "A.html").read_text(encoding="utf-8")

    article = rendered.split('<main id="main-article"', 1)[1].split("</main>", 1)[0]
    lowered = article.lower()
    assert "<script" not in lowered
    assert "onclick" not in lowered
    assert "javascript:" not in lowered
    assert "safe text" in article


def test_site_escapes_raw_text_payloads(tmp_path: Path) -> None:
    pytest.importorskip("markdown")
    _init(tmp_path)
    _page(
        tmp_path,
        "A.md",
        {"title": "A"},
        '<script><img src=x onerror="alert(1)"></script>\n\n'
        '<style><img src=x onerror="alert(2)"></style>\n\n'
        '<textarea><img src=x onerror="alert(3)"></textarea>\n\n'
        '<script/><img src=x onerror="alert(4)">',
    )
    site.generate_site(tmp_path)
    rendered = (config.wiki_root(tmp_path) / "site" / "A.html").read_text(encoding="utf-8")
    article = rendered.split('<main id="main-article"', 1)[1].split("</main>", 1)[0]

    assert "<script" not in article.lower()
    assert "<style" not in article.lower()
    assert "<textarea" not in article.lower()
    assert "<img" not in article.lower()


def test_rest_write_failure_never_falls_back_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init(tmp_path)
    index = config.wiki_root(tmp_path) / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("OLD", encoding="utf-8")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH", "wiki/.agent-wiki-vault-id.md")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_VAULT_ID", "vault-one")
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: True)
    monkeypatch.setattr(commands.obsidian_api, "put_file", lambda *args, **kwargs: False)

    with pytest.raises(commands.obsidian_api.WriteSafetyError):
        commands._write_index(tmp_path, "NEW", use_rest=True, expected_content="OLD")

    assert index.read_text(encoding="utf-8") == "OLD"


def test_rest_412_is_a_conflict_not_a_false_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_wiki import obsidian_api

    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "secret")

    def fail(req: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError("url", 412, "conflict", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(obsidian_api.WriteConflictError):
        obsidian_api.put_file("wiki/index.md", "NEW")


def test_rest_preflight_rejects_wrong_target_or_changed_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_wiki import obsidian_api

    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "secret")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH", "wiki/.agent-wiki-vault-id.md")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_VAULT_ID", "vault-one")
    responses = iter(
        [
            {"path": "wiki/.agent-wiki-vault-id.md", "content": "vault-one"},
            {"version": "v1"},
            {"path": "Other/wiki/index.md", "content": "OLD"},
            {"path": "wiki/.agent-wiki-vault-id.md", "content": "vault-one"},
            {"version": "v2"},
            {"path": "wiki/index.md", "content": "NEWER"},
        ]
    )

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(next(responses)).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())

    with pytest.raises(obsidian_api.TargetVerificationError):
        obsidian_api.put_file("wiki/index.md", "NEW", expected_content="OLD")
    with pytest.raises(obsidian_api.WriteConflictError):
        obsidian_api.put_file("wiki/index.md", "NEW", expected_content="OLD")


def test_research_metadata_is_normalized_without_affecting_plain_notes(tmp_path: Path) -> None:
    _init(tmp_path)
    _page(
        tmp_path,
        "paper.md",
        {
            "title": "Paper",
            "citekey": "smith2024",
            "doi": "10.1234/example",
            "library_id": "zotero:ABC",
            "review_status": "needs_review",
            "reviewed_at": "2026-09-05",
        },
    )
    _page(tmp_path, "plain.md", {"title": "Plain"})

    topics = wiki_index.rebuild(tmp_path)[0]["topics"]
    assert topics["paper.md"]["citekey"] == "smith2024"
    assert topics["paper.md"]["doi"] == "10.1234/example"
    assert topics["paper.md"]["library_id"] == "zotero:ABC"
    assert topics["paper.md"]["review_status"] == "needs_review"
    assert topics["plain.md"]["citekey"] == ""


def test_static_site_includes_query_reports_and_search_metadata(tmp_path: Path) -> None:
    pytest.importorskip("markdown")
    _init(tmp_path)
    _page(tmp_path, "topic.md", {"title": "Topic"})
    queries = config.queries_dir(tmp_path)
    queries.mkdir(parents=True, exist_ok=True)
    (queries / "report.md").write_text(
        frontmatter.dump(
            {
                "title": "Report",
                "authors": ["Ada"],
                "year_start": 2024,
                "keywords": ["Survey"],
                "summary": "A research report",
            },
            "Evidence [^1].\n\n[^1]: Page 4.",
        ),
        encoding="utf-8",
    )

    site.generate_site(tmp_path)
    site_dir = config.wiki_root(tmp_path) / "site"
    index_html = (site_dir / "index.html").read_text(encoding="utf-8")

    assert (site_dir / "queries_report.html").exists()
    assert "Report" in index_html
    assert "ada" in index_html and "2024" in index_html and "survey" in index_html
    report_html = (site_dir / "queries_report.html").read_text(encoding="utf-8")
    assert "Page 4." in report_html
    assert "fn" in report_html


def test_source_change_is_a_distinct_worklist_reason(tmp_path: Path) -> None:
    _init(tmp_path)
    source = tmp_path / "paper.md"
    source.write_text("old", encoding="utf-8")
    topic = _page(
        tmp_path,
        "topic.md",
        {"title": "Topic", "sources": ["paper.md"]},
        "## A\n\nword " * 100 + "\n\n## B\n\nword " * 100,
    )
    from agent_wiki import cache

    data = cache.empty_schema()
    stat = source.stat()
    cache.upsert(data, "paper.md", cache.sha256_file(source), stat.st_mtime_ns, stat.st_size, ["topic.md"])
    source.write_text("new", encoding="utf-8")

    result = worklist.compute_worklist(tmp_path)
    stale = next(item for item in result["stale"] if item["path"] == "topic.md")
    assert stale["reason"] == "source_changed"
    assert "source_changed" in stale["reasons"]
    assert topic.exists()


def test_source_change_marks_query_for_review(tmp_path: Path) -> None:
    _init(tmp_path)
    source = tmp_path / "paper.md"
    source.write_text("old", encoding="utf-8")
    queries = config.queries_dir(tmp_path)
    queries.mkdir(parents=True, exist_ok=True)
    (queries / "report.md").write_text(
        frontmatter.dump({"title": "Report", "sources": ["paper.md"]}, "Evidence"),
        encoding="utf-8",
    )
    from agent_wiki import cache

    data = cache.empty_schema()
    stat = source.stat()
    cache.upsert(data, "paper.md", cache.sha256_file(source), stat.st_mtime_ns, stat.st_size, [])
    source.write_text("new", encoding="utf-8")

    result = worklist.compute_worklist(tmp_path)
    assert result["review"] == [{"path": "queries/report.md", "kind": "query", "reason": "source_changed"}]


def test_status_marks_changed_query_site_stale(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _init(tmp_path)
    _page(tmp_path, "topic.md", {"title": "Topic"})
    query = config.queries_dir(tmp_path) / "report.md"
    query.parent.mkdir(parents=True, exist_ok=True)
    query.write_text(frontmatter.dump({"title": "Report"}, "body"), encoding="utf-8")
    args = type("Args", (), {"vault": str(tmp_path), "format": "json", "verbose": False})()
    commands.cmd_gen_site(args)
    capsys.readouterr()
    import time
    time.sleep(0.01)
    query.touch()
    commands.cmd_status(args)
    status = json.loads(capsys.readouterr().out)
    assert status["site_stale"] is True
    assert status["review_count"] == 0


def test_research_query_template_is_reproducible() -> None:
    template = Path(__file__).parents[1] / "templates" / "query" / "research.md"
    text = template.read_text(encoding="utf-8")
    for heading in ("研究问题", "检索记录", "证据矩阵", "争议", "下一步阅读"):
        assert heading in text
