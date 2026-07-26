from agent_wiki import cache, scanner


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_walk_sources_skips_wiki_obsidian_attachments_git_trash(tmp_path):
    write(tmp_path / "a.md", "a")
    write(tmp_path / "attachments" / "ignored.md", "x")
    write(tmp_path / "wiki" / "ignored.md", "x")
    write(tmp_path / ".obsidian" / "ignored.md", "x")
    write(tmp_path / ".git" / "ignored.md", "x")
    write(tmp_path / ".trash" / "ignored.md", "x")

    assert [p.name for p in scanner.walk_sources(tmp_path)] == ["a.md"]


def test_walk_sources_honors_wikiignore(tmp_path):
    write(tmp_path / ".wikiignore", "ignored/**\n")
    write(tmp_path / "kept.md", "a")
    write(tmp_path / "ignored" / "skip.md", "x")

    assert [p.name for p in scanner.walk_sources(tmp_path)] == ["kept.md"]


def test_classify_new_modified_unchanged_deleted_and_unicode_paths(tmp_path):
    write(tmp_path / "新笔记.md", "new")
    write(tmp_path / "same.md", "same")
    write(tmp_path / "changed.md", "changed-now")
    data = cache.empty_schema()
    same_file = tmp_path / "same.md"
    same_st = same_file.stat()
    cache.upsert(data, "same.md", cache.sha256_file(same_file), same_st.st_mtime_ns, same_st.st_size, ["same-topic.md"])
    cache.upsert(data, "changed.md", "old-sha", 1000000000000000000, 11, ["changed-topic.md"])
    cache.upsert(data, "deleted.md", "old-sha", 1000000000000000000, 7, ["deleted-topic.md"])

    result = scanner.classify(tmp_path, data)

    assert [item["path"] for item in result["new"]] == ["新笔记.md"]
    assert [item["path"] for item in result["modified"]] == ["changed.md"]
    assert [item["path"] for item in result["unchanged"]] == ["same.md"]
    assert result["modified"][0]["derived_topics"] == ["changed-topic.md"]
    assert result["deleted"] == [{"path": "deleted.md", "derived_topics": ["deleted-topic.md"]}]


def test_format_report_omits_unchanged_from_actionable_lists(tmp_path):
    result = {
        "new": [],
        "modified": [],
        "unchanged": [{"path": "same.md"}],
        "deleted": [],
        "errors": [],
        "skipped_symlinks": [],
    }

    report = scanner.format_report(result, tmp_path)

    assert report["version"] == 1
    assert report["stats"]["unchanged"] == 1
    assert "unchanged" not in report
    assert report["new"] == []


def test_zero_byte_markdown_is_valid_source(tmp_path):
    (tmp_path / "empty.md").write_bytes(b"")

    result = scanner.classify(tmp_path, cache.empty_schema())

    assert result["new"][0]["path"] == "empty.md"
    assert result["new"][0]["size"] == 0
