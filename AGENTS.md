# Repository Guidelines

This project packages a FastAPI service for fetching Alpaca quote data and rendering an HTML heatmap dashboard. Use the conventions below to keep contributions consistent and production-ready.

## Project Structure & Module Organization
- `app/main.py` hosts the FastAPI entrypoint, route wiring, and Jinja template rendering.
- `app/services/alpaca_market_data.py` wraps the Alpaca SDK; keep remote calls and data shaping here.
- `app/config.py` centralizes environment-driven settings; extend `Settings` for new configuration.
- `app/templates/index.html` provides the dashboard UI. Add supporting assets under `app/static/` if needed.
- Place new integration or unit tests under `tests/`, mirroring the `app/` package layout.

## Build, Test, and Development Commands
- Create a virtual environment and install dependencies:
  ```bash
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  ```
- Run the local API with hot reload:
  ```bash
  uvicorn app.main:app --reload
  ```
- Execute the test suite (add `pytest` to your dev tooling if not yet installed):
  ```bash
  pytest
  ```

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and descriptive, snake_case module and function names.
- Use type hints consistently; surface request/response contracts with Pydantic models when adding endpoints.
- Prefer small, focused services under `app/services/`; keep asynchronous FastAPI handlers thin.
- Format code with `black` (line length 88) and lint with `ruff` before opening a PR: `ruff check app tests`.

## Testing Guidelines
- Target pytest for automated coverage; name files `test_*.py` and functions `test_*`.
- Mock Alpaca dependencies using fixtures to avoid live API calls; isolate external requests to service classes.
- Include regression tests when fixing bugs and describe new scenarios in docstrings or comments when needed.

## Commit & Pull Request Guidelines
- Use conventional commits (`feat:`, `fix:`, `chore:`) and keep subject lines under 72 characters.
- Reference related issues in the PR description, summarize behavioral changes, and include screenshots or API samples when UI or response formats change.
- Ensure CI passes (`pytest`, `ruff`, `black --check`) before requesting review; note any intentional deviations.

## Security & Configuration Tips
- Never commit secrets; store Alpaca credentials in `.env` (ignored by git) or environment variables.
- Document required settings updates in the PR if new keys are introduced, and add defaults in `Settings` when safe.
