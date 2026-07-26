from agent_wiki import config, frontmatter, source_type, wiki_index
from test_wiki_index import _init, _topic


# --- unit: ref classification ----------------------------------------------

def test_classify_ref_by_extension():
    assert source_type.classify_ref("物理/量子力学.md") == "markdown"
    assert source_type.classify_ref("refs/paper.PDF") == "pdf"
    assert source_type.classify_ref("a.docx") == "word"
    assert source_type.classify_ref("data.csv") == "spreadsheet"
    assert source_type.classify_ref("sheet.xlsx") == "spreadsheet"
    assert source_type.classify_ref("notes.txt") == "text"
    assert source_type.classify_ref("deck.pptx") == "slides"
    assert source_type.classify_ref("https://example.com/post") == "web"
    assert source_type.classify_ref("archive.zip") == "other"
    assert source_type.classify_ref("") == ""


def test_classify_sources_single_mixed_empty():
    assert source_type.classify_sources(["a.md", "b.md"]) == "markdown"
    assert source_type.classify_sources(["a.md", "b.pdf"]) == "mixed"
    assert source_type.classify_sources(["a.csv", "b.xlsx"]) == "spreadsheet"
    assert source_type.classify_sources([]) == ""
    assert source_type.classify_sources("solo.pdf") == "pdf"


# --- integration: index derives purely from format, ignores frontmatter ----

def test_index_source_type_is_pure_format(tmp_path):
    _init(tmp_path)
    _topic(tmp_path, "MD.md", {"sources": ["a.md", "b.md"]})
    _topic(tmp_path, "MIX.md", {"sources": ["a.md", "paper.pdf"]})
    _topic(tmp_path, "SEM.md", {"sources": ["a.md"], "source_type": "综述"})
    _topic(tmp_path, "DOC.md", {"sources": ["report.docx"], "source_type": "混合"})
    topics = wiki_index.rebuild(tmp_path)[0]["topics"]
    assert topics["MD.md"]["source_type"] == "markdown"
    assert topics["MIX.md"]["source_type"] == "mixed"
    assert topics["SEM.md"]["source_type"] == "markdown"   # Chinese frontmatter ignored
    assert topics["DOC.md"]["source_type"] == "word"


# --- backfill: rewrite frontmatter to format, dropping Chinese values -------

def _read_source_type(path):
    meta, _ = frontmatter.parse(path.read_text(encoding="utf-8-sig"))
    return meta.get("source_type")


def test_backfill_rewrites_to_format(tmp_path):
    _init(tmp_path)
    sem = _topic(tmp_path, "SEM.md", {"sources": ["a.md"], "source_type": "综述"})
    mixed = _topic(tmp_path, "MIX.md", {"sources": ["a.md", "b.md"], "source_type": "混合"})
    pdf = _topic(tmp_path, "E.md", {"sources": ["report.pdf"]})
    multi = _topic(tmp_path, "M.md", {"sources": ["a.md", "data.csv"]})

    result = source_type.backfill(tmp_path)

    assert {c["path"]: c["source_type"] for c in result["changed"]} == {
        "SEM.md": "markdown", "MIX.md": "markdown", "E.md": "pdf", "M.md": "mixed",
    }
    assert _read_source_type(sem) == "markdown"
    assert _read_source_type(mixed) == "markdown"
    assert _read_source_type(pdf) == "pdf"
    assert _read_source_type(multi) == "mixed"


def test_backfill_skips_no_sources_and_is_idempotent(tmp_path):
    _init(tmp_path)
    nosrc = _topic(tmp_path, "N.md", {"title": "N", "source_type": "综述"})  # no sources to derive from
    topic = _topic(tmp_path, "T.md", {"sources": ["a.md"]})

    first = source_type.backfill(tmp_path)
    assert {c["path"] for c in first["changed"]} == {"T.md"}
    assert _read_source_type(nosrc) == "综述"  # cannot derive a format, left untouched

    mtime = topic.stat().st_mtime_ns
    second = source_type.backfill(tmp_path)
    assert second["changed"] == []
    assert topic.stat().st_mtime_ns == mtime
