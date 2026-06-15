"""Deterministic static HTML site export (optional) — Editorial Atlas design.

Renders a self-contained static site under ``wiki/site/`` from the retrieval
index and topic bodies. Requires the optional ``markdown`` package; degrades
gracefully to escaped plaintext when absent. All styling and interactivity are
inline static literals so each page is self-contained and byte-deterministic.
"""

from __future__ import annotations

import hashlib
import html
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

# Per-type accent cycle (D4/D10), assigned deterministically by sorted type.
_TYPE_ACCENTS = ["--cinnabar", "--night", "--jade", "--amber", "--violet", "--green"]

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_CODESPAN_RE = re.compile(r"(`+)(.+?)\1")
_WIKILINK_RE = re.compile(r"!?\[\[([^\[\]]+?)\]\]")
_HEADING_RE = re.compile(r"<h([23])>(.*?)</h\1>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", str(s))


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _sanitize_filename(stem: str) -> str:
    """Sanitize stem for filesystem: replace unsafe chars with underscore, preserve CJK."""
    unsafe_pattern = r'[/\\:*?"<>|\x00-\x1f\x7f]|\s+'
    return re.sub(unsafe_pattern, '_', stem)


def _slug(topic_key: str) -> str:
    """Generate deterministic injective filename: sanitize(stem)-sha256[:8].html"""
    stem = topic_key[:-3] if topic_key.endswith(".md") else topic_key
    sanitized = _sanitize_filename(stem)
    key_hash = hashlib.sha256(_nfc(topic_key).encode("utf-8")).hexdigest()[:8]
    return f"{sanitized}-{key_hash}.html"


# --- Inline design system (D4) -------------------------------------------------

_STYLE = """
:root{
--radius-sm:6px;--radius:12px;--radius-lg:18px;--pill:999px;
--s1:4px;--s2:8px;--s3:16px;--s4:24px;--s5:36px;
--font-serif:"Noto Serif SC","Songti SC","STSong",Georgia,serif;
--font-ui:"Noto Sans SC",-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
--font-mono:"SFMono-Regular",ui-monospace,Menlo,Consolas,monospace;
--bg:#F4EFE4;--surface:#FFFDF7;--surface-2:#F8F1E4;--vellum:#E9DDC9;--mist:#ECE5D8;
--ink:#241F1A;--muted:#6F6559;--faint:#9B8F7E;--rule:#D8CDBB;--line:#CFC4B1;
--cinnabar:#8B2E24;--cinnabar-2:#A23B2A;--jade:#4B7564;--green:#3E6B4B;--night:#315F72;--amber:#B7791F;--violet:#6F557F;
--shadow:0 18px 36px rgba(36,31,26,.11);
}
[data-theme="mo-ye"]{
--bg:#0D0F0E;--surface:#181A18;--surface-2:#21231F;--vellum:#2C2D28;--mist:#20241F;
--ink:#F5F0E6;--muted:#C6BBAB;--faint:#8F8677;--rule:#3B3932;--line:#8E8778;
--cinnabar:#E45D4A;--cinnabar-2:#FF8066;--jade:#8AB6A2;--green:#8BAE78;--night:#A9BFCB;--amber:#E0B35E;--violet:#C1A8D5;
--shadow:0 22px 44px rgba(0,0,0,.48);
}
[data-theme="hu-yan"]{
--bg:#EFE6D2;--surface:#F7EFDD;--surface-2:#EDE2C9;--vellum:#E2D4B8;--mist:#E8DCC4;
--ink:#3B3024;--muted:#6B5D45;--faint:#8A7B60;--rule:#D8C7A4;--line:#CDBB95;
--cinnabar:#9C3B2E;--cinnabar-2:#B0473A;--jade:#436B54;--green:#3C6447;--night:#2E5868;--amber:#9A6A1C;--violet:#645074;
--shadow:0 14px 30px rgba(59,48,36,.10);
}
*{box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{
margin:0;font-family:var(--font-ui);font-size:14px;line-height:1.65;color:var(--ink);
background-color:var(--bg);
background-image:radial-gradient(120% 70% at 50% -10%,rgba(255,255,255,.16),rgba(255,255,255,0) 60%),repeating-linear-gradient(0deg,rgba(120,100,70,.022) 0 1px,rgba(120,100,70,0) 1px 4px);
background-attachment:fixed;
}
a{color:var(--cinnabar);text-decoration:underline;text-underline-offset:2px;}
h1,h2,h3,h4{font-family:var(--font-serif);line-height:1.3;color:var(--ink);}
:focus-visible{outline:2px solid var(--cinnabar);outline-offset:2px;border-radius:var(--radius-sm);}
.muted{color:var(--muted);}
.star{color:var(--amber);}
.skip-link{position:absolute;left:-9999px;top:0;z-index:20;display:inline-flex;align-items:center;min-height:44px;padding:0 16px;background:var(--cinnabar);color:#fff;border-radius:var(--radius-sm);text-decoration:none;}
.skip-link:focus{left:var(--s2);top:var(--s2);}
.band{display:flex;align-items:center;gap:var(--s3);flex-wrap:wrap;max-width:1320px;margin:0 auto;padding:var(--s4);border-bottom:1px solid var(--rule);background:var(--surface);}
.seal{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:var(--radius-sm);background:var(--cinnabar);color:var(--surface);font-family:var(--font-serif);font-size:20px;box-shadow:var(--shadow);}
.band__title{font-size:22px;font-weight:700;margin:0;flex:0 1 auto;}
.search{flex:1 1 200px;min-width:160px;min-height:44px;padding:8px 14px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--surface-2);color:var(--ink);font-family:var(--font-ui);font-size:16px;}
.search::placeholder{color:var(--muted);}
.theme-toggle{min-height:44px;min-width:44px;padding:0 16px;border:1px solid var(--line);border-radius:var(--pill);background:var(--surface-2);color:var(--ink);font-family:var(--font-ui);font-size:13px;cursor:pointer;}
.theme-toggle:hover{border-color:var(--cinnabar);}
.layout{display:grid;gap:var(--s4);max-width:1320px;margin:0 auto;padding:var(--s4);}
.zone{min-width:0;}
.collapse>summary{min-height:44px;display:flex;align-items:center;cursor:pointer;font-family:var(--font-serif);font-weight:700;color:var(--ink);list-style:none;padding:var(--s1) 0;border-bottom:1px solid var(--rule);}
.collapse>summary::-webkit-details-marker{display:none;}
.article{max-width:72ch;margin:0 auto;}
.article h1{font-size:28px;margin:.2em 0 .6em;}
.article h2{font-size:20px;margin:1.4em 0 .5em;padding-bottom:.2em;border-bottom:1px solid var(--rule);}
.article h3{font-size:16px;margin:1.2em 0 .4em;}
.article img{max-width:100%;height:auto;display:block;margin:1.5em auto;border-radius:var(--radius-sm);}
.article pre,.article table{overflow-x:auto;max-width:100%;}
.article code{font-family:var(--font-mono);font-size:.92em;background:var(--surface-2);border:1px solid var(--rule);border-radius:var(--radius-sm);padding:1px 5px;}
.article pre{background:var(--surface-2);border:1px solid var(--rule);border-radius:var(--radius);padding:var(--s3);}
.article pre code{background:none;border:0;padding:0;}
.article table{border-collapse:collapse;width:100%;}
.article th,.article td{border:1px solid var(--rule);padding:6px 10px;text-align:left;}
.article th{background:var(--surface-2);}
.article tbody tr:nth-child(even){background:var(--mist);}
.article blockquote{margin:1em 0;padding:var(--s2) var(--s3);background:var(--surface-2);border-left:3px solid var(--cinnabar);border-radius:0 var(--radius-sm) var(--radius-sm) 0;color:var(--ink);}
.wikilink{color:var(--cinnabar);text-underline-offset:2px;}
.wikilink--missing{color:var(--muted);text-decoration:underline dashed;cursor:default;}
.toc{list-style:none;margin:var(--s2) 0 0;padding:0;font-size:13px;}
.toc__item{margin:2px 0;}
.toc__item--h3{padding-left:var(--s3);}
.toc__link{display:block;padding:3px var(--s2);color:var(--muted);text-decoration:none;border-left:2px solid transparent;}
.toc__link:hover{color:var(--ink);}
.toc__link--active{color:var(--cinnabar);border-left-color:var(--cinnabar);background:var(--surface-2);}
.infobox{font-size:13px;margin-top:var(--s2);}
.info-row{display:grid;grid-template-columns:84px 1fr;gap:var(--s2);padding:6px 0;border-bottom:1px solid var(--rule);}
.info-label{color:var(--muted);}
.info-value{color:var(--ink);word-break:break-word;}
.chip{display:inline-flex;align-items:center;gap:6px;padding:1px 10px;border-radius:var(--pill);background:var(--vellum);color:var(--ink);border:1px solid var(--rule);font-size:12px;}
.chip-dot{width:8px;height:8px;border-radius:50%;background:var(--dot,var(--faint));}
.badge{display:inline-block;padding:1px 10px;border-radius:var(--pill);font-size:12px;font-weight:600;color:#14110D;}
.badge--premium{background:var(--cinnabar);color:#FFFDF7;}
.badge--rich{background:var(--green);color:#FFFDF7;}
.badge--standard{background:var(--night);color:#FFFDF7;}
.badge--basic{background:var(--amber);}
.badge--stub{background:var(--faint);}
[data-theme="mo-ye"] .badge--premium,[data-theme="mo-ye"] .badge--rich,[data-theme="mo-ye"] .badge--standard{color:#14110D;}
[data-theme="hu-yan"] .badge--basic{color:#FFFDF7;}
.kw{display:inline-block;margin:0 4px 4px 0;padding:0 8px;border-radius:var(--pill);background:var(--mist);color:var(--ink);border:1px solid var(--rule);font-size:12px;}
.index-main{max-width:1320px;margin:0 auto;padding:var(--s4);}
.section__title{display:flex;align-items:center;gap:var(--s2);font-size:18px;margin:var(--s5) 0 var(--s3);}
.type-dot{width:10px;height:10px;border-radius:50%;background:var(--dot,var(--faint));}
.featured .section__title{color:var(--cinnabar);}
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:var(--s3);}
.card{display:flex;flex-direction:column;gap:var(--s2);padding:var(--s3);background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);color:inherit;text-decoration:none;transition:transform .15s,border-color .15s,box-shadow .15s;}
.card:hover{transform:translateY(-1px);border-color:var(--cinnabar);box-shadow:var(--shadow);}
.card__meta{display:flex;align-items:center;gap:var(--s2);flex-wrap:wrap;}
.card__title{font-size:16px;margin:0;}
.card__summary{margin:0;color:var(--muted);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}
.card__backlinks{font-size:12px;color:var(--muted);margin-top:auto;}
.is-hidden{display:none!important;}
.search-empty{padding:var(--s5) 0;text-align:center;color:var(--muted);}
.foot{display:flex;align-items:center;justify-content:space-between;gap:var(--s3);flex-wrap:wrap;max-width:1320px;margin:0 auto;padding:var(--s4);border-top:1px solid var(--rule);color:var(--muted);font-size:12px;}
.legend{display:flex;gap:var(--s2);flex-wrap:wrap;align-items:center;}
@media(min-width:1100px){
.layout{grid-template-columns:minmax(220px,260px) minmax(0,1fr) minmax(260px,320px);align-items:start;}
.zone--nav,.zone--aside{position:sticky;top:var(--s4);max-height:calc(100vh - 2*var(--s4));overflow:auto;}
}
@media(min-width:768px) and (max-width:1099px){
.layout{grid-template-columns:minmax(0,1fr) minmax(240px,300px);}
.zone--nav{grid-column:1 / -1;}
}
@media(max-width:767px){.layout{grid-template-columns:1fr;}}
@media(prefers-reduced-motion:reduce){
html{scroll-behavior:auto;}
*{transition:none!important;animation:none!important;}
.card:hover{transform:none;}
}
""".strip()

# Early synchronous theme bootstrap (before first paint, no FOUC) — static literal.
_HEAD_SCRIPT = (
    "<script>(function(){try{var t=localStorage.getItem('agentwiki-theme');"
    "if(!t){t=matchMedia('(prefers-color-scheme: dark)').matches?'mo-ye':'shan-shui';}"
    "document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>"
)

# Body interactivity (theme cycle / scroll-spy / search / collapse) — static literal.
_BODY_SCRIPT = (
    "(function(){"
    "var root=document.documentElement;var ORDER=['shan-shui','hu-yan','mo-ye'];"
    "var btn=document.querySelector('[data-theme-toggle]');"
    "if(btn){btn.addEventListener('click',function(){"
    "var cur=root.getAttribute('data-theme')||'shan-shui';"
    "var next=ORDER[(ORDER.indexOf(cur)+1)%ORDER.length];"
    "root.setAttribute('data-theme',next);"
    "try{localStorage.setItem('agentwiki-theme',next);}catch(e){}});}"
    "var reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;"
    "var toc=document.querySelector('[data-toc]');"
    "if(toc){var links=[].slice.call(toc.querySelectorAll('a[href^=\"#\"]'));var map={};"
    "links.forEach(function(a){var id=a.getAttribute('href').slice(1);map[id]=a;"
    "a.addEventListener('click',function(e){var el=document.getElementById(id);"
    "if(el){e.preventDefault();el.scrollIntoView({behavior:reduce?'auto':'smooth'});"
    "history.replaceState(null,'','#'+id);}});});"
    "var heads=[].slice.call(document.querySelectorAll('#main-article h2[id],#main-article h3[id]'));"
    "if(window.IntersectionObserver&&heads.length){var vis={};"
    "var obs=new IntersectionObserver(function(es){"
    "es.forEach(function(en){vis[en.target.id]=en.isIntersecting;});"
    "var top='';for(var i=0;i<heads.length;i++){if(vis[heads[i].id]){top=heads[i].id;break;}}"
    "links.forEach(function(a){a.classList.remove('toc__link--active');a.removeAttribute('aria-current');});"
    "if(top&&map[top]){map[top].classList.add('toc__link--active');map[top].setAttribute('aria-current','true');}},"
    "{rootMargin:'0px 0px -70% 0px'});heads.forEach(function(h){obs.observe(h);});}}"
    "var search=document.getElementById('search');"
    "if(search){var cards=[].slice.call(document.querySelectorAll('[data-search]'));"
    "var sections=[].slice.call(document.querySelectorAll('.type-section,.featured'));"
    "var empty=document.getElementById('search-empty');"
    "search.addEventListener('input',function(){var q=search.value.toLowerCase().trim(),ws=q?q.split(/\\s+/):[];var any=false;"
    "cards.forEach(function(c){var s=c.getAttribute('data-search'),hit=ws.every(function(w){return s.indexOf(w)>=0;});"
    "c.classList.toggle('is-hidden',!hit);if(hit)any=true;});"
    "sections.forEach(function(s){var on=s.querySelectorAll('[data-search]:not(.is-hidden)').length>0;"
    "s.classList.toggle('is-hidden',!on);});if(empty){empty.hidden=any;}});}"
    "function sync(){var w=window.innerWidth;"
    "[].slice.call(document.querySelectorAll('details[data-collapse]')).forEach(function(d){"
    "var bp=parseInt(d.getAttribute('data-collapse'),10);d.open=w>=bp;});}"
    "sync();window.addEventListener('resize',sync);"
    "})();"
)

_TIERS = ("premium", "rich", "standard", "basic", "stub")


# --- Content rendering (D8/D9) -------------------------------------------------

def _resolve_target(target: str, topic_keys: set[str], alias_index: dict) -> str | None:
    """Resolve a wikilink target to a slug: exact key -> Target.md -> alias_index."""
    if target in topic_keys:
        return _slug(target)
    key = target + ".md"
    if key in topic_keys:
        return _slug(key)
    if target in alias_index:
        return _slug(alias_index[target])
    return None


def _convert_links(text: str, topic_keys: set[str], alias_index: dict) -> str:
    """Replace `[[...]]` outside code with escaped anchors/inert spans."""
    def repl(m: re.Match) -> str:
        raw = m.group(1)
        if "|" in raw:
            target_spec, label = raw.split("|", 1)
            label = _nfc(label.strip())
        else:
            target_spec, label = raw, None
        target = target_spec
        for sep in ("#", "^"):
            target = target.split(sep, 1)[0]
        target = _nfc(target.strip())
        if label is None:
            label = target
        slug = _resolve_target(target, topic_keys, alias_index)
        if slug:
            return f'<a class="wikilink" href="{_esc(slug)}">{_esc(label)}</a>'
        return f'<span class="wikilink wikilink--missing">{_esc(label)}</span>'
    return _WIKILINK_RE.sub(repl, text)


def _convert_inline(line: str, topic_keys: set[str], alias_index: dict) -> str:
    """Convert wikilinks on a line, leaving inline code spans untouched."""
    parts = []
    pos = 0
    for m in _CODESPAN_RE.finditer(line):
        parts.append(_convert_links(line[pos:m.start()], topic_keys, alias_index))
        parts.append(m.group(0))
        pos = m.end()
    parts.append(_convert_links(line[pos:], topic_keys, alias_index))
    return "".join(parts)


def _resolve_wikilinks(body: str, topic_keys: set[str], alias_index: dict) -> str:
    """Pre-pass over raw markdown: convert wikilinks outside fenced blocks and code spans."""
    out = []
    in_fence = False
    fence = ""
    for line in body.split("\n"):
        m = _FENCE_RE.match(line)
        if in_fence:
            out.append(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                in_fence = False
                fence = ""
            continue
        if m:
            in_fence = True
            fence = m.group(1)
            out.append(line)
            continue
        out.append(_convert_inline(line, topic_keys, alias_index))
    return "\n".join(out)


def _add_heading_ids(html_body: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Post-pass: give h2/h3 deterministic collision-suffixed ids; return (html, toc)."""
    seen: dict[str, int] = {}
    toc: list[tuple[str, str, str]] = []

    def repl(m: re.Match) -> str:
        level, inner = m.group(1), m.group(2)
        label = _TAG_RE.sub("", inner).strip()
        base = "h-" + _sanitize_filename(_nfc(label)).lower()
        n = seen.get(base, 0) + 1
        seen[base] = n
        hid = base if n == 1 else f"{base}-{n}"
        toc.append((level, hid, label))
        return f'<h{level} id="{_esc(hid)}">{inner}</h{level}>'

    return _HEADING_RE.sub(repl, html_body), toc


def _render_body_and_toc(body: str, topic_keys: set[str], alias_index: dict):
    """Render a topic body to HTML + TOC, or escaped plaintext fallback (degraded)."""
    if MARKDOWN_AVAILABLE:
        pre = _resolve_wikilinks(body, topic_keys, alias_index)
        rendered = markdown_lib.markdown(
            pre, extensions=["fenced_code", "tables"], output_format="html"
        )
        return _add_heading_ids(rendered)
    return f"<pre>{html.escape(body)}</pre>", []


def _render_toc(toc: list[tuple[str, str, str]]) -> str:
    if not toc:
        return ""
    items = []
    for level, hid, label in toc:
        cls = "toc__item toc__item--h3" if level == "3" else "toc__item"
        items.append(f'<li class="{cls}"><a class="toc__link" href="#{_esc(hid)}">{label}</a></li>')
    return '<ul class="toc" data-toc>' + "".join(items) + "</ul>"


# --- Components ----------------------------------------------------------------

def _chip(type_str: str, type_accent: dict) -> str:
    accent = type_accent.get(_nfc(type_str), "--faint")
    return (f'<span class="chip"><span class="chip-dot" style="--dot:var({accent})"></span>'
            f'{_esc(type_str)}</span>')


def _render_infobox(entry: dict, type_accent: dict) -> str:
    rows = []

    def row(label: str, value_html: str) -> None:
        rows.append(f'<div class="info-row"><span class="info-label">{label}</span>'
                    f'<span class="info-value">{value_html}</span></div>')

    row("Title", _esc(entry.get("title", "")))
    type_str = entry.get("type", "")
    if type_str:
        row("Type", _chip(type_str, type_accent))
    tier = entry.get("quality_tier", "")
    if tier:
        row("Quality", f'<span class="badge badge--{_esc(tier)}">{_esc(tier)}</span>')
    if entry.get("featured"):
        row("Featured", '<span class="star">⭐</span>')
    row("Backlinks", str(entry.get("backlinks", 0)))
    sources = entry.get("sources") or []
    if sources:
        row("Sources", " ".join(f'<a href="{_esc(s)}">{_esc(s)}</a>' for s in sources))
    authors = entry.get("authors") or []
    if authors:
        row("Authors", _esc(", ".join(authors)))
    ys, ye = entry.get("year_start"), entry.get("year_end")
    if ys or ye:
        yr = f"{ys}–{ye}" if (ys and ye and ys != ye) else str(ys or ye)
        row("Year", _esc(yr))
    keywords = entry.get("keywords") or []
    if keywords:
        row("Keywords", " ".join(f'<span class="kw">{_esc(k)}</span>' for k in keywords))
    return "".join(rows)


def _card(key: str, entry: dict, type_accent: dict) -> str:
    title = entry.get("title", "")
    type_str = _nfc(entry.get("type", ""))
    tier = entry.get("quality_tier", "")
    summary = entry.get("summary", "")
    keywords = entry.get("keywords") or []
    backlinks = entry.get("backlinks", 0)
    search_payload = _esc(" ".join([title, *keywords, summary]).lower())
    meta = ""
    if type_str:
        meta += _chip(type_str, type_accent)
    if tier:
        meta += f'<span class="badge badge--{_esc(tier)}">{_esc(tier)}</span>'
    if entry.get("featured"):
        meta += '<span class="star" title="精选">⭐</span>'
    summ = f'<p class="card__summary">{_esc(summary)}</p>' if summary else ""
    backl = f'<span class="card__backlinks">{backlinks} backlinks</span>' if backlinks else ""
    return (f'<a href="{_esc(_slug(key))}" class="card" data-search="{search_payload}">'
            f'<span class="card__meta">{meta}</span>'
            f'<h3 class="card__title">{_esc(title)}</h3>{summ}{backl}</a>')


def _footer(generated_at: str) -> str:
    legend = "".join(f'<span class="badge badge--{t}">{t}</span>' for t in _TIERS)
    return (f'<span class="foot__time">生成于 {_esc(generated_at)}</span>'
            f'<span class="legend" aria-label="质量分级">{legend}</span>')


# --- Page templates ------------------------------------------------------------

def _article_page(title, generated_at, toc_html, body_html, infobox_html) -> str:
    nav_inner = toc_html or '<p class="muted">（无目录）</p>'
    return f"""<!DOCTYPE html>
<html lang="zh" data-theme="shan-shui">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<style>{_STYLE}</style>
{_HEAD_SCRIPT}
</head>
<body>
<a class="skip-link" href="#main-article">跳到正文</a>
<header class="band">
<span class="seal" aria-hidden="true">志</span>
<h1 class="band__title">{_esc(title)}</h1>
<button class="theme-toggle" data-theme-toggle type="button" aria-label="切换主题">☯ 主题</button>
</header>
<div class="layout">
<nav class="zone zone--nav" aria-label="目录">
<details class="collapse" data-collapse="768" open><summary>文献目录</summary>{nav_inner}</details>
</nav>
<main id="main-article" class="zone zone--main">
<article class="article">{body_html}</article>
</main>
<aside class="zone zone--aside" aria-label="批注札记">
<details class="collapse" data-collapse="1100" open><summary>批注札记</summary><div class="infobox">{infobox_html}</div></details>
</aside>
</div>
<footer class="foot">{_footer(generated_at)}</footer>
<script>{_BODY_SCRIPT}</script>
</body>
</html>"""


def _section(label: str, accent_token: str, cards_html: str, kind: str, extra: str = "") -> str:
    dot = f'<span class="type-dot" style="--dot:var({accent_token})"></span>'
    return (f'<section class="{kind}"{extra}>'
            f'<h2 class="section__title">{dot}{_esc(label)}</h2>'
            f'<div class="card-grid">{cards_html}</div></section>')


def _index_page(data: dict, type_accent: dict, generated_at: str) -> str:
    topics = data["topics"]
    items = list(topics.items())

    def by_title(ke):
        return (_nfc(ke[1].get("title", "")), ke[0])

    sections = []
    featured = sorted((ke for ke in items if ke[1].get("featured")), key=by_title)
    if featured:
        cards = "".join(_card(k, e, type_accent) for k, e in featured)
        sections.append(
            '<section class="featured" aria-label="精选">'
            '<h2 class="section__title"><span class="star">⭐</span> 精选</h2>'
            f'<div class="card-grid">{cards}</div></section>'
        )

    groups: dict[str, list] = {}
    for k, e in items:
        groups.setdefault(_nfc(e.get("type", "")), []).append((k, e))
    for t in sorted(x for x in groups if x):
        cards = "".join(_card(k, e, type_accent) for k, e in sorted(groups[t], key=by_title))
        sections.append(_section(t, type_accent.get(t, "--faint"), cards, "type-section"))
    if "" in groups:
        cards = "".join(_card(k, e, type_accent) for k, e in sorted(groups[""], key=by_title))
        sections.append(_section("未分类", "--faint", cards, "type-section"))

    body = "".join(sections)
    return f"""<!DOCTYPE html>
<html lang="zh" data-theme="shan-shui">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>知识舆图</title>
<style>{_STYLE}</style>
{_HEAD_SCRIPT}
</head>
<body>
<a class="skip-link" href="#main-index">跳到正文</a>
<header class="band">
<span class="seal" aria-hidden="true">舆</span>
<h1 class="band__title">知识舆图</h1>
<input type="search" id="search" class="search" placeholder="搜索标题 / 关键词 / 摘要…" aria-label="搜索">
<button class="theme-toggle" data-theme-toggle type="button" aria-label="切换主题">☯ 主题</button>
</header>
<main id="main-index" class="index-main">
{body}
<div id="search-empty" class="search-empty" role="status" hidden>无匹配结果</div>
</main>
<footer class="foot">{_footer(generated_at)}</footer>
<script>{_BODY_SCRIPT}</script>
</body>
</html>"""


# --- Atomic write + orchestration (D11, contract preserved) --------------------

def _atomic_write(site_dir: Path, name: str, content: str) -> None:
    out_path = site_dir / name
    tmp_fd, tmp_path = tempfile.mkstemp(dir=site_dir, suffix=".html")
    try:
        os.write(tmp_fd, content.encode("utf-8"))
        os.close(tmp_fd)
        os.replace(tmp_path, out_path)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def generate_site(vault: str | Path) -> dict:
    """Generate a self-contained static HTML site under wiki/site/.

    Returns ``{"ok": True, "pages": int, "out": str, "degraded": bool}``.
    Raises ``ValueError("wiki_not_initialized")`` if the wiki is absent and
    ``ValueError("site_slug_collision: ...")`` on an impossible slug clash.
    """
    vault = Path(vault)
    wiki_root = config.wiki_root(vault)
    if not wiki_root.exists():
        raise ValueError("wiki_not_initialized")

    data, _ = wiki_index.rebuild(vault)
    topics = data["topics"]
    alias_index = data.get("alias_index", {})
    generated_at = data.get("generated_at", wiki_index.EPOCH)
    topic_keys = set(topics.keys())

    # Injective slug check (no overwrite).
    slug_map: dict[str, str] = {}
    for key in topics:
        slug = _slug(key)
        if slug in slug_map:
            raise ValueError(f"site_slug_collision: {key} and {slug_map[slug]}")
        slug_map[slug] = key

    # Deterministic per-type accent assignment.
    nonempty_types = sorted({_nfc(e.get("type", "")) for e in topics.values() if _nfc(e.get("type", ""))})
    type_accent = {t: _TYPE_ACCENTS[i % len(_TYPE_ACCENTS)] for i, t in enumerate(nonempty_types)}

    site_dir = wiki_root / "site"
    site_dir.mkdir(parents=True, exist_ok=True)
    topics_dir = config.topics_dir(vault)

    pages_written = 0
    for key, entry in topics.items():
        topic_path = topics_dir / key
        if not topic_path.exists():
            continue
        try:
            text = topic_path.read_text(encoding="utf-8-sig")
            _meta, body = frontmatter.parse(text)
        except Exception:
            continue
        body_html, toc = _render_body_and_toc(body, topic_keys, alias_index)
        page = _article_page(
            entry.get("title", key), generated_at,
            _render_toc(toc), body_html, _render_infobox(entry, type_accent),
        )
        _atomic_write(site_dir, _slug(key), page)
        pages_written += 1

    # index.html is written LAST so status.site_stale stays correct.
    _atomic_write(site_dir, "index.html", _index_page(data, type_accent, generated_at))

    return {
        "ok": True,
        "pages": pages_written,
        "out": str(site_dir),
        "degraded": not MARKDOWN_AVAILABLE,
    }
