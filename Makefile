.PHONY: help install install-dev run test lint format report clean

## help: List all available make targets
help:
	@grep -E '^## ' Makefile | sed 's/^## //'

## install: Install lclg and its dependencies
install:
	pip install -e "."

## install-dev: Install lclg and dev dependencies
install-dev:
	pip install -e ".[dev]"

## run: Run the pipeline (set TOPIC="your topic" or LCLG_TOPIC env var)
run:
	python -m lclg $(if $(TOPIC),--topic "$(TOPIC)",)

## test: Run the test suite
test:
	pytest

## lint: Run ruff (lint + format check) and mypy
lint:
	ruff check src/ tests/
	ruff format --check src/ tests/
	mypy src/

## format: Auto-format source files with ruff
format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

## report: Re-render the most recent cached report without making LLM calls
report:
	python -m lclg --render-only

## clean: Remove generated output, caches, and build artifacts
clean:
	rm -rf output/*/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .mypy_cache .ruff_cache .pytest_cache dist/
