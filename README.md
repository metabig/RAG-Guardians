# RAG-Guardians

Autonomous RAG experimentation project with two execution modes:

1. Autonomous tool-calling agent loop (LM Studio + OpenAI-compatible API)
2. KnowledgeMCP server for structured file retrieval, search, and background generation

The project currently uses local LM Studio with model google/gemma-4-e4b.

## What This Project Does

- Reads and processes knowledge files under knowledge/
- Exposes knowledge through MCP tools and resources
- Generates document metadata such as:
	- FAQ pairs
	- Magic filters (document section slices)
- Keeps metadata in sidecar JSON files under knowledge/.knowledge_meta/

## Project Structure

```text
.
├── env.py
├── main.py
├── tools.py
├── utils.py
├── Makefile
├── prompts/
│   └── system.py
├── sandbox/
├── sandbox_backup/
├── knowledge/
│   ├── rag_source.txt
│   └── .knowledge_meta/
│       └── rag_source.txt.json
└── knowledge_mcp/
		├── __init__.py
		├── server.py
		├── reader.py
		├── metadata.py
		├── search.py
		└── ai_tasks.py
```

## Requirements

- macOS/Linux shell (Makefile uses zsh)
- Python virtual environment at .venv/
- LM Studio running locally
- Model loaded in LM Studio:
	- google/gemma-4-e4b

## Setup

1. Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies

```bash
pip install openai "mcp[cli]"
```

3. Start LM Studio and load model google/gemma-4-e4b

4. Quick connectivity check

```bash
make test-lmstudio
```

Expected output includes model name and a short reply.

## Running Modes

### 1) Run the autonomous benchmark agent

```bash
source .venv/bin/activate
python main.py
```

This runs an infinite loop where the model can call tools defined in tools.py.

### 2) Run KnowledgeMCP server

```bash
make run-mcp
```

Equivalent to:

```bash
python -m knowledge_mcp.server
```

## Makefile Commands

```bash
make help
```

Available shortcuts:

- make test-lmstudio
- make run-mcp
- make gen-once
- make gen-loop
- make status

### Generate once

```bash
make gen-once
```

Runs:

- trigger_faq_generation
- trigger_magic_filter_generation

for URI knowledge://rag_source.txt.

### Run continuous generation loop

```bash
make gen-loop
```

Runs generation every INTERVAL seconds (default 600).

Stop with Ctrl+C.

### Override runtime variables

```bash
make gen-once URI=knowledge://mydoc.txt N=5
make gen-loop URI=knowledge://mydoc.txt N=8 INTERVAL=300
```

## Metadata Output

Generated metadata is persisted to sidecar files under:

- knowledge/.knowledge_meta/

Example:

- knowledge/.knowledge_meta/rag_source.txt.json

Check current counts:

```bash
make status
```

## KnowledgeMCP Capabilities

Current tool set in knowledge_mcp/server.py:

- list_knowledge_files
- read_knowledge_file
- index_knowledge_file
- semantic_search
- trigger_magic_filter_generation
- trigger_faq_generation

Core behavior:

- URI scheme: knowledge://<relative_path>
- Windowed file reading with line ranges
- Lexical search (BM25-inspired) via search.py
- AI generation tasks via ai_tasks.py

## Important Token/Context Notes

Gemma-4-e4b is used as a reasoning model in this setup.

Relevant values in env.py:

- MAX_CONTEXT_TOKENS = 4096
- LLM_MAX_TOKENS = 2048
- AI_TASK_MAX_DOC_CHARS = 3500

This balance avoids prompt overflow/truncated JSON in generation tasks.

## Troubleshooting

### Empty or truncated model outputs

- Increase max_tokens for generation calls (already configured in env.py)
- Keep AI_TASK_MAX_DOC_CHARS conservative
- Ensure LM Studio has the model loaded and active

### 400 Bad Request from LM Studio

- Usually prompt + completion budget exceeds loaded context
- Reduce document size or increase context in LM Studio model settings

### Makefile says missing .venv/bin/python

- Create the virtual environment first:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install openai "mcp[cli]"
```

## Quick Start (Copy/Paste)

```bash
cd /Users/toni/rag_guardian
python3 -m venv .venv
source .venv/bin/activate
pip install openai "mcp[cli]"
make test-lmstudio
make gen-once
make status
```

## License

No license file is defined yet.
