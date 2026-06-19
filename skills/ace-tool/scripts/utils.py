"""Utility functions for ACE-Tool CLI."""

import os
import re
import uuid
from pathlib import Path
from typing import Optional

_SESSION_ID: Optional[str] = None


def load_env():
    """Load environment variables from the skill root .env file."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    value = value.strip()
                    # Strip inline comments (unquoted # preceded by whitespace)
                    if value and value[0] not in ('"', "'"):
                        value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
                    else:
                        value = value.strip('"\'')
                    os.environ.setdefault(key.strip(), value)


def get_session_id() -> str:
    """Get or create persistent session ID."""
    global _SESSION_ID
    if _SESSION_ID is None:
        _SESSION_ID = str(uuid.uuid4())
    return _SESSION_ID


def is_chinese_text(text: str) -> bool:
    """Detect if text is primarily Chinese."""
    chinese_chars = re.findall(r"[\u4e00-\u9fa5]", text)
    if not chinese_chars:
        return False
    if len(chinese_chars) >= 3:
        return True
    non_ws = len([c for c in text if not c.isspace()])
    return non_ws > 0 and len(chinese_chars) / non_ws >= 0.1


def parse_chat_history(conversation_history: str) -> list[dict]:
    """Parse conversation history into ChatMessage format."""
    messages = []
    current_role = None
    current_lines = []

    user_prefixes = ["User:", "用户:"]
    assistant_prefixes = ["AI:", "Assistant:", "助手:"]

    for line in conversation_history.split("\n"):
        trimmed = line.strip()
        if not trimmed:
            if current_role:
                current_lines.append("")
            continue

        role_found = None
        content = None
        for prefix in user_prefixes:
            if trimmed.startswith(prefix):
                role_found = "user"
                content = trimmed[len(prefix):].strip()
                break
        if not role_found:
            for prefix in assistant_prefixes:
                if trimmed.startswith(prefix):
                    role_found = "assistant"
                    content = trimmed[len(prefix):].strip()
                    break

        if role_found:
            if current_role:
                messages.append({"role": current_role, "content": "\n".join(current_lines)})
            current_role = role_found
            current_lines = [content]
        elif current_role:
            current_lines.append(line)

    if current_role:
        messages.append({"role": current_role, "content": "\n".join(current_lines)})

    return messages


def detect_and_read(file_path: Path, encoding_chain: list[str]) -> Optional[str]:
    """Try multiple encodings to read a file. Returns None for binary/unreadable."""
    try:
        raw = file_path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8192]:
        return None
    for enc in encoding_chain:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def sanitize_content(content: str) -> str:
    """Normalize line endings and remove null bytes."""
    return content.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")


def _validate_session_data(data: dict) -> tuple[Optional[str], Optional[str]]:
    """Validate and extract session data fields.

    Returns (tenant_url, access_token) or (None, None) if invalid.
    """
    if not isinstance(data, dict):
        return None, None
    access_token = data.get("accessToken", "")
    tenant_url = data.get("tenantURL", "")
    if (isinstance(access_token, str) and access_token.strip() and
        isinstance(tenant_url, str) and tenant_url.strip()):
        return tenant_url.rstrip("/"), access_token
    return None, None


def load_session_auth() -> tuple[Optional[str], Optional[str], str]:
    """Load authentication from session.json, AUGMENT_SESSION_AUTH, or legacy env vars.

    Returns:
        (base_url, token, source) where source is one of:
        - "session.json"
        - "AUGMENT_SESSION_AUTH"
        - "ACE_API_TOKEN"
        - "none"
    """
    import json
    import logging

    log = logging.getLogger(__name__)

    # Try session.json first
    session_path = Path.home() / ".augment" / "session.json"
    if session_path.exists():
        try:
            content = session_path.read_text(encoding="utf-8-sig")
            data = json.loads(content)
            tenant_url, access_token = _validate_session_data(data)
            if tenant_url and access_token:
                log.debug("Auth source: session.json")
                return tenant_url, access_token, "session.json"
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            log.debug("Failed to load session.json: %s", e)

    # Try AUGMENT_SESSION_AUTH env var
    env_session = os.getenv("AUGMENT_SESSION_AUTH", "")
    if env_session:
        try:
            data = json.loads(env_session)
            tenant_url, access_token = _validate_session_data(data)
            if tenant_url and access_token:
                log.debug("Auth source: AUGMENT_SESSION_AUTH")
                return tenant_url, access_token, "AUGMENT_SESSION_AUTH"
        except (json.JSONDecodeError, TypeError) as e:
            log.debug("Failed to parse AUGMENT_SESSION_AUTH: %s", e)

    # Fallback to legacy env vars
    legacy_url = os.getenv("ACE_API_URL", "").rstrip("/")
    legacy_token = os.getenv("ACE_API_TOKEN", "")
    if legacy_url or legacy_token:
        log.debug("Auth source: ACE_API_TOKEN (legacy)")
        return legacy_url or None, legacy_token or None, "ACE_API_TOKEN"

    log.debug("Auth source: none")
    return None, None, "none"
