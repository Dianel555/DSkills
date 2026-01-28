"""CLI package for Serena tools using Typer."""
import typer
from typing import Optional, List
from pathlib import Path

app = typer.Typer(
    name="serena",
    help="Semantic code operations with IDE-like symbol navigation",
    no_args_is_help=True,
)


class State:
    """Global state for sharing SerenaCore instance across commands."""
    core: Optional["SerenaCore"] = None


@app.callback()
def main(
    ctx: typer.Context,
    project: str = typer.Option(
        ".",
        "-p",
        "--project",
        envvar="SERENA_PROJECT",
        help="Project directory path",
    ),
    context: str = typer.Option(
        "agent",
        "-c",
        "--context",
        envvar="SERENA_CONTEXT",
        help="Execution context (agent, claude-code, ide, codex)",
    ),
    mode: Optional[List[str]] = typer.Option(
        None,
        "-m",
        "--mode",
        help="Operation modes (can be specified multiple times)",
    ),
):
    """
    Initialize SerenaCore with global options.

    All commands inherit these global options and share the same SerenaCore instance.
    """
    from ..core import SerenaCore
    from ..extended.cmd_tools import RunCommandTool, RunScriptTool
    from ..extended.config_tools import ReadConfigTool, UpdateConfigTool
    from ..output import output_error

    try:
        # Initialize SerenaCore with global options
        modes = mode if mode else ["interactive", "editing"]
        State.core = SerenaCore(project=project, context=context, modes=modes)

        # Register extended tools
        State.core.register_tool(RunCommandTool())
        State.core.register_tool(RunScriptTool())
        State.core.register_tool(ReadConfigTool())
        State.core.register_tool(UpdateConfigTool())

    except Exception as e:
        output_error("INIT_FAILED", str(e))


# Command groups will be registered here
from .symbol import app as symbol_app
from .memory import app as memory_app
from .file import app as file_app
from .workflow import app as workflow_app
from .cmd import app as cmd_app
from .config import app as config_app

app.add_typer(symbol_app, name="symbol")
app.add_typer(memory_app, name="memory")
app.add_typer(file_app, name="file")
app.add_typer(workflow_app, name="workflow")
app.add_typer(cmd_app, name="cmd")
app.add_typer(config_app, name="config")
