"""ACE-Tool CLI package."""

from .client import AceToolClient
from .indexer import Indexer
from .utils import detect_and_read, get_session_id, is_chinese_text, load_env, parse_chat_history, sanitize_content
from .web_ui import run_interactive_enhance

# Auto-load environment variables on import. Client/indexer/web_ui only read env
# in methods, not at import time, so this can sit after the imports.
load_env()

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
