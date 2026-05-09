"""
AI-powered background tasks for KnowledgeMCP.

Uses the local LM Studio endpoint to:
    - generate_summary        : produce a concise document summary
  - generate_magic_filters : auto-divide a document into labelled sections
  - generate_faqs           : extract Q&A pairs from a document

Both functions read the file content, call the LLM with a structured prompt,
parse the JSON response, and persist results to the metadata sidecar.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_guardian.env import AI_TASK_MAX_DOC_CHARS, KNOWLEDGE_DIR, LLM_MAX_TOKENS, MODEL_NAME
from knowledge_mcp.metadata import FAQ, MagicFilter, get_meta, save_meta
from rag_guardian.utils import build_client


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_full(rel_path: str, char_limit: int | None = None) -> tuple[str, int]:
    """
    Read up to char_limit characters from a knowledge file.

        Defaults to AI_TASK_MAX_DOC_CHARS — a conservative limit that accounts for
        poor tokenisation ratios in non-English / wiki-markup text.

    Returns (content, total_line_count).
    """
    if char_limit is None:
                char_limit = AI_TASK_MAX_DOC_CHARS

    abs_path = KNOWLEDGE_DIR / rel_path
    text = abs_path.read_text(encoding="utf-8", errors="replace")
    total_lines = text.count("\n") + 1
    return text[:char_limit], total_lines


def _extract_json_object(text: str) -> str | None:
    """
    Extract the first JSON object from an LLM response.
    Handles responses that wrap JSON in markdown code fences.
    """
    text = re.sub(r"```(?:json)?", "", text).strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_json_array(text: str) -> str | None:
    """
    Extract the first JSON array from an LLM response.
    Handles responses that wrap JSON in markdown code fences.
    """
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find outermost JSON array
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _call_llm(system: str, user: str) -> str:
    client = build_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=LLM_MAX_TOKENS,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# 2.0 - Summary generation
# ---------------------------------------------------------------------------


def generate_summary(rel_path: str, max_chars: int = 500) -> str:
    """
    Use the LLM to produce a concise summary for a document.

    Saves the result to metadata.summary and returns the summary text.

    Parameters
    ----------
    rel_path : str
        Relative path from the knowledge root.
    max_chars : int
        Maximum summary length to persist (default 500 chars).
    """
    content, total_lines = _read_full(rel_path)

    system = (
        "You are a concise document summarization assistant. "
        "Always respond with valid JSON only - no markdown, no extra text."
    )
    user = f"""Read the document below and write a concise, factual summary.

Return a JSON object with exactly this key:
  "summary" - one compact paragraph (3-6 sentences) describing the core points

Rules:
- Use only information present in the document.
- Keep the summary neutral and clear.
- Do not include lists or markdown formatting.

Document ({total_lines} lines):
{content}"""

    raw = _call_llm(system, user)
    json_str = _extract_json_object(raw)
    if json_str is None:
        raise RuntimeError(
            f"LLM returned no JSON object for summary.\nRaw response: {raw[:500]}"
        )

    try:
        item = json.loads(json_str)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Could not parse summary JSON: {exc}\nRaw: {raw[:500]}"
        ) from exc

    summary = str(item.get("summary", "")).strip()
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "..."

    meta = get_meta(rel_path)
    meta.summary = summary
    save_meta(rel_path, meta)
    return summary


# ---------------------------------------------------------------------------
# 2.1 — Magic filter generation
# ---------------------------------------------------------------------------


def generate_magic_filters(rel_path: str) -> list[MagicFilter]:
    """
    Use the LLM to identify logical sections in a document.

    Analyses the full file content and asks the model to divide it into
    named, non-overlapping sections (e.g. chapters, quarters, clauses).
    Saves the result to metadata.magic_filters and returns the list.

    Parameters
    ----------
    rel_path : str
        Relative path from the knowledge root.
    """
    content, total_lines = _read_full(rel_path)

    system = (
        "You are a document structure analyst. "
        "Always respond with valid JSON only — no markdown, no extra text."
    )
    user = f"""Analyze the document below and identify its logical sections or divisions.

Return a JSON array. Each item must have exactly these keys:
  "label"       – short section name (e.g. "Introduction", "Q1 Results", "Clause 3")
  "start_line"  – integer, first line of the section (1-indexed, min 1, max {total_lines})
  "end_line"    – integer, last line of the section (1-indexed, min 1, max {total_lines})
  "description" – one sentence describing what this section contains

Rules:
- Sections must be non-overlapping and ordered by line number.
- Together they should cover the full document (line 1 to {total_lines}).
- Aim for 3-10 sections depending on document length.

Document ({total_lines} lines total):
{content}"""

    raw = _call_llm(system, user)
    json_str = _extract_json_array(raw)
    if json_str is None:
        raise RuntimeError(
            f"LLM returned no JSON array for magic filters.\nRaw response: {raw[:500]}"
        )

    try:
        items = json.loads(json_str)
        filters = [
            MagicFilter(
                label=str(item.get("label", f"Section {i + 1}")),
                start_line=max(1, int(item.get("start_line", 1))),
                end_line=min(total_lines, int(item.get("end_line", total_lines))),
                description=str(item.get("description", "")),
            )
            for i, item in enumerate(items)
            if isinstance(item, dict)
        ]
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Could not parse magic filter JSON: {exc}\nRaw: {raw[:500]}"
        ) from exc

    meta = get_meta(rel_path)
    meta.magic_filters = filters
    save_meta(rel_path, meta)
    return filters


# ---------------------------------------------------------------------------
# 2.2 — FAQ generation
# ---------------------------------------------------------------------------


def generate_faqs(rel_path: str, n_questions: int = 10) -> list[FAQ]:
    """
    Use the LLM to extract Q&A pairs from a document.

    Generates pre-analyzed question-answer pairs that agents can retrieve
    quickly without re-reading the full file.
    Saves the result to metadata.faqs and returns the list.

    Parameters
    ----------
    rel_path    : str  – relative path from the knowledge root
    n_questions : int  – number of Q&A pairs to generate (default 10)
    """
    content, total_lines = _read_full(rel_path)

    system = (
        "You are a document analysis assistant. "
        "Always respond with valid JSON only — no markdown, no extra text."
    )
    user = f"""Read the document below and generate {n_questions} useful question-answer pairs.
Focus on the most important facts, figures, names, dates, and topics a reader would ask about.

Return a JSON array. Each item must have exactly these keys:
  "question" – a clear, specific question
  "answer"   – a concise answer (1-3 sentences) based solely on the document

Return ONLY the JSON array, no other text.

Document ({total_lines} lines):
{content}"""

    raw = _call_llm(system, user)
    json_str = _extract_json_array(raw)
    if json_str is None:
        raise RuntimeError(
            f"LLM returned no JSON array for FAQs.\nRaw response: {raw[:500]}"
        )

    try:
        items = json.loads(json_str)
        faqs = [
            FAQ(
                question=str(f.get("question", "")),
                answer=str(f.get("answer", "")),
            )
            for f in items
            if isinstance(f, dict)
        ]
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Could not parse FAQ JSON: {exc}\nRaw: {raw[:500]}"
        ) from exc

    meta = get_meta(rel_path)
    meta.faqs = faqs
    save_meta(rel_path, meta)
    return faqs
