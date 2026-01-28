#!/usr/bin/env python3
"""Serena CLI - MCP-independent semantic code operations."""

import argparse
import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Any

# Error codes
ERROR_INVALID_ARGS = "INVALID_ARGS"
ERROR_TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
ERROR_INIT_FAILED = "INIT_FAILED"
ERROR_RUNTIME_ERROR = "RUNTIME_ERROR"

def ensure_dependencies():
    """Check and install dependencies."""
    try:
        import serena.agent
        import serena.config
        return
    except ImportError:
        print("Serena dependencies not found. Attempting auto-installation...", file=sys.stderr)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "serena-agent"])
            import serena.agent
        except Exception as e:
            print(f"Error: Failed to install serena-agent: {e}", file=sys.stderr)
            sys.exit(1)

ensure_dependencies()

from .core import SerenaCore
from .cmd_tools import RunCommandTool, RunScriptTool
from .config_tools import ReadConfigTool, UpdateConfigTool


def output_json(data: Any):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def init_core(args: argparse.Namespace) -> SerenaCore:
    modes = args.modes or ["interactive", "editing"]
    core = SerenaCore(
        project=args.project,
        context=args.context,
        modes=modes,
    )

    # Register extended tools
    core.register_tool(RunCommandTool())
    core.register_tool(RunScriptTool())
    core.register_tool(ReadConfigTool())
    core.register_tool(UpdateConfigTool())

    return core


# --- Command Handlers ---

def cmd_find_symbol(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool(
        "find_symbol",
        name_path=args.name_path,
        relative_path=args.path,
        include_body=args.body,
        depth=args.depth,
        substring_matching=not args.exact,
    )
    output_json(result)


def cmd_get_symbols_overview(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool("get_symbols_overview", relative_path=args.path)
    output_json(result)


def cmd_find_referencing_symbols(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool(
        "find_referencing_symbols",
        name_path=args.name_path,
        relative_path=args.path,
        include_code_snippets=not args.no_snippets,
    )
    output_json(result)


def cmd_replace_symbol_body(core: SerenaCore, args: argparse.Namespace):
    new_body = args.body
    if args.body_file:
        new_body = Path(args.body_file).read_text(encoding="utf-8")
    result = core.call_tool(
        "replace_symbol_body",
        name_path=args.name_path,
        relative_path=args.path,
        new_body=new_body,
    )
    output_json(result)


def cmd_insert_after_symbol(core: SerenaCore, args: argparse.Namespace):
    content = args.content
    if args.content_file:
        content = Path(args.content_file).read_text(encoding="utf-8")
    result = core.call_tool(
        "insert_after_symbol",
        name_path=args.name_path,
        relative_path=args.path,
        content=content,
    )
    output_json(result)


def cmd_insert_before_symbol(core: SerenaCore, args: argparse.Namespace):
    content = args.content
    if args.content_file:
        content = Path(args.content_file).read_text(encoding="utf-8")
    result = core.call_tool(
        "insert_before_symbol",
        name_path=args.name_path,
        relative_path=args.path,
        content=content,
    )
    output_json(result)


def cmd_rename_symbol(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool(
        "rename_symbol",
        name_path=args.name_path,
        relative_path=args.path,
        new_name=args.new_name,
    )
    output_json(result)


def cmd_write_memory(core: SerenaCore, args: argparse.Namespace):
    content = args.content
    if args.content_file:
        content = Path(args.content_file).read_text(encoding="utf-8")
    result = core.call_tool("write_memory", name=args.name, content=content)
    output_json(result)


def cmd_read_memory(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool("read_memory", name=args.name)
    output_json(result)


def cmd_list_memories(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool("list_memories")
    output_json(result)


def cmd_edit_memory(core: SerenaCore, args: argparse.Namespace):
    content = args.content
    if args.content_file:
        content = Path(args.content_file).read_text(encoding="utf-8")
    result = core.call_tool("edit_memory", name=args.name, content=content)
    output_json(result)


def cmd_delete_memory(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool("delete_memory", name=args.name)
    output_json(result)


def cmd_list_dir(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool(
        "list_dir",
        relative_path=args.path,
        recursive=args.recursive,
        max_depth=args.max_depth,
    )
    output_json(result)


def cmd_find_file(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool(
        "find_file",
        pattern=args.pattern,
        relative_path=args.path,
    )
    output_json(result)


def cmd_search_for_pattern(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool(
        "search_for_pattern",
        pattern=args.pattern,
        relative_path=args.path,
        file_pattern=args.file_pattern,
        case_sensitive=not args.ignore_case,
    )
    output_json(result)


def cmd_onboarding(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool("onboarding")
    output_json(result)


def cmd_check_onboarding(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool("check_onboarding_performed")
    output_json(result)


def cmd_list_tools(core: SerenaCore, args: argparse.Namespace):
    tools = core.list_tools(scope=args.scope)
    output_json({"tools": tools})


# --- New Extended Tool Handlers ---

def cmd_run_command(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool(
        "run_command",
        command=args.cmd,
        cwd=args.cwd,
        timeout=args.timeout
    )
    output_json(result)

def cmd_run_script(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool(
        "run_script",
        script_path=args.script,
        args=args.args
    )
    output_json(result)

def cmd_read_config(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool(
        "read_config",
        path=args.path,
        format=args.format
    )
    output_json(result)

def cmd_update_config(core: SerenaCore, args: argparse.Namespace):
    result = core.call_tool(
        "update_config",
        path=args.path,
        key=args.key,
        value=args.value
    )
    output_json(result)


# --- Parser Builder ---

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="serena-cli",
        description="Serena CLI - Semantic code operations without MCP",
    )
    parser.add_argument(
        "--project", "-p",
        default=os.environ.get("SERENA_PROJECT", "."),
        help="Project path (default: current directory or SERENA_PROJECT env)",
    )
    parser.add_argument(
        "--context", "-c",
        default=os.environ.get("SERENA_CONTEXT", "agent"),
        help="Serena context (default: agent)",
    )
    parser.add_argument(
        "--mode", "-m",
        action="append",
        dest="modes",
        help="Operational modes (can specify multiple)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Symbol tools
    p = subparsers.add_parser("find-symbol", help="Find symbols by name")
    p.add_argument("name_path", help="Symbol name or path (e.g., 'MyClass/method')")
    p.add_argument("--path", help="Restrict to file/directory")
    p.add_argument("--body", action="store_true", help="Include implementation")
    p.add_argument("--depth", type=int, default=0, help="Include nested symbols")
    p.add_argument("--exact", action="store_true", help="Exact name match")
    p.set_defaults(func=cmd_find_symbol)

    p = subparsers.add_parser("symbols-overview", help="List symbols in file")
    p.add_argument("path", help="File path")
    p.set_defaults(func=cmd_get_symbols_overview)

    p = subparsers.add_parser("find-refs", help="Find symbol references")
    p.add_argument("name_path", help="Symbol name or path")
    p.add_argument("--path", help="File containing symbol")
    p.add_argument("--no-snippets", action="store_true", help="Omit code snippets")
    p.set_defaults(func=cmd_find_referencing_symbols)

    p = subparsers.add_parser("replace-symbol", help="Replace symbol body")
    p.add_argument("name_path", help="Symbol to replace")
    p.add_argument("--path", required=True, help="File containing symbol")
    p.add_argument("--body", help="New body content")
    p.add_argument("--body-file", help="Read body from file")
    p.set_defaults(func=cmd_replace_symbol_body)

    p = subparsers.add_parser("insert-after", help="Insert after symbol")
    p.add_argument("name_path", help="Reference symbol")
    p.add_argument("--path", required=True, help="File containing symbol")
    p.add_argument("--content", help="Content to insert")
    p.add_argument("--content-file", help="Read content from file")
    p.set_defaults(func=cmd_insert_after_symbol)

    p = subparsers.add_parser("insert-before", help="Insert before symbol")
    p.add_argument("name_path", help="Reference symbol")
    p.add_argument("--path", required=True, help="File containing symbol")
    p.add_argument("--content", help="Content to insert")
    p.add_argument("--content-file", help="Read content from file")
    p.set_defaults(func=cmd_insert_before_symbol)

    p = subparsers.add_parser("rename-symbol", help="Rename symbol")
    p.add_argument("name_path", help="Symbol to rename")
    p.add_argument("new_name", help="New name")
    p.add_argument("--path", required=True, help="File containing symbol")
    p.set_defaults(func=cmd_rename_symbol)

    # Memory tools
    p = subparsers.add_parser("write-memory", help="Create/update memory")
    p.add_argument("name", help="Memory name")
    p.add_argument("--content", help="Memory content")
    p.add_argument("--content-file", help="Read content from file")
    p.set_defaults(func=cmd_write_memory)

    p = subparsers.add_parser("read-memory", help="Read memory")
    p.add_argument("name", help="Memory name")
    p.set_defaults(func=cmd_read_memory)

    p = subparsers.add_parser("list-memories", help="List all memories")
    p.set_defaults(func=cmd_list_memories)

    p = subparsers.add_parser("edit-memory", help="Edit memory")
    p.add_argument("name", help="Memory name")
    p.add_argument("--content", help="New content")
    p.add_argument("--content-file", help="Read content from file")
    p.set_defaults(func=cmd_edit_memory)

    p = subparsers.add_parser("delete-memory", help="Delete memory")
    p.add_argument("name", help="Memory name")
    p.set_defaults(func=cmd_delete_memory)

    # File tools
    p = subparsers.add_parser("list-dir", help="List directory")
    p.add_argument("--path", default="", help="Directory path")
    p.add_argument("--recursive", "-r", action="store_true")
    p.add_argument("--max-depth", type=int, help="Max recursion depth")
    p.set_defaults(func=cmd_list_dir)

    p = subparsers.add_parser("find-file", help="Find files by pattern")
    p.add_argument("pattern", help="Glob pattern")
    p.add_argument("--path", help="Search directory")
    p.set_defaults(func=cmd_find_file)

    p = subparsers.add_parser("search", help="Search for pattern in files")
    p.add_argument("pattern", help="Regex pattern")
    p.add_argument("--path", help="Restrict to path")
    p.add_argument("--file-pattern", help="File glob filter")
    p.add_argument("--ignore-case", "-i", action="store_true")
    p.set_defaults(func=cmd_search_for_pattern)

    # Workflow tools
    p = subparsers.add_parser("onboarding", help="Initialize project")
    p.set_defaults(func=cmd_onboarding)

    p = subparsers.add_parser("check-onboarding", help="Check onboarding status")
    p.set_defaults(func=cmd_check_onboarding)

    p = subparsers.add_parser("list-tools", help="List available tools")
    p.add_argument("--scope", choices=["active", "all"], default="active")
    p.set_defaults(func=cmd_list_tools)

    # Extended Tools - CMD
    p = subparsers.add_parser("run-command", help="Execute shell command")
    p.add_argument("cmd", help="Command to execute")
    p.add_argument("--cwd", help="Working directory")
    p.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    p.set_defaults(func=cmd_run_command)

    p = subparsers.add_parser("run-script", help="Execute script file")
    p.add_argument("script", help="Path to script")
    p.add_argument("--args", help="Arguments string")
    p.set_defaults(func=cmd_run_script)

    # Extended Tools - Config
    p = subparsers.add_parser("read-config", help="Read config file (json/yaml)")
    p.add_argument("path", help="Config file path")
    p.add_argument("--format", help="Force format (json/yaml)")
    p.set_defaults(func=cmd_read_config)

    p = subparsers.add_parser("update-config", help="Update config value")
    p.add_argument("path", help="Config file path")
    p.add_argument("key", help="Key to update (dot.notation)")
    p.add_argument("value", help="New value")
    p.set_defaults(func=cmd_update_config)

    return parser


def main():
    parser = build_parser()

    try:
        args = parser.parse_args()
        core = init_core(args)
        args.func(core, args)
        core.shutdown()
    except SystemExit as e:
        if e.code == 0:
            sys.exit(0)
        sys.exit(e.code)
    except Exception as e:
        output_json({"error": {"code": ERROR_RUNTIME_ERROR, "message": str(e)}})
        sys.exit(1)


if __name__ == "__main__":
    main()
