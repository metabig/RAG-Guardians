SHELL := /bin/zsh

VENV_PYTHON := .venv/bin/python
MODEL := google/gemma-4-e4b
URI ?= all
N := 10
INTERVAL := 600

.PHONY: help check-venv test-lmstudio run-mcp inspect-mcp mcp-tools-list mcp-tool-info mcp-tool-run mcp-shell gen-summaries gen-once gen-loop status

help:
	@echo "RAG Guardian - shortcuts"
	@echo ""
	@echo "make test-lmstudio          # quick LM Studio connectivity test"
	@echo "make run-mcp                # start KnowledgeMCP server (stdio)"
	@echo "make run-mcp-debug          # start KnowledgeMCP server with debug-friendly env"
	@echo "make inspect-mcp            # launch MCP Inspector + stdio server"
	@echo "make mcp-tools-list         # list MCP tool functions available to call"
	@echo "make mcp-tool-info TOOL=... # show signature + docs for one MCP tool"
	@echo "make mcp-tool-run TOOL=... ARGS='{"\"key\"":"\"value\""}'  # call tool and print JSON"
	@echo "make mcp-shell              # interactive shell to run/rerun tools with hot reload"
	@echo "make gen-summaries          # generate summaries once (all files by default)"
	@echo "make gen-once               # generate summaries + FAQs + magic filters"
	@echo "make gen-loop               # keep generating every INTERVAL seconds"
	@echo "make status                 # show metadata counters for all files"
	@echo ""
	@echo "Override variables example:"
	@echo "make gen-summaries URI=file://mydoc.txt"
	@echo "make gen-once URI=file://mydoc.txt N=5"
	@echo "make gen-loop INTERVAL=300"
	@echo "make mcp-tool-run TOOL=semantic_search ARGS='{"\"query\"":"\"token\"","\"top_k\"":3}'"

check-venv:
	@if [[ ! -x "$(VENV_PYTHON)" ]]; then \
		echo "Missing $(VENV_PYTHON). Create your venv first."; \
		exit 1; \
	fi

test-lmstudio: check-venv
	@PYTHONPATH=src $(VENV_PYTHON) -c "from rag_guardian.utils import build_client; from rag_guardian.env import MODEL_NAME, LLM_MAX_TOKENS; c=build_client(); r=c.chat.completions.create(model=MODEL_NAME, messages=[{'role':'user','content':'Say OK in one word.'}], max_tokens=LLM_MAX_TOKENS); print('model:', r.model); print('reply:', (r.choices[0].message.content or '').strip())"

run-mcp: check-venv
	@$(VENV_PYTHON) -m knowledge_mcp.server

run-mcp-debug: check-venv
	@echo "Starting KnowledgeMCP in debug mode (unbuffered stdout/stderr)..."
	@PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1 $(VENV_PYTHON) -m knowledge_mcp.server

inspect-mcp: check-venv
	@echo "Starting MCP Inspector (server command: $(VENV_PYTHON) -m knowledge_mcp.server)"
	@npx @modelcontextprotocol/inspector $(VENV_PYTHON) -m knowledge_mcp.server

mcp-tools-list: check-venv
	@$(VENV_PYTHON) scripts/mcp_tool_runner.py --list

TOOL ?= list_knowledge_files
ARGS ?= {}

mcp-tool-info: check-venv
	@$(VENV_PYTHON) scripts/mcp_tool_runner.py --tool-info '$(TOOL)'

mcp-tool-run: check-venv
	@$(VENV_PYTHON) scripts/mcp_tool_runner.py --tool '$(TOOL)' --args-json '$(ARGS)'

mcp-shell: check-venv
	@$(VENV_PYTHON) scripts/mcp_tool_shell.py

gen-summaries: check-venv
	@URI='$(URI)' $(VENV_PYTHON) -c "import json, os, sys; sys.path.insert(0,'.'); from knowledge_mcp.reader import list_files; from knowledge_mcp.server import trigger_summary_generation; uri=os.environ['URI']; uris=[uri] if uri.startswith('file://') else [e['uri'] for e in list_files()]; total_summaries=0; print('files:', len(uris)); print('no knowledge files found') if not uris else None; code='''for u in uris:\n    s=json.loads(trigger_summary_generation(u))\n    summary=(s.get(\"summary\") or \"\").strip()\n    ok=bool(s.get(\"ok\")) and bool(summary)\n    total_summaries += 1 if ok else 0\n    print(\"---\", u)\n    print(\"summary_ok:\", ok)\n    print(\"summary_chars:\", len(summary))\n    print(\"summary_error:\", s.get(\"error\", \"\"))'''; exec(code); print('TOTAL summaries:', total_summaries)"

gen-once: check-venv
	@URI='$(URI)' N='$(N)' $(VENV_PYTHON) -c "import json, os, sys; sys.path.insert(0,'.'); from knowledge_mcp.reader import list_files; from knowledge_mcp.server import trigger_faq_generation, trigger_magic_filter_generation, trigger_summary_generation; uri=os.environ['URI']; n=int(os.environ['N']); uris=[uri] if uri.startswith('file://') else [e['uri'] for e in list_files()]; total_summaries=0; total_faqs=0; total_filters=0; print('files:', len(uris)); print('no knowledge files found') if not uris else None; code='''for u in uris:\n    s=json.loads(trigger_summary_generation(u))\n    faq=json.loads(trigger_faq_generation(u, n_questions=n))\n    mf=json.loads(trigger_magic_filter_generation(u))\n    summary=(s.get(\"summary\") or \"\").strip()\n    summary_ok=bool(s.get(\"ok\")) and bool(summary)\n    fcnt=len(faq.get(\"faqs\", []))\n    mcnt=len(mf.get(\"magic_filters\", []))\n    total_summaries += 1 if summary_ok else 0\n    total_faqs += fcnt\n    total_filters += mcnt\n    print(\"---\", u)\n    print(\"summary_ok:\", summary_ok)\n    print(\"summary_chars:\", len(summary))\n    print(\"faq_ok:\", faq.get(\"ok\"))\n    print(\"magic_ok:\", mf.get(\"ok\"))\n    print(\"faqs:\", fcnt)\n    print(\"magic_filters:\", mcnt)\n    print(\"summary_error:\", s.get(\"error\", \"\"))\n    print(\"faq_error:\", faq.get(\"error\", \"\"))\n    print(\"magic_error:\", mf.get(\"error\", \"\"))'''; exec(code); print('TOTAL summaries:', total_summaries); print('TOTAL faqs:', total_faqs); print('TOTAL magic_filters:', total_filters)"

gen-loop: check-venv
	@echo "Starting continuous generation for URI=$(URI) every $(INTERVAL)s (Ctrl+C to stop)"
	@while true; do \
		$(MAKE) --no-print-directory gen-once URI='$(URI)' N='$(N)'; \
		echo "Sleeping $(INTERVAL)s..."; \
		sleep $(INTERVAL); \
	done

status: check-venv
	@PYTHONPATH=src $(VENV_PYTHON) -c "import json; from rag_guardian.env import KNOWLEDGE_META_DIR; from knowledge_mcp.metadata import get_meta; from knowledge_mcp.reader import list_files; files=list_files(); total_summaries=0; total_faqs=0; total_filters=0; total_tokens=0; print('files:', len(files)); print('no knowledge files found') if not files else None; code='''for e in files:\n    rel=e[\"rel_path\"]\n    m=get_meta(rel)\n    total_summaries += 1 if (m.summary or \"\").strip() else 0\n    total_faqs += len(m.faqs)\n    total_filters += len(m.magic_filters)\n    total_tokens += m.token_count\n    sidecar = KNOWLEDGE_META_DIR / f\"{rel}.json\"\n    d = json.loads(sidecar.read_text(encoding=\"utf-8\")) if sidecar.exists() else {}\n    summary=(d.get(\"summary\", \"\") or \"\").strip()\n    print(\"---\", e[\"uri\"])\n    print(\"Summary generated:\", bool(summary))\n    print(\"Summary chars:\", len(summary))\n    print(\"FAQs:\", len(m.faqs))\n    print(\"Magic filters:\", len(m.magic_filters))\n    print(\"token_count:\", d.get(\"token_count\", m.token_count))'''; exec(code); print('TOTAL summaries:', total_summaries); print('TOTAL FAQs:', total_faqs); print('TOTAL Magic filters:', total_filters); print('TOTAL tokens:', total_tokens)"