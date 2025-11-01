# Earnings → Calendar Package

该包提供从多家数据源抓取财报日期并同步到日历（ICS、Google Calendar、iCloud CalDAV）的 CLI / 库能力。

## 环境准备

1. 准备 Python 虚拟环境并安装仓库依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 配置所需数据源的 API Key：
   ```bash
   export FMP_API_KEY=your_fmp_token        # 使用 FMP 数据源
   export FINNHUB_API_KEY=your_finnhub_token  # 使用 Finnhub 数据源
   ```

## 命令行用法

运行帮助查看全部参数：
```bash
python -m data_sources.earnings_to_calendar --help
```

典型拉取命令：
```bash
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
- `--icloud-insert`：同步到 iCloud，需提供 `--icloud-id` 与 `--icloud-app-pass`。

## 配置文件（可选）

命令支持通过 `--config` 指定 JSON 配置文件，集中管理常用参数：
```json
{
  "symbols": ["AAPL", "MSFT", "NVDA"],
  "source": "finnhub",
  "days": 60,
  "google_insert": true,
  "google_credentials": "credentials.json",
  "google_token": "token.json",
  "icloud_insert": false
}
```

运行时可省略已在配置中声明的选项：
```bash
python -m data_sources.earnings_to_calendar --config=./earnings_config.json
```
若命令行提供了相同参数，将优先覆盖配置文件内的数值。

## 如何把财报日程同步到 Google Calendar（大白话版）

1. 到 Google Calendar API 的 Quickstart 页面下载 `credentials.json`，丢在项目根目录（或者你喜欢的路径，后面命令要对应）。
2. 准备好数据源的 API Key，例如：
   ```bash
   export FMP_API_KEY=你的FMP密钥
   ```
3. 第一次运行命令：
   ```bash
   python -m data_sources.earnings_to_calendar \
     --symbols=AAPL,MSFT,NVDA \
     --source=fmp \
     --google-insert \
     --google-credentials=credentials.json \
     --google-token=token.json
   ```
   跑起来后会跳浏览器让你授权，授权完会在同目录生成 `token.json`（以后会自动刷新）。
4. 到 Google Calendar（默认的 primary 日历）里看下有没有新的财报提醒。
5. 想要固定配置？写一个 JSON（比如 `earnings_config.json`）：
   ```json
   {
     "symbols": ["AAPL", "MSFT", "NVDA"],
     "source": "fmp",
     "days": 90,
     "google_insert": true,
     "google_credentials": "credentials.json",
     "google_token": "token.json"
   }
   ```
   以后直接：
   ```bash
   python -m data_sources.earnings_to_calendar --config=earnings_config.json
   ```
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
