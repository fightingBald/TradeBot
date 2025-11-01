# AlpacaTrading FastAPI Service

This project exposes a small FastAPI application that fetches real-time quotes for equities such as Apple (`AAPL`) and Alphabet (`GOOGL`) using the Alpaca Market Data API.

## Prerequisites

- Python 3.10+ (recommended)
- An Alpaca account with API credentials that have access to the desired data feed (e.g., `iex` or `sip`).

## Setup

> 所有命令默认在项目根目录执行：先 `cd /path/to/AlpacaTrading`。

1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   cd /path/to/AlpacaTrading
   pip install -r requirements.txt
   ```
3. Provide your Alpaca credentials, either through environment variables or an `.env` file at the project root. Both the `ALPACA_*` and Alpaca's default `APCA_*` names are supported:
   ```
   ALPACA_API_KEY=YOUR_KEY
   ALPACA_API_SECRET=YOUR_SECRET
   ALPACA_DATA_FEED=iex
   # Optional if you need a different endpoint
   ALPACA_BASE_URL=https://data.alpaca.markets/v2
   ```
   ```
   APCA_API_KEY_ID=YOUR_KEY
   APCA_API_SECRET_KEY=YOUR_SECRET
   APCA_API_DATA_URL=https://data.alpaca.markets/v2
   ```
   The defaults target `https://data.alpaca.markets/v2`.
4. (Optional) Configure trading endpoints if you want to pull portfolio positions:
   ```
   ALPACA_TRADING_BASE_URL=https://paper-api.alpaca.markets
   ALPACA_PAPER_TRADING=true
   ```

## Launching the API

Start the FastAPI app with uvicorn:

```bash
cd /path/to/AlpacaTrading
uvicorn app.main:app --reload
```

Once running, the API provides:

- `GET /health` — basic health check.
- `GET /quotes` — fetches latest quotes. Add `symbols` query parameters to override the default `AAPL` and `GOOGL`, for example:
  ```
  http://127.0.0.1:8000/quotes?symbols=AAPL&symbols=GOOGL
  ```
- `GET /positions` — returns the current Alpaca account positions, mapped into the local `UserPosition` domain model.
- `GET /` — Plotly heatmap dashboard that visualizes the relative percentage move of each symbol over time.

## Interactive Heatmap Dashboard

- Navigate to `http://127.0.0.1:8000/` after starting the server.
- The page polls `/quotes` every 5 seconds and plots a heatmap where rows are symbols, columns are timestamps, and each cell shows the percentage change versus the first observed quote.
- Customize the symbols by adding them as query parameters in the browser URL, e.g. `http://127.0.0.1:8000/?symbols=AAPL&symbols=GOOGL&symbols=MSFT`.

## Testing

- Run the automated test suite with pytest:
  ```bash
  cd /path/to/AlpacaTrading
  pytest
  ```
- (Recommended) Lint and format before committing:
  ```bash
  cd /path/to/AlpacaTrading
  ruff check app tests
  black --check app tests
  ```

## Data Utilities

- `data_sources/earnings_to_calendar` 提供了一个模块化的 CLI/库，用于从 FMP 或 Finnhub 抓取财报日程并导出到 ICS、Google Calendar 或 iCloud。运行 `python -m data_sources.earnings_to_calendar --help` 查看可用参数，或使用 `--config=path/to/config.json` 统一管理 `symbols`、Google/ICloud 凭据等默认选项。敏感信息建议写在 `.env`（参考 `.env.example`），CLI 会自动加载，也可以用 `--env-file` 指向其他路径。需要调试时可加 `--log-level=DEBUG` 输出详细日志。
- `notebooks/fmp_data_check.ipynb` 提供交互式示例，可快速验证本地 `FMP_API_KEY` 是否能成功拉取财报数据。

## Notes

- Quote availability depends on the data feed tied to your Alpaca plan. Demo accounts usually have access to the `iex` feed.
- If you need streaming updates, consider using Alpaca's websocket client (`alpaca-py` provides `StockDataStream`), and bridge updates into FastAPI via background tasks or WebSocket endpoints.

## TODO

- 接入国会议员持仓
- 接入trump
- 接入polymarket
- 接入日历， 避免像是vix交割这种风险
- hypeliquid whale API https://docs.coinglass.com/reference/hyperliquid-whale-alert
