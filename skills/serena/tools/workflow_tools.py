"""Workflow tools wrapper - re-exports from serena-agent."""

try:
    from serena.tools.workflow_tools import (
        OnboardingTool,
        CheckOnboardingPerformedTool,
    )
    __all__ = [
        "OnboardingTool",
        "CheckOnboardingPerformedTool",
    ]
except ImportError:
    __all__ = []
