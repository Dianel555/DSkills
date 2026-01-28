"""Serena Core Wrapper."""

import os
from pathlib import Path
from typing import Any, Optional, List, Dict

try:
    from serena.agent import SerenaAgent, SerenaConfig
    from serena.tools import ToolRegistry
except ImportError:
    raise ImportError("serena-agent is not installed")

class SerenaCore:
    """Wrapper for SerenaAgent providing CLI-friendly interface and context awareness."""

    def __init__(
        self,
        project: Optional[str] = None,
        context: Optional[str] = None,
        modes: Optional[List[str]] = None,
    ):
        self.project_path = Path(project).resolve() if project else Path.cwd()
        self.context = context or self._detect_context(self.project_path)
        self.modes = modes or ["interactive", "editing"]
        self._agent: Optional[SerenaAgent] = None
        self._extended_tools: Dict[str, Any] = {}

    def _detect_context(self, path: Path) -> str:
        """Detect environment context based on file markers."""
        if (path / ".claude").exists() or os.environ.get("CLAUDE_CODE_SESSION"):
            return "claude-code"
        if (path / ".vscode").exists():
            return "ide"
        if (path / ".idea").exists():
            return "ide"
        if (path / ".codex").exists():
            return "codex"
        return "agent"

    def _ensure_agent(self) -> SerenaAgent:
        if self._agent is None:
            config = SerenaConfig()
            self._agent = SerenaAgent(project=str(self.project_path), serena_config=config)
        return self._agent

    def register_tool(self, tool: Any):
        """Register an extended tool locally in the wrapper."""
        tool_name = tool.name if hasattr(tool, 'name') else str(tool)
        self._extended_tools[tool_name] = tool

    def call_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name."""

        # Priority 1: Check extended tools managed by wrapper
        if name in self._extended_tools:
            tool = self._extended_tools[name]
            try:
                if hasattr(tool, "_run"):
                    result = tool._run(**kwargs)
                elif hasattr(tool, "run"):
                    result = tool.run(**kwargs)
                else:
                    return {"error": {"code": "RUNTIME_ERROR", "message": f"Tool '{name}' has no recognized execution method"}}
                return {"result": result}
            except Exception as e:
                return {"error": {"code": "RUNTIME_ERROR", "message": str(e)}}

        # Priority 2: Use ToolRegistry to find and execute core tools
        registry = ToolRegistry()
        if not registry.is_valid_tool_name(name):
            return {"error": {"code": "TOOL_NOT_FOUND", "message": f"Tool '{name}' not found"}}

        try:
            tool_class = registry.get_tool_class_by_name(name)
            agent = self._ensure_agent()
            tool_instance = agent.get_tool(tool_class)

            if hasattr(tool_instance, "apply_ex"):
                result = tool_instance.apply_ex(**kwargs)
            else:
                result = tool_instance.apply(**kwargs)
            return {"result": result}
        except Exception as e:
            return {"error": {"code": "RUNTIME_ERROR", "message": str(e)}}

    def list_tools(self, scope: str = "active") -> List[str]:
        """List available tools (Agent + Extended)."""
        tools = list(self._extended_tools.keys())

        try:
            agent = self._ensure_agent()
            if scope == "all":
                registry = ToolRegistry()
                tools.extend(registry.get_tool_names())
            else:
                tools.extend(agent.get_active_tool_names())
        except Exception:
            pass

        return sorted(list(set(tools)))

    def shutdown(self):
        """Cleanup resources."""
        if self._agent and hasattr(self._agent, "shutdown"):
            self._agent.shutdown()
        self._agent = None
