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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
RUNNER = ROOT / "scripts" / "mcp_tool_runner.py"


def _run_runner(args: list[str]) -> int:
    cmd = [PYTHON, str(RUNNER), *args]
    proc = subprocess.run(cmd, cwd=ROOT)
    return proc.returncode


def _print_help() -> None:
    print("Commands:")
    print("  help                     Show this help")
    print("  capabilities             Show tools/resources/prompts")
    print("  list                     List available tool names")
    print("  resources                List available resource URI patterns")
    print("  resource <uri>           Read one resource URI")
    print("  prompts                  List available prompt templates")
    print("  tool <name>              Select active tool")
    print("  args <json>              Set active args JSON object")
    print("  show                     Show current tool + args")
    print("  run                      Execute current tool")
    print("  r                        Re-run last execution")
    print("  call <name> <json>       One-shot execution")
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


def main() -> int:
    current_tool = "list_knowledge_files"
    current_args = "{}"
    last_tool = current_tool
    last_args = current_args

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
            current_tool = parts[1]
            print(f"Current tool: {current_tool}")
            continue

        if cmd == "args":
            if len(parts) < 2:
                print("Usage: args <json>")
                continue
            value = raw[len(parts[0]) :].strip()
            if not _validate_json_object(value):
                continue
            current_args = value
            print("Current args updated.")
            continue

        if cmd == "show":
            print(f"tool: {current_tool}")
            print(f"args: {current_args}")
            continue

        if cmd == "run":
            last_tool = current_tool
            last_args = current_args
            _run_runner(["--tool", current_tool, "--args-json", current_args])
            continue

        if cmd == "r":
            _run_runner(["--tool", last_tool, "--args-json", last_args])
            continue

        if cmd == "call":
            if len(parts) < 3:
                print("Usage: call <name> <json>")
                continue
            tool_name = parts[1]
            json_start = raw.find(tool_name) + len(tool_name)
            one_shot_args = raw[json_start:].strip()
            if not _validate_json_object(one_shot_args):
                continue
            last_tool = tool_name
            last_args = one_shot_args
            _run_runner(["--tool", tool_name, "--args-json", one_shot_args])
            continue

        print(f"Unknown command: {cmd}. Type 'help' for available commands.")


if __name__ == "__main__":
    raise SystemExit(main())
