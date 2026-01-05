# Apps

- `apps/api`: FastAPI control plane (state read + command orchestration).
- `apps/engine`: execution engine (WS subscribe + state sync + risk actions).
  - `main.py` entrypoint + orchestration
  - `commands.py` command handling loop
  - `sync.py` position sync loop
  - `streams.py` trading websocket runner
- `apps/marketdata`: market data daemon (quotes/trades/bars streaming + cache writes).
  - `main.py` entrypoint + logging
  - `streams.py` market data websocket runner
- `apps/ui`: Streamlit dashboard (read-only + command buttons).
  - `main.py` entrypoint + session wiring
  - `api_client.py` FastAPI client
  - `transformers.py` dataframe shaping
  - `views.py` UI rendering
