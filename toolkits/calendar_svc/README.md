# 日历底层库说明（`toolkits/calendar_svc`）

## 为啥单独拆成库？
CLI、服务、notebook 都得复用同一套逻辑：抓财报、拼宏观事件、清洗后输出到 ICS/Google/iCloud。所以这里只放“纯业务逻辑”，不掺命令行解析，让其它层随便调用。

## 模块速查表

| 模块 | 职责 |
| --- | --- |
| `defaults.py` | 默认常量（时区、事件时长、会话时间映射等）。 |
| `domain.py` | `EarningsEvent` 等数据结构 + 去重、排序辅助。 |
| `providers.py` | FMP / Finnhub 财报抓取适配器。 |
| `macro_events.py` | Benzinga 宏观数据抓取。 |
| `market_events.py` | 生成四巫日、OPEX、VIX 交割等补充事件。 |
| `calendars.py` | 输出渠道：ICS、本地文件、Google、iCloud CalDAV。 |
| `settings.py` | 统一处理 `.env` + TOML/JSON + CLI 参数，最终拼成 `RuntimeOptions`。 |
| `runner.py` | 高层编排：抓事件 → 合并去重 → 写入输出 → 产出 `RunSummary`。 |
| `sync_state.py` | Google 增量同步状态文件读写。 |
| `logging_utils.py` | 统一 logger。 |

## 最小示例

```python
import argparse
from pathlib import Path
from toolkits.calendar_svc import build_runtime_options, load_config, load_env_file, run

project_root = Path(__file__).resolve().parents[1]
load_env_file(".env", search_root=project_root)

config_data, config_base = load_config(
    "config/events_to_google_calendar.toml",
    default_path=project_root / "config" / "events_to_google_calendar.toml",
)

args = argparse.Namespace(
    symbols="AAPL,MSFT",
    source="fmp",
    days=45,
    export_ics="earnings.ics",
    google_insert=False,
    google_credentials=None,
    google_token=None,
    google_calendar_id=None,
    google_calendar_name=None,
    google_create_calendar=False,
    source_tz=None,
    target_tz=None,
    event_duration=None,
    session_times=None,
    market_events=True,
    macro_events=False,
    macro_event_keywords=None,
    macro_event_source="benzinga",
    incremental=False,
    sync_state_path=None,
    icloud_insert=False,
    icloud_id=None,
    icloud_app_pass=None,
)

options = build_runtime_options(args, config_data, config_base=config_base, project_root=project_root)
summary = run(options)
print(f"共处理 {len(summary.events)} 条事件")
```

只想单独抓宏观事件，也能直接调用：

```python
from datetime import date
from toolkits.calendar_svc import RuntimeOptions, fetch_macro_events

options = RuntimeOptions(
    symbols=["AAPL"],
    source="fmp",
    days=30,
    export_ics=None,
    google_insert=False,
    google_credentials="secrets/credentials.json",
    google_token="secrets/token.json",
    google_calendar_id=None,
    google_calendar_name=None,
    google_create_calendar=False,
    source_timezone="America/New_York",
    target_timezone="America/New_York",
    event_duration_minutes=60,
    session_time_map={"AMC": "17:00"},
    market_events=False,
    icloud_insert=False,
    icloud_id=None,
    icloud_app_pass=None,
    macro_events=True,
    macro_event_keywords=[],
    macro_event_source="benzinga",
    incremental_sync=False,
    sync_state_path=None,
)

events = fetch_macro_events(date(2025, 1, 1), date(2025, 1, 31), options)
for evt in events:
    print(evt.summary(), evt.notes)
```

写 Google Calendar 只想靠底层 API 也行：

```python
from toolkits.calendar_svc import GoogleCalendarConfig, google_insert

cfg = GoogleCalendarConfig(
    calendar_name="Company Earnings",
    create_if_missing=True,
    creds_path="secrets/credentials.json",
    token_path="secrets/token.json",
)
calendar_id = google_insert(events, config=cfg)
print("成功写入日历：", calendar_id)
```

## 运行前需要的环境
- `FMP_API_KEY` / `FINNHUB_API_KEY` / `BENZINGA_API_KEY`：按需提供。
- `GOOGLE_*`：写 Google 时要指定 credentials/token/calendar。
- `ICLOUD_*`：走 CalDAV 时要 Apple ID + App Password。
- 建议用 `load_env_file()` 读取 `.env`，减少硬编码。

## 和 CLI 的关系
- 官方 CLI 在 `py_scripts/calendar/run.py`，里面只是做参数解析，最后还是调 `runner.run()`。
- 想扩展自己的 CLI 或服务，只要 import 这些模块即可，不需要复制粘贴逻辑。
