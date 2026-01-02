# 半人马交易机器人（Centaur Trading Bot）

## 1) 项目目标总揽（Project North Star）
- **定位**：半自动交易系统（Half-Automated / Centaur）
- **核心规则**：人类负责**买入决策**；机器人负责**风控 + 自动卖出 + 雷达信号**
- **市场范围**：美股（可扩展到与加密相关的美股，例如 COIN）
- **券商现状/未来**：
  - 当前：Alpaca
  - 未来必须支持：**多券商切换**（如 IBKR/Tradier/…）与 **同券商多账号**（Paper/Live/子账户）
- **下单风格**：只做 **Stop Buy / Stop Sell**（外加撤单/改单）
- **明确不做**：
  - 默认不做全自动买入（除非手动开启）
  - 不做高频/HFT

## 2) 当前目标描述（Current Focus: Local Desktop MVP）
目前想要获得这些信息

### 2.1 环境（Environment）
- 本地桌面运行（个人使用）
- 仅覆盖 Alpaca（支持 paper/live，但 live 默认关闭，需手动开启）
- 目标是“能稳定跑起来 + 不自爆”，先不追求功能全面

### 2.2 前端（Frontend / GUI）
- **你能看到的**：
  - 账户概览（净值/现金/当日盈亏等）
  - 持仓分布（仓位/权重/盈亏）
  - 订单与执行结果概览
-- **你能操作的**：
  - 批量生成下单草稿（仅 Stop Buy / Stop Sell）
  - 二次确认后执行
  - 一键清仓（Kill Switch）+ 二次确认
- **当前阶段前端不做**：
  - 复杂图表与高级分析页
  - 盘前动作卡/收盘验尸报告的完整展示（先留入口概念）



## 2.3 后端（Backend / Robot Core）
- **机器人必须能做的**：
  - 监控账户/持仓/订单变化
  - 执行硬风控：自动卖出 / 降仓 / 停机（Kill）
  - 保证订单处理可靠：不“以为撤单成功”导致资金错判
  - ✅【新增】成交后保护链路（Post-Entry Protection）：
    - Stop Buy **成交后立刻**挂出保护单（Trailing Stop 优先）
    - 保护单挂单成功必须可验证（accepted/open），失败必须告警 + 进入降级策略
    - 下单前做“券商能力/时段”校验：不支持就别硬挂（避免 silent failure）

### 2.3.1 成交后保护链路（Post-Entry Protection: Trailing Stop）
- **目标**：把“入场”变成“入场 + 自动系安全带”
- **触发条件**：Stop Buy 订单状态变为 `filled`（含 partial fill 的处理规则）
- **动作**：
  1) 读取 fill 回报（qty、avg_fill_price、filled_at）
  2) 立刻提交 `trailing_stop` 卖出单（可选 `trail_percent` 或 `trail_price`）
  3) 校验订单已被券商接受（状态可查），并写入本地状态（SSOT）
- **关键约束（Alpaca）**：
  - Trailing stop 在触发后会“变成市价单”风格执行，可能产生滑点（风险提示要写进日志/告警）。:contentReference[oaicite:1]{index=1}
  - 夜盘 24/5（Blue Ocean ATS）官方只支持 `limit` + `day`，所以 trailing stop 这类单在夜盘不该指望能挂得上。:contentReference[oaicite:2]{index=2}
  - 扩展时段（pre/after）通常也以 limit/day 为主，机器人必须做“订单类型能力矩阵”。:contentReference[oaicite:3]{index=3}

### 2.3.2 Trailing Stop 参数策略（Trail Policy Engine）
- **目标**：trail 不是拍脑袋，是可配置、可回测、可替换的策略模块
- **MVP 做法（先别上复杂数学）**：
  - 每个 symbol 一个默认档位（例如：low/medium/high 波动三档）
  - 参数来源先用：最近 N 天日内K线（1m/5m）统计“正常抖动幅度”
  - 输出：`trail_percent`（优先）或 `trail_price`
- **迭代方向（以后再加）**：
  - 事件日（财报/CPI/FOMC）自动切更宽 trail
  - 结合点差/流动性动态加宽（避免被报价噪音扫掉）

### 2.3.3 订单可靠性（Order Lifecycle & Idempotency）
- **目标**：任何“取消/改单/挂保护单”都不能靠感觉
- **必须有**：
  - 订单状态机（submitted → accepted → open → filled / canceled / rejected）
  - 幂等键（client_order_id）+ 重试策略（防网络抖动导致重复下单）
  - “以券商回报为准”的最终确认（本地状态只是缓存，不许自嗨）

## 2.4 数据与单一事实源（SSOT: MVP）
- **MVP SSOT（本地即可）**：
  - SQLite/Postgres 保存：
    - orders（含 broker_order_id、client_order_id、状态、时间戳）
    - fills（成交明细）
    - positions（快照 + 变更日志）
    - protection_links（entry_order_id → trailing_stop_order_id 的关联）
- **缓存层（可选）**：
  - Redis 只当“加速器”，不当真账本（缓存今日快照、symbol→events 索引等）


## Further TODO(not being considered right now)
- 接入外部数据源（新闻/事件日历/期权链等）
- 风控
- Event Master" (事件主数据)
- 怎么构建“单一事实源” (SSOT)

