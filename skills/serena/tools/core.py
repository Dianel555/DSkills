"""Serena Core Wrapper."""

import os
from pathlib import Path
from typing import Any, Optional, List, Dict

try:
    from serena.agent import SerenaAgent, SerenaConfig
    from serena.tools import ToolRegistry
except ImportError:
    raise ImportError("serena-agent is not installed")

from .paths import SerenaToolsPaths


class SerenaCore:
    """Wrapper for SerenaAgent providing CLI-friendly interface and context awareness."""

    KNOWN_CONTEXTS = ["agent", "claude-code", "ide", "codex"]

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

        # Initialize config path
        self._paths = SerenaToolsPaths()
        self._paths.ensure_config_exists()

    def _detect_context(self, path: Path) -> str:
        """Detect environment context from SERENA_CONTEXT env var only.

        No automatic detection - context must be explicitly configured.
        Default: desktop-app (full toolset)
        """
        # Read from environment variable only
        context = os.environ.get("SERENA_CONTEXT", "desktop-app")
        return context

    def _resolve_context(self) -> Optional[Any]:
        """Convert string context to SerenaAgentContext if needed."""
        if self.context:
            try:
                from serena.agent import SerenaAgentContext
                # Map common aliases to actual context names
                context_map = {
                    "claude-code": "desktop-app",  # Claude Code uses desktop-app context
                }
                context_name = context_map.get(self.context, self.context)
                return SerenaAgentContext.from_name(context_name)
            except Exception:
                return None
        return None

    def _resolve_modes(self) -> Optional[List[Any]]:
        """Convert string modes to SerenaAgentMode list if needed."""
        if self.modes:
            try:
                from serena.agent import SerenaAgentMode
                return [SerenaAgentMode(m) for m in self.modes]
            except Exception:
                return None
        return None

    def _ensure_agent(self) -> SerenaAgent:
        if self._agent is None:
            config = SerenaConfig()
            self._agent = SerenaAgent(
                project=str(self.project_path),
                serena_config=config,
                context=self._resolve_context(),
                modes=self._resolve_modes(),
            )
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

    def get_active_context(self) -> str:
        """Get active context name from wrapper.

        Returns the user-configured context name (not the mapped internal name).
        """
        return self.context

    def get_active_modes(self) -> List[str]:
        """Get active mode names from wrapper configuration.

        Returns the user-configured modes (not filtered by agent).
        """
        return sorted(set(self.modes))

    def list_modes(self, scope: str = "all") -> List[str]:
        """List modes (active or all registered when discoverable)."""
        active_modes = self.get_active_modes()
        if scope == "active":
            return active_modes

        try:
            from serena.agent import SerenaAgentMode
            all_modes = SerenaAgentMode.list_registered_mode_names()
            return sorted(set(active_modes + all_modes))
        except Exception:
            return active_modes

    def list_contexts(self, scope: str = "all") -> List[str]:
        """List contexts (active or all registered when discoverable)."""
        active_context = self.get_active_context()
        if scope == "active":
            return [active_context] if active_context else []

        discovered: List[str] = []
        try:
            from serena.agent import SerenaAgentContext
            discovered = SerenaAgentContext.list_registered_context_names()
        except Exception:
            discovered = []

        base_contexts = discovered if discovered else list(self.KNOWN_CONTEXTS)
        if active_context:
            base_contexts.append(active_context)
        return sorted(set(base_contexts))

    def get_dashboard_info(self) -> Dict[str, Any]:
        """Get dashboard-like overview of current/available configuration."""
        active_tools = self.list_tools(scope="active")
        available_tools = self.list_tools(scope="all")

        active_project_path = str(self.project_path)
        try:
            agent = self._ensure_agent()
            if hasattr(agent, "get_active_project"):
                project = agent.get_active_project()
                if project is not None and hasattr(project, "project_root"):
                    active_project_path = str(Path(project.project_root).resolve())
        except Exception:
            pass

        return {
            "active_project_path": active_project_path,
            "context": self.get_active_context(),
            "active_modes": self.get_active_modes(),
            "active_tools_count": len(active_tools),
            "active_tools": active_tools,
            "available_tools": available_tools,
            "available_modes": self.list_modes(scope="all"),
            "available_contexts": self.list_contexts(scope="all"),
        }

    def shutdown(self):
        """Cleanup resources."""
        if self._agent and hasattr(self._agent, "shutdown"):
            self._agent.shutdown()
        self._agent = None
