"""Deterministic static HTML site export (optional).

Renders a self-contained static site under `wiki/site/` from the retrieval index
and topic bodies. Requires the optional `markdown` package; degrades gracefully
to escaped plaintext when absent.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from . import config, frontmatter, wiki_index

# Optional markdown import - strictly gated inside this module
try:
    import markdown as markdown_lib
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _sanitize_filename(stem: str) -> str:
    """Sanitize stem for filesystem: replace unsafe chars with underscore, preserve CJK."""
    # Replace: / \ : * ? " < > | control chars and whitespace runs
    unsafe_pattern = r'[/\\:*?"<>|\x00-\x1f\x7f]|\s+'
    return re.sub(unsafe_pattern, '_', stem)


def _slug(topic_key: str) -> str:
    """Generate deterministic injective filename: sanitize(stem)-sha256[:8].html"""
    stem = topic_key[:-3] if topic_key.endswith(".md") else topic_key
    sanitized = _sanitize_filename(stem)
    key_hash = hashlib.sha256(_nfc(topic_key).encode("utf-8")).hexdigest()[:8]
    return f"{sanitized}-{key_hash}.html"


def _render_markdown(body: str) -> str:
    """Render markdown to HTML using python-markdown, or escaped plaintext fallback."""
    if MARKDOWN_AVAILABLE:
        # Fresh conversion per page (no shared Markdown() instance state)
        return markdown_lib.markdown(
            body,
            extensions=["fenced_code", "tables"],
            output_format="html"
        )
    else:
        # Degraded mode: HTML-escape plaintext
        import html
        return f"<pre>{html.escape(body)}</pre>"


def _html_escape(text: str) -> str:
    """HTML-escape a string."""
    import html
    return html.escape(text)


def generate_site(vault: str | Path) -> dict:
    """Generate static HTML site under wiki/site/.

    Returns:
        {
            "ok": True,
            "pages": int,
            "out": str,
            "degraded": bool
        }

    Raises:
        ValueError: if wiki not initialized
    """
    vault = Path(vault)
    wiki_root = config.wiki_root(vault)

    if not wiki_root.exists():
        raise ValueError("wiki_not_initialized")

    # Rebuild index
    data, _ = wiki_index.rebuild(vault)

    # Check for slug collisions
    slug_map: dict[str, str] = {}
    for topic_key in data["topics"].keys():
        slug = _slug(topic_key)
        if slug in slug_map:
            raise ValueError(f"site_slug_collision: {topic_key} and {slug_map[slug]}")
        slug_map[slug] = topic_key

    # Prepare output directory
    site_dir = wiki_root / "site"
    site_dir.mkdir(parents=True, exist_ok=True)

    pages_written = 0

    # Generate per-topic pages
    topics_dir = config.topics_dir(vault)
    for topic_key, entry in data["topics"].items():
        topic_path = topics_dir / topic_key
        if not topic_path.exists():
            continue

        try:
            text = topic_path.read_text(encoding="utf-8-sig")
            meta, body = frontmatter.parse(text)
        except Exception:
            continue

        # Render body
        body_html = _render_markdown(body)

        # Build infobox from frontmatter
        infobox_lines = []
        if entry.get("title"):
            infobox_lines.append(f"<strong>Title:</strong> {_html_escape(entry['title'])}")
        if entry.get("type"):
            infobox_lines.append(f"<strong>Type:</strong> {_html_escape(entry['type'])}")
        if entry.get("quality_tier"):
            infobox_lines.append(f"<strong>Quality:</strong> {_html_escape(entry['quality_tier'])}")
        if entry.get("featured"):
            infobox_lines.append(f"<strong>Featured:</strong> ⭐")
        if entry.get("backlinks", 0) > 0:
            infobox_lines.append(f"<strong>Backlinks:</strong> {entry['backlinks']}")

        infobox_html = "<br>".join(infobox_lines) if infobox_lines else ""

        # Build page HTML
        page_html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_html_escape(entry.get('title', topic_key))}</title>
<style>
body {{ font-family: sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
.container {{ display: flex; gap: 20px; }}
.sidebar {{ flex: 0 0 250px; border: 1px solid #ddd; padding: 15px; border-radius: 5px; }}
.content {{ flex: 1; }}
h1 {{ margin-top: 0; }}
</style>
</head>
<body>
<div class="container">
<aside class="sidebar">
<h3>Info</h3>
{infobox_html}
</aside>
<main class="content">
<h1>{_html_escape(entry.get('title', topic_key))}</h1>
{body_html}
</main>
</div>
</body>
</html>"""

        # Write atomically
        slug = _slug(topic_key)
        out_path = site_dir / slug
        tmp_fd, tmp_path = tempfile.mkstemp(dir=site_dir, suffix=".html", text=True)
        try:
            os.write(tmp_fd, page_html.encode("utf-8"))
            os.close(tmp_fd)
            os.replace(tmp_path, out_path)
            pages_written += 1
        except OSError:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # Generate index.html (simple list of topics)
    index_lines = ["<!DOCTYPE html>", "<html lang=\"zh\">", "<head>",
                   "<meta charset=\"UTF-8\">",
                   "<title>Wiki Index</title>",
                   "<style>body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }</style>",
                   "</head>", "<body>", "<h1>Wiki Index</h1>", "<ul>"]

    for topic_key in sorted(data["topics"].keys()):
        entry = data["topics"][topic_key]
        slug = _slug(topic_key)
        title = _html_escape(entry.get("title", topic_key))
        index_lines.append(f'<li><a href="{slug}">{title}</a></li>')

    index_lines.extend(["</ul>", "</body>", "</html>"])
    index_html = "\n".join(index_lines)

    index_path = site_dir / "index.html"
    tmp_fd, tmp_path = tempfile.mkstemp(dir=site_dir, suffix=".html", text=True)
    try:
        os.write(tmp_fd, index_html.encode("utf-8"))
        os.close(tmp_fd)
        os.replace(tmp_path, index_path)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return {
        "ok": True,
        "pages": pages_written,
        "out": str(site_dir),
        "degraded": not MARKDOWN_AVAILABLE
    }
