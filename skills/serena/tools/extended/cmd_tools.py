"""Command execution tools with structured output."""
from typing import Optional, Type, Dict, Any
import subprocess
import shlex
import json
from pathlib import Path
from pydantic import BaseModel, Field

try:
    from serena.tools.base import BaseTool
except ImportError:
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

    def _execute(self, command: str, cwd: Optional[str], timeout: int) -> Dict[str, Any]:
        """Internal method returning structured data."""
        try:
            process = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "exit_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "error": {
                    "code": "TIMEOUT",
                    "message": f"Command timed out after {timeout} seconds"
                }
            }
        except Exception as e:
            return {
                "error": {
                    "code": "RUNTIME_ERROR",
                    "message": str(e)
                }
            }

    def _run(self, command: str, cwd: Optional[str] = None, timeout: int = 300) -> str:
        """BaseTool-compatible method returning JSON string."""
        result = self._execute(command, cwd, timeout)
        return json.dumps(result, ensure_ascii=False)


class RunScriptInput(BaseModel):
    script_path: str = Field(..., description="Path to the script file")
    args: Optional[str] = Field(None, description="Arguments for the script")


class RunScriptTool(BaseTool):
    name = "run_script"
    description = "Execute a local script file (python, bash, etc.)"
    args_schema: Type[BaseModel] = RunScriptInput

    def _execute(self, script_path: str, args: Optional[str]) -> Dict[str, Any]:
        """Internal method returning structured data."""
        import sys

        path = Path(script_path)
        if not path.exists():
            return {
                "error": {
                    "code": "FILE_NOT_FOUND",
                    "message": f"Script not found at {script_path}"
                }
            }

        cmd = []
        if path.suffix == '.py':
            cmd = [sys.executable, str(path)]
        elif path.suffix == '.sh':
            cmd = ['bash', str(path)]
        else:
            cmd = [str(path)]

        if args:
            cmd.extend(shlex.split(args))

        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            return {
                "exit_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
        except Exception as e:
            return {
                "error": {
                    "code": "RUNTIME_ERROR",
                    "message": str(e)
                }
            }

    def _run(self, script_path: str, args: Optional[str] = None) -> str:
        """BaseTool-compatible method returning JSON string."""
        result = self._execute(script_path, args)
        return json.dumps(result, ensure_ascii=False)
