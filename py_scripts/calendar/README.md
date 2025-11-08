# Calendar CLI (`py_scripts/calendar/run.py`)

该脚本是 `toolkits/calendar_svc` 的官方命令行入口，负责解析参数、读取配置与 `.env`，最终调用库层完成“抓取财报/宏观事件 → 写入 ICS/Google/iCloud”。

## 环境准备

```bash
cd /path/to/AlpacaTrading
pip install -r requirements.txt
```

设置数据源凭据（示例）：

```bash
export FMP_API_KEY=your_fmp_token
export FINNHUB_API_KEY=your_finnhub_token
export BENZINGA_API_KEY=your_benzinga_token
```

## 查看帮助

```bash
cd /path/to/AlpacaTrading
python py_scripts/calendar/run.py --help
```

## 常见命令

```bash
# 拉取 FMP 数据并导出 ICS
python py_scripts/calendar/run.py \
  --symbols=AAPL,MSFT,NVDA \
  --source=fmp \
  --days=90 \
  --export-ics=earnings.ics

# 使用配置文件 + .env，直接写入 Google Calendar
python py_scripts/calendar/run.py \
  --config=config/earnings_to_calendar.toml \
  --env-file=.env \
  --google-insert \
  --market-events \
  --macro-events \
  --log-level=INFO
```

## 主要参数

- `--symbols`：逗号分隔股票代码（默认读取配置文件）。
- `--source`：`fmp` 或 `finnhub`。
- `--days`：查询区间天数。
- `--export-ics`：导出本地 ICS 文件。
- `--google-insert` 与相关 `--google-*` 参数：写入 Google Calendar 时需提供凭据/日历信息。
- `--market-events` / `--macro-events`：是否附加衍生市场事件或 Benzinga 宏观事件；`--macro-event-keywords` 可筛选事件。
- `--incremental` + `--sync-state-path`：开启 Google Calendar 增量同步，避免重复写入。
- `--icloud-insert` + `--icloud-*`：写入 iCloud CalDAV。
- `--source-tz` / `--target-tz`、`--event-duration`、`--session-times`：控制时间相关设置。
- `--env-file`：读取 `.env` 风格文件；未提供则默认寻找项目根目录 `.env`。
- `--config`：TOML/JSON 配置文件（默认 `config/earnings_to_calendar.toml`）。

## `.env` & 配置文件

- `.env` 示例：
  ```
  FMP_API_KEY=xxx
  BENZINGA_API_KEY=xxx
  GOOGLE_CREDENTIALS_PATH=secrets/credentials.json
  GOOGLE_TOKEN_PATH=secrets/token.json
  GOOGLE_INSERT=true
  ```
- `config/earnings_to_calendar.toml` 可配置 symbols、时区、会话时间映射、是否启用市场/宏观事件、增量同步等。脚本会自动在命令行参数 > TOML > `.env` > 默认值 之间取优先级。

## Google Calendar 授权流程

1. 从 Google API Console 下载 `credentials.json` 并放入 `secrets/credentials.json`。
2. 首次运行带 `--google-insert` 的命令，会跳转到浏览器授权；完成后会生成 `token.json`。
3. 后续脚本会自动复用/刷新该 token。

## 备注

- 自定义脚本可直接 `import toolkits.calendar_svc_svc` 调用业务函数；此处 CLI 只是官方示例。
- 如果需要在 CI 中运行，可沿用此脚本，再用环境变量或参数注入配置。 
