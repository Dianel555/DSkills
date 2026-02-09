"""Dashboard-like information command group."""
import os
import shlex
import subprocess
import sys
from typing import Optional

import typer
from . import State
from ..output import output_json, output_error

app = typer.Typer(help="Dashboard-style configuration overview")


def _resolve_windows_browser_command() -> Optional[list[str]]:
    """Resolve default HTTP browser command from Windows registry."""
    try:
        import winreg
    except Exception:
        return None

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice",
        ) as key:
            prog_id, _ = winreg.QueryValueEx(key, "ProgId")

        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            rf"{prog_id}\shell\open\command",
        ) as key:
            command, _ = winreg.QueryValueEx(key, None)

        tokens = shlex.split(command, posix=False)
        cleaned: list[str] = []
        for token in tokens:
            token_lower = token.lower()
            if token_lower in {"%1", "%l", "%*"}:
                continue
            if "%1" in token_lower or "%l" in token_lower:
                continue
            cleaned.append(token)
        return cleaned or None
    except Exception:
        return None


def _open_browser_url(url: str, browser_cmd: Optional[str] = None) -> str:
    """Open URL in browser using the most reliable method for each platform."""
    if sys.platform == "win32":
        if browser_cmd:
            cmd = shlex.split(browser_cmd, posix=False)
            subprocess.Popen([*cmd, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "explicit-browser-cmd"
        resolved = _resolve_windows_browser_command()
        if resolved:
            subprocess.Popen([*resolved, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "windows-registry-command"
        os.startfile(url)
        return "os.startfile-fallback"
    if sys.platform == "darwin":
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "open"
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "xdg-open"


@app.command("info")
def info():
    """Show current configuration and discoverable options."""
    output_json({"result": State.core.get_dashboard_info()})


@app.command("tools")
def tools():
    """Show active and available tools."""
    active_tools = State.core.list_tools(scope="active")
    available_tools = State.core.list_tools(scope="all")
    output_json(
        {
            "result": {
                "active_count": len(active_tools),
                "active": active_tools,
                "available_count": len(available_tools),
                "available": available_tools,
            }
        }
    )


@app.command("modes")
def modes():
    """Show active and available modes."""
    active_modes = State.core.list_modes(scope="active")
    available_modes = State.core.list_modes(scope="all")
    output_json(
        {"result": {"active": active_modes, "available": available_modes}}
    )


@app.command("contexts")
def contexts():
    """Show active and available contexts."""
    active_contexts = State.core.list_contexts(scope="active")
    available_contexts = State.core.list_contexts(scope="all")
    output_json(
        {"result": {"active": active_contexts, "available": available_contexts}}
    )


@app.command("serve")
def serve(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Dashboard listen address",
    ),
    port: int = typer.Option(
        0,
        "--port",
        "-p",
        help="Dashboard listen port (0 means auto-select)",
    ),
    open_browser: bool = typer.Option(
        False,
        "--open-browser/--no-open-browser",
        help="Open dashboard URL in browser on startup",
    ),
    browser_cmd: Optional[str] = typer.Option(
        None,
        "--browser-cmd",
        envvar="SERENA_BROWSER_CMD",
        help="Launch browser via explicit command, e.g. 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'",
    ),
):
    """Serve Serena web dashboard."""
    if State.core is None:
        output_error("INIT_FAILED", "SerenaCore is not initialized")

    from ..server.dashboard_server import DashboardServer

    dashboard_server = DashboardServer(core=State.core)
    thread, actual_port = dashboard_server.run_in_thread(
        host=host, port=port if port > 0 else None
    )
    url = dashboard_server.get_dashboard_url(host=host, port=actual_port)

    if open_browser:
        print(f"[DEBUG] PID={os.getpid()}: About to open browser with URL: {url}", file=sys.stderr)
        try:
            method = _open_browser_url(url, browser_cmd=browser_cmd)
            print(f"[DEBUG] PID={os.getpid()}: Browser launched via method={method}", file=sys.stderr)
        except Exception as e:
            print(f"[WARNING] Failed to open browser: {e}", file=sys.stderr)
        print(f"[DEBUG] PID={os.getpid()}: Browser open call completed", file=sys.stderr)
    else:
        # Display URL for manual opening
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"  Serena Dashboard is running!", file=sys.stderr)
        print(f"  URL: {url}", file=sys.stderr)
        print(f"  Copy and paste this URL into your browser", file=sys.stderr)
        print(f"  Or use --open-browser flag to open automatically", file=sys.stderr)
        print(f"{'='*70}\n", file=sys.stderr)

    output_json({"result": {"status": "running", "host": host, "port": actual_port, "url": url}})
    while thread.is_alive():
        thread.join(timeout=0.5)
