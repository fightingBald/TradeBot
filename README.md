# Trade Bot Centaur Mode

Local-first trading system focused on execution safety, state integrity, and human-in-the-loop control. The current scope targets Alpaca (paper/live) with a minimal desktop setup and a clear path to future expansion.

## Architecture
- Engine: subscribes to Alpaca trading WebSocket, maintains state, enforces risk controls, and syncs positions to SQLite.
- FastAPI: control plane; reads state for the UI, accepts commands, and orchestrates draft/confirm/kill-switch flows.
- Streamlit: read-only UI for monitoring positions and issuing commands; never talks to the broker directly.

Shared domain and interfaces live in `core/`, with concrete implementations in `adapters/`.

## Docs
- Internal notes: `docs/README_CN.md`
- Roadmap: `docs/roadmap.md`
- External API references: `docs/external_api/alpaca_doc.md`

## Technology Choices
- Alpaca-py for trading REST and `trade_updates` WebSocket.
- FastAPI as the control plane (state queries + command orchestration).
- Streamlit + Altair for a read-only desktop UI.
- SQLite + SQLAlchemy + Alembic for local state; Postgres in Docker Compose.
- Redis for command queueing between FastAPI and Engine.
- Pydantic settings for configuration via environment variables.

## Current Scope (Local Desktop MVP)
- Alpaca integration only (paper/live).
- Position distribution and PnL visualization in the GUI.
- Kill switch with a confirmation step for live trading.
- No external data sources yet; local default is SQLite while Docker uses Postgres.
- Structured logs for key actions and environment context.

## Requirements
- Python 3.10+
- uv (Python package manager)
- Alpaca account and API keys
- Redis (local or container)
- SQLite (local file)
- Docker + Docker Compose (optional)

Optional keys (only if you use the related scripts): FMP/Finnhub/Benzinga/Google/iCloud.

## Install
```bash
cd /path/to/AlpacaTrading
uv venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e .
```

## Configuration
Use environment variables. Minimal set:
```
ALPACA_API_KEY=xxx
ALPACA_API_SECRET=xxx
ALPACA_TRADING_BASE_URL=https://paper-api.alpaca.markets
ALPACA_PAPER_TRADING=true
ALPACA_DATA_FEED=iex
DATABASE_URL=sqlite:///./data/engine.db
REDIS_URL=redis://localhost:6379/0
ENGINE_POLL_INTERVAL_SECONDS=10
ENGINE_SYNC_MIN_INTERVAL_SECONDS=3
ENGINE_ENABLE_TRADING_WS=true
ENGINE_TRADING_WS_MAX_BACKOFF_SECONDS=30
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

## Docker Compose (paper/live)
Create env files:
```bash
cp deploy/env/common.env.example deploy/env/common.env
cp deploy/env/paper.env.example deploy/env/paper.env
cp deploy/env/live.env.example deploy/env/live.env
```
Fill in shared keys in `deploy/env/common.env` plus profile overrides, then run the profile you need.
Docker builds ignore `deploy/env/*.env` to keep secrets out of images.
```bash
docker compose -f deploy/docker-compose.yml --profile paper run --rm migrate-paper
docker compose -f deploy/docker-compose.yml --profile paper up -d
```
Live profile (separate containers and ports):
```bash
docker compose -f deploy/docker-compose.yml --profile live run --rm migrate-live
docker compose -f deploy/docker-compose.yml --profile live up -d
```
Ports: paper API `:8000`, paper UI `:8501`; live API `:8001`, live UI `:8502`.

Note: UI talks to FastAPI only; Engine owns the broker/WebSocket connection.

## API Endpoints
- `GET /health` health check
- `GET /state/profile` active profile and environment
- `GET /state/positions` position snapshot (from Engine + SQLite)
- `POST /commands/draft` stage a command
- `POST /commands/confirm` confirm staged command
- `POST /commands/kill-switch` emergency liquidation request

## Execution & State Strategy (Current)
- Engine owns the single trading WebSocket connection (free-plan friendly).
- `trade_updates` triggers an immediate position refresh; periodic polling remains as reconciliation.
- Position sync is throttled by `ENGINE_SYNC_MIN_INTERVAL_SECONDS` to respect rate limits.
- WebSocket reconnect uses exponential backoff with jitter (`ENGINE_TRADING_WS_MAX_BACKOFF_SECONDS`).
- UI uses FastAPI only and never talks directly to the broker.

## Optional CLI Tools
- Earnings calendar: `earnings-calendar` (see `config/events_to_google_calendar.toml`).
- ARK holdings automation: `py_scripts/ark_holdings/`.

## Quality Gates
```bash
make build
make lint
make test
make coverage
```
Coverage threshold: 80% on runtime modules (`apps/api`, `apps/engine`, `core`, `adapters`, `toolkits`).

## Directory Layout
- `apps/` entrypoints (api/engine/ui)
- `core/` domain models and ports
- `adapters/` external system adapters (broker/storage/messaging)
- `storage/` database migrations and schema
- `toolkits/` shared business logic
- `py_scripts/` CLI scripts
- `config/` TOML configuration (includes `config/ci/` for CI variables)
- `deploy/` Docker artifacts (Compose, Dockerfile, env examples)
- `docs/` internal docs and references
- `tests/` pytest tests
- `scripts/` CI and automation
- `secrets/` local credentials (only `.gitkeep` is committed)

## Roadmap
See `docs/roadmap.md` for long-term planning and milestones.
