"""Command execution command group."""
import typer
from typing import Optional
from . import State
from ..output import output_json

app = typer.Typer(help="Command execution operations")


@app.command("run")
def run_command(
    command: str = typer.Argument(..., help="Shell command to execute"),
    cwd: Optional[str] = typer.Option(None, "--cwd", help="Working directory"),
    timeout: int = typer.Option(300, "--timeout", "-t", help="Timeout in seconds"),
):
    """Execute a shell command."""
    result = State.core.call_tool(
        "run_command",
        command=command,
        cwd=cwd,
        timeout=timeout,
    )
    output_json(result)


@app.command("script")
def run_script(
    script_path: str = typer.Argument(..., help="Path to script file"),
    args: Optional[str] = typer.Option(None, "--args", "-a", help="Script arguments"),
):
    """Execute a script file."""
    result = State.core.call_tool(
        "run_script",
        script_path=script_path,
        args=args,
    )
    output_json(result)
