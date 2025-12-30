# AlpacaTrading

Local-first trading system focused on execution safety, state integrity, and human-in-the-loop control. The current scope targets Alpaca (paper/live) with a minimal desktop setup and a clear path to future expansion.

## Architecture
- Engine: subscribes to Alpaca trading WebSocket, maintains state, enforces risk controls, and syncs positions to SQLite.
- FastAPI: control plane; reads state for the UI, accepts commands, and orchestrates draft/confirm/kill-switch flows.
- Streamlit: read-only UI for monitoring positions and issuing commands; never talks to the broker directly.

Shared domain and interfaces live in `core/`, with concrete implementations in `adapters/`.

## Current Scope (Local Desktop MVP)
- Alpaca integration only (paper/live).
- Position distribution and PnL visualization in the GUI.
- Kill switch with a confirmation step for live trading.
- No external data sources or external DB yet, but interfaces are reserved.
- Structured logs for key actions and environment context.

## Requirements
- Python 3.10+
- Alpaca account and API keys
- Redis (local or container)
- SQLite (local file)

Optional keys (only if you use the related scripts): FMP/Finnhub/Benzinga/Google/iCloud.

## Install
```bash
cd /path/to/AlpacaTrading
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

## Configuration
Use environment variables or a `.env` file. See `.env.example` for a complete list.

Minimal set:
```
ALPACA_API_KEY=xxx
ALPACA_API_SECRET=xxx
ALPACA_TRADING_BASE_URL=https://paper-api.alpaca.markets
ALPACA_PAPER_TRADING=true
ALPACA_DATA_FEED=iex
DATABASE_URL=sqlite:///./data/engine.db
REDIS_URL=redis://localhost:6379/0
ENGINE_POLL_INTERVAL_SECONDS=10
ENGINE_ENABLE_TRADING_WS=true
```

## Run (Local)
Migrations:
```bash
alembic upgrade head
```

FastAPI:
```bash
uvicorn apps.api.main:app --reload
```

Engine:
```bash
python -m apps.engine.main
```

Streamlit UI:
```bash
streamlit run apps/ui/main.py
```

## API Endpoints
- `GET /health` health check
- `GET /state/profile` active profile and environment
- `GET /state/positions` position snapshot (from Engine + SQLite)
- `POST /commands/draft` stage a command
- `POST /commands/confirm` confirm staged command
- `POST /commands/kill-switch` emergency liquidation request

## Market Data Strategy (Current)
- Trading WebSocket for execution updates.
- Position snapshots still synced by polling (can be replaced with event-driven updates).
- UI uses FastAPI only.

## Optional CLI Tools
- Earnings calendar: `earnings-calendar` (see `config/events_to_google_calendar.toml`).
- ARK holdings automation: `py_scripts/ark_holdings/`.

## Quality Gates
```bash
make build
make lint
make test
```

## Directory Layout
- `apps/` entrypoints (api/engine/ui)
- `core/` domain models and ports
- `adapters/` external system adapters (broker/storage/messaging)
- `storage/` database migrations and schema
- `toolkits/` shared business logic
- `py_scripts/` CLI scripts
- `config/` TOML configuration
- `tests/` pytest tests
- `scripts/` CI and automation
- `secrets/` local credentials (only `.gitkeep` is committed)

## Roadmap
See `roadmap.md` for long-term planning and milestones.
