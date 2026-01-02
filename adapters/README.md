# Adapters

Adapters implement the core ports and isolate external SDKs.

## Alpaca

`adapters/brokers/alpaca.py` wraps `adapters/brokers/alpaca_service.py` to expose
`BrokerPort` and `MarketDataPort` through the core ports.

## Storage

`adapters/storage/sqlalchemy_state_store.py` persists positions, orders, fills, and
protection links via SQLAlchemy (SQLite locally, Postgres in Docker Compose).

## Messaging

`adapters/messaging/redis_command_bus.py` publishes and consumes command messages.

## Market data strategy (current)

- Engine uses REST polling for positions plus the Alpaca trading websocket for
  trade updates.
- UI reads state via FastAPI and does not call the broker directly.
