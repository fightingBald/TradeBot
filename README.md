# AlpacaTrading 项目说明

## 这套东西是干嘛的？
* 一套本地可跑的 FastAPI 服务，实时去 Alpaca 拉行情，顺手画热力图页面。
* 一堆脚本（`py_scripts/`）帮忙管仓位：批量设置止损、同步财报/宏观日历、抓 ARK ETF 持仓、发邮件。
* 共享的业务逻辑放在 `toolkits/`，方便 CLI、服务、notebook 复用。
* 先做风控和执行，别先做“预测未来”
*  撤A买B要状态机	订单状态不同步是散户第一死因
*  半人马模式最适合散户 机器砍手，我扣扳机
*  系统设计要允许多账号papaer tarding ， real trading 切换
## 环境/账号要求
- Python 3.10 以上（本地推荐装成 `.venv`）。
- Alpaca 账号和一对 API Key（写入 `.env` 或环境变量）。
- 可选：FMP/Finnhub/Benzinga/Google/iCloud 等三方 Key，按需放进 `.env`。

## 快速开工（建议逐条敲）
```bash
cd /path/to/AlpacaTrading
python -m venv .venv
source .venv/bin/activate  # Windows 用 .venv\Scripts\activate
pip install -e .
```

`.env` 示范（缺啥补啥）：
```
ALPACA_API_KEY=xxx
ALPACA_API_SECRET=xxx
ALPACA_DATA_FEED=iex
ALPACA_TRADING_BASE_URL=https://paper-api.alpaca.markets
ALPACA_PAPER_TRADING=true
FMP_API_KEY=xxx
FINNHUB_API_KEY=xxx
BENZINGA_API_KEY=xxx
GOOGLE_CREDENTIALS_PATH=secrets/credentials.json
GOOGLE_TOKEN_PATH=secrets/token.json
```

## 跑 FastAPI 服务
```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```
跑起来后：
- `GET /health`：心跳。
- `GET /quotes`：实时报价，可加 `?symbols=AAPL&symbols=MSFT`。
- `GET /positions`：读取账户持仓（需要交易端权限）。
- `GET /`：五秒刷一次的热力图 Dashboard。

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
改动完建议起码跑 `build` / `lint` / `test` 各一次。

## 目录结构速览
- `app/`：FastAPI（配置、模型、服务、模板）。
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

Kubernetes 运行框架（符合你平时 MDB Marketplace 的风格）
有其它点子就直接在 README 最后增删，保持这份文档信息最新。***
