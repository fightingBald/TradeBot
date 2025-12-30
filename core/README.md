# Core

Core hosts the hexagonal ports and shared abstractions. It must not import
from adapters or app entry points.

## Ports

- `BrokerPort`: positions and account-level actions.
- `MarketDataPort`: latest quote snapshots.
- `StateStore`: persistence for positions and state snapshots.
- `CommandBus`: command publish/consume interface.

Adapters implement these interfaces and entry points (FastAPI/Engine/UI)
depend on the ports.
