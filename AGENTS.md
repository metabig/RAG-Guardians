# AGENTS.md

## Scope
Applies to the whole repository.

## Goal
Help coding agents make safe, fast changes across the autonomous loop and KnowledgeMCP server without breaking runtime behavior.

## Start Here
- Project overview and setup: [README.md](README.md)
- Runnable shortcuts and variables: [Makefile](Makefile)
- Runtime limits and paths: [env.py](env.py)

## Fast Commands
Run from repository root.

- Create/check venv manually:
  - .venv/bin/python should exist before running Make targets.
- LM Studio connectivity check:
  - make test-lmstudio
- Run MCP server:
  - make run-mcp
- Inspect MCP tools interactively:
  - make inspect-mcp
- Generate metadata once:
  - make gen-once
- Metadata status:
  - make status

## Architecture Map
- Autonomous tool-calling loop: [main.py](main.py)
- Local agent tools for sandbox operations: [tools.py](tools.py)
- MCP server tools and resource handlers: [knowledge_mcp/server.py](knowledge_mcp/server.py)
- Knowledge file IO and URI parsing: [knowledge_mcp/reader.py](knowledge_mcp/reader.py)
- Sidecar metadata model and persistence: [knowledge_mcp/metadata.py](knowledge_mcp/metadata.py)
- Search ranking logic: [knowledge_mcp/search.py](knowledge_mcp/search.py)
- AI generation tasks (FAQs, magic filters): [knowledge_mcp/ai_tasks.py](knowledge_mcp/ai_tasks.py)

## Repository Conventions
- Keep path safety guards intact:
  - Sandbox tooling must stay constrained by resolver logic in [tools.py](tools.py).
  - KnowledgeMCP file access must stay constrained to knowledge directory in [knowledge_mcp/reader.py](knowledge_mcp/reader.py).
- Preserve MCP tool response contracts unless explicitly changing API behavior.
- Preserve UTF-8 JSON output behavior using ensure_ascii=False in server responses.
- Keep changes minimal and scoped; avoid broad refactors unless requested.

## Current API Detail Worth Remembering
- list_knowledge_files currently returns a compact list where each item includes:
  - uri
  - total_files
  - total_tokens
  - summary
- This behavior is implemented in [knowledge_mcp/server.py](knowledge_mcp/server.py).

## Validation Checklist After Edits
- Run targeted syntax/problem checks for touched files.
- If MCP behavior changed, run a direct function check with .venv/bin/python and verify JSON shape.
- If generation behavior changed, run make gen-once and confirm sidecar updates.

## Common Pitfalls
- LM Studio must be running locally with a loaded model before runtime tests.
- make inspect-mcp exits with Ctrl+C (exit 130) when stopped manually.
- Character/token limits are strict and defined in [env.py](env.py); avoid inflating prompts or read windows without reason.
