"""Configuration file operations command group."""
import typer
from typing import Optional
from . import State
from ..output import output_json

app = typer.Typer(help="Configuration file operations")


@app.command("read")
def read_config(
    path: str = typer.Argument(..., help="Path to configuration file"),
    format: Optional[str] = typer.Option(None, "--format", "-f", help="Format: json or yaml (auto-detected if omitted)"),
):
    """Read a configuration file."""
    result = State.core.call_tool(
        "read_config",
        path=path,
        format=format,
    )
    output_json(result)


@app.command("update")
def update_config(
    path: str = typer.Argument(..., help="Path to configuration file"),
    key: str = typer.Argument(..., help="Dot-notation key (e.g., 'server.port')"),
    value: str = typer.Argument(..., help="New value (parsed as JSON if possible)"),
):
    """Update a configuration file key."""
    result = State.core.call_tool(
        "update_config",
        path=path,
        key=key,
        value=value,
    )
    output_json(result)
