# AGENTS.md

## Scope
Applies to the whole repository.

## Goal
Help coding agents make safe, fast changes across the autonomous loop and KnowledgeMCP server without breaking runtime behavior.

## Start Here
- Project overview and setup: [README.md](README.md)
- Runnable shortcuts and variables: [Makefile](Makefile)
- Runtime limits and paths: [src/rag_guardian/env.py](src/rag_guardian/env.py)

## Fast Commands
Run from repository root.

- Create/check venv manually:
  - .venv/bin/python should exist before running Make targets.
- LM Studio connectivity check:
  - make test-lmstudio
- Run MCP server:
  - make run-mcp
- Run MCP server in debug mode (unbuffered output/error):
  - make run-mcp-debug
- Inspect MCP tools interactively (MCP Inspector UI):
  - make inspect-mcp
- Generate metadata once:
  - make gen-once
- Metadata status:
  - make status

## MCP Debugging & Testing
Interactive MCP tool exploration and testing:

- List available MCP tools with signatures:
  - make mcp-tools-list
- Show detailed signature and docs for one tool:
  - make mcp-tool-info TOOL=<tool_name>
- Execute a single MCP tool from command line:
  - make mcp-tool-run TOOL=<tool_name> ARGS='{"key":"value"}'
- Interactive MCP shell (REPL with hot-reload):
  - make mcp-shell
  - Inside shell: help, list, info <tool>, capabilities, resources, resource <uri>, prompts, tool <name>, args <json>, run, r (rerun), call <name> <json>, show, exit

- Run endpoint test suite:
  - python -m unittest discover -s tests -v

**Example workflow in mcp-shell:**
```
mcp> list
mcp> info semantic_search
mcp> tool semantic_search
mcp> args {"query":"Bill Gates","top_k":3}
mcp> run
mcp> r
```

## Architecture Map
- Autonomous tool-calling loop: [src/rag_guardian/main.py](src/rag_guardian/main.py)
- Local agent tools for sandbox operations: [src/rag_guardian/tools.py](src/rag_guardian/tools.py)
- MCP server tools and resource handlers: [knowledge_mcp/server.py](knowledge_mcp/server.py)
- Knowledge file IO and URI parsing: [knowledge_mcp/reader.py](knowledge_mcp/reader.py)
- Sidecar metadata model and persistence: [knowledge_mcp/metadata.py](knowledge_mcp/metadata.py)
- Search ranking logic: [knowledge_mcp/search.py](knowledge_mcp/search.py)
- AI generation tasks (FAQs, magic filters): [knowledge_mcp/ai_tasks.py](knowledge_mcp/ai_tasks.py)
- MCP tool runner (CLI, introspection, validation): [scripts/mcp_tool_runner.py](scripts/mcp_tool_runner.py)
- MCP interactive shell (REPL, hot-reload): [scripts/mcp_tool_shell.py](scripts/mcp_tool_shell.py)
- MCP endpoint test suite: [tests/test_mcp_endpoints.py](tests/test_mcp_endpoints.py)

## Repository Conventions
- Keep path safety guards intact:
  - Sandbox tooling must stay constrained by resolver logic in [tools.py](tools.py).
  - KnowledgeMCP file access must stay constrained to knowledge directory in [knowledge_mcp/reader.py](knowledge_mcp/reader.py).
- Preserve MCP tool response contracts unless explicitly changing API behavior.
- Preserve UTF-8 JSON output behavior using ensure_ascii=False in server responses.
- Keep changes minimal and scoped; avoid broad refactors unless requested.

## MCP Shell & Runner Implementation Notes
The MCP debugging suite ([scripts/mcp_tool_runner.py](scripts/mcp_tool_runner.py) and [scripts/mcp_tool_shell.py](scripts/mcp_tool_shell.py)) includes:

**Runner Features (mcp_tool_runner.py):**
- Exit code contract: 0 (success), 1 (runtime error), 2 (usage/validation error)
- Tool introspection: `--tool-info <name>` shows signature + doc preview
- Improved discoverability: `--list` now prints function signatures
- Argument coercion: validates and converts int/float/bool/Optional types before tool invocation
- Resource URI safety: rejects absolute paths (`file:///`) and traversal attempts (`..`)
- Pretty-printed JSON output with `ensure_ascii=False`

**Shell Features (mcp_tool_shell.py):**
- Interactive REPL with command history (readline support when available)
- Hot-reload behavior: each command runs in fresh subprocess (code changes picked up immediately)
- Robust `call <name> <json>` parsing (no fragile substring matching)
- Per-tool command: `info <tool>` shows signature + docs inline
- Non-zero exit hints printed to guide user action
- Clear help with JSON formatting examples

**Test Suite (tests/test_mcp_endpoints.py):**
- 10 unit tests covering all 7 tools + 2 resources
- Uses temporary fixtures to avoid touching real data
- Includes success and error-path scenarios
- Verifies JSON response shape and error handling

**Key Improvements Applied:**
- Discoverability: users can explore endpoints without reading source code
- Safety: URI validation prevents path traversal exploits
- Usability: argument coercion handles string numeric inputs gracefully
- Robustness: parsing is immune to tool names appearing in JSON payloads
- Debugging: hot-reload shell enables rapid iteration during development

## Current API Detail Worth Remembering
- list_knowledge_files currently returns a compact list where each item includes:
  - uri
  - total_files
  - total_tokens
  - summary
- This behavior is implemented in [knowledge_mcp/server.py](knowledge_mcp/server.py).
- MCP runner validates resource URIs and rejects absolute paths and traversal attempts.
- MCP shell `call <name> <json>` requires maxsplit=2 for robust parsing (not substring search).
- Argument coercion in runner handles Union types and Optional via type hints.
- Shell subprocess model ensures hot-reload: code changes picked up without restart.

## Validation Checklist After Edits
- Run targeted syntax/problem checks for touched files.
- If MCP behavior changed, run a direct function check with .venv/bin/python and verify JSON shape.
- If generation behavior changed, run make gen-once and confirm sidecar updates.

## Common Pitfalls
- LM Studio must be running locally with a loaded model before runtime tests.
- make inspect-mcp exits with Ctrl+C (exit 130) when stopped manually.
- Character/token limits are strict and defined in [src/rag_guardian/env.py](src/rag_guardian/env.py); avoid inflating prompts or read windows without reason.
- MCP runner coerces `"10"` (string) to `10` (int) automatically; this is intentional for usability.
- MCP shell `args` command requires full JSON on the same line; use quotes around multi-word values.
- Runner exit code 2 = usage/validation error (check --help); exit code 1 = tool runtime error (check stderr).
- `make mcp-shell` runs each command in a subprocess; very large operations may be slow due to startup overhead.
