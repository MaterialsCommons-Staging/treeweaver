SHELL := /bin/sh

PY := uv run
UPSTREAM_REPO := SINTEF/physmet-data-documentation-templates
UPSTREAM_REF ?= 840f8789412687ddd457b35b3e63f3da7d8a1c8c

.PHONY: help install test lint format refresh-corpus clean

help:
	@echo "install         create the virtualenv and install with test extras"
	@echo "test            run everything, including the ported upstream suite"
	@echo "lint            ruff and mypy over the code we wrote"
	@echo "format          apply ruff formatting"
	@echo "refresh-corpus  re-pull the vendored upstream sources at UPSTREAM_REF"

install:
	uv venv
	uv pip install -e ".[dev]"

test:
	$(PY) pytest -q

# The vendored upstream sources are excluded in pyproject.toml, so this only
# ever reports on code we wrote.
lint:
	$(PY) ruff check .
	$(PY) ruff format --check .
	$(PY) mypy

format:
	$(PY) ruff check --fix .
	$(PY) ruff format .

# Replaces the port and the corpus in one step. Anything that then fails in
# tests/treeweaver is a real upstream change, not drift on our side.
refresh-corpus:
	@mkdir -p .cache
	gh api repos/$(UPSTREAM_REPO)/tarball/$(UPSTREAM_REF) > .cache/upstream.tar.gz
	@rm -rf .cache/x && mkdir -p .cache/x
	tar xzf .cache/upstream.tar.gz -C .cache/x
	@set -e; U=$$(find .cache/x -maxdepth 1 -mindepth 1 -type d); \
	  rm -rf src/tabular tests/treeweaver/data; \
	  cp "$$U/src/treeweaver/treeweaver.py"  src/treeweaver/treeweaver.py; \
	  cp "$$U/src/treeweaver/treeweaver2.py" src/treeweaver/treeweaver2.py; \
	  cp -r "$$U/src/tabular" src/tabular; \
	  cp "$$U/tests/treeweaver/test_treeweaver.py"       tests/treeweaver/; \
	  cp "$$U/tests/treeweaver/test_treeweaver2.py"      tests/treeweaver/; \
	  cp "$$U/tests/treeweaver/test_treeweaver2_main.py" tests/treeweaver/; \
	  cp "$$U/tests/treeweaver/callmodule.py"            tests/treeweaver/; \
	  cp -r "$$U/tests/treeweaver/data" tests/treeweaver/data; \
	  cp "$$U/LICENSE" LICENSE.upstream
	@echo "Update the pin in tests/treeweaver/PROVENANCE.md to $(UPSTREAM_REF)"

clean:
	rm -rf .cache .pytest_cache .ruff_cache .mypy_cache
	rm -rf tests/treeweaver/data/output
