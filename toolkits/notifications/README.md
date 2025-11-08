# 邮件通知模块（`toolkits/notifications`）

## 核心作用
把“发邮件”这件事封成一个小服务：配置从环境变量读取，支持文本/HTML/附件、收件人分组。无论是策略告警还是日报播报都能直接用。

## 配置一次到位
在 `.env` 或系统环境里写：
```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USERNAME=myuser@gmail.com
EMAIL_PASSWORD=应用专用密码
EMAIL_SENDER="交易机器人 <myuser@gmail.com>"
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
EMAIL_TIMEOUT=20
EMAIL_MAX_RETRIES=1
```
TLS 与 SSL 只能二选一，两个都开会直接报错。

收件人集中放在 `config/notification_recipients.toml`：
```toml
to = ["alice@example.com"]
cc = []
bcc = []
```
注释即可暂时停用。

## 最简单的发送示例
```python
from toolkits.notifications import (
    EmailNotificationService,
    EmailRecipients,
    EmailSettings,
    load_recipient_config,
)

settings = EmailSettings()              # 自动读 EMAIL_* 变量
mailer = EmailNotificationService(settings)
recipients = load_recipient_config()

mailer.send_email(
    subject="策略触发提醒",
    body="今天的条件满足了，记得查看。",
    recipients=EmailRecipients(to=recipients.to),
)
```

## 带 HTML / 附件
```python
from toolkits.notifications import EmailAttachment, EmailMessageOptions, EmailRecipients

mailer.send_email(
    subject="每日盈亏",
    body="<h1>Summary</h1><p>今日 +3.2%</p>",
    recipients=EmailRecipients(
        to=["boss@example.com"],
        cc=["team@example.com"],
    ),
    options=EmailMessageOptions(
        subtype="html",
        attachments=[
            EmailAttachment(
                filename="report.csv",
                content=b"symbol,pnl\nAAPL,2300\n",
                mimetype="text/csv",
            )
        ],
    ),
)
```

## 错误处理
发送失败会抛 `EmailDeliveryError`，异常里带有每次尝试的原因，日志也会记录：  
```python
from toolkits.notifications import EmailDeliveryError

try:
    mailer.send_email(...)
except EmailDeliveryError as exc:
    print("邮件没发出去：", exc)
    # 这里可以写入告警、落库、延迟重试等
```

## Gmail 534 提示怎么破？
看到 `534 5.7.9 Application-specific password required` 时，说明需要：
1. 在 Google 账号里开启两步验证。
2. 生成“应用专用密码”，把得到的 16 位字符串填到 `EMAIL_PASSWORD`。
普通登录密码不能直接拿来跑 SMTP。

## 适用场景
- 策略/风控即时提醒。
- 批处理日报。
- 与 `py_scripts/ark_holdings/daily_pipeline.py` 组合，群发差分报告。

模块只依赖标准库 + pydantic，不额外引入重量级依赖，要扩展别的通知渠道（企业微信/Slack）时照葫芦画瓢就行。
