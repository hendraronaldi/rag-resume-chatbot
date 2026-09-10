.PHONY: reindex docker-build

# Python for index rebuilds: prefer the local uv venv, fall back to `uv run`
# (which creates/uses .venv automatically). Both keep parity with run-local.sh.
RAG_PYTHON ?= .venv/bin/python
ifeq ($(wildcard $(RAG_PYTHON)),)
RAG_PYTHON = uv run --with-requirements requirements.txt -- python
endif

# Rebuild the live LlamaIndex store from app/data/resume.md, then refresh deterministic index.json.
reindex:
	$(RAG_PYTHON) builder.py && $(RAG_PYTHON) build_index.py

# Rebuild the index first so the image carries a fresh live store, then build.
docker-build: reindex
	docker build -t rag-resume-chatbot .
