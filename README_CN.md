# AlpacaTrading 项目说明

## 这套东西是干嘛的？
* Engine 独立进程：订阅 WS + 管状态 + 风控自动卖出。
* FastAPI：读状态给 UI + 接收命令 + 编排（draft/confirm/kill switch）。
* Streamlit：只看 + 点按钮，不直接打券商。
* 一堆脚本（`py_scripts/`）帮忙管仓位：批量设置止损、同步财报/宏观日历、抓 ARK ETF 持仓、发邮件。
* 共享的业务逻辑放在 `toolkits/`，方便 CLI、服务、notebook 复用。
* 先做风控和执行，别先做“预测未来”
*  撤A买B要状态机	订单状态不同步是散户第一死因
*  半人马模式最适合散户 机器砍手，我扣扳机
*  系统设计要允许多账号papaer tarding ， real trading 切换
* GUI 可以用streamlit

## 当前阶段（Local Desktop MVP）
- 仅接入 Alpaca（paper/live），先把持仓读取与展示做稳。
- 本地 GUI 展示持仓分布与盈亏。
- GUI 一键清仓（Kill Switch）+ live 二次确认。
- 外部数据源与外部 DB 暂不接入，但保留接口以便后续扩展。
- 结构化日志记录关键动作与环境信息。

## 技术选型
- Alpaca-py：交易 REST + `trade_updates` WebSocket。
- FastAPI：控制面（状态查询 + 命令编排）。
- Streamlit + Altair：只读桌面 GUI。
- SQLite + SQLAlchemy + Alembic：本地状态存储与迁移。
- Redis：FastAPI 与 Engine 之间的命令队列。
- Pydantic settings：统一环境变量与 `.env` 配置。

## 环境/账号要求
- Python 3.10 以上（本地推荐装成 `.venv`）。
- uv（Python 包管理器）。
- Alpaca 账号和一对 API Key（写入 `.env` 或环境变量）。
- Redis（本地或容器）。
- SQLite（默认本地文件）。
- 可选：FMP/Finnhub/Benzinga/Google/iCloud 等三方 Key，按需放进 `.env`。

## 快速开工（建议逐条敲）
```bash
cd /path/to/AlpacaTrading
uv venv .venv
source .venv/bin/activate  # Windows 用 .venv\Scripts\activate
uv pip install -e .
```

`.env` 示范（缺啥补啥）：
```
ALPACA_API_KEY=xxx
ALPACA_API_SECRET=xxx
ALPACA_DATA_FEED=iex
ALPACA_TRADING_BASE_URL=https://paper-api.alpaca.markets
ALPACA_PAPER_TRADING=true
DATABASE_URL=sqlite:///./data/engine.db
REDIS_URL=redis://localhost:6379/0
ENGINE_POLL_INTERVAL_SECONDS=10
ENGINE_SYNC_MIN_INTERVAL_SECONDS=3
ENGINE_ENABLE_TRADING_WS=true
ENGINE_TRADING_WS_MAX_BACKOFF_SECONDS=30
FMP_API_KEY=xxx
FINNHUB_API_KEY=xxx
BENZINGA_API_KEY=xxx
GOOGLE_CREDENTIALS_PATH=secrets/credentials.json
GOOGLE_TOKEN_PATH=secrets/token.json
```

## 跑 FastAPI 服务
```bash
source .venv/bin/activate
uvicorn apps.api.main:app --reload
```
跑起来后：
- `GET /health`：心跳。
- `GET /state/profile`：当前 profile 与环境。
- `GET /state/positions`：读取持仓快照（来自 Engine + SQLite）。
- `POST /commands/*`：下发命令（draft/confirm/kill-switch）。

## 跑 Engine
```bash
source .venv/bin/activate
python -m apps.engine.main
```
说明：Engine 负责 WS + 轮询同步持仓并落库，命令通过 Redis 队列下发。

## 数据库迁移
```bash
alembic upgrade head
```

## 跑 Streamlit GUI（持仓分布 + 一键清仓）
```bash
source .venv/bin/activate
streamlit run apps/ui/main.py
```
提示：live 环境需要二次确认口令；执行 Kill Switch 会进入命令队列。

## 执行与状态策略（Current）
- Engine 独占交易 WS（符合免费版单连接限制）。
- `trade_updates` 触发即时持仓刷新，轮询保留做最终对账。
- `ENGINE_SYNC_MIN_INTERVAL_SECONDS` 限制刷新频率，避免打满速率限制。
- WS 断线后指数退避重连（`ENGINE_TRADING_WS_MAX_BACKOFF_SECONDS`）。
- UI 只走 FastAPI，不直连券商。

## Earnings Calendar CLI（财报/宏观日历）
- 命令：`earnings-calendar`（安装 `pip install -e .` 后自动带上），也可以 `python -m py_scripts.calendar.run`。
- 默认配置文件：`config/events_to_google_calendar.toml`。如果没有，脚本会自动生成模板。
- `.env` 里至少要放 FMP/Finnhub Key；要写入 Google，就再放 `GOOGLE_*`；要抓宏观就放 `BENZINGA_API_KEY`。

常用例子：
```bash
earnings-calendar \
  --config=config/events_to_google_calendar.toml \
  --env-file=.env \
  --google-insert \
  --market-events \
  --macro-events \
  --fallback-source=finnhub \
  --log-level=INFO

# 仅导出 ICS
earnings-calendar --symbols=AAPL,MSFT --days=60 --export-ics=earnings.ics
```
小贴士：命令行参数 > TOML > `.env` > 默认值。只改想改的那几项就行。
如果主数据源漏掉个别符号，可加 `--fallback-source=finnhub`（或在配置里设置 `fallback_source`）用后备源补齐。

## ARK 持仓自动化
1. `.env` 填好邮箱 SMTP（`EMAIL_HOST/PORT/USERNAME/PASSWORD` 等），收件人写在 `config/notification_recipients.toml`。
2. 想比对每天的变动，直接跑：
   ```bash
   python py_scripts/ark_holdings/daily_pipeline.py \
     --baseline-dir baseline_snapshots \
     --output-dir out/latest \
     --summary-path out/diff_summary.md \
     --summary-json out/diff_summary.json \
     --send-email
   ```
3. GitHub Actions 版本放在 `.github/workflows/ark-holdings-daily.yml`，逻辑和本地一样。

## 质量保障
- `make build`：把所有包编译一遍，检查语法。
- `make lint`：`ruff` 静态检查。
- `make format`：`ruff` 自动修风格。
- `make test`：`pytest` 单测 + 轻量集成测试。
- `make coverage`：覆盖率统计（阈值 80%）。
改动完建议起码跑 `build` / `lint` / `test` 各一次。
说明：覆盖率门槛只统计运行时核心模块（`apps/api`、`apps/engine`、`core`、`adapters`、`toolkits`）。

## 目录结构速览
- `apps/`：入口层（api/engine/ui）。
- `core/`：领域模型与 ports 接口。
- `adapters/`：外部系统适配器（券商/存储/消息）。
- `storage/`：数据库迁移与结构化存储。
- `toolkits/`：通用业务模块（日历、ARK、通知等）。
- `py_scripts/`：命令行脚本入口。
- `config/`：TOML 配置（事件日历、邮件收件人）。
- `tests/`：pytest 测试。
- `scripts/`：CI/批处理脚本。
- `secrets/`：放本地凭据（仓库里只有 `.gitkeep`，别提交真实钥匙）。

## 后续想做的事
- 接入美国议员持仓
- 接入 Trump 相关数据
- 接入 Polymarket
- 日历里补上 VIX 交割等特别日子，避免踩坑
- 对接 hypeliquid whale API（https://docs.coinglass.com/reference/hyperliquid-whale-alert）
  数据源（行情）

- 策略引擎

- 回测模块

- 风控

- 执行层（连接 IBKR/Alpaca）

- 日志系统

- 任务调度、重试逻辑
