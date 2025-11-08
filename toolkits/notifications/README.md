# Notification Service（大白话版）

这个小包就干一件事：**帮你把邮件发出去**，而且配置写在环境变量里，随时可以切换 SMTP 服务器（Gmail、企业邮箱都行）。

## 1. 快速上手

1. 在环境变量或 `.env` 文件里配置 SMTP 信息（前缀都是 `EMAIL_`）：

   ```dotenv
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USERNAME=myuser@gmail.com
   EMAIL_PASSWORD=超级秘密
   EMAIL_SENDER="交易机器人 <myuser@gmail.com>"
   EMAIL_USE_TLS=true          # 587 端口一般是 TLS
   EMAIL_USE_SSL=false         # 465 端口才需要改成 true
   ```

2. 代码里这样用：

   ```python
from toolkits.notifications import (
    EmailNotificationService,
    EmailRecipients,
    EmailSettings,
    load_recipient_config,
)

settings = EmailSettings()          # 自动读取 EMAIL_* 配置
mailer = EmailNotificationService(settings)
recipient_cfg = load_recipient_config()

mailer.send_email(
    subject="策略告警",
    body="今天的策略触发啦，快来看看。",
    recipients=EmailRecipients(to=recipient_cfg.to),
)
   ```

   如果想发 HTML、CC/BCC 或带附件，也可以：

   ```python
from toolkits.notifications import EmailAttachment, EmailMessageOptions, EmailRecipients

mailer.send_email(
    subject="每日盈亏汇总",
    body="<h1>Summary</h1><p>今日+3.2%</p>",
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

## 2. 配置说明

| 环境变量           | 作用                             | 默认值           |
| ------------------ | -------------------------------- | ---------------- |
| `EMAIL_HOST`       | SMTP 服务器主机名                | (必填)           |
| `EMAIL_PORT`       | SMTP 端口                        | 587              |
| `EMAIL_USERNAME`   | 登录用户名（如果需要认证）       | 可选             |
| `EMAIL_PASSWORD`   | 登录密码（推荐使用“应用专用密码”） | 可选             |
| `EMAIL_SENDER`     | 默认的 “From” 邮件地址           | (必填)           |
| `EMAIL_REPLY_TO`   | 默认回复地址（可覆盖）           | 可选             |
| `EMAIL_USE_TLS`    | 是否用 STARTTLS（587 常用）      | true             |
| `EMAIL_USE_SSL`    | 是否用 SSL 直连（465 常用）      | false            |
| `EMAIL_TIMEOUT`    | 连接超时时间（秒）               | 20               |
| `EMAIL_MAX_RETRIES`| 发送失败自动重试次数             | 1                |

`use_tls` 和 `use_ssl` 只能开一个，否则会直接报错提示你。

## 3. 错误处理

发邮件失败会抛 `EmailDeliveryError`，日志里也会记录每次尝试的失败原因。可以在业务层捕获它做降级，比如：先写入数据库、稍后重试。

```python
from toolkits.notifications import EmailDeliveryError

try:
    mailer.send_email(...
    略)
    except EmailDeliveryError as exc:
    # 写告警、落库、回退等
    print("邮件没发出去：", exc)
```

## 4. 适用场景

- 策略触发后发一封通知邮件；
- 夜间批处理完成后推送日报；
- 风控系统发现异常，第一时间 ping 运维/交易员。

代码本身只依赖标准库 + pydantic，不会额外拖一堆包。后续如果要接企业微信、Slack，只要仿照这个服务再加一个模块即可。***

### 附：集中管理收件人

我们把群发名单放在 `config/notification_recipients.toml`。格式长这样：

```toml
to = [
  "alice@example.com",
  # "bob@example.com",  # 暂时停用就注释掉
]

cc = [
  # "ops@example.com",
]

bcc = [
  # "boss@example.com",
]
```

写好之后，用 `load_recipient_config()` 读出来就能把 To/Cc/Bcc 自动带上。***

## 5. 常见坑：Gmail 的 534 5.7.9 报错怎么办？

如果日志里出现：

```
534 5.7.9 Application-specific password required (Failure)
```

说明你的 Gmail 开了两步验证（或开启了更高的安全策略），但是你还在用“正常登录密码”去跑 SMTP。由于 SMTP 不会弹出二次验证，所以 Google 会直接拒绝。

解决办法：

1. **开启两步验证（2FA）**  
   在谷歌账户的“安全性”页面，打开两步验证（OTP、短信、硬件钥匙都行）。

2. **生成应用专用密码**  
   仍在“安全性”页面，找到“应用专用密码”。新建一个（名字随便写，比如 `SMTP`），Google 会给你一串 16 位的密码。  
   记住，这串密码才是 SMTP 的 `EMAIL_PASSWORD`，不是你平时登录用的那串！

3. **更新 `.env` 或环境变量**  
   ```dotenv
   EMAIL_USERNAME=example@gmail.com
   EMAIL_PASSWORD=这里填刚刚生成的16位应用专用密码
   ```

搞完这两步，再跑发送脚本，就不会再遇到 534 5.7.9 的报错了。***
