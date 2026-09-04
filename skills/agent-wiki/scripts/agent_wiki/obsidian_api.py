"""Optional write-through to an open Obsidian vault via the Local REST API plugin.

Used only for ``wiki/index.md`` so a write updates Obsidian's own editor buffer
and disk together, avoiding the "external write vs open-editor-buffer" conflict
that can clobber files an external tool replaces while a tab has them open. When
the API is unconfigured or unreachable, callers fall back to a direct atomic
file write.

Config is read from the environment only, so the API key is never persisted by
agent-wiki:
  AGENT_WIKI_OBSIDIAN_API_KEY  bearer token (Obsidian → Settings → Local REST API)
  AGENT_WIKI_OBSIDIAN_API_URL  base URL, default https://127.0.0.1:27124
"""

from __future__ import annotations

import http.client
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "https://127.0.0.1:27124"
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
# available()/put_file() must never raise: any transport failure becomes False so
# the caller can fall back. http.client.HTTPException (e.g. BadStatusLine) is not
# an OSError subclass, so it is listed explicitly.
_TRANSPORT_ERRORS = (urllib.error.URLError, http.client.HTTPException, OSError, ValueError)


def _config() -> tuple[str, str] | None:
    key = os.getenv("AGENT_WIKI_OBSIDIAN_API_KEY", "").strip()
    if not key:
        return None
    url = os.getenv("AGENT_WIKI_OBSIDIAN_API_URL", "").strip().rstrip("/") or DEFAULT_URL
    return key, url


def _context(url: str) -> ssl.SSLContext | None:
    # The plugin's HTTPS server uses a self-signed cert; skip verification only
    # for loopback hosts, where there is no meaningful MITM surface.
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        return None
    return ssl._create_unverified_context() if parsed.hostname in _LOCAL_HOSTS else None


def available(timeout: float = 2.0) -> bool:
    """True when the API is configured, reachable, and the key is accepted."""
    cfg = _config()
    if cfg is None:
        return False
    key, url = cfg
    req = urllib.request.Request(url + "/", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_context(url)) as resp:
            return bool(200 <= resp.status < 300)
    except _TRANSPORT_ERRORS:
        return False


def put_file(vault_rel_path: str, text: str, timeout: float = 10.0) -> bool:
    """Create-or-replace a whole note at an Obsidian-vault-root-relative path.
    Returns True on a 2xx response; any error returns False so the caller can
    fall back to a direct file write."""
    cfg = _config()
    if cfg is None:
        return False
    key, url = cfg
    target = url + "/vault/" + urllib.parse.quote(vault_rel_path)
    req = urllib.request.Request(
        target,
        data=text.encode("utf-8"),
        method="PUT",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "text/markdown; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_context(url)) as resp:
            return bool(200 <= resp.status < 300)
    except _TRANSPORT_ERRORS:
        return False
