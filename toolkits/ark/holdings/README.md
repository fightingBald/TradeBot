# ARK 持仓数据源说明

## 这个包解决什么问题？
每天美股收盘后，ARK 系列 ETF（木头姐家的 ARKK、ARKQ 等）会更新官方 CSV。这里负责：
- 自动下载对应 CSV；
- 清洗列名/格式，统一成 Pydantic 模型；
- 输出好用的 `HoldingSnapshot`，方便做差分、汇总、推送通知。

## 提供的能力
- `fetch_holdings_snapshot(etf)`：下载并解析指定 ETF。
- `FUND_CSV`：枚举所有支持的 ETF，便于批量抓取。
- 数据字段都转为标准类型，比如权重直接变成 0~1 的小数，市值去掉 `$` 和逗号。

## 快速示例
```python
from toolkits.ark.holdings import FUND_CSV, fetch_holdings_snapshot

single = fetch_holdings_snapshot("ARKK")
print(single.as_of, len(single.holdings))

bulk = {fund: fetch_holdings_snapshot(fund) for fund in FUND_CSV}
```

## `Holding` 模型字段
| 字段 | 说明 |
| --- | --- |
| `as_of` | 快照日期（交易日） |
| `etf` | ETF 代码 |
| `company` | 公司全称 |
| `ticker` | 股票代码（统一大写） |
| `shares` | 持股数量（float） |
| `market_value` | 市值（美元） |
| `weight` | 在 ETF 中的权重占比（0~1） |
| `price` | 官方 CSV 当日价格（如果给出） |

## 更新频率
ARK 官方一般在每个交易日收盘后放出最新 CSV。周末/假期会延续上一份，没有新数据。

## 注意事项
- 如果官方 CSV 为空或结构变动，函数会抛异常；调用方自行决定重试策略。
- 这个模块只负责“抓 + 清洗”，存储、对比、通知逻辑请放到脚本或上层服务。
- 欢迎在 `toolkits/ark/holdings` 里继续加 diff 或聚合工具，但遵循“provider 只做抓数”的原则。

## 相关测试
- `tests/data_sources/ark_holdings/test_transform.py`：验证清洗逻辑。
- `tests/data_sources/ark_holdings/test_provider.py`：用 mock HTTP 校验快照结构。
