"""
File reading utilities for KnowledgeMCP.

Handles URI parsing and windowed (paginated) file reads with char-cap enforcement.
URI format:  file://<relative_path>
Example:     file://docs/manual-empleado.md
"""

from __future__ import annotations

from pathlib import Path

from rag_guardian.env import KNOWLEDGE_DIR, MAX_READ_CHARS


# ---------------------------------------------------------------------------
# URI parsing
# ---------------------------------------------------------------------------


def parse_uri(uri: str) -> str:
    """
    Convert a file:// URI to a relative path string.

    Examples
    --------
    >>> parse_uri("file://rag_source.txt")
    'rag_source.txt'
    >>> parse_uri("file://docs/manual-empleado.md")
    'docs/manual-empleado.md'
    """
    if uri.startswith("file://"):
        return uri[len("file://"):]
    # Accept bare relative paths as a convenience
    return uri


def _resolve_safe(rel_path: str) -> Path:
    """
    Resolve rel_path inside KNOWLEDGE_DIR and raise ValueError if it escapes.
    """
    abs_path = (KNOWLEDGE_DIR / rel_path).resolve()
    try:
        abs_path.relative_to(KNOWLEDGE_DIR.resolve())
    except ValueError:
        raise ValueError(f"Path '{rel_path}' escapes the knowledge directory.")
    if not abs_path.exists():
        raise FileNotFoundError(f"File not found in knowledge base: {rel_path}")
    return abs_path


# ---------------------------------------------------------------------------
# Windowed reader
# ---------------------------------------------------------------------------


def read_windowed(rel_path: str, start_line: int = 1, end_line: int = 200) -> dict:
    """
    Read lines [start_line, end_line] (1-indexed, inclusive) from a knowledge file.

    Enforces MAX_READ_CHARS: if the requested window exceeds the limit the
    end_line is truncated and a `truncated` flag is set in the response.

    Parameters
    ----------
    rel_path : str
        Relative path from knowledge root, or a file:// URI.
    start_line : int
        First line to read (1-indexed).
    end_line : int
        Last line to read (inclusive, 1-indexed).

    Returns
    -------
    dict with keys:
        ok          bool
        content     str   – joined lines
        start_line  int   – actual start
        end_line    int   – actual end (may be less than requested if truncated)
        total_lines int   – total line count in the file
        truncated   bool  – True if char cap forced an early stop
        error       str   – only present on failure
    """
    rel_path = parse_uri(rel_path)

    try:
        abs_path = _resolve_safe(rel_path)
    except (ValueError, FileNotFoundError) as exc:
        return {"ok": False, "error": str(exc)}

    try:
        all_lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except OSError as exc:
        return {"ok": False, "error": f"Could not read file: {exc}"}

    total = len(all_lines)

    # Clamp to valid range
    start = max(1, start_line)
    end = min(end_line, total)

    if start > total:
        return {
            "ok": True,
            "content": "",
            "start_line": start,
            "end_line": start - 1,
            "total_lines": total,
            "truncated": False,
        }

    # Collect lines up to MAX_READ_CHARS
    chars_accumulated = 0
    actual_end = start - 1
    selected: list[str] = []

    for line in all_lines[start - 1 : end]:
        if chars_accumulated + len(line) > MAX_READ_CHARS:
            break
        selected.append(line)
        chars_accumulated += len(line)
        actual_end += 1

    content = "".join(selected)
    truncated = actual_end < end

    return {
        "ok": True,
        "content": content,
        "start_line": start,
        "end_line": actual_end,
        "total_lines": total,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Directory listing
# ---------------------------------------------------------------------------


def list_files(subpath: str = "") -> list[dict]:
    """
    Walk knowledge/ (or a subdirectory) and return file info dicts.

    Each entry contains filesystem facts only (no metadata loaded here —
    the server layer calls metadata.get_meta() separately to avoid circular
    imports and to keep this module side-effect-free).
    """
    base = KNOWLEDGE_DIR
    if subpath:
        base = base / subpath

    if not base.exists():
        return []

    entries = []
    for p in sorted(base.rglob("*")):
        # Skip hidden meta directory and its contents
        if ".knowledge_meta" in p.parts:
            continue
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(KNOWLEDGE_DIR).as_posix()
        except ValueError:
            continue
        entries.append({
            "uri": f"file://{rel}",
            "rel_path": rel,
            "name": p.name,
            "size_bytes": p.stat().st_size,
        })

    return entries
