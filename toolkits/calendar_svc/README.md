# Calendar Library (`toolkits/calendar_svc`)

该目录只包含**库代码**，供脚本或其他服务调用。CLI/运行脚本全部移到了
`py_scripts/calendar/`，若需要命令行用法请阅读那里的 README。

## 模块概览

| 模块            | 说明                                                                          |
| --------------- | ----------------------------------------------------------------------------- |
| `defaults.py`   | 默认常量（超时、时区、事件时长、Session 映射等）。                            |
| `domain.py`     | `EarningsEvent` 数据结构、去重与辅助函数。                                    |
| `providers.py`  | FMP / Finnhub 财报数据抓取适配器。                                            |
| `macro_events.py` | Benzinga 宏观事件抓取与归一化。                                             |
| `market_events.py` | 生成四巫日 / OPEX / VIX 等衍生市场事件。                                   |
| `calendars.py`  | ICS 构建、Google Calendar 写入、iCloud CalDAV 写入。                          |
| `settings.py`   | 解析 `.env` + 配置文件 + CLI 参数，产出 `RuntimeOptions`。                    |
| `runner.py`     | 高层编排：`collect_events` → `apply_outputs`，并返回 `RunSummary`。           |
| `sync_state.py` | 增量同步状态文件读写与 diff 计算。                                            |
| `logging_utils.py` | 统一 logger。                                                              |
| `__init__.py`   | 导出所有常用 API，方便上层直接 `from toolkits.calendar_svc import ...`。              |

## 快速示例

以下代码演示如何在自定义脚本中直接调用库 API：

```python
from datetime import date
from pathlib import Path
from toolkits.calendar_svc import (
    RuntimeOptions,
    build_runtime_options,
    load_config,
    load_env_file,
    run,
)

project_root = Path(__file__).resolve().parents[1]
load_env_file(".env", search_root=project_root)

config_data, config_base = load_config(
    "config/earnings_to_calendar.toml",
    default_path=project_root / "config" / "earnings_to_calendar.toml",
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
    env_file=None,
    config=None,
    log_level="INFO",
)

options: RuntimeOptions = build_runtime_options(
    args,
    config_data,
    config_base=config_base,
    project_root=project_root,
)

summary = run(options)
print("Fetched", len(summary.events), "events")
```

或者只想单独取宏观事件：

```python
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
    incremental_sync=False,
    sync_state_path=None,
)

macros = fetch_macro_events(date(2025, 1, 1), date(2025, 1, 31), options)
for event in macros:
    print(event.summary(), event.notes)
```

若只想把手头的 `EarningsEvent` 写进 Google Calendar，可以直接使用
`GoogleCalendarConfig`：

```python
from toolkits.calendar_svc import GoogleCalendarConfig, google_insert

config = GoogleCalendarConfig(
    calendar_name="Company Earnings",
    create_if_missing=True,
    creds_path="secrets/credentials.json",
    token_path="secrets/token.json",
)
calendar_id = google_insert(events, config=config)
print("Inserted events into", calendar_id)
```

## 依赖注入与运行环境

- HTTP 请求依赖外部 `FMP_API_KEY`、`FINNHUB_API_KEY`、`BENZINGA_API_KEY` 等环境变量。
- `load_env_file()` 可读取 `.env` 风格文件，在脚本/测试里注入变量。
- `build_runtime_options()` 是连接 CLI 参数、配置文件与 `.env` 的统一入口。即便不使用官方脚本，也建议借助它来生成 `RuntimeOptions`。
- 写入 Google / iCloud 时，需要 `calendars.google_insert()`、`calendars.icloud_caldav_insert()` 所需的证书/凭据，调用者需自行准备。

## 相关脚本

- `py_scripts/calendar/run.py`：官方 CLI 封装，演示如何组装 `.env + TOML + CLI` 并调用 `run()`。
- `py_scripts/calendar/README.md`：包含所有命令行参数说明、示例命令及 `.env` / 配置文件模板。

本目录不会包含任何“命令行入口”或“环境配置”说明，保证其始终作为纯库存在。如需扩展 CLI，请在 `py_scripts/` 下新增脚本并调用这里导出的 API。 
