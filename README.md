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

## Project Layout

- `app/` — FastAPI 层（配置、模型、服务、模板）。
- `src/` — 共享业务模块：
  - `src/ark/holdings/` — 木头姐 ETF 持仓抓取、清洗、差异化与 I/O。
  - `src/earnings/calendar/` — 财报/宏观日程抓取、去重、日历输出。
  - `src/notifications/` — 邮件通知实现与收件人配置。
- `py_scripts/` — CLI & 作业脚本（在需要时把 `src` 加入 `sys.path`）。
- `tests/` — 单元与集成测试，按模块就近布局。

## Data Utilities & Automation

### Earnings Calendar CLI

- 入口：`src/earnings/calendar`。支持从 FMP/Finnhub 抓取财报或宏观事件并推送到 ICS / Google / iCloud。
- 默认配置：`config/earnings_to_calendar.toml`（可覆盖时区、事件时长、会议时间等）。
- 快速启动：
  ```bash
  python -m earnings.calendar \
    --config=config/earnings_to_calendar.toml \
    --env-file=.env \
    --google-insert \
    --market-events \
    --log-level=INFO
  ```
- 调试建议：通过 `--log-level=DEBUG` 或在 notebooks/fmp_data_check.ipynb 内验证 API Key。

### ARK Holdings Automation

#### 使用步骤

1. **配置环境**  
   - 在仓库 *Secrets* 中设置 `EMAIL_USERNAME`、`EMAIL_PASSWORD`（例如 Gmail 应用专用密码）。  
   - 在仓库 *Variables* 中配置 SMTP 参数：`EMAIL_HOST`、`EMAIL_PORT`、`EMAIL_SENDER`、`EMAIL_USE_TLS`、`EMAIL_USE_SSL`、`EMAIL_MAX_RETRIES`。为空的变量会被自动忽略。  
   - 配置收件人：  
     - 本地：使用 `config/notification_recipients.toml`（含 To/Cc/Bcc）。  
     - CI：若该文件不存在，则读取 `EMAIL_RECIPIENTS_TO` / `EMAIL_RECIPIENTS_CC` / `EMAIL_RECIPIENTS_BCC`（逗号分隔）。  
   - 可选变量：  
     - `EMAIL_ENABLED`（默认 `true`）  
     - `FUND_LIST`（默认六只 ARK ETF）  
     - `MIN_WEIGHT_BP`（权重阈值，单位基点）  
     - `MIN_SHARE_DELTA`（持股阈值）  
     - `BASELINE_ARTIFACT_NAME`、`BASELINE_DIR`、`OUTPUT_DIR`、`RETENTION_DAYS`

2. **本地运行（可选）**  
   ```bash
   python py_scripts/ark_holdings/daily_pipeline.py \
     --baseline-dir baseline_snapshots \
     --output-dir out/latest \
     --summary-path out/diff_summary.md \
     --summary-json out/diff_summary.json \
     --send-email
   ```
   命令将会抓取最新持仓，和 `baseline_snapshots` 下的基线对比，并（若启用）发送 HTML 报告，摘要会写入 `out/`。

3. **GitHub Actions 调度**  
   - 工作流：`.github/workflows/ark-holdings-daily.yml`
   - 触发方式：  
     - 定时：`cron: "5 1 * * 1-5"`（美股交易日收盘后约 21:05 美东时间）  
     - 手动：Actions → ARK Holdings Daily → Run workflow
   - 工作流会：  
1. 下载上一份 Artifact 作为基线（若首次运行则跳过）；  
2. 运行 `scripts/run_ark_pipeline.py`，由脚本解析环境变量后调用 `daily_pipeline`；  
3. 生成 Markdown/JSON 摘要，写入 Job Summary；  
4. 上传新的 Artifact（含最新快照与摘要），并删除旧版本，确保仅保留最新基线；  
5. 当 `EMAIL_ENABLED=true` 且凭据完整时发送邮件播报。

#### 实现思路

- **数据抓取**：`src/ark/holdings/provider.py` 负责下载并清洗 ARK 官方 CSV；`src/ark/holdings/io.py` 将快照与 CSV 互转，便于 Artifact 存取。  
- **差异分析**：`src/ark/holdings/diff.py` 将当前快照与基线比对，产出增/减持及新进/退出动作；阈值通过环境变量控制。  
- **报告产出**：`py_scripts/ark_holdings/daily_pipeline.py` 构建 Markdown 和 JSON，邮件正文按权重绝对变化排序，同时附带最新持仓 Top N 表。  
- **Artifacts 管理**：基线仅保存在 GitHub Artifact，不写入主分支；上传前先清除旧版本，避免历史堆积。  
- **邮件回退**：若 TOML 文件缺失，管道会自动读取 `EMAIL_RECIPIENTS_*` 变量；空字符串会被忽略，防止 Pydantic 校验失败。
- **CI 调度脚本**：`scripts/run_ark_pipeline.py` 统一处理 GitHub Actions `vars`/`secrets`，减少 YAML 中的复杂 Bash，亦可本地复用。

## Notes

- Quote availability depends on the data feed tied to your Alpaca plan. Demo accounts usually have access to the `iex` feed.
- If you need streaming updates, consider using Alpaca's websocket client (`alpaca-py` provides `StockDataStream`), and bridge updates into FastAPI via background tasks or WebSocket endpoints.

## TODO

- 接入国会议员持仓
- 接入trump
- 接入polymarket
- 接入日历， 避免像是vix交割这种风险
- hypeliquid whale API https://docs.coinglass.com/reference/hyperliquid-whale-alert
