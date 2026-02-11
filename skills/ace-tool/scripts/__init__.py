"""ACE-Tool CLI package."""

from .utils import load_env, get_session_id, is_chinese_text, parse_chat_history, detect_and_read, sanitize_content

# Auto-load environment variables on import
load_env()

from .client import AceToolClient
from .indexer import Indexer
from .web_ui import run_interactive_enhance

__all__ = [
    "AceToolClient",
    "Indexer",
    "load_env",
    "get_session_id",
    "is_chinese_text",
    "parse_chat_history",
    "detect_and_read",
    "sanitize_content",
    "run_interactive_enhance",
]
