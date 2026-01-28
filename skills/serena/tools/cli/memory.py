"""Memory operations command group."""
import typer
from . import State
from ..output import output_json

app = typer.Typer(help="Project memory operations (persistent knowledge)")


@app.command("list")
def list_memories():
    """List all project memories."""
    result = State.core.call_tool("list_memories")
    output_json(result)


@app.command("read")
def read_memory(
    name: str = typer.Argument(..., help="Memory name"),
):
    """Read memory content."""
    result = State.core.call_tool(
        "read_memory",
        name=name,
    )
    output_json(result)


@app.command("write")
def write_memory(
    name: str = typer.Argument(..., help="Memory name"),
    content: str = typer.Option(..., "--content", "-c", help="Memory content"),
):
    """Create or update memory."""
    result = State.core.call_tool(
        "write_memory",
        name=name,
        content=content,
    )
    output_json(result)


@app.command("edit")
def edit_memory(
    name: str = typer.Argument(..., help="Memory name"),
    content: str = typer.Option(..., "--content", "-c", help="New memory content"),
):
    """Edit existing memory."""
    result = State.core.call_tool(
        "edit_memory",
        name=name,
        content=content,
    )
    output_json(result)


@app.command("delete")
def delete_memory(
    name: str = typer.Argument(..., help="Memory name"),
):
    """Delete a memory."""
    result = State.core.call_tool(
        "delete_memory",
        name=name,
    )
    output_json(result)
