# 半人马交易机器人（Centaur Trading Bot）

## 1) 项目目标总揽（Project North Star）
- **定位**：半自动交易系统（Centaur）
- **核心规则**：人类负责**买入决策**；机器人负责**风控 + 自动卖出 + 雷达信号**
- **市场范围**：美股（可扩展到与加密相关的美股，例如 COIN）
- **券商现状/未来**：
  - 当前：Alpaca（paper/live，live 默认关闭需手动开启）
  - 未来：多券商切换（IBKR/Tradier/…）+ 同券商多账号
- **下单风格**：只做 Stop Buy / Stop Sell（外加撤单/改单）
- **明确不做**：
  - 默认不做全自动买入（除非手动开启）
  - 不做高频/HFT

---

## 2) 当前目标（Current Focus: Local Desktop MVP）
目标：**能稳定跑起来 + 不自爆**（可靠 > 功能多）

### 2.1 前端（Frontend / GUI）要达成的效果
- **你能看到的**
  - 账户概览：净值 / 现金 / 购买力 / 当日盈亏
  - 持仓概览：仓位 / 权重 / 盈亏
  - 关注列表行情：last、bid/ask、点差、最后更新时间（实时跳）
  - 订单与成交：状态、成交价/时间、是否已挂保护单
  - 市场状态：盘前/盘中/盘后/休市 + halt 提示（如果能拿到）
- **你能操作的**
  - 生成下单草稿（仅 Stop Buy / Stop Sell）
  - 二次确认后执行
  - 一键清仓（Kill Switch）+ 二次确认
- **当前阶段不做**
  - 复杂图表与高级分析页
  - 盘前动作卡 / 收盘验尸报告（只留入口概念）

### 2.2 后端（Backend / Robot Core）要达成的效果
- **账户与订单事实跟踪**
  - 实时跟踪账户/持仓/订单变化（以券商回报为准）
  - 订单可靠：撤单/改单/挂保护单都要“确认成功”，不允许自嗨
- **成交后自动保护（核心）**
  - 任意 Stop Buy 一旦成交（包括你网页手动下的单），机器人自动挂 **Trailing Stop 卖出保护单**
  - 保护单挂单失败必须告警，并执行一个最小保命降级（先不复杂）
  - 默认规则：Trailing Stop Buy = DAY；Trailing Stop Loss = GTC；extended_hours=false
- **硬风控**
  - Kill Switch：一键清仓/停机
  - 基础风险限制：最大仓位、单笔最大风险（先能挡住大坑）
- **可复盘**
  - 关键动作留痕：发生了什么、系统做了什么、结果如何

### 2.3 Infra（本地运行与依赖）要达成的效果
- 本地桌面运行（个人使用）
- Alpaca only（paper/live，live 默认关闭）
- 允许断线重连、重启恢复状态（不能重启就失忆）
- UI 不直连券商：UI 只读 + 发命令；由后端统一对接券商与行情
- 有一个“热数据层”给 UI 秒开（不要求长期存）

---

## 3) Further TODO（暂时不考虑，但要记账）
> 这里放“实现细节/系统设计/高级能力”，当前阶段不展开

- Trade Loop 详细状态机（filled/partial filled 的完整规则）
- 订单状态机 + 幂等键 + 重试策略的工程化细节
- 成交后保护的完整降级策略（trailing 不可用时：stop/stop-limit/flatten 等）
- Trailing Stop 参数策略（从固定 2% → 波动率自适应/按 symbol 分档）
- SSOT 详细表结构（orders/fills/positions/protection_links/trailing_state…）
- Redis key 设计、PubSub/Streams、缓存策略与 TTL
- 市场日历/事件系统（Market Calendar / Event Master / 审计版本）
- 外部数据源融合（新闻/事件日历/期权链/公司行为）
- 多券商、多账号
- 回测框架/策略研究流水线
- 报表：盘前动作卡 / 收盘验尸报告

---

## 4) Constraints（限制与已知坑，统一放最后）
- 免费 IEX 行情：订阅 symbols 数量有限（例如 <=30）
- 行情 WebSocket 连接数受限（通常 1 条），需要单连接复用
- 不同交易时段（盘前/盘后/夜盘）对订单类型有约束：某些单可能挂不上/不触发
- Trailing Stop 触发后成交方式可能带滑点（风险提示必须展示）
- Redis 只做热数据/公告栏，不当真账本；关键事实必须能复盘
