#!/usr/bin/env python3
"""List and invoke KnowledgeMCP tool functions directly for local debugging.

Exit codes:
- 0: success
- 1: runtime execution error
- 2: usage/validation error
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import types
from pathlib import Path
from typing import Any, Callable, Union, get_args, get_origin, get_type_hints

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


def _print_json_or_raw(raw: str) -> None:
    try:
        data: Any = json.loads(raw)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except (TypeError, json.JSONDecodeError):
        print(raw)


def _parse_json_object(raw: str, *, flag_name: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON in {flag_name}: {exc}"

    if not isinstance(payload, dict):
        return None, f"{flag_name} must decode to a JSON object."

    return payload, None


def _format_signature(name: str, fn: Callable[..., str]) -> str:
    sig = inspect.signature(fn)
    return f"{name}{sig}"


def _doc_preview(fn: Callable[..., str], max_lines: int = 6) -> str:
    doc = inspect.getdoc(fn) or "No documentation available."
    lines = [line.rstrip() for line in doc.splitlines() if line.strip()]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append("...")
    return "\n".join(lines)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError(f"Expected bool, got {type(value).__name__}")


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("Expected int, got bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError(f"Expected int, got {type(value).__name__}")


def _coerce_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("Expected float, got bool")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.strip())
    raise ValueError(f"Expected float, got {type(value).__name__}")


def _coerce_to_annotation(value: Any, annotation: Any) -> Any:
    if annotation is inspect._empty or annotation is Any:
        return value

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        non_none = [a for a in args if a is not type(None)]
        last_error: Exception | None = None
        for ann in non_none:
            try:
                return _coerce_to_annotation(value, ann)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise ValueError(str(last_error))
        return value

    if annotation is bool:
        return _coerce_bool(value)
    if annotation is int:
        return _coerce_int(value)
    if annotation is float:
        return _coerce_float(value)
    if annotation is str:
        if isinstance(value, str):
            return value
        raise ValueError(f"Expected str, got {type(value).__name__}")

    if origin in (list, tuple):
        if not isinstance(value, list):
            raise ValueError(f"Expected list, got {type(value).__name__}")
        if not args:
            return value
        inner = args[0]
        coerced = [_coerce_to_annotation(item, inner) for item in value]
        return coerced

    return value


def _coerce_payload(fn: Callable[..., str], payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    allowed = set(sig.parameters.keys())
    unknown = sorted(set(payload.keys()) - allowed)
    if unknown:
        return None, f"Unknown arguments: {', '.join(unknown)}"

    coerced: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name not in payload:
            if param.default is inspect._empty:
                return None, f"Missing required argument: {name}"
            continue
        value = payload[name]
        annotation = hints.get(name, param.annotation)
        try:
            coerced[name] = _coerce_to_annotation(value, annotation)
        except Exception as exc:
            return None, f"Invalid value for '{name}': {exc}"

    return coerced, None


def _validate_resource_uri(uri: str) -> tuple[bool, str | None]:
    if not uri.startswith("file://"):
        return False, "Resource URI must start with file://"
    if uri == "file://":
        return True, None

    path = uri[len("file://") :]
    if not path:
        return False, "Use file:// to list all resources or file://<relative_path> to read one."
    if path.startswith("/"):
        return False, "Absolute paths are not allowed. Use file://<relative_path>."
    if len(path) >= 2 and path[1] == ":":
        return False, "Drive-letter absolute paths are not allowed. Use relative paths."

    parts = [p for p in path.split("/") if p]
    if any(part == ".." for part in parts):
        return False, "Path traversal is not allowed in resource URIs."

    return True, None


def _print_tools() -> int:
    print("Available MCP tool functions:")
    for name in sorted(TOOLS):
        print(f"- {_format_signature(name, TOOLS[name])}")
    return 0


def _print_tool_info(name: str) -> int:
    fn = TOOLS.get(name)
    if fn is None:
        print(f"Unknown tool: {name}", file=sys.stderr)
        print("Run with --list to see valid names.", file=sys.stderr)
        return 2

    print(f"Tool: {name}")
    print(f"Signature: {_format_signature(name, fn)}")
    print("Documentation:")
    print(_doc_preview(fn))
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
    print("Examples:")
    print("- --read-resource file://")
    print("- --read-resource file://bill_gates.wiki.raw")
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
    valid, error = _validate_resource_uri(uri)
    if not valid:
        print(error, file=sys.stderr)
        return 2

    if uri == "file://":
        raw = RESOURCES["file://"]()
    else:
        path = uri[len("file://") :]
        raw = RESOURCES["file://{path}"](path)

    _print_json_or_raw(raw)
    return 0


def _invoke_tool(name: str, args_json: str) -> int:
    if name not in TOOLS:
        print(f"Unknown tool: {name}", file=sys.stderr)
        print("Run with --list to see valid names.", file=sys.stderr)
        return 2

    payload, error = _parse_json_object(args_json, flag_name="--args-json")
    if error is not None:
        print(error, file=sys.stderr)
        return 2

    fn = TOOLS[name]
    coerced, error = _coerce_payload(fn, payload or {})
    if error is not None:
        print(f"Invalid arguments for {name}: {error}", file=sys.stderr)
        return 2

    try:
        raw = fn(**(coerced or {}))
    except TypeError as exc:
        print(f"Invalid arguments for {name}: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Tool execution failed: {exc}", file=sys.stderr)
        return 1

    _print_json_or_raw(raw)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List and execute KnowledgeMCP tool functions locally."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available tool function names and signatures",
    )
    parser.add_argument(
        "--tool-info",
        type=str,
        help="Show signature and documentation preview for one tool",
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

    if args.tool_info:
        return _print_tool_info(args.tool_info)

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
