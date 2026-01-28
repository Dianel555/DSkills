"""Symbol tools wrapper - re-exports from serena-agent."""

try:
    from serena.tools.symbol_tools import (
        FindSymbolTool,
        GetSymbolsOverviewTool,
        FindReferencingSymbolsTool,
        ReplaceSymbolBodyTool,
        InsertAfterSymbolTool,
        InsertBeforeSymbolTool,
        RenameSymbolTool,
    )
    __all__ = [
        "FindSymbolTool",
        "GetSymbolsOverviewTool",
        "FindReferencingSymbolsTool",
        "ReplaceSymbolBodyTool",
        "InsertAfterSymbolTool",
        "InsertBeforeSymbolTool",
        "RenameSymbolTool",
    ]
except ImportError:
    __all__ = []
