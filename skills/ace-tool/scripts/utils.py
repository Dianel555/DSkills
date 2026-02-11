"""Utility functions for ACE-Tool CLI."""

import os
import re
import uuid
from pathlib import Path
from typing import Optional

_SESSION_ID: Optional[str] = None


def load_env():
    """Load environment variables from .env file."""
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ.setdefault(key.strip(), value.strip().strip('"\''))
            break


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
