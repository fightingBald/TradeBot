"""Send a one-off HTML test email via the notification service."""

from __future__ import annotations

from toolkits.notifications import (
    EmailNotificationService,
    EmailSettings,
    load_recipient_config,
)


def main() -> None:
    settings = EmailSettings()

    service = EmailNotificationService(settings)

    html_body = """
    <html>
      <body>
        <h1>测试邮件</h1>
        <p>您好，这是来自 <strong>huayiTradeBot</strong> 的 HTML 测试邮件。</p>
        <p>祝交易顺利！</p>
      </body>
    </html>
    """

    recipient_config = load_recipient_config()
    if not recipient_config.to:
        raise ValueError("收件人列表为空，请编辑 config/notification_recipients.toml")

    message_id = service.send_email(
        subject="[测试] huayiTradeBot HTML 邮件",
        body=html_body,
        subtype="html",
        recipients=recipient_config.to,
        cc=recipient_config.cc or None,
        bcc=recipient_config.bcc or None,
    )

    print(f"邮件已发送，Message-ID: {message_id}")


if __name__ == "__main__":
    main()
