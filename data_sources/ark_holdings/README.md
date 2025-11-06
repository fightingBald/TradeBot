**# ARK Holdings 数据源（大白话版）

这个包专门解决一个问题：**每天收盘后，抓取 ARK 系列 ETF（木头姐）最新的持仓快照**，并把数据清洗成我们统一的结构，方便后续做仓位追踪、通知或持久化。

## 📦 包含哪些功能？

- 自动下载 ARK 官方发布的 CSV 持仓文件（ARKK / ARKQ / ARKG / ARKF / ARKW / ARKX）。
- 解析并清洗所有字段（日期、权重百分比、金额等），转成 Pydantic 模型。
- 提供 `HoldingSnapshot` 对象，里面是当日的全量持仓列表。
- 支持一次性抓取所有 ETF 的快照。

## 🔧 快速上手

```python
from data_sources.ark_holdings import fetch_holdings_snapshot

snapshot = fetch_holdings_snapshot("ARKK")
print(snapshot.as_of)             # => datetime.date
print(len(snapshot.holdings))     # => 持仓数量
print(snapshot.holdings[0].ticker)
```

批量抓取：

```python
from data_sources.ark_holdings import FUND_CSV, fetch_holdings_snapshot

all_snapshots = {etf: fetch_holdings_snapshot(etf) for etf in FUND_CSV}
```

## 📁 数据字段说明

`Holding` 模型核心字段：

| 字段        | 说明                                  |
| ----------- | ------------------------------------- |
| `as_of`     | 快照日期（交易日）                     |
| `etf`       | ETF 代码，例如 `ARKK`                  |
| `company`   | 公司名称                               |
| `ticker`    | 股票代码（已统一成大写）               |
| `shares`    | 持股数量（float）                      |
| `market_value` | 市值（美元）                       |
| `weight`    | 在 ETF 中的权重（0~1 之间的小数）      |
| `price`     | 官方 CSV 中给出的最新价（如存在）      |

权重字段自动把 `12.30%` 转成 `0.123`，市值去掉 `$` 和逗号后转成数字。

## ⏰ 更新频率

ARK 官方 CSV 通常在**每个交易日收盘后**更新一次。周末或节假日会保持在最近一次交易日。

## ⚠️ 注意事项

- 网络异常或 ARK 暂时未更新时，CSV 可能为空（代码会抛出异常，调用方需决定是否重试）。
- 若需要落地存储（CSV/Parquet/数据库），建议在脚本层处理，方便统一管理输出路径。
- 后续可在此模块增加 diff/变动检测逻辑（例如 `tracker.py`），但保持 provider 本身只负责“抓 + 清洗”。

## ✅ 单元测试

- `tests/data_sources/ark_holdings/test_transform.py`：验证列名、数值清洗。
- `tests/data_sources/ark_holdings/test_provider.py`：Mock HTTP，确认快照结构正确。

