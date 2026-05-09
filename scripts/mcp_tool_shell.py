#!/usr/bin/env python3
"""Interactive shell to run KnowledgeMCP tool functions with fast reruns.

Each execution calls scripts/mcp_tool_runner.py in a fresh subprocess so any
code changes are picked up immediately without restarting the shell.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import readline  # noqa: F401
except ImportError:
    readline = None

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
RUNNER = ROOT / "scripts" / "mcp_tool_runner.py"


@dataclass
class ShellState:
    current_tool: str = "list_knowledge_files"
    current_args: str = "{}"
    last_tool: str = "list_knowledge_files"
    last_args: str = "{}"

    def remember_last(self, tool_name: str, args_json: str) -> None:
        self.last_tool = tool_name
        self.last_args = args_json


def _run_runner(args: list[str]) -> int:
    cmd = [PYTHON, str(RUNNER), *args]
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        print(f"Runner failed with exit code {proc.returncode}. Use 'help' or 'info <tool>' for guidance.")
    return proc.returncode


def _run_tool(tool_name: str, args_json: str) -> int:
    return _run_runner(["--tool", tool_name, "--args-json", args_json])


def _print_help() -> None:
    print("Commands:")
    print("  help                     Show this help")
    print("  capabilities             Show tools/resources/prompts")
    print("  list                     List available tool names")
    print("  info <tool>              Show signature + docs for one tool")
    print("  resources                List available resource URI patterns")
    print("  resource <uri>           Read one resource URI")
    print("  prompts                  List available prompt templates")
    print("  tool <name>              Select active tool")
    print("  args <json>              Set active args JSON object")
    print("                           Example: args {\"query\":\"Bill Gates\",\"top_k\":3}")
    print("  show                     Show current tool + args")
    print("  run                      Execute current tool")
    print("  r                        Re-run last execution")
    print("  call <name> <json>       One-shot execution")
    print("                           Tip: wrap JSON in single quotes if it contains spaces")
    print("  quit / exit              Leave shell")


def _validate_json_object(value: str) -> bool:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}")
        return False

    if not isinstance(parsed, dict):
        print("JSON must be an object, for example: {} or {\"query\":\"rag\"}")
        return False
    return True


def _raw_suffix(raw: str, *, maxsplit: int) -> str | None:
    split = raw.split(maxsplit=maxsplit)
    if len(split) <= maxsplit:
        return None
    return split[maxsplit].strip()


def main() -> int:
    state = ShellState()

    print("KnowledgeMCP Interactive Shell")
    print("Type 'help' for commands. Type 'list' to see tools.")

    while True:
        try:
            raw = input("mcp> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not raw:
            continue

        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            print(f"Parse error: {exc}")
            continue

        cmd = parts[0].lower()

        if cmd in {"quit", "exit"}:
            return 0

        if cmd == "help":
            _print_help()
            continue

        if cmd == "capabilities":
            _run_runner(["--capabilities"])
            continue

        if cmd == "list":
            _run_runner(["--list"])
            continue

        if cmd == "info":
            if len(parts) < 2:
                print("Usage: info <tool>")
                continue
            _run_runner(["--tool-info", parts[1]])
            continue

        if cmd == "resources":
            _run_runner(["--list-resources"])
            continue

        if cmd == "resource":
            if len(parts) < 2:
                print("Usage: resource <uri>")
                continue
            _run_runner(["--read-resource", parts[1]])
            continue

        if cmd == "prompts":
            _run_runner(["--list-prompts"])
            continue

        if cmd == "tool":
            if len(parts) < 2:
                print("Usage: tool <name>")
                continue
            state.current_tool = parts[1]
            print(f"Current tool: {state.current_tool}")
            continue

        if cmd == "args":
            if len(parts) < 2:
                print("Usage: args <json>")
                continue
            value = _raw_suffix(raw, maxsplit=1)
            if value is None:
                print("Usage: args <json>")
                continue
            if not _validate_json_object(value):
                continue
            state.current_args = value
            print("Current args updated.")
            continue

        if cmd == "show":
            print(f"tool: {state.current_tool}")
            print(f"args: {state.current_args}")
            continue

        if cmd == "run":
            state.remember_last(state.current_tool, state.current_args)
            _run_tool(state.current_tool, state.current_args)
            continue

        if cmd == "r":
            _run_tool(state.last_tool, state.last_args)
            continue

        if cmd == "call":
            one_shot_args = _raw_suffix(raw, maxsplit=2)
            if len(parts) < 2 or one_shot_args is None:
                print("Usage: call <name> <json>")
                continue
            tool_name = parts[1].strip()
            if not _validate_json_object(one_shot_args):
                continue
            state.remember_last(tool_name, one_shot_args)
            _run_tool(tool_name, one_shot_args)
            continue

        print(f"Unknown command: {cmd}. Type 'help' for available commands.")


if __name__ == "__main__":
    raise SystemExit(main())
