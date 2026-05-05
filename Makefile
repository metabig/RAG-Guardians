SHELL := /bin/zsh

VENV_PYTHON := .venv/bin/python
MODEL := google/gemma-4-e4b
URI := knowledge://rag_source.txt
N := 10
INTERVAL := 600

.PHONY: help check-venv test-lmstudio run-mcp gen-once gen-loop status

help:
	@echo "RAG Guardian - shortcuts"
	@echo ""
	@echo "make test-lmstudio          # quick LM Studio connectivity test"
	@echo "make run-mcp                # start KnowledgeMCP server (stdio)"
	@echo "make gen-once               # generate FAQs + magic filters once"
	@echo "make gen-loop               # keep generating every INTERVAL seconds"
	@echo "make status                 # show sidecar metadata counters"
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

gen-once: check-venv
	@$(VENV_PYTHON) -c "import sys, json; sys.path.insert(0,'.'); from knowledge_mcp.server import trigger_faq_generation, trigger_magic_filter_generation; uri='$(URI)'; n=int('$(N)'); faq=json.loads(trigger_faq_generation(uri, n_questions=n)); mf=json.loads(trigger_magic_filter_generation(uri)); print('faq_ok:', faq.get('ok')); print('magic_ok:', mf.get('ok')); print('faqs:', len(faq.get('faqs', []))); print('magic_filters:', len(mf.get('magic_filters', []))); print('faq_error:', faq.get('error','')); print('magic_error:', mf.get('error',''))"

gen-loop: check-venv
	@echo "Starting continuous generation for $(URI) every $(INTERVAL)s (Ctrl+C to stop)"
	@while true; do \
		$(VENV_PYTHON) -c "import sys, json; sys.path.insert(0,'.'); from knowledge_mcp.server import trigger_faq_generation, trigger_magic_filter_generation; uri='$(URI)'; n=int('$(N)'); faq=json.loads(trigger_faq_generation(uri, n_questions=n)); mf=json.loads(trigger_magic_filter_generation(uri)); print('faq_ok:', faq.get('ok'), 'magic_ok:', mf.get('ok')); print('faqs:', len(faq.get('faqs', [])), 'magic_filters:', len(mf.get('magic_filters', []))); print('faq_error:', faq.get('error','')); print('magic_error:', mf.get('error',''))"; \
		echo "Sleeping $(INTERVAL)s..."; \
		sleep $(INTERVAL); \
	done

status: check-venv
	@$(VENV_PYTHON) -c "import sys, json; sys.path.insert(0,'.'); from knowledge_mcp.metadata import get_meta; m=get_meta('rag_source.txt'); print('FAQs:', len(m.faqs)); print('Magic filters:', len(m.magic_filters)); from env import KNOWLEDGE_META_DIR; sidecar=KNOWLEDGE_META_DIR/'rag_source.txt.json'; d=json.loads(sidecar.read_text()); print('Sidecar:', sidecar); print('summary:', repr(d.get('summary',''))); print('token_count:', d.get('token_count'))"