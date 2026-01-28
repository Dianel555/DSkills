"""Symbol operations command group."""
import typer
from typing import Optional
from . import State
from ..output import output_json

app = typer.Typer(help="Symbol operations (find, overview, references, edit)")


@app.command("find")
def find_symbol(
    name_path: str = typer.Argument(..., help="Symbol name or path pattern"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Restrict search to file/directory"),
    body: bool = typer.Option(False, "--body", "-b", help="Include symbol body in output"),
    depth: int = typer.Option(0, "--depth", "-d", help="Depth for nested symbols (0=current level only)"),
    exact: bool = typer.Option(False, "--exact", "-e", help="Exact match (disable substring matching)"),
):
    """Find symbols by name or path pattern."""
    result = State.core.call_tool(
        "find_symbol",
        name_path=name_path,
        relative_path=path,
        include_body=body,
        depth=depth,
        substring_matching=not exact,
    )
    output_json(result)


@app.command("overview")
def symbols_overview(
    path: str = typer.Argument(..., help="File path to analyze"),
):
    """List all symbols in a file."""
    result = State.core.call_tool(
        "get_symbols_overview",
        relative_path=path,
    )
    output_json(result)


@app.command("refs")
def find_refs(
    name_path: str = typer.Argument(..., help="Symbol name or path"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Restrict search to file/directory"),
    snippets: bool = typer.Option(True, "--snippets/--no-snippets", help="Include code snippets"),
):
    """Find references to a symbol."""
    result = State.core.call_tool(
        "find_referencing_symbols",
        name_path=name_path,
        relative_path=path,
        include_code_snippets=snippets,
    )
    output_json(result)


@app.command("replace")
def replace_symbol(
    name_path: str = typer.Argument(..., help="Symbol name or path"),
    path: str = typer.Option(..., "--path", "-p", help="File containing the symbol"),
    body: str = typer.Option(..., "--body", "-b", help="New symbol body"),
):
    """Replace symbol body."""
    result = State.core.call_tool(
        "replace_symbol_body",
        name_path=name_path,
        relative_path=path,
        new_body=body,
    )
    output_json(result)


@app.command("insert-after")
def insert_after(
    name_path: str = typer.Argument(..., help="Symbol name or path"),
    path: str = typer.Option(..., "--path", "-p", help="File containing the symbol"),
    content: str = typer.Option(..., "--content", "-c", help="Content to insert"),
):
    """Insert content after a symbol."""
    result = State.core.call_tool(
        "insert_after_symbol",
        name_path=name_path,
        relative_path=path,
        content=content,
    )
    output_json(result)


@app.command("insert-before")
def insert_before(
    name_path: str = typer.Argument(..., help="Symbol name or path"),
    path: str = typer.Option(..., "--path", "-p", help="File containing the symbol"),
    content: str = typer.Option(..., "--content", "-c", help="Content to insert"),
):
    """Insert content before a symbol."""
    result = State.core.call_tool(
        "insert_before_symbol",
        name_path=name_path,
        relative_path=path,
        content=content,
    )
    output_json(result)


@app.command("rename")
def rename_symbol(
    name_path: str = typer.Argument(..., help="Symbol name or path"),
    new_name: str = typer.Argument(..., help="New symbol name"),
    path: str = typer.Option(..., "--path", "-p", help="File containing the symbol"),
):
    """Rename a symbol."""
    result = State.core.call_tool(
        "rename_symbol",
        name_path=name_path,
        relative_path=path,
        new_name=new_name,
    )
    output_json(result)
