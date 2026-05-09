# ============================================================================
# Windowed File Reading (10k char limit enforced)
# ============================================================================


import subprocess
import textwrap
from typing import Any

from .env import MAX_READ_CHARS, SANDBOX_DIR
from .utils import append_trace, read_file_lines, resolve_sandbox_path, write_file_text


def wrap_file_lines(path_str: str, max_chars_per_line: int = 100, output_path: str | None = None) -> dict[str, Any]:
    """
    Reflow file content so each output line is at most max_chars_per_line.
    Writes to output_path if provided, otherwise rewrites path_str in place.
    """
    if max_chars_per_line < 20:
        return {"ok": False, "error": "max_chars_per_line must be >= 20"}

    try:
        source = resolve_sandbox_path(path_str, must_exist=True)
        target_rel = output_path or path_str
        target = resolve_sandbox_path(target_rel)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    original_lines = read_file_lines(source)
    wrapped_lines: list[str] = []

    for line in original_lines:
        if line == "":
            wrapped_lines.append("")
            continue

        if len(line) <= max_chars_per_line:
            wrapped_lines.append(line)
            continue

        chunks = textwrap.wrap(
            line,
            width=max_chars_per_line,
            break_long_words=True,
            break_on_hyphens=False,
            drop_whitespace=False,
            replace_whitespace=False,
        )
        wrapped_lines.extend(chunks if chunks else [line])

    wrapped_content = "\n".join(wrapped_lines)
    if original_lines:
        wrapped_content += "\n"

    write_file_text(target, wrapped_content, append=False)

    return {
        "ok": True,
        "source_file": path_str,
        "output_file": target_rel,
        "max_chars_per_line": max_chars_per_line,
        "original_line_count": len(original_lines),
        "wrapped_line_count": len(wrapped_lines),
    }


def read_file_windowed(path_str: str, start_line: int, end_line: int) -> dict[str, Any]:
    """
    Read file between start_line and end_line (1-indexed, inclusive).
    Enforces max 10,000 characters. Returns error if exceeded.
    Includes awareness metadata: total lines, lines returned, chars read, has_more.
    """
    try:
        path = resolve_sandbox_path(path_str, must_exist=True)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    if start_line < 1 or end_line < start_line:
        return {"ok": False, "error": "start_line >= 1 and end_line >= start_line required"}

    all_lines = read_file_lines(path)
    total_lines = len(all_lines)

    if start_line > total_lines:
        return {
            "ok": True,
            "file": path_str,
            "start_line": start_line,
            "end_line": start_line,
            "total_lines": total_lines,
            "lines": [],
            "characters_read": 0,
            "has_more": False,
            "message": "start_line exceeds file length"
        }

    actual_end = min(end_line, total_lines)
    selected_lines = all_lines[start_line - 1:actual_end]

    # Join and check character limit
    content = "\n".join(selected_lines)
    char_count = len(content)

    if char_count > MAX_READ_CHARS:
        # Estimate how many lines fit within the char limit
        lines_in_range = actual_end - start_line + 1
        avg_chars_per_line = char_count / max(lines_in_range, 1)
        safe_lines = max(1, int(MAX_READ_CHARS / avg_chars_per_line) - 1)
        suggested_end = start_line + safe_lines - 1
        return {
            "ok": False,
            "error": f"Range {start_line}-{actual_end} exceeds {MAX_READ_CHARS} character limit ({char_count} chars). "
                     f"Lines are ~{int(avg_chars_per_line)} chars each. "
                     f"Suggest: read lines {start_line} to {suggested_end} instead.",
            "file": path_str,
            "total_lines": total_lines,
            "suggested_max_end": suggested_end
        }

    has_more = actual_end < total_lines
    next_start = actual_end + 1 if has_more else None

    return {
        "ok": True,
        "file": path_str,
        "start_line": start_line,
        "end_line": actual_end,
        "total_lines": total_lines,
        "lines": selected_lines,
        "characters_read": char_count,
        "has_more": has_more,
        "next_window": f"{next_start}-{min(next_start + 100, total_lines)}" if (has_more and next_start is not None) else None
    }


# ============================================================================
# Tool Executors
# ============================================================================

def tool_read_file_windowed(path: str, start_line: int, end_line: int) -> dict:
    result = read_file_windowed(path, start_line, end_line)
    append_trace({"tool": "read_file_windowed", "path": path, "start_line": start_line, "end_line": end_line, "result": result})
    return result


def tool_wrap_file_lines(path: str, max_chars_per_line: int = 100, output_path: str | None = None) -> dict:
    result = wrap_file_lines(path, max_chars_per_line=max_chars_per_line, output_path=output_path)
    append_trace({
        "tool": "wrap_file_lines",
        "path": path,
        "output_path": output_path,
        "max_chars_per_line": max_chars_per_line,
        "result": result,
    })
    return result


def tool_create_file(path: str, content: str, overwrite: bool = False) -> dict:
    try:
        resolved = resolve_sandbox_path(path)
        if resolved.exists() and not overwrite:
            return {"ok": False, "error": f"File exists and overwrite=False: {path}"}
        write_file_text(resolved, content, append=False)
        result = {"ok": True, "file": path, "size_bytes": len(content)}
        append_trace({"tool": "create_file", "path": path, "result": result})
        return result
    except Exception as e:
        result = {"ok": False, "error": str(e)}
        append_trace({"tool": "create_file", "path": path, "result": result})
        return result


def tool_append_to_file(path: str, content: str) -> dict:
    try:
        resolved = resolve_sandbox_path(path)
        if not resolved.exists():
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text("", encoding="utf-8")
        write_file_text(resolved, content, append=True)
        result = {"ok": True, "file": path, "appended_bytes": len(content)}
        append_trace({"tool": "append_to_file", "path": path, "result": result})
        return result
    except Exception as e:
        result = {"ok": False, "error": str(e)}
        append_trace({"tool": "append_to_file", "path": path, "result": result})
        return result


def tool_delete_file(path: str) -> dict:
    try:
        resolved = resolve_sandbox_path(path, must_exist=True)
        resolved.unlink()
        result = {"ok": True, "file": path}
        append_trace({"tool": "delete_file", "path": path, "result": result})
        return result
    except Exception as e:
        result = {"ok": False, "error": str(e)}
        append_trace({"tool": "delete_file", "path": path, "result": result})
        return result


def tool_list_sandbox_files(max_files: int = 100) -> dict:
    try:
        files = sorted(SANDBOX_DIR.rglob("*"))
        entries = [
            str(f.relative_to(SANDBOX_DIR))
            for f in files
            if f.is_file()
        ][:max_files]
        result = {"ok": True, "files": entries, "count": len(entries)}
        append_trace({"tool": "list_sandbox_files", "result": result})
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def tool_execute_shell_command(command: str, timeout_seconds: int = 30) -> dict:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(SANDBOX_DIR)
        )
        output = {
            "ok": True,
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout[:5000],  # Truncate for context
            "stderr": result.stderr[:2000]
        }
        append_trace({"tool": "execute_shell_command", "command": command, "exit_code": result.returncode})
        return output
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timeout after {timeout_seconds}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file_windowed",
            "description": "Read a file by line window. REQUIRED: specify start_line and end_line. "
                          "Maximum 10,000 characters per read; if exceeded, returns an error forcing a smaller window. "
                          "Returns metadata: total lines, lines read, characters, whether more content exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside sandbox (e.g. rag_source.txt)"},
                    "start_line": {"type": "integer", "description": "Starting line number (1-indexed)"},
                    "end_line": {"type": "integer", "description": "Ending line number (1-indexed, inclusive)"}
                },
                "required": ["path", "start_line", "end_line"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wrap_file_lines",
            "description": "Rewrite or create a wrapped copy of a file so each line is at most N characters (default 100). "
                          "Useful before read_file_windowed when raw files have very long lines and hit character limits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside sandbox (source file)"},
                    "max_chars_per_line": {"type": "integer", "description": "Max characters per line (default: 100)"},
                    "output_path": {"type": "string", "description": "Optional destination path; if omitted, rewrites source file"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create or overwrite a file in sandbox. Supports any format: JSONL, CSV, txt, py, db, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside sandbox (e.g. results.jsonl)"},
                    "content": {"type": "string", "description": "File content"},
                    "overwrite": {"type": "boolean", "description": "If true, overwrite; if false, fail if file exists"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "append_to_file",
            "description": "Append text to the end of an existing file in sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside sandbox"},
                    "content": {"type": "string", "description": "Text to append"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file inside sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside sandbox"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_sandbox_files",
            "description": "List files inside sandbox/ (up to 100 by default).",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_files": {"type": "integer", "description": "Maximum number of files to return"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_shell_command",
            "description": "Execute a shell command inside sandbox. Returns stdout, stderr, exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute (e.g. python script.py)"},
                    "timeout_seconds": {"type": "integer", "description": "Timeout in seconds (default: 30)"}
                },
                "required": ["command"]
            }
        }
    },
]


# Maps tool name → callable so dispatch is O(1) and easy to extend.
TOOL_REGISTRY: dict[str, Any] = {
    "read_file_windowed": tool_read_file_windowed,
    "wrap_file_lines": tool_wrap_file_lines,
    "create_file": tool_create_file,
    "append_to_file": tool_append_to_file,
    "delete_file": tool_delete_file,
    "list_sandbox_files": tool_list_sandbox_files,
    "execute_shell_command": tool_execute_shell_command,
}


def dispatch_tool(tool_name: str, tool_args: dict) -> dict:
    """Look up and call a tool by name. Returns an error dict for unknown tools."""
    handler = TOOL_REGISTRY.get(tool_name)
    if handler is None:
        return {"ok": False, "error": f"Unknown tool: {tool_name}"}
    return handler(**tool_args)
