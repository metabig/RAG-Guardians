SHELL := /bin/zsh

VENV_PYTHON := .venv/bin/python
MODEL := google/gemma-4-e4b
URI ?= all
N := 10
INTERVAL := 600

.PHONY: help check-venv test-lmstudio run-mcp inspect-mcp gen-once gen-loop status

help:
	@echo "RAG Guardian - shortcuts"
	@echo ""
	@echo "make test-lmstudio          # quick LM Studio connectivity test"
	@echo "make run-mcp                # start KnowledgeMCP server (stdio)"
	@echo "make inspect-mcp            # launch MCP Inspector + stdio server"
	@echo "make gen-once               # generate FAQs + magic filters (all files by default)"
	@echo "make gen-loop               # keep generating every INTERVAL seconds"
	@echo "make status                 # show metadata counters for all files"
	@echo ""
	@echo "Override variables example:"
	@echo "make gen-once URI=knowledge://mydoc.txt N=5"
	@echo "make gen-loop INTERVAL=300"

check-venv:
	@if [[ ! -x "$(VENV_PYTHON)" ]]; then \
		echo "Missing $(VENV_PYTHON). Create your venv first."; \
		exit 1; \
	fi

test-lmstudio: check-venv
	@$(VENV_PYTHON) -c "import sys; sys.path.insert(0,'.'); from utils import build_client; from env import MODEL_NAME, LLM_MAX_TOKENS; c=build_client(); r=c.chat.completions.create(model=MODEL_NAME, messages=[{'role':'user','content':'Say OK in one word.'}], max_tokens=LLM_MAX_TOKENS); print('model:', r.model); print('reply:', (r.choices[0].message.content or '').strip())"

run-mcp: check-venv
	@$(VENV_PYTHON) -m knowledge_mcp.server

inspect-mcp: check-venv
	@echo "Starting MCP Inspector (server command: $(VENV_PYTHON) -m knowledge_mcp.server)"
	@npx @modelcontextprotocol/inspector $(VENV_PYTHON) -m knowledge_mcp.server

gen-once: check-venv
	@URI='$(URI)' N='$(N)' $(VENV_PYTHON) -c "import json, os, sys; sys.path.insert(0,'.'); from knowledge_mcp.reader import list_files; from knowledge_mcp.server import trigger_faq_generation, trigger_magic_filter_generation; uri=os.environ['URI']; n=int(os.environ['N']); uris=[uri] if uri.startswith('knowledge://') else [e['uri'] for e in list_files()]; total_faqs=0; total_filters=0; print('files:', len(uris)); print('no knowledge files found') if not uris else None; code='''for u in uris:\n    faq=json.loads(trigger_faq_generation(u, n_questions=n))\n    mf=json.loads(trigger_magic_filter_generation(u))\n    fcnt=len(faq.get(\"faqs\", []))\n    mcnt=len(mf.get(\"magic_filters\", []))\n    total_faqs += fcnt\n    total_filters += mcnt\n    print(\"---\", u)\n    print(\"faq_ok:\", faq.get(\"ok\"))\n    print(\"magic_ok:\", mf.get(\"ok\"))\n    print(\"faqs:\", fcnt)\n    print(\"magic_filters:\", mcnt)\n    print(\"faq_error:\", faq.get(\"error\", \"\"))\n    print(\"magic_error:\", mf.get(\"error\", \"\"))'''; exec(code); print('TOTAL faqs:', total_faqs); print('TOTAL magic_filters:', total_filters)"

gen-loop: check-venv
	@echo "Starting continuous generation for URI=$(URI) every $(INTERVAL)s (Ctrl+C to stop)"
	@while true; do \
		$(MAKE) --no-print-directory gen-once URI='$(URI)' N='$(N)'; \
		echo "Sleeping $(INTERVAL)s..."; \
		sleep $(INTERVAL); \
	done

status: check-venv
	@$(VENV_PYTHON) -c "import json, sys; sys.path.insert(0,'.'); from env import KNOWLEDGE_META_DIR; from knowledge_mcp.metadata import get_meta; from knowledge_mcp.reader import list_files; files=list_files(); total_faqs=0; total_filters=0; total_tokens=0; print('files:', len(files)); print('no knowledge files found') if not files else None; code='''for e in files:\n    rel=e[\"rel_path\"]\n    m=get_meta(rel)\n    total_faqs += len(m.faqs)\n    total_filters += len(m.magic_filters)\n    total_tokens += m.token_count\n    sidecar = KNOWLEDGE_META_DIR / f\"{rel}.json\"\n    d = json.loads(sidecar.read_text(encoding=\"utf-8\")) if sidecar.exists() else {}\n    print(\"---\", e[\"uri\"])\n    print(\"FAQs:\", len(m.faqs))\n    print(\"Magic filters:\", len(m.magic_filters))\n    print(\"summary:\", repr(d.get(\"summary\", \"\")))\n    print(\"token_count:\", d.get(\"token_count\", m.token_count))'''; exec(code); print('TOTAL FAQs:', total_faqs); print('TOTAL Magic filters:', total_filters); print('TOTAL tokens:', total_tokens)"