"""Workflow operations command group."""
import typer
from . import State
from ..output import output_json

app = typer.Typer(help="Workflow operations (onboarding, diagnostics)")


@app.command("onboarding")
def onboarding():
    """Run project onboarding process."""
    result = State.core.call_tool("onboarding")
    output_json(result)


@app.command("check")
def check_onboarding():
    """Check if onboarding has been performed."""
    result = State.core.call_tool("check_onboarding_performed")
    output_json(result)


@app.command("tools")
def list_tools(
    scope: str = typer.Option("active", "--scope", "-s", help="Tool scope: 'active' or 'all'"),
):
    """List available tools."""
    tools = State.core.list_tools(scope=scope)
    output_json({"result": tools})
