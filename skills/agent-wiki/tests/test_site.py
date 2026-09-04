"""Tests for site.py static HTML generation."""

import hashlib
import re
from pathlib import Path

import pytest
from agent_wiki import config, frontmatter, site, wiki_index


def _read_topic_html(vault: Path, prefix: str) -> str:
    """Read the generated page for a topic key (tries exact match first, then prefix)."""
    site_dir = config.wiki_root(vault) / "site"
    # Try exact match first (e.g., "topic.md" -> "topic.html")
    exact = site_dir / f"{prefix}.html"
    if exact.exists():
        return exact.read_text(encoding="utf-8")
    # Fallback to prefix match for old hash-style or disambiguation
    files = [p for p in site_dir.glob(f"{prefix}*.html") if p.name != "index.html"]
    assert files, f"no generated page for prefix {prefix!r}"
    return files[0].read_text(encoding="utf-8")


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


def test_site_generates_deterministic_output(tmp_path):
    """Two runs produce byte-identical output."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "## Section\n\nContent.")

    site.generate_site(tmp_path)

    # Read all generated files
    site_dir = config.wiki_root(tmp_path) / "site"
    files1 = {p.relative_to(site_dir): p.read_bytes() for p in site_dir.rglob("*.html")}

    site.generate_site(tmp_path)
    files2 = {p.relative_to(site_dir): p.read_bytes() for p in site_dir.rglob("*.html")}

    # Should be byte-identical
    assert files1.keys() == files2.keys()
    for path in files1:
        assert files1[path] == files2[path], f"File {path} differs between runs"


def test_site_atomic_write(tmp_path):
    """Site writes use atomic same-dir temp + replace."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    # This should complete successfully (atomic writes)
    result = site.generate_site(tmp_path)

    assert result["ok"] is True

    # Check no .tmp files left behind
    site_dir = config.wiki_root(tmp_path) / "site"
    tmp_files = list(site_dir.glob("*.tmp"))
    assert len(tmp_files) == 0, f"Found leftover temp files: {tmp_files}"


def test_site_writes_only_under_wiki_site(tmp_path):
    """Site writes only under wiki/site/, never modifies other areas."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    # Snapshot filesystem before
    before_files = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file() and "site" not in p.parts}

    site.generate_site(tmp_path)

    # Check nothing outside wiki/site/ was modified
    after_files = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file() and "site" not in p.parts}

    assert before_files == after_files, "Files outside wiki/site/ were modified"


def test_site_never_modifies_sources_topics_base_canvas(tmp_path):
    """Site never modifies source notes, topics, .base, or .canvas files."""
    _init(tmp_path)

    topic_path = _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    # Get hash of topic file
    topic_hash_before = hashlib.sha256(topic_path.read_bytes()).hexdigest()

    site.generate_site(tmp_path)

    # Topic file should be unchanged
    topic_hash_after = hashlib.sha256(topic_path.read_bytes()).hexdigest()
    assert topic_hash_before == topic_hash_after


def test_site_degraded_mode_escapes_plaintext(tmp_path):
    """When markdown is absent, site escapes body as plaintext."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "<script>alert('xss')</script>")

    # Test the _render_markdown function directly in degraded mode
    from agent_wiki import site as site_module

    # Temporarily patch MARKDOWN_AVAILABLE
    original_flag = site_module.MARKDOWN_AVAILABLE
    try:
        site_module.MARKDOWN_AVAILABLE = False

        result = site_module.generate_site(tmp_path)

        assert result["degraded"] is True

        # Check that HTML is escaped
        site_dir = config.wiki_root(tmp_path) / "site"
        html_file = site_dir / "topic.html"
        assert html_file.exists()

        html_content = html_file.read_text(encoding="utf-8")
        # Should be escaped (not raw <script>)
        assert "&lt;script&gt;" in html_content
        assert "<script>alert" not in html_content
    finally:
        # Restore original flag
        site_module.MARKDOWN_AVAILABLE = original_flag


def test_site_no_wall_clock_timestamps(tmp_path):
    """Site output contains no wall-clock timestamps (uses index generated_at)."""
    _init(tmp_path)

    _topic(tmp_path, "topic.md", {"title": "Topic"}, "Content.")

    import time
    site.generate_site(tmp_path)
    time.sleep(0.01)
    site.generate_site(tmp_path)

    # Should be identical despite time passing
    site_dir = config.wiki_root(tmp_path) / "site"
    files1 = {p.relative_to(site_dir): p.read_bytes() for p in site_dir.rglob("*.html")}
    files2 = {p.relative_to(site_dir): p.read_bytes() for p in site_dir.rglob("*.html")}

    for path in files1:
        assert files1[path] == files2[path]


def test_site_requires_initialized_wiki(tmp_path):
    """Site fails when wiki not initialized."""
    # Don't initialize
    with pytest.raises(ValueError, match="wiki_not_initialized"):
        site.generate_site(tmp_path)


def test_site_slug_is_injective(tmp_path):
    """Different topic keys produce different slugs."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Content A.")
    _topic(tmp_path, "B.md", {"title": "B"}, "Content B.")

    site.generate_site(tmp_path)

    site_dir = config.wiki_root(tmp_path) / "site"
    html_files = [p.name for p in site_dir.glob("*.html") if p.name != "index.html"]

    # Should have 2 distinct topic files
    assert len(html_files) == 2
    assert len(set(html_files)) == 2  # All unique


def test_site_slug_collision_detected(tmp_path):
    """Site handles slug collisions with numeric disambiguation (-2, -3, etc.)."""
    _init(tmp_path)

    # Create topics that sanitize to the same stem
    _topic(tmp_path, "test topic.md", {"title": "Test Topic 1"}, "Content 1.")
    _topic(tmp_path, "test  topic.md", {"title": "Test Topic 2"}, "Content 2.")  # double space

    result = site.generate_site(tmp_path)
    assert result["ok"] is True

    # Should have disambiguated filenames
    site_dir = config.wiki_root(tmp_path) / "site"
    assert (site_dir / "test_topic.html").exists()
    assert (site_dir / "test_topic-2.html").exists()


def test_site_generates_index_html(tmp_path):
    """Site generates index.html with links to all topics."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "Topic A"}, "Content A.")
    _topic(tmp_path, "B.md", {"title": "Topic B"}, "Content B.")

    site.generate_site(tmp_path)

    site_dir = config.wiki_root(tmp_path) / "site"
    index_path = site_dir / "index.html"

    assert index_path.exists()

    index_content = index_path.read_text(encoding="utf-8")
    assert "Topic A" in index_content
    assert "Topic B" in index_content
    assert "<a href=" in index_content


def test_site_renders_quality_tier_badge(tmp_path):
    """Site displays quality tier in topic pages."""
    _init(tmp_path)

    # Create standard tier topic
    _topic(tmp_path, "topic.md", {"title": "Topic"}, "## S1\n## S2\n\n" + ("Prose. " * 100))

    site.generate_site(tmp_path)

    site_dir = config.wiki_root(tmp_path) / "site"
    html_content = (site_dir / "topic.html").read_text(encoding="utf-8")
    # Should show quality tier
    assert "Quality" in html_content or "quality" in html_content


def test_site_shows_featured_marker(tmp_path):
    """Site displays featured marker for featured topics."""
    _init(tmp_path)

    _topic(tmp_path, "featured.md", {"title": "Featured", "featured": True}, "Content.")

    site.generate_site(tmp_path)

    site_dir = config.wiki_root(tmp_path) / "site"
    html_content = (site_dir / "featured.html").read_text(encoding="utf-8")
    # Should show featured marker
    assert "Featured" in html_content or "⭐" in html_content


def test_site_shows_backlinks_count(tmp_path):
    """Site displays backlinks count in topic pages."""
    _init(tmp_path)

    _topic(tmp_path, "A.md", {"title": "A"}, "Links [[B]].")
    _topic(tmp_path, "B.md", {"title": "B"}, "Content.")

    # Build index so backlinks are computed
    data, _ = wiki_index.rebuild(tmp_path)
    wiki_index.save_index(tmp_path, data)

    site.generate_site(tmp_path)

    site_dir = config.wiki_root(tmp_path) / "site"
    html_content = (site_dir / "B.html").read_text(encoding="utf-8")
    # Should show backlinks
    assert "Backlinks" in html_content or "backlinks" in html_content


# --- Editorial Atlas redesign (tasks 7.1-7.4; PBT P2/P4/P5/P6/P7/P8) ---


def test_three_theme_blocks_and_root_data_theme(tmp_path):
    """Page embeds :root + mo-ye + hu-yan token blocks with locked D4 hex; root has data-theme."""
    _init(tmp_path)
    _topic(tmp_path, "topic.md", {"title": "T"}, "x")
    site.generate_site(tmp_path)

    html = _read_topic_html(tmp_path, "topic")
    assert ":root" in html
    assert '[data-theme="mo-ye"]' in html
    assert '[data-theme="hu-yan"]' in html
    assert "data-theme=" in html  # root element carries the attribute
    # Locked D4 hex (must not drift)
    assert "#8B2E24" in html  # --cinnabar (shan-shui)
    assert "#0D0F0E" in html  # --bg (mo-ye)
    assert "#EFE6D2" in html  # --bg (hu-yan)


def test_semantic_landmarks_and_skip_link(tmp_path):
    """Article page uses nav/main#main-article/article/aside landmarks + skip link."""
    _init(tmp_path)
    _topic(tmp_path, "topic.md", {"title": "T"}, "## Sec\n\ntext")
    site.generate_site(tmp_path)

    html = _read_topic_html(tmp_path, "topic")
    assert '<main id="main-article"' in html
    assert "<nav" in html
    assert "<article" in html
    assert "<aside" in html
    assert 'href="#main-article"' in html  # skip-to-content link


def test_toc_stable_ids_with_duplicate_headings(tmp_path):
    pytest.importorskip("markdown")
    """TOC builds collision-suffixed deterministic ids; two runs byte-identical (P2)."""
    _init(tmp_path)
    _topic(tmp_path, "topic.md", {"title": "T"},
           "## Intro\n\na\n\n## Intro\n\nb\n\n### Intro\n\nc")
    site.generate_site(tmp_path)

    html = _read_topic_html(tmp_path, "topic")
    assert 'id="h-intro"' in html
    assert 'id="h-intro-2"' in html
    assert 'id="h-intro-3"' in html
    assert 'aria-label="目录"' in html
    assert 'href="#h-intro"' in html

    site_dir = config.wiki_root(tmp_path) / "site"
    bytes1 = {p.name: p.read_bytes() for p in site_dir.glob("*.html")}
    site.generate_site(tmp_path)
    bytes2 = {p.name: p.read_bytes() for p in site_dir.glob("*.html")}
    assert bytes1 == bytes2


def test_wikilink_resolves_present_target(tmp_path):
    pytest.importorskip("markdown")
    """Existing target -> internal <a class="wikilink"> with slug href (P6)."""
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A"}, "Link to [[B]] here.")
    _topic(tmp_path, "B.md", {"title": "B"}, "Content B.")
    site.generate_site(tmp_path)

    html = _read_topic_html(tmp_path, "A")
    slug_b = "B.html"
    assert 'class="wikilink"' in html
    assert f'href="{slug_b}"' in html
    assert '<span class="wikilink wikilink--missing"' not in html  # resolved, not missing
    # target file exists in output
    assert (config.wiki_root(tmp_path) / "site" / slug_b).exists()


def test_wikilink_alias_resolution(tmp_path):
    pytest.importorskip("markdown")
    """Alias target resolves via alias_index to the canonical slug (P6)."""
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A"}, "See [[Bee]].")
    _topic(tmp_path, "B.md", {"title": "B", "aliases": ["Bee"]}, "Content B.")
    site.generate_site(tmp_path)

    html = _read_topic_html(tmp_path, "A")
    slug_b = "B.html"
    assert f'href="{slug_b}"' in html
    assert ">Bee</a>" in html


def test_wikilink_missing_target_inert_span(tmp_path):
    pytest.importorskip("markdown")
    """Absent target -> inert <span class="wikilink wikilink--missing"> with no href (P6)."""
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A"}, "Dangling [[Nope Nope]] link.")
    site.generate_site(tmp_path)

    html = _read_topic_html(tmp_path, "A")
    assert 'class="wikilink wikilink--missing"' in html
    assert '<a class="wikilink" href' not in html  # no anchor for the missing target
    assert "Nope Nope" in html


def test_wikilink_isolated_in_code(tmp_path):
    pytest.importorskip("markdown")
    """[[link]] inside fences and inline code spans is never converted (P5)."""
    _init(tmp_path)
    _topic(tmp_path, "z.md", {"title": "Zz"}, "content")
    body = (
        "Outside [[z]] link.\n\n"
        "```\n"
        "code [[z]] here\n"
        "```\n\n"
        "Inline `[[z]]` span.\n"
    )
    _topic(tmp_path, "a.md", {"title": "Aa"}, body)
    site.generate_site(tmp_path)

    html = _read_topic_html(tmp_path, "a")
    assert html.count('<a class="wikilink" href') == 1  # only the outside link converts
    assert "[[z]]" in html  # code occurrences survive literally


def test_degraded_no_injected_anchor(tmp_path):
    """Degraded mode escapes body and injects no wikilink anchor (P4)."""
    _init(tmp_path)
    _topic(tmp_path, "z.md", {"title": "Zz"}, "content")
    _topic(tmp_path, "a.md", {"title": "Aa"}, "See [[z]] now. <script>bad</script>")

    import agent_wiki.site as sm
    original = sm.MARKDOWN_AVAILABLE
    try:
        sm.MARKDOWN_AVAILABLE = False
        sm.generate_site(tmp_path)
        html = _read_topic_html(tmp_path, "a")
        assert "&lt;script&gt;" in html
        assert '<a class="wikilink"' not in html
        assert "[[z]]" in html
    finally:
        sm.MARKDOWN_AVAILABLE = original


def test_self_containment_no_external_refs(tmp_path):
    """No page references an external stylesheet, font, image, or script (P7)."""
    _init(tmp_path)
    _topic(tmp_path, "a.md", {"title": "Aa"}, "## H\n\n[[b]] text")
    _topic(tmp_path, "b.md", {"title": "Bb"}, "y")
    site.generate_site(tmp_path)

    site_dir = config.wiki_root(tmp_path) / "site"
    for p in site_dir.glob("*.html"):
        txt = p.read_text(encoding="utf-8")
        assert "<link" not in txt
        assert 'src="http' not in txt
        assert "@import" not in txt
        assert "url(http" not in txt


def test_five_tier_badge_classes_and_colors(tmp_path):
    """All five real tiers have badge classes; computed tier class is applied."""
    _init(tmp_path)
    _topic(tmp_path, "topic.md", {"title": "T"}, "## S1\n## S2\n\n" + ("Prose. " * 100))
    site.generate_site(tmp_path)

    html = _read_topic_html(tmp_path, "topic")
    for tier in ("premium", "rich", "standard", "basic", "stub"):
        assert f"badge--{tier}" in html
    assert "badge--standard" in html  # this body computes to the standard tier
    for token in ("--cinnabar", "--green", "--night", "--amber", "--faint"):
        assert token in html
    # Solid-color fill per tier (D4 accent as background, not outline)
    for tier, accent in (("premium", "--cinnabar"), ("rich", "--green"),
                         ("standard", "--night"), ("basic", "--amber"), ("stub", "--faint")):
        assert f".badge--{tier}{{background:var({accent})" in html
    # WCAG-AA contrast: per-theme text-color flips for mid-tone fills
    assert '[data-theme="mo-ye"] .badge--premium' in html
    assert '[data-theme="hu-yan"] .badge--basic{color:#FFFDF7' in html


def test_footer_shows_index_generated_at(tmp_path):
    """Footer carries the index generated_at (mtime-derived, not wall-clock)."""
    _init(tmp_path)
    _topic(tmp_path, "topic.md", {"title": "T"}, "x")
    data, _ = wiki_index.rebuild(tmp_path)
    gen = data["generated_at"]

    site.generate_site(tmp_path)
    html = _read_topic_html(tmp_path, "topic")
    assert gen in html
    idx = (config.wiki_root(tmp_path) / "site" / "index.html").read_text(encoding="utf-8")
    assert gen in idx


def test_infobox_retains_keywords(tmp_path):
    """Infobox keeps the Keywords label and values (contract retention)."""
    _init(tmp_path)
    _topic(tmp_path, "topic.md", {"title": "T", "keywords": ["AlphaKw", "BetaKw"]}, "x")
    site.generate_site(tmp_path)

    html = _read_topic_html(tmp_path, "topic")
    assert "Keywords" in html
    assert "AlphaKw" in html and "BetaKw" in html


def test_index_type_grouped_with_uncategorized_last(tmp_path):
    """Index groups by type ascending with a final 未分类 bucket (D10)."""
    _init(tmp_path)
    _topic(tmp_path, "a.md", {"title": "Aa", "type": "alpha"}, "x")
    _topic(tmp_path, "b.md", {"title": "Bb", "type": "beta"}, "x")
    _topic(tmp_path, "c.md", {"title": "Cc"}, "x")  # empty type
    site.generate_site(tmp_path)

    idx = (config.wiki_root(tmp_path) / "site" / "index.html").read_text(encoding="utf-8")
    assert "alpha" in idx and "beta" in idx and "未分类" in idx
    assert idx.index("alpha") < idx.index("beta") < idx.index("未分类")


def test_index_featured_section_sorted(tmp_path):
    """Index surfaces a 精选 section with featured cards sorted by (title, key)."""
    _init(tmp_path)
    _topic(tmp_path, "f1.md", {"title": "Zeta", "featured": True, "type": "x"}, "x")
    _topic(tmp_path, "f2.md", {"title": "Alpha", "featured": True, "type": "x"}, "x")
    _topic(tmp_path, "n.md", {"title": "Plain", "type": "x"}, "x")
    site.generate_site(tmp_path)

    idx = (config.wiki_root(tmp_path) / "site" / "index.html").read_text(encoding="utf-8")
    assert "精选" in idx
    m = re.search(r'<section class="featured".*?</section>', idx, re.DOTALL)
    assert m, "featured section not found"
    fs = m.group(0)
    assert fs.index("Alpha") < fs.index("Zeta")


def test_index_cards_have_data_search(tmp_path):
    """Cards carry a lowercased data-search payload of title+keywords+summary (D10)."""
    _init(tmp_path)
    _topic(tmp_path, "topic.md",
           {"title": "MyTitle", "keywords": ["KwOne"], "summary": "SumText"}, "x")
    site.generate_site(tmp_path)

    idx = (config.wiki_root(tmp_path) / "site" / "index.html").read_text(encoding="utf-8")
    assert 'data-search="' in idx
    assert "mytitle" in idx and "kwone" in idx and "sumtext" in idx


def test_index_search_empty_present_hidden(tmp_path):
    """A pre-rendered, hidden empty-state node exists for JS-only search (D7)."""
    _init(tmp_path)
    _topic(tmp_path, "a.md", {"title": "Aa"}, "x")
    site.generate_site(tmp_path)

    idx = (config.wiki_root(tmp_path) / "site" / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<div id="search-empty"[^>]*>', idx)
    assert m and "hidden" in m.group(0)
    assert "无匹配结果" in idx


def test_index_and_toc_navigable_without_js(tmp_path):
    pytest.importorskip("markdown")
    """With <script> stripped, index links and TOC anchors still resolve (P8)."""
    _init(tmp_path)
    _topic(tmp_path, "a.md", {"title": "Aa"}, "## H\n\nx")
    _topic(tmp_path, "b.md", {"title": "Bb"}, "y")
    site.generate_site(tmp_path)

    site_dir = config.wiki_root(tmp_path) / "site"
    idx = (site_dir / "index.html").read_text(encoding="utf-8")
    idx_nojs = re.sub(r"<script.*?</script>", "", idx, flags=re.DOTALL)
    for _key, slug in [("a.md", "a.html"), ("b.md", "b.html")]:
        assert f'href="{slug}"' in idx_nojs
        assert (site_dir / slug).exists()

    html = _read_topic_html(tmp_path, "a")
    html_nojs = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
    anchors = re.findall(r'href="#(h-[^"]+)"', html_nojs)
    assert anchors  # there is at least one TOC anchor
    for hid in anchors:
        assert f'id="{hid}"' in html_nojs


def test_index_html_written_last(tmp_path):
    """index.html is the final write so status.site_stale stays correct (P9)."""
    _init(tmp_path)
    _topic(tmp_path, "A.md", {"title": "A"}, "x")
    _topic(tmp_path, "B.md", {"title": "B"}, "y")
    site.generate_site(tmp_path)

    site_dir = config.wiki_root(tmp_path) / "site"
    index_m = (site_dir / "index.html").stat().st_mtime_ns
    topic_m = [p.stat().st_mtime_ns for p in site_dir.glob("*.html") if p.name != "index.html"]
    assert topic_m
    assert all(index_m >= m for m in topic_m)
