"""Optional write-through to an open Obsidian vault via the Local REST API plugin.

Used only for ``wiki/index.md`` when the installed plugin exposes a document-map
version and conditional root PATCH semantics. An existing note is written only
with that compare-and-swap contract; plugins without it are rejected rather than
falling back to an unconditional overwrite. When the API is unavailable, callers
use atomic writes.

Config is read from the environment only, so the API key is never persisted by
agent-wiki:
  AGENT_WIKI_OBSIDIAN_API_KEY       bearer token (Obsidian → Settings → Local REST API)
  AGENT_WIKI_OBSIDIAN_API_URL       base URL, default https://127.0.0.1:27124
  AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH vault-relative marker path (bootstrapped by gen-home)
  AGENT_WIKI_OBSIDIAN_VAULT_ID      exact marker content (bootstrapped by gen-home)
"""

from __future__ import annotations

import http.client
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "https://127.0.0.1:27124"
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
# Transport failures become False for availability and unconditional PUTs;
# conditional writes raise a safety error instead of permitting a disk fallback.
# http.client.HTTPException (e.g. BadStatusLine) is not an OSError subclass, so it
# is listed explicitly.
_TRANSPORT_ERRORS = (urllib.error.URLError, http.client.HTTPException, OSError, ValueError)


class WriteSafetyError(RuntimeError):
    """A REST write was not safe to complete or to fall back locally."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class TargetVerificationError(WriteSafetyError):
    pass


class VaultIdentitySetupRequiredError(WriteSafetyError):
    def __init__(self, environment: dict[str, str], marker_file: str) -> None:
        self.environment = environment
        self.marker_file = marker_file
        super().__init__("obsidian_vault_identity_setup_required")


class WriteConflictError(WriteSafetyError):
    pass


def _config() -> tuple[str, str] | None:
    key = os.getenv("AGENT_WIKI_OBSIDIAN_API_KEY", "").strip()
    if not key:
        return None
    url = os.getenv("AGENT_WIKI_OBSIDIAN_API_URL", "").strip().rstrip("/") or DEFAULT_URL
    return key, url


def configured() -> bool:
    """Whether REST is enabled by environment configuration."""
    return _config() is not None


def identity_configured() -> bool:
    """Whether a valid vault marker path and expected value are configured."""
    return _identity_config() is not None


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
    req = urllib.request.Request(
        url + "/", headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_context(url)) as resp:
            if not 200 <= resp.status < 300:
                return False
            payload = json.loads(resp.read().decode("utf-8"))
    except _TRANSPORT_ERRORS + (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("authenticated") is True


def _target_url(url: str, vault_rel_path: str) -> str:
    return url + "/vault/" + urllib.parse.quote(vault_rel_path, safe="/")


def _same_path(actual: object, expected: str) -> bool:
    if not isinstance(actual, str):
        return False
    actual_path = urllib.parse.unquote(actual).replace("\\", "/").lstrip("/")
    expected_path = expected.replace("\\", "/").lstrip("/")
    return actual_path == expected_path


def _identity_config() -> tuple[str, str] | None:
    marker_path = os.getenv("AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH", "").strip()
    marker_value = os.getenv("AGENT_WIKI_OBSIDIAN_VAULT_ID", "").strip()
    normalized = marker_path.replace("\\", "/")
    if (
        not marker_path
        or not marker_value
        or normalized.startswith("/")
        or ".." in normalized.split("/")
    ):
        return None
    return normalized, marker_value


def require_vault_identity_configured() -> None:
    """Reject an enabled REST write before probing an unbound API endpoint."""
    if _identity_config() is None:
        raise TargetVerificationError("obsidian_vault_identity_required")


def _verify_vault_identity(timeout: float) -> None:
    identity = _identity_config()
    if identity is None:
        raise TargetVerificationError("obsidian_vault_identity_required")
    marker_path, expected_value = identity
    marker = read_file(marker_path, timeout=timeout)
    if not _same_path(marker.get("path"), marker_path) or marker.get("content") != expected_value:
        raise TargetVerificationError("obsidian_vault_identity_mismatch")


def _read_json(vault_rel_path: str, accept: str, timeout: float) -> object:
    cfg = _config()
    if cfg is None:
        raise TargetVerificationError("obsidian_api_not_configured")
    key, url = cfg
    req = urllib.request.Request(
        _target_url(url, vault_rel_path),
        headers={"Authorization": f"Bearer {key}", "Accept": accept},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_context(url)) as resp:
            if not 200 <= resp.status < 300:
                raise TargetVerificationError("obsidian_target_unreadable")
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise TargetVerificationError("obsidian_target_unreadable") from exc
    except _TRANSPORT_ERRORS as exc:
        raise TargetVerificationError("obsidian_target_unreadable") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TargetVerificationError("obsidian_target_unreadable") from exc


def read_file(vault_rel_path: str, timeout: float = 5.0) -> dict[str, object]:
    """Read note metadata/content and require a JSON document response."""
    payload = _read_json(vault_rel_path, "application/vnd.olrapi.note+json", timeout)
    if not isinstance(payload, dict):
        raise TargetVerificationError("obsidian_target_unreadable")
    return payload


def read_document_map(vault_rel_path: str, timeout: float = 5.0) -> dict[str, object]:
    """Read the REST API document map and require its concurrency token."""
    payload = _read_json(vault_rel_path, "application/vnd.olrapi.document-map+json", timeout)
    if not isinstance(payload, dict):
        raise TargetVerificationError("obsidian_target_unreadable")
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        raise TargetVerificationError("obsidian_conditional_write_unsupported")
    return payload


def put_file(
    vault_rel_path: str,
    text: str,
    timeout: float = 10.0,
    *,
    expected_content: str | None = None,
) -> bool:
    """Create-or-replace a note, optionally with a conditional root PATCH.

    With ``expected_content`` set, a missing/unknown target or changed remote
    content raises instead of allowing a local fallback to overwrite it.
    """
    cfg = _config()
    if cfg is None:
        return False
    key, url = cfg
    if expected_content is not None:
        # The API exposes only vault-relative paths, so verify an explicit
        # per-vault marker before trusting the target and its version.
        read_timeout = min(timeout, 5.0)
        _verify_vault_identity(read_timeout)
        # Capture the version before the content check. Any edit before the
        # check is rejected by that check; any edit after it makes PATCH fail.
        document_map = read_document_map(vault_rel_path, timeout=read_timeout)
        document = read_file(vault_rel_path, timeout=min(timeout, 5.0))
        if not _same_path(document.get("path"), vault_rel_path):
            raise TargetVerificationError("obsidian_target_mismatch")
        remote_content = document.get("content")
        if not isinstance(remote_content, str):
            raise TargetVerificationError("obsidian_target_unreadable")
        if remote_content != expected_content:
            raise WriteConflictError("obsidian_write_conflict")
        data = json.dumps(
            {
                "targetType": "heading",
                "target": None,
                "operation": "replace",
                "content": text,
                "ifMatch": document_map["version"],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        method = "PATCH"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    else:
        data = text.encode("utf-8")
        method = "PUT"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "text/markdown; charset=utf-8"}
    req = urllib.request.Request(
        _target_url(url, vault_rel_path), data=data, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_context(url)) as resp:
            return bool(200 <= resp.status < 300)
    except urllib.error.HTTPError as exc:
        if exc.code == 412:
            raise WriteConflictError("obsidian_write_conflict") from exc
        return False
    except _TRANSPORT_ERRORS:
        return False
