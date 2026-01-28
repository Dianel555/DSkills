from typing import Optional, Type
import subprocess
import shlex
from pydantic import BaseModel, Field

try:
    from serena.tools.base import BaseTool
except ImportError:
    # Mock for development if serena not installed
    class BaseTool:
        pass

class RunCommandInput(BaseModel):
    command: str = Field(..., description="The shell command to execute")
    cwd: Optional[str] = Field(None, description="Working directory for execution")
    timeout: Optional[int] = Field(300, description="Timeout in seconds")

class RunCommandTool(BaseTool):
    name = "run_command"
    description = "Execute a shell command on the system. Use with caution."
    args_schema: Type[BaseModel] = RunCommandInput

    def _run(self, command: str, cwd: Optional[str] = None, timeout: int = 300) -> str:
        try:
            # Basic safety check - mostly relying on user discretion in this local tool
            process = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            output = f"Exit Code: {process.returncode}\n"
            if process.stdout:
                output += f"STDOUT:\n{process.stdout}\n"
            if process.stderr:
                output += f"STDERR:\n{process.stderr}\n"
            return output
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Error executing command: {str(e)}"

class RunScriptInput(BaseModel):
    script_path: str = Field(..., description="Path to the script file")
    args: Optional[str] = Field(None, description="Arguments for the script")

class RunScriptTool(BaseTool):
    name = "run_script"
    description = "Execute a local script file (python, bash, etc.)"
    args_schema: Type[BaseModel] = RunScriptInput

    def _run(self, script_path: str, args: Optional[str] = None) -> str:
        import sys

        path = Path(script_path)
        if not path.exists():
            return f"Error: Script not found at {script_path}"

        cmd = []
        if path.suffix == '.py':
            cmd = [sys.executable, str(path)]
        elif path.suffix == '.sh':
            cmd = ['bash', str(path)]
        else:
            # Try to execute directly
            cmd = [str(path)]

        if args:
            cmd.extend(shlex.split(args))

        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            return f"Exit Code: {process.returncode}\nSTDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}"
        except Exception as e:
            return f"Error running script: {str(e)}"
