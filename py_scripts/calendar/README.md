# 财报日历 CLI 说明（`py_scripts/calendar/run.py`）

## 这玩意儿干嘛用？
负责把 FMP/Finnhub 抓到的财报、宏观事件整理成日历事件，可导出 ICS，也能直接推到 Google Calendar 或 iCloud。所有真正的业务逻辑在 `toolkits/calendar_svc/`，这个 README 只讲怎么用命令。

## 准备动作
```bash
cd /path/to/AlpacaTrading
source .venv/bin/activate        # 没有就先建 venv
pip install -e .
```

需要的环境变量放在 `.env`（示例）：
```
FMP_API_KEY=your_fmp_token
FINNHUB_API_KEY=your_finnhub_token
BENZINGA_API_KEY=your_benzinga_token
GOOGLE_CREDENTIALS_PATH=secrets/credentials.json
GOOGLE_TOKEN_PATH=secrets/token.json
GOOGLE_CALENDAR_NAME=Company Earnings
GOOGLE_CREATE_CALENDAR=true
```

## 查看帮助
```bash
earnings-calendar --help
# 或者 python -m py_scripts.calendar.run --help
```

## 常用命令
```bash
# 仅导出 ICS
earnings-calendar \
  --symbols=AAPL,MSFT,NVDA \
  --source=fmp \
  --days=90 \
  --export-ics=earnings.ics

# 用 TOML + .env，一次性写入 Google Calendar，并附带市场/宏观事件
earnings-calendar \
  --config=config/events_to_google_calendar.toml \
  --env-file=.env \
  --google-insert \
  --market-events \
  --macro-events \
  --log-level=INFO
```

## 参数大白话
- `--symbols`：逗号分隔的股票列表；不填就用配置文件的。
- `--source`：`fmp` 或 `finnhub`。
- `--days`：从今天起往后看几天。
- `--export-ics`：给个路径就会生成本地 ICS。
- `--google-insert` + `--google-*`：需要把事件写进 Google Calendar 时用。
- `--market-events` / `--macro-events`：附加衍生品结算日、Benzinga 宏观日历；`--macro-event-keywords` 可作白名单。
- `--incremental` + `--sync-state-path`：做增量同步，避免重复写 Google。
- `--icloud-insert` + `--icloud-*`：写 iCloud CalDAV。
- `--source-tz` / `--target-tz` / `--event-duration` / `--session-times`：各种时间设置。
- `--env-file`：默认找项目根目录 `.env`，也可以指定其它路径。
- `--config`：TOML/JSON 配置；默认是 `config/events_to_google_calendar.toml`，文件不存在会自动生成模板。

优先级：命令行 > TOML > `.env` > 默认值。只覆盖你关心的字段就好。

## `.env` 与配置文件
- `.env` 存 API Key、Google 凭据位置、是否默认写入 Google 等开关。
- `config/events_to_google_calendar.toml` 存符号列表、时区、会话时间、是否启用市场/宏观事件、增量同步路径等。首次跑如果没有会自动创建一份模板。

## Google Calendar 授权
1. Google Cloud Console 打开 Calendar API，下载 `credentials.json`。
2. 放到仓库的 `secrets/credentials.json`（目录在 `.gitignore` 里，安全）。
3. 首次运行带 `--google-insert` 的命令时，浏览器会提示授权；登录完成后会生成 `token.json`，以后都会复用。

## 其它提醒
- 直接写脚本也行，`toolkits.calendar_svc` 里导出的函数都可用。
- CI 场景也是跑这个 CLI，所有需要的东西都能用环境变量注入。
