"""Lightweight Flask dashboard server for Serena CLI wrapper."""

import os
import socket
import threading
from pathlib import Path
from typing import Any, Optional

from flask import Flask, Response, redirect, request, send_from_directory

from ..core import SerenaCore


class DashboardServer:
    """Flask-based dashboard HTTP server."""

    DEFAULT_START_PORT = 0x5EDA
    UPSTREAM_DASHBOARD_DIR = Path(
        os.environ.get(
            "SERENA_UPSTREAM_DASHBOARD_DIR",
            "E:/Python/PythonProject1/serena/src/serena/resources/dashboard",
        )
    )

    def __init__(self, core: SerenaCore, dashboard_dir: Optional[Path | str] = None):
        self._core = core
        self._dashboard_dir = self._resolve_dashboard_dir(dashboard_dir)
        self._app = Flask(__name__)
        self._setup_routes()

        # Register current project in global Serena config
        self._update_global_serena_config()

    @property
    def app(self) -> Flask:
        return self._app

    @staticmethod
    def _normalize_names(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            normalized = [str(item) for item in value if item is not None and str(item)]
            return sorted(set(normalized))
        value_str = str(value)
        return [value_str] if value_str else []

    @staticmethod
    def _build_active_project_name(project_path: Optional[str]) -> Optional[str]:
        if not project_path:
            return None
        path = Path(project_path)
        return path.name or project_path

    def _resolve_dashboard_dir(self, dashboard_dir: Optional[Path | str]) -> Path:
        candidates: list[Path] = []
        if dashboard_dir is not None:
            candidates.append(Path(dashboard_dir))
        candidates.append(Path(__file__).resolve().parents[1] / "resources" / "dashboard")
        candidates.append(self.UPSTREAM_DASHBOARD_DIR)

        for candidate in candidates:
            if (candidate / "index.html").exists():
                return candidate

        searched = ", ".join(str(path) for path in candidates)
        raise FileNotFoundError(f"Serena dashboard static files not found. searched=[{searched}]")

    def _update_global_serena_config(self) -> None:
        """Update global Serena config to register the current project."""
        try:
            import yaml
            from pathlib import Path

            # Get current project path
            dashboard_info = self._core.get_dashboard_info()
            project_path = dashboard_info.get("active_project_path")
            if not project_path:
                return

            project_path = str(Path(project_path).resolve())

            # Load global config
            global_config_path = Path.home() / ".serena" / "serena_config.yml"
            if not global_config_path.exists():
                return

            with open(global_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

            # Add project to projects list if not already present
            projects = config.get("projects", [])
            if project_path not in projects:
                projects.append(project_path)
                config["projects"] = projects

                # Save updated config
                with open(global_config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        except Exception as e:
            # Don't fail if global config update fails
            import sys
            print(f"[WARNING] Failed to update global Serena config: {e}", file=sys.stderr)

    def _build_config_overview(self) -> dict[str, Any]:
        dashboard_info = self._core.get_dashboard_info()

        project_path_raw = dashboard_info.get("active_project_path")
        project_path = str(project_path_raw) if project_path_raw else None
        project_name = self._build_active_project_name(project_path)

        context_name = str(dashboard_info.get("context") or "agent")

        active_tools = self._normalize_names(dashboard_info.get("active_tools"))
        available_tools = self._normalize_names(dashboard_info.get("available_tools"))
        if not available_tools:
            available_tools = list(active_tools)

        active_modes = self._normalize_names(dashboard_info.get("active_modes"))
        available_modes = self._normalize_names(dashboard_info.get("available_modes"))
        available_modes = sorted(set(available_modes + active_modes))

        available_contexts = self._normalize_names(dashboard_info.get("available_contexts"))
        available_contexts = sorted(set(available_contexts + [context_name]))

        active_tool_set = set(active_tools)
        active_mode_set = set(active_modes)

        registered_projects: list[dict[str, str | bool]] = []
        if project_path:
            registered_projects.append(
                {
                    "name": project_name or project_path,
                    "path": project_path,
                    "is_active": True,
                }
            )

        return {
            "active_project": {
                "name": project_name,
                "language": None,
                "path": project_path,
            },
            "context": {
                "name": context_name,
                "description": "",
                "path": "",
            },
            "modes": [
                {
                    "name": mode_name,
                    "description": "",
                    "path": "",
                }
                for mode_name in active_modes
            ],
            "active_tools": active_tools,
            "tool_stats_summary": {
                tool_name: {"num_calls": 0}
                for tool_name in active_tools
            },
            "registered_projects": registered_projects,
            "available_tools": [
                {"name": tool_name, "is_active": False}
                for tool_name in available_tools
                if tool_name not in active_tool_set
            ],
            "available_modes": [
                {
                    "name": mode_name,
                    "is_active": mode_name in active_mode_set,
                    "path": "",
                }
                for mode_name in available_modes
            ],
            "available_contexts": [
                {
                    "name": context_item,
                    "is_active": context_item == context_name,
                    "path": "",
                }
                for context_item in available_contexts
            ],
            "available_memories": None,
            "jetbrains_mode": False,
            "languages": [],
            "encoding": None,
            "current_client": None,
        }

    def _setup_routes(self) -> None:
        @self._app.route("/")
        def root() -> Response:
            return redirect("/dashboard/index.html", code=302)

        @self._app.route("/dashboard")
        def dashboard_root() -> Response:
            return redirect("/dashboard/index.html", code=302)

        @self._app.route("/dashboard/")
        def dashboard_index_redirect() -> Response:
            return redirect("/dashboard/index.html", code=302)

        @self._app.route("/dashboard/index.html")
        def dashboard_index() -> Response:
            return send_from_directory(str(self._dashboard_dir), "index.html")

        @self._app.route("/dashboard/<path:filename>")
        def dashboard_files(filename: str) -> Response:
            return send_from_directory(str(self._dashboard_dir), filename)

        @self._app.route("/heartbeat", methods=["GET"])
        def heartbeat() -> dict[str, str]:
            return {"status": "alive"}

        @self._app.route("/get_config_overview", methods=["GET"])
        def get_config_overview() -> dict[str, Any]:
            return self._build_config_overview()

        @self._app.route("/get_tool_names", methods=["GET"])
        def get_tool_names() -> dict[str, list[str]]:
            return {"tool_names": self._normalize_names(self._core.list_tools(scope="active"))}

        @self._app.route("/get_log_messages", methods=["POST"])
        def get_log_messages() -> dict[str, Any]:
            request_data = request.get_json(silent=True) or {}
            if not isinstance(request_data, dict):
                request_data = {}
            try:
                start_idx = int(request_data.get("start_idx", 0))
            except (TypeError, ValueError):
                start_idx = 0

            dashboard_info = self._core.get_dashboard_info()
            project_path = dashboard_info.get("active_project_path")
            active_project = self._build_active_project_name(str(project_path)) if project_path else None
            return {
                "messages": [],
                "max_idx": start_idx - 1,
                "active_project": active_project,
            }

        @self._app.route("/queued_task_executions", methods=["GET"])
        def queued_task_executions() -> dict[str, list]:
            """Return empty executions queue (CLI wrapper doesn't track executions)."""
            return {"queued_executions": []}

        @self._app.route("/last_execution", methods=["GET"])
        def last_execution() -> dict[str, Any]:
            """Return empty last execution (CLI wrapper doesn't track executions)."""
            return {
                "task_id": None,
                "is_running": False,
                "name": None,
                "finished_successfully": False,
                "logged": False,
            }

        @self._app.route("/get_serena_config", methods=["GET"])
        def get_serena_config() -> dict[str, Any]:
            """Return Serena configuration from .env file."""
            from pathlib import Path
            import os

            # Try to find .env file
            env_paths = [
                Path(__file__).resolve().parents[2] / ".env",  # skills/serena/.env
                Path.cwd() / ".env",
            ]

            config_content = ""
            config_path = None

            for env_path in env_paths:
                if env_path.exists():
                    config_path = str(env_path)
                    try:
                        with open(env_path, 'r', encoding='utf-8') as f:
                            config_content = f.read()
                        break
                    except Exception:
                        pass

            if not config_content:
                # Return default template if no .env found
                config_content = """# Serena CLI Configuration
SERENA_CONTEXT=claude-code
SERENA_MODES=interactive,editing,onboarding
SERENA_PROJECT=.
SERENA_DASHBOARD_ENABLED=true
SERENA_DASHBOARD_PORT=24282
"""
                config_path = str(env_paths[0])

            return {
                "status": "success",
                "content": config_content,
                "config": config_content,  # Backward compatibility
                "path": config_path,
            }

        @self._app.route("/save_serena_config", methods=["POST"])
        @self._app.route("/update_serena_config", methods=["POST"])
        def update_serena_config() -> dict[str, Any]:
            """Update Serena configuration in .env file."""
            from pathlib import Path

            request_data = request.get_json(silent=True) or {}
            # Support both 'content' (frontend) and 'config' (backward compatibility)
            new_config = request_data.get("content")
            if new_config is None:
                new_config = request_data.get("config", "")

            if not new_config:
                return {
                    "status": "error",
                    "message": "No configuration provided",
                    "success": False,
                }

            # Try to find .env file
            env_paths = [
                Path(__file__).resolve().parents[2] / ".env",
                Path.cwd() / ".env",
            ]

            config_path = None
            for env_path in env_paths:
                if env_path.exists():
                    config_path = env_path
                    break

            if not config_path:
                # Create new .env file
                config_path = env_paths[0]

            try:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(new_config)

                return {
                    "status": "success",
                    "message": "Serena config saved successfully",
                    "path": str(config_path),
                    "success": True,
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": str(e),
                    "success": False,
                }

    @staticmethod
    def _find_first_free_port(start_port: int, host: str) -> int:
        port = max(0, start_port)
        while port <= 65535:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind((host, port))
                    return port
            except OSError:
                port += 1
        raise RuntimeError(f"No free ports found starting from {start_port}")

    @staticmethod
    def get_dashboard_url(host: str, port: int) -> str:
        browser_host = "localhost" if host in {"0.0.0.0", "::"} else host
        # Use canonical URL to avoid equivalent-path duplication in browser tabs
        return f"http://{browser_host}:{port}/dashboard/index.html"

    def run(self, host: str, port: int) -> int:
        from flask import cli
        cli.show_server_banner = lambda *args, **kwargs: None
        self._app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        return port

    def run_in_thread(self, host: str = "127.0.0.1", port: Optional[int] = None) -> tuple[threading.Thread, int]:
        resolved_port = port if port is not None and port > 0 else self._find_first_free_port(self.DEFAULT_START_PORT, host)
        thread = threading.Thread(target=lambda: self.run(host=host, port=resolved_port), daemon=True)
        thread.start()
        return thread, resolved_port
