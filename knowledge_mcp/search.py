"""
Lexical search over knowledge files using BM25-inspired TF-IDF scoring.

No external dependencies required — uses stdlib only.

NOTE: This is a lexical (term-frequency) implementation. It works well for
exact and near-exact term matching. For true vector semantic search, upgrade
to embedding-based scoring via the LM Studio /v1/embeddings endpoint and
store per-chunk embedding vectors in a sidecar file.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from rag_guardian.env import KNOWLEDGE_DIR
from knowledge_mcp.reader import _resolve_safe, parse_uri


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokenizer supporting latin/accented characters."""
    return re.findall(r"[\w\u00c0-\u024f]+", text.lower())


def _chunk_lines(
    abs_path: Path, chunk_size: int
) -> list[tuple[int, int, str]]:
    """
    Split a file into non-overlapping chunks of chunk_size lines.

    Returns list of (start_line, end_line, text) tuples (1-indexed).
    """
    lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines(
        keepends=True
    )
    chunks = []
    for i in range(0, len(lines), chunk_size):
        slice_ = lines[i : i + chunk_size]
        start = i + 1
        end = i + len(slice_)
        chunks.append((start, end, "".join(slice_)))
    return chunks


# ---------------------------------------------------------------------------
# Public search function
# ---------------------------------------------------------------------------


def search(
    query: str,
    rel_paths: list[str],
    top_k: int = 5,
    chunk_size: int = 20,
) -> list[dict]:
    """
    BM25-inspired lexical search over one or more knowledge files.

    Parameters
    ----------
    query      : search query string
    rel_paths  : relative paths or file:// URIs to search in
    top_k      : maximum number of results to return
    chunk_size : lines per scoring chunk (default 20)

    Returns
    -------
    List of result dicts sorted by score descending:
        uri        str   – file:// URI
        rel_path   str
        start_line int
        end_line   int
        score      float – BM25-inspired relevance score
        excerpt    str   – first 300 chars of the matching chunk
    """
    query_terms = Counter(_tokenize(query))
    if not query_terms:
        return []

    results: list[dict] = []

    for raw_path in rel_paths:
        rel = parse_uri(raw_path)
        try:
            abs_path = _resolve_safe(rel)
        except (ValueError, FileNotFoundError):
            continue

        chunks = _chunk_lines(abs_path, chunk_size)
        if not chunks:
            continue

        # Pre-tokenize all chunks and compute document frequency per term
        tokenized: list[tuple[int, int, str, Counter]] = []
        doc_freq: Counter = Counter()

        for start, end, text in chunks:
            terms = Counter(_tokenize(text))
            tokenized.append((start, end, text, terms))
            for term in terms:
                doc_freq[term] += 1

        n = len(chunks)

        for start, end, text, terms in tokenized:
            chunk_len = sum(terms.values()) or 1
            score = 0.0
            for term, qf in query_terms.items():
                tf = terms.get(term, 0) / chunk_len
                # Smooth IDF: log((N+1)/(df+1)) + 1
                idf = math.log((n + 1) / (doc_freq.get(term, 0) + 1)) + 1
                score += tf * idf * qf

            if score > 0:
                results.append(
                    {
                        "uri": f"file://{rel}",
                        "rel_path": rel,
                        "start_line": start,
                        "end_line": end,
                        "score": round(score, 6),
                        "excerpt": text[:300].rstrip(),
                    }
                )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
