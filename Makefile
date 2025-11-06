.PHONY: install build test format lint clean fetch-ark diff-ark

PYTHON ?= python
VENV ?= .venv
ACTIVATE := . $(VENV)/bin/activate

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

build:
	$(PYTHON) -m compileall app src py_scripts

test:
	$(ACTIVATE) && pytest

format:
	$(ACTIVATE) && black app src py_scripts tests

lint:
	$(ACTIVATE) && ruff check app src py_scripts tests

clean:
	rm -rf build dist .pytest_cache .mypy_cache htmlcov coverage .ruff_cache

fetch-ark:
	$(ACTIVATE) && python py_scripts/ark_holdings/fetch_snapshots.py --output-dir data/ark_holdings

# Example usage: make diff-ark PREV=path/to/prev.csv CURR=path/to/curr.csv
PREV ?=
CURR ?=
diff-ark:
	@if [ -z "$(PREV)" ] || [ -z "$(CURR)" ]; then \
		echo "Usage: make diff-ark PREV=... CURR=..."; \
		exit 1; \
	fi
	$(ACTIVATE) && python py_scripts/ark_holdings/diff_snapshots.py --previous $(PREV) --current $(CURR)
