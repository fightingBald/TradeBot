# Earnings → Calendar Package

该包提供从多家数据源抓取财报日期并同步到日历（ICS、Google Calendar、iCloud CalDAV）的 CLI / 库能力。

## 环境准备

> 以下命令均假设在项目根目录执行：`cd /path/to/AlpacaTrading`

1. 准备 Python 虚拟环境并安装仓库依赖：
   ```bash
   cd /path/to/AlpacaTrading
   pip install -r requirements.txt
   ```
2. 配置所需数据源的 API Key：
   ```bash
   cd /path/to/AlpacaTrading
   export FMP_API_KEY=your_fmp_token        # 使用 FMP 数据源
   export FINNHUB_API_KEY=your_finnhub_token  # 使用 Finnhub 数据源
   ```

## 命令行用法

运行帮助查看全部参数：
```bash
cd /path/to/AlpacaTrading
python -m earnings.calendar --help
```

典型拉取命令：
```bash
cd /path/to/AlpacaTrading
python -m earnings.calendar \
  --symbols=AAPL,MSFT,NVDA \
  --source=fmp \
  --days=90 \
  --export-ics=earnings.ics
```

常用选项说明：
- `--symbols`：逗号分隔的股票代码。
- `--source`：`fmp`（默认）或 `finnhub`。
- `--days`：查询起止区间（今天起算）天数，默认 120。
- `--export-ics`：将结果导出为本地 ICS 文件。
- `--google-insert`：直接写入 Google Calendar，需要 `--google-credentials` 和 `--google-token`。
- `--google-calendar-id` / `--google-calendar-name`：指定目标日历；未提供时默认使用 `primary`，若只给 name 可配合 `--google-create-calendar` 自动创建。
- `--market-events`：追加四巫日 / OPEX / VIX 等市场事件。
- `--macro-events`：追加宏观经济事件（FOMC / CPI / NFP 等），可配合 `--macro-event-keywords` 精准筛选。
- `--incremental`：开启 Google Calendar 增量同步（仅对 Google 写入生效）。
- `--sync-state-path`：指定增量同步状态文件路径（默认为 `.cache/earnings_sync.json`）。
- `--icloud-insert`：同步到 iCloud，需提供 `--icloud-id` 与 `--icloud-app-pass`。

## 配置文件（可选）

命令默认读取 `config/earnings_to_calendar.toml`（首次运行会自动生成模板），其中可配置：
- `source_timezone` / `target_timezone`：数据源时区与日历写入时区；
- `event_duration_minutes`：默认事件时长（分钟）；
- `[session_times]`：将诸如 `BMO`、`AMC` 映射到具体时间；
- `market_events`：是否同时加入四巫日/OPEX/VIX 结算等市场事件；
- `macro_events`：是否追加宏观事件（FOMC / ECB / BOE / BOJ 决议、CPI / PPI、NFP、零售销售、ISM、财政部拍卖等）；
- `macro_event_keywords`：宏观事件关键词白名单，默认覆盖常见项目，可按需增删；
- `incremental_sync` / `sync_state_path`：开启并配置增量同步状态文件，避免重复向 Google Calendar 写入未变化事件；
TOML 支持 `#` 注释，可按需启用/关闭字段，也可以通过 `--config=...` 指向其他 TOML/JSON 文件。

运行时只需覆盖想临时调整的字段（TOML 支持 `#` 注释，方便禁用配置）：
```bash
cd /path/to/AlpacaTrading
python -m earnings.calendar --config=config/earnings_to_calendar.toml
```
若命令行提供了相同参数，将优先覆盖配置文件内的数值。

## 使用 `.env` 管理敏感信息

- 把 API Key、Google/iCloud 凭据路径写进项目根目录的 `.env`（已在 `.gitignore` 中），例如：
  ```
  FMP_API_KEY=你的FMP密钥
  GOOGLE_CREDENTIALS_PATH=secrets/credentials.json
  GOOGLE_TOKEN_PATH=secrets/token.json
  GOOGLE_INSERT=true
  GOOGLE_CALENDAR_NAME=Company Earnings
  GOOGLE_CREATE_CALENDAR=true
  ICLOUD_INSERT=false
  ICLOUD_APPLE_ID=user@icloud.com
  ICLOUD_APP_PASSWORD=xxxx-xxxx
  ```
- 运行命令时会自动读取当前目录的 `.env`；若想指定别的路径，可用 `--env-file=/path/to/.env`。
- 建议把真实的 `credentials.json` / `token.json` 等敏感文件放在仓库忽略的 `secrets/` 目录（项目已提供 `.gitkeep` 与 `.gitignore`），避免误提交。
- `.env` 不要提交到仓库；如需共享模板，可参考根目录的 `.env.example`。

## 如何把财报日程同步到 Google Calendar（大白话版）

1. 到 Google Calendar API 的 Quickstart 页面下载 `credentials.json`，放到 `secrets/credentials.json`（或其他安全路径，并在 `.env` / 命令参数里指向该路径）。
2. 准备好数据源的 API Key，例如：
   ```bash
   cd /path/to/AlpacaTrading
   export FMP_API_KEY=你的FMP密钥
   ```
3. 第一次运行命令：
   ```bash
   cd /path/to/AlpacaTrading
      python -m earnings.calendar \
        --symbols=AAPL,MSFT,NVDA \
        --source=fmp \
        --google-insert \
        --google-credentials=secrets/credentials.json \
        --google-token=secrets/token.json \
        --google-calendar-name="Company Earnings" \
        --google-create-calendar
   ```
   跑起来后会跳浏览器让你授权，授权完会在同目录生成 `token.json`（以后会自动刷新）。
4. 到 Google Calendar（默认的 primary 日历）里看下有没有新的财报提醒。
5. 想要固定配置？直接编辑 `config/earnings_to_calendar.toml`（仓库已给出示例），以后直接：
   ```bash
   cd /path/to/AlpacaTrading
   python -m earnings.calendar --config=config/earnings_to_calendar.toml --env-file=.env --log-level=INFO
   ```
   （相对路径如 `secrets/credentials.json` 会自动按项目根目录解析，若需要其他位置请使用绝对路径或写成 `../path/to/file`。`--log-level` 支持 `DEBUG|INFO|WARNING|ERROR|CRITICAL`，便于调试请求；如需自动创建并写入指定名称的日历，可配合 `--google-calendar-name` 与 `--google-create-calendar`。）
6. 想要顺便导出备份？加上 `--export-ics=earnings.ics` 就会多生成一个 ICS 文件。

## 代码结构

- `defaults.py`：封装默认天数、超时、User-Agent 等常量。
- `domain.py`：`EarningsEvent` 模型及去重、日期解析工具。
- `providers.py`：数据源适配层，目前支持 FMP 与 Finnhub。
- `market_events.py`：生成四巫日 / OPEX / VIX 结算等市场事件。
- `macro_events.py`：抓取并归一化宏观经济事件（FOMC / CPI / NFP 等）。
- `settings.py`：解析 `.env`、配置文件与 CLI 参数，产出 `RuntimeOptions`。
- `runner.py`：主业务编排（拉取数据、写 ICS/Google/iCloud），并输出运行概要。
- `calendars.py`：ICS 构建与 Google/iCloud 写入逻辑。
- `sync_state.py`：管理增量同步状态文件与差异计算。
- `cli.py`：命令行入口，负责解析参数与调用 `runner.run()`。
- `__init__.py`：对外统一导出。

可直接在其他模块中导入：
```python
from src.earnings.calendar import FmpEarningsProvider, build_ics
```
