"""File operations command group."""
import typer
from typing import Optional
from . import State
from ..output import output_json

app = typer.Typer(help="File system operations (list, find, search)")


@app.command("list")
def list_dir(
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Directory path (default: project root)"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="List recursively"),
):
    """List directory contents."""
    result = State.core.call_tool(
        "list_dir",
        relative_path=path if path is not None else ".",
        recursive=recursive,
    )
    output_json(result)


@app.command("find")
def find_file(
    pattern: str = typer.Argument(..., help="File pattern (glob syntax, e.g., '**/*.py')"),
):
    """Find files by pattern."""
    result = State.core.call_tool(
        "find_file",
        file_mask=pattern,
        relative_path=".",
    )
    output_json(result)


@app.command("search")
def search_pattern(
    pattern: str = typer.Argument(..., help="Search pattern (regex)"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Restrict search to file/directory"),
):
    """Search for pattern in files."""
    result = State.core.call_tool(
        "search_for_pattern",
        substring_pattern=pattern,
        relative_path=path if path is not None else ".",
    )
    output_json(result)
