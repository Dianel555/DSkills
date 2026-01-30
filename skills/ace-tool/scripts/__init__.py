"""ACE-Tool CLI package."""

from .utils import load_env, get_session_id, is_chinese_text, parse_chat_history

# Auto-load environment variables on import
load_env()

from .client import AceToolClient
from .web_ui import run_interactive_enhance

__all__ = [
    "AceToolClient",
    "load_env",
    "get_session_id",
    "is_chinese_text",
    "parse_chat_history",
    "run_interactive_enhance",
]
