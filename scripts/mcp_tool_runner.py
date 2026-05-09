#!/usr/bin/env python3
"""List and invoke KnowledgeMCP tool functions directly for local debugging."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

# Ensure project root is importable when executed from scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from knowledge_mcp import server


TOOLS: dict[str, Callable[..., str]] = {
    "list_knowledge_files": server.list_knowledge_files,
    "read_knowledge_file": server.read_knowledge_file,
    "index_knowledge_file": server.index_knowledge_file,
    "semantic_search": server.semantic_search,
    "trigger_summary_generation": server.trigger_summary_generation,
    "trigger_magic_filter_generation": server.trigger_magic_filter_generation,
    "trigger_faq_generation": server.trigger_faq_generation,
}

RESOURCES: dict[str, Callable[..., str]] = {
    "file://": server.resource_list_all,
    "file://{path}": server.resource_read_file,
}

# No prompt templates are currently declared in knowledge_mcp.server.
PROMPTS: dict[str, Callable[..., str]] = {}


def _print_tools() -> int:
    print("Available MCP tool functions:")
    for name in sorted(TOOLS):
        print(f"- {name}")
    return 0


def _print_prompts() -> int:
    print("Available MCP prompts:")
    if not PROMPTS:
        print("- (none)")
        return 0
    for name in sorted(PROMPTS):
        print(f"- {name}")
    return 0


def _print_resources() -> int:
    print("Available MCP resources:")
    for pattern in sorted(RESOURCES):
        print(f"- {pattern}")
    return 0


def _print_capabilities() -> int:
    print("KnowledgeMCP capabilities")
    print(f"tools: {len(TOOLS)}")
    for name in sorted(TOOLS):
        print(f"- {name}")
    print(f"resources: {len(RESOURCES)}")
    for pattern in sorted(RESOURCES):
        print(f"- {pattern}")
    print(f"prompts: {len(PROMPTS)}")
    if PROMPTS:
        for name in sorted(PROMPTS):
            print(f"- {name}")
    else:
        print("- (none)")
    return 0


def _read_resource(uri: str) -> int:
    if uri == "file://":
        raw = RESOURCES["file://"]()
    elif uri.startswith("file://"):
        path = uri[len("file://") :]
        raw = RESOURCES["file://{path}"](path)
    else:
        print("Resource URI must start with file://", file=sys.stderr)
        return 2

    try:
        data: Any = json.loads(raw)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except (TypeError, json.JSONDecodeError):
        print(raw)
    return 0


def _invoke_tool(name: str, args_json: str) -> int:
    if name not in TOOLS:
        print(f"Unknown tool: {name}", file=sys.stderr)
        print("Run with --list to see valid names.", file=sys.stderr)
        return 2

    try:
        payload = json.loads(args_json)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in --args-json: {exc}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict):
        print("--args-json must decode to a JSON object.", file=sys.stderr)
        return 2

    fn = TOOLS[name]
    try:
        raw = fn(**payload)
    except TypeError as exc:
        print(f"Invalid arguments for {name}: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Tool execution failed: {exc}", file=sys.stderr)
        return 1

    # Most server tools already return JSON strings; pretty-print if possible.
    try:
        data: Any = json.loads(raw)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except (TypeError, json.JSONDecodeError):
        print(raw)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List and execute KnowledgeMCP tool functions locally."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available tool function names",
    )
    parser.add_argument(
        "--list-resources",
        action="store_true",
        help="List available resource URI patterns",
    )
    parser.add_argument(
        "--list-prompts",
        action="store_true",
        help="List available prompt template names",
    )
    parser.add_argument(
        "--capabilities",
        action="store_true",
        help="List tools/resources/prompts in one view",
    )
    parser.add_argument(
        "--read-resource",
        type=str,
        help="Read a resource URI (for example file:// or file://mydoc.txt)",
    )
    parser.add_argument(
        "--tool",
        type=str,
        help="Tool function name to execute",
    )
    parser.add_argument(
        "--args-json",
        type=str,
        default="{}",
        help="JSON object with keyword args for the selected tool",
    )

    args = parser.parse_args()

    if args.list:
        return _print_tools()

    if args.list_resources:
        return _print_resources()

    if args.list_prompts:
        return _print_prompts()

    if args.capabilities:
        return _print_capabilities()

    if args.read_resource:
        return _read_resource(args.read_resource)

    if not args.tool:
        parser.error("Provide --tool <name> or use --list")

    return _invoke_tool(args.tool, args.args_json)


if __name__ == "__main__":
    raise SystemExit(main())
