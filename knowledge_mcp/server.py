"""
KnowledgeMCP — MCP server for structured knowledge base access.

Exposes files under knowledge/ as paginated, metadata-rich resources
accessible via the Model Context Protocol (stdio transport).

Run directly:
    python -m knowledge_mcp.server

Or as an MCP server entry point:
    python knowledge_mcp/server.py

Tools exposed
-------------
list_knowledge_files              List files with metadata (tokens, summary, magic_filters…)
read_knowledge_file               Read a file slice by URI + line range
index_knowledge_file              (Re)index a file to refresh its metadata
semantic_search                   BM25 lexical search across one or more files
trigger_summary_generation        AI: generate a concise document summary
trigger_magic_filter_generation   AI: auto-divide a document into labelled sections
trigger_faq_generation            AI: generate Q&A pairs from a document

Resources
---------
file://            List all files (same as list_knowledge_files with no args)
file://{path}      Read first page of a specific file
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is importable when running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP

from env import KNOWLEDGE_PAGE_SIZE
from knowledge_mcp.metadata import MetaRecord, get_meta, index_file, save_meta
from knowledge_mcp.reader import list_files, parse_uri, read_windowed
from knowledge_mcp import search as _search
from knowledge_mcp import ai_tasks as _ai

mcp = FastMCP(
    name="KnowledgeMCP",
    instructions=(
        "Access structured knowledge files. "
        "Use list_knowledge_files to discover available documents, "
        "then read_knowledge_file to retrieve content page by page."
    ),
)


# ---------------------------------------------------------------------------
# Tool: list_knowledge_files
# ---------------------------------------------------------------------------


@mcp.tool()
def list_knowledge_files(path: str = "") -> str:
    """
    List files in the knowledge base with their metadata.

    Parameters
    ----------
    path : str, optional
        Subdirectory to list (relative to knowledge root). Defaults to root.

    Returns
    -------
    JSON array of compact objects with only:
        uri          str   - file:// URI of the file
        total_files  int   - number of files in the listing
        total_tokens int   - aggregate estimated token count
        summary      str   - per-file summary (fallback when empty)
    """
    entries = list_files(path)
    rows = []
    total_tokens = 0

    def _truncate(text: str, max_chars: int = 240) -> str:
        cleaned = " ".join((text or "").split())
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max_chars - 3].rstrip() + "..."

    def _fallback_summary(rel_path: str) -> str:
        window = read_windowed(rel_path, start_line=1, end_line=20)
        if not window.get("ok"):
            return "No summary available yet."

        content = (window.get("content") or "").strip()
        if not content:
            return "No summary available yet."

        return _truncate(content)

    for entry in entries:
        rel = entry["rel_path"]
        meta = get_meta(rel)
        total_tokens += meta.token_count
        summary = (meta.summary or "").strip()
        if not summary:
            summary = _fallback_summary(rel)
        rows.append(
            {
                "uri": entry["uri"],
                "summary": summary,
            }
        )

    compact = [
        {
            "uri": row["uri"],
            "total_files": len(rows),
            "total_tokens": total_tokens,
            "summary": row["summary"],
        }
        for row in rows
    ]
    return json.dumps(compact, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool: read_knowledge_file
# ---------------------------------------------------------------------------


@mcp.tool()
def read_knowledge_file(
    uri: str,
    start_line: int = 1,
    end_line: int = KNOWLEDGE_PAGE_SIZE,
) -> str:
    """
    Read a slice of a knowledge file by URI and line range.

    Parameters
    ----------
    uri : str
        file:// URI from list_knowledge_files, e.g.
        file://rag_source.txt  or  file://docs/manual-empleado.md
    start_line : int
        First line to read (1-indexed, default 1).
    end_line : int
        Last line to read inclusive (default 200). Reading stops earlier if
        the char limit (MAX_READ_CHARS) is reached; check `truncated` in response.

    Returns
    -------
    JSON object with:
        ok          bool
        content     str   - file text for the requested slice
        start_line  int
        end_line    int   - actual end (may differ if truncated)
        total_lines int   - total lines in the file
        truncated   bool  - True when char cap forced early termination
        error       str   - present only on failure
    """
    rel = parse_uri(uri)
    result = read_windowed(rel, start_line=start_line, end_line=end_line)
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool: index_knowledge_file
# ---------------------------------------------------------------------------


@mcp.tool()
def index_knowledge_file(uri: str) -> str:
    """
    (Re)index a knowledge file to refresh its filesystem-derived metadata.

    Recomputes token_count, file_type, and created_at from the file on disk.
    Preserves any existing summary, magic_filters, and faqs.

    Parameters
    ----------
    uri : str
        file:// URI of the file to index.

    Returns
    -------
    JSON object with the updated metadata record, or an error field on failure.
    """
    rel = parse_uri(uri)
    try:
        meta = index_file(rel)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    from dataclasses import asdict
    return json.dumps({"ok": True, **asdict(meta)}, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool: semantic_search  (1.1.3)
# ---------------------------------------------------------------------------


@mcp.tool()
def semantic_search(
    query: str,
    uris: list[str] | None = None,
    top_k: int = 5,
    chunk_size: int = 20,
) -> str:
    """
    Lexical (BM25-inspired) search over one or more knowledge files.

    When called by an agent, combine with query rephrasing for best results —
    e.g. rephrase "books with animal names by Shakespeare" as
    "Shakespeare titles animals" before calling this tool.

    Parameters
    ----------
    query      : search query string
    uris       : list of file:// URIs to search in;
                 omit or pass null to search all files in the knowledge base
    top_k      : maximum number of results to return (default 5)
    chunk_size : lines per scoring chunk (default 20)

    Returns
    -------
    JSON array of result objects sorted by relevance score, each with:
        uri        str   – file:// URI of the source file
        start_line int   – first line of the matching chunk
        end_line   int   – last line of the matching chunk
        score      float – relevance score (higher = more relevant)
        excerpt    str   – up to 300 chars from the matching chunk
    """
    if not uris:
        # Default to all files in the knowledge base
        uris = [e["uri"] for e in list_files()]

    results = _search.search(
        query=query,
        rel_paths=[parse_uri(u) for u in uris],
        top_k=top_k,
        chunk_size=chunk_size,
    )
    return json.dumps(results, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool: trigger_summary_generation  (2.0)
# ---------------------------------------------------------------------------


@mcp.tool()
def trigger_summary_generation(uri: str) -> str:
    """
    Use the LLM to generate a concise summary from a document.

    Stores the summary in metadata.summary and returns it.

    Parameters
    ----------
    uri : str
        file:// URI of the file to process.

    Returns
    -------
    JSON object with:
        ok       bool
        summary  str
        error    str  - present only on failure
    """
    rel = parse_uri(uri)
    try:
        summary = _ai.generate_summary(rel)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    return json.dumps(
        {
            "ok": True,
            "summary": summary,
        },
        indent=2,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Tool: trigger_magic_filter_generation  (2.1)
# ---------------------------------------------------------------------------


@mcp.tool()
def trigger_magic_filter_generation(uri: str) -> str:
    """
    Use the LLM to auto-divide a document into labelled sections (magic filters).

    Analyses the full document and identifies logical divisions such as chapters,
    financial quarters, clauses, or any natural structural units. The result is
    persisted to the file's metadata sidecar and returned.

    After this runs, list_knowledge_files will include the magic_filters for this
    file, allowing agents to jump directly to relevant sections.

    Parameters
    ----------
    uri : str
        file:// URI of the file to process.

    Returns
    -------
    JSON object with:
        ok             bool
        magic_filters  list – generated MagicFilter objects
        error          str  – present only on failure
    """
    rel = parse_uri(uri)
    try:
        filters = _ai.generate_magic_filters(rel)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    return json.dumps(
        {
            "ok": True,
            "magic_filters": [
                {
                    "label": mf.label,
                    "start_line": mf.start_line,
                    "end_line": mf.end_line,
                    "description": mf.description,
                }
                for mf in filters
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Tool: trigger_faq_generation  (2.2)
# ---------------------------------------------------------------------------


@mcp.tool()
def trigger_faq_generation(uri: str, n_questions: int = 10) -> str:
    """
    Use the LLM to generate pre-analyzed Q&A pairs from a document.

    Extracts the most important facts, figures, and topics as question-answer
    pairs. These FAQs are persisted to the metadata sidecar and can be
    retrieved instantly via list_knowledge_files — useful for fast retrieval
    without re-reading the full document.

    Parameters
    ----------
    uri         : str – file:// URI of the file to process
    n_questions : int – number of Q&A pairs to generate (default 10)

    Returns
    -------
    JSON object with:
        ok    bool
        faqs  list – generated FAQ objects with 'question' and 'answer' keys
        error str  – present only on failure
    """
    rel = parse_uri(uri)
    try:
        faqs = _ai.generate_faqs(rel, n_questions=n_questions)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    return json.dumps(
        {
            "ok": True,
            "faqs": [
                {"question": f.question, "answer": f.answer}
                for f in faqs
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("file://")
def resource_list_all() -> str:
    """List all knowledge files (resource view of list_knowledge_files)."""
    return list_knowledge_files()


@mcp.resource("file://{path}")
def resource_read_file(path: str) -> str:
    """Read the first page of a knowledge file."""
    return read_knowledge_file(
        uri=f"file://{path}",
        start_line=1,
        end_line=KNOWLEDGE_PAGE_SIZE,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    mcp.run(transport="stdio")
