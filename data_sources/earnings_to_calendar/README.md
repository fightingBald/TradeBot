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
python -m data_sources.earnings_to_calendar --help
```

典型拉取命令：
```bash
cd /path/to/AlpacaTrading
python -m data_sources.earnings_to_calendar \
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
- `--icloud-insert`：同步到 iCloud，需提供 `--icloud-id` 与 `--icloud-app-pass`。

## 配置文件（可选）

命令支持通过 `--config` 指定配置文件（默认读取 `config/earnings_to_calendar.toml`）：
```json
{
  "symbols": ["AAPL", "MSFT", "NVDA"],
  "source": "finnhub",
  "days": 60,
  "google_insert": true,
  "google_credentials": "credentials.json",
  "google_token": "token.json",
  "google_calendar_name": "Company Earnings",
  "google_create_calendar": true,
 "icloud_insert": false
}
```

运行时可省略已在配置中声明的选项（TOML 支持 `#` 注释，方便按需禁用字段）：
```bash
cd /path/to/AlpacaTrading
python -m data_sources.earnings_to_calendar --config=config/earnings_to_calendar.toml
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
  python -m data_sources.earnings_to_calendar \
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
5. 想要固定配置？直接编辑 `config/earnings_to_calendar.toml`（可随时注释/启用字段），以后直接：
   ```bash
   cd /path/to/AlpacaTrading
   python -m data_sources.earnings_to_calendar --config=config/earnings_to_calendar.toml --env-file=.env --log-level=INFO
   ```
   （相对路径如 `secrets/credentials.json` 会自动按项目根目录解析，若需要其他位置请使用绝对路径或写成 `../path/to/file`。`--log-level` 支持 `DEBUG|INFO|WARNING|ERROR|CRITICAL`，便于调试请求；如需自动创建并写入指定名称的日历，可配合 `--google-calendar-name` 与 `--google-create-calendar`。）
6. 想要顺便导出备份？加上 `--export-ics=earnings.ics` 就会多生成一个 ICS 文件。

## 代码结构

- `config.py`：常量配置，如默认天数、请求超时、User-Agent。
- `domain.py`：`EarningsEvent` 模型及去重、日期解析工具。
- `providers.py`：数据源适配层，目前支持 FMP 与 Finnhub。
- `calendars.py`：ICS 构建与 Google/iCloud 写入逻辑。
- `cli.py`：命令行入口逻辑，可独立调用 `main()`。
- `__init__.py`：对外统一导出。

可直接在其他模块中导入：
```python
from data_sources.earnings_to_calendar import FmpEarningsProvider, build_ics
```
