.PHONY: install test lint fix check

VENV_BIN := .venv/bin

install:
	python3 -m venv .venv
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -e ".[dev]"

test:
	$(VENV_BIN)/pytest

lint:
	$(VENV_BIN)/ruff check .

fix:
	$(VENV_BIN)/ruff check --fix .

check: lint test
