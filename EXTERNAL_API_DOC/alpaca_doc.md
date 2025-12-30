
> 适用日期：**2025-12-30**（按 Alpaca 官方文档与页面整理） ([Alpaca API Docs][1])

---

# Alpaca API 使用指南（Free Plan / Copilot 版）

## 0. 目标与范围

* 目标：提供 Alpaca **Trading API（交易）** + **Market Data API（行情/新闻/期权/加密）** 的可实现接口清单、URL、鉴权方式、免费套餐限制、WebSocket 订阅协议与错误码。
* 读者：Copilot / 代码生成器（内容偏“可执行”而非“教学”）。
* 非目标：策略、指标、下单逻辑本身（那是你们系统自己的事）。

---

## 1. 套餐能力与硬限制（Free / Basic）

### 1.1 免费套餐行情源限制（股票）

* 免费用户 **实时股票 WebSocket 只能用 IEX feed**：`wss://stream.data.alpaca.markets/v2/iex` ([Alpaca API Docs][2])
* 试用/自检 stream：`wss://stream.data.alpaca.markets/v2/test`，symbol 用 `FAKEPACA` ([Alpaca API Docs][3])

### 1.2 免费套餐 WebSocket 连接与订阅上限（重要）

* **同一个 endpoint 通常只允许 1 条并发 WebSocket 连接**，多开会 406（connection limit exceeded）。 ([Alpaca API Docs][3])
* 免费套餐对 **trades/quotes 的订阅 symbol 数量**存在上限（常见描述：**30 个 channel**），minute bars 通常不受同样限制（以官方说明为准）。 ([Alpaca][4])

### 1.3 历史/REST 调用速率（免费套餐）

* Market Data（历史/REST）免费套餐常见速率：**200 calls/min**（以及历史数据限制条款以官方为准）。 ([Alpaca API Docs][5])

### 1.4 交易 API 速率（跟行情订阅无关）

* Trading API 常见默认：**200 requests/min 每个 account**（paper 与 live 分开算）。([Alpaca Community Forum][6])
* Trading API 响应 header 会给速率信息（用于退避/节流）：`X-Ratelimit-Limit / Remaining / Reset`。 ([Alpaca Community Forum][7])

### 1.5 期权数据（免费套餐）

* WebSocket 期权 stream：`wss://stream.data.alpaca.markets/v1beta1/{feed}`

    * 免费/基础计划通常只能用 **indicative**（不是 OPRA 全量实时）。 ([Alpaca API Docs][8])
    * **期权 stream 只有 msgpack**（不是 JSON）。 ([Alpaca API Docs][8])

---

## 2. 鉴权（Trading / Market Data 通用）

### 2.1 Header 鉴权（最常用）

所有私有接口（交易/多数行情）使用 HTTP headers：

* `APCA-API-KEY-ID: <KEY_ID>`
* `APCA-API-SECRET-KEY: <SECRET_KEY>`

([Alpaca API Docs][1])

### 2.2 Paper 与 Live 分离（别把真钱当纸烧）

* Live domain：`https://api.alpaca.markets`
* Paper domain：`https://paper-api.alpaca.markets`
* **Paper keys 与 Live keys 不同**，API 规格相同，切换就是换 domain + 换 key。 ([Alpaca API Docs][1])

---

## 3. Base URLs 总表（建议写进配置）

```yaml
alpaca:
  trading:
    live_base_url: "https://api.alpaca.markets"
    paper_base_url: "https://paper-api.alpaca.markets"
    trading_api_version: "v2"

  market_data_rest:
    base_url: "https://data.alpaca.markets"

  market_data_ws:
    stocks_free_ws: "wss://stream.data.alpaca.markets/v2/iex"
    stocks_test_ws: "wss://stream.data.alpaca.markets/v2/test"
    news_ws: "wss://stream.data.alpaca.markets/v1beta1/news"
    crypto_ws_template: "wss://stream.data.alpaca.markets/v1beta3/crypto/{loc}"
    options_ws_template: "wss://stream.data.alpaca.markets/v1beta1/{feed}"  # feed=indicative/opra
```

对应依据：股票/新闻/加密/期权 WS 地址与模板见官方文档。 ([Alpaca API Docs][9])

---

## 4. Trading API（REST，v2）关键用法清单

> 域名：paper 用 `https://paper-api.alpaca.markets`；live 用 `https://api.alpaca.markets`；路径一般从 `/v2/...` 开始。 ([Alpaca API Docs][1])

### 4.1 账户

* `GET /v2/account`：账户信息、购买力等（用于风控面板） ([Alpaca API Docs][1])

### 4.2 持仓

* `GET /v2/positions`：全部持仓
* `GET /v2/positions/{symbol}`：单票持仓
  （SDK 也直接封装了 positions） ([Alpaca][10])

### 4.3 订单

* `POST /v2/orders`：下单
* `GET /v2/orders`：查订单（open/closed、按时间过滤等）
* `DELETE /v2/orders/{order_id}`：撤单
* `DELETE /v2/orders`：批量撤单（通常是 cancel all） ([Alpaca][10])

### 4.4 资产列表

* `GET /v2/assets`：可交易标的列表（检查 tradable 等） ([GitHub][11])

### 4.5 Trading API 速率控制（必须实现）

* 按 header 做节流；遇到 `429 rate limit exceeded` 就等到 `X-Ratelimit-Reset` 再继续。 ([Alpaca Community Forum][7])

---

## 5. Trading WebSocket（订单/成交/账户更新：trade_updates）

> 这是“交易状态流”，跟行情 WS 是两条不同的线。

* endpoint：

    * paper：`wss://paper-api.alpaca.markets/stream`
    * live：`wss://api.alpaca.markets/stream` ([Alpaca API Docs][12])
* listen 消息（订阅 trade_updates）：

```json
{
  "action": "listen",
  "data": { "streams": ["trade_updates"] }
}
```

([Alpaca API Docs][12])

* 注意：paper 的 trade_updates 可能走 **binary frame**（跟 data stream 的 text frame 不同）。 ([Alpaca API Docs][12])

### 推荐 SDK（Python）

* `alpaca-py`：

    * `TradingClient(...)` 走 REST
    * `TradingStream(...).subscribe_trade_updates(handler)` 走 trade_updates ([Alpaca][10])

---

## 6. Market Data WebSocket（行情/新闻/加密/期权）

### 6.1 通用协议（连接 → 认证 → subscribe）

* URL 模板：`wss://stream.data.alpaca.markets/{version}/{feed}`（以及各子类 endpoint）([Alpaca API Docs][3])
* 连接成功回包：`[{"T":"success","msg":"connected"}]` ([Alpaca API Docs][3])
* 认证（消息方式，连接后 10 秒内完成）：

```json
{"action":"auth","key":"<KEY_ID>","secret":"<SECRET>"}
```

([Alpaca API Docs][3])

* subscribe 示例（股票 trades/quotes/bars）：

```json
{"action":"subscribe","trades":["AAPL"],"quotes":["AMD"],"bars":["*"]}
```

([Alpaca API Docs][9])

### 6.2 股票（Free：IEX）

* Free 实时股票 WS：`wss://stream.data.alpaca.markets/v2/iex` ([Alpaca API Docs][2])
* 频道：trades / quotes / bars / 等（按官方 stock stream 文档） ([Alpaca API Docs][9])

### 6.3 新闻（real-time news）

* WS：`wss://stream.data.alpaca.markets/v1beta1/news`
* 消息类型：`T="n"`（news），字段含 headline/summary/content/url 等。 ([Alpaca API Docs][13])

### 6.4 加密（crypto）

* WS 模板：`wss://stream.data.alpaca.markets/v1beta3/crypto/{loc}`，loc 如 `us / us-1 / eu-1` ([Alpaca API Docs][14])

### 6.5 期权（options）

* WS 模板：`wss://stream.data.alpaca.markets/v1beta1/{feed}`，feed 取 `indicative` 或 `opra`（取决于订阅） ([Alpaca API Docs][8])
* **仅 msgpack**：客户端必须 msgpack 解码。 ([Alpaca API Docs][8])

### 6.6 WebSocket 错误码（必须处理）

常见错误（节选）：

* 401 not authenticated（先 auth 再 subscribe）
* 405 symbol limit exceeded（免费订阅数超了）
* 406 connection limit exceeded（你多开 WS 了）
* 407 slow client（处理太慢会被踢）
* 409 insufficient subscription（你订阅了付费 feed）
* 410 invalid subscribe action for this feed（比如对 news stream 订 trades） ([Alpaca API Docs][3])

---

## 7. Market Data REST（历史数据 / 拉 bars 等）

* 历史股票 bars 示例（feed 参数可选 iex/sip；免费一般用 iex）：
  `GET https://data.alpaca.markets/v2/stocks/{SYMBOL}/bars?feed=iex&timeframe=...` ([Alpaca API Docs][2])

* 期权链/快照（链路之一）：
  `https://data.alpaca.markets/v1beta1/options`（用于 option chain retrieval 的常见 base） ([Alpaca][15])

---

## 8. “我免费用户，支持 WebSocket 吗？”（给 Copilot 的结论句）

**支持**，但免费用户股票实时 WebSocket 只能连 **IEX**，通常只允许 **1 条并发连接**，并且 trades/quotes 订阅数量有限（常见为 30）。 ([Alpaca][4])

---

## 9. 实现建议（面向你“Streamlit 看板 + 交易机器人”那套）

### 9.1 不要在 Streamlit 里直接维持行情 WS（除非你就一个页面玩玩）

原因：免费套餐 **WS=1 条**，Streamlit rerun/多标签页/热重载都很容易把连接搞成“幽灵多开”，然后你就被 406 踢出。 ([Alpaca API Docs][3])

**推荐模式：**

* 单独起一个 `marketdata_daemon`（后台常驻进程）：

    * 独占 WebSocket（IEX）
    * 把最新 quotes/bars/news 写到 Redis / 内存缓存
* Streamlit 只读缓存（轮询 Redis / HTTP 拉取）
* Trading 部分用 REST + trade_updates stream 做“最终一致”

（这条是工程建议，不是 Alpaca 文档原句。）

### 9.2 持仓获取：REST 轮询 + trade_updates 增量

* “真相源”：`GET /v2/positions`（定时全量刷新）
* “事件流”：trade_updates（成交/撤单/拒单触发 UI 更新） ([Alpaca][10])

### 9.3 节流铁律

* Trading API：严格按 200/min 做节流，读 `X-Ratelimit-*` headers 实现自适应退避。 ([Alpaca Community Forum][7])
* Market Data REST：按免费计划限制做节流（官方页面/表格写了 200/min 级别）。 ([Alpaca API Docs][5])

---

## 10. Copilot 可用的最小配置 Schema（建议）

```yaml
profile:
  name: "paper_default"
  mode: "paper"            # paper|live
  broker: "alpaca"
  api_key_id: "${APCA_API_KEY_ID}"
  api_secret: "${APCA_API_SECRET_KEY}"

alpaca:
  trading_base_url: "https://paper-api.alpaca.markets"
  market_data_rest_base_url: "https://data.alpaca.markets"
  market_data_ws_url: "wss://stream.data.alpaca.markets/v2/iex"

limits:
  trading_requests_per_min: 200
  ws_max_connections_per_endpoint: 1
  ws_symbol_limit_trades_quotes: 30
```

