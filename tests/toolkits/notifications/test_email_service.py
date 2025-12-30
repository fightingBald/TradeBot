from __future__ import annotations

import smtplib
from typing import ClassVar

import pytest
from pydantic import SecretStr

from toolkits.notifications.email_service import (
    EmailAttachment,
    EmailDeliveryError,
    EmailMessageOptions,
    EmailNotificationService,
    EmailRecipients,
    EmailSettings,
)


def test_service_rejects_conflicting_tls_ssl() -> None:
    settings = EmailSettings(
        host="smtp.example.com",
        sender="noreply@example.com",
        use_tls=True,
        use_ssl=True,
    )
    with pytest.raises(ValueError, match="use_ssl"):
        EmailNotificationService(settings)


def test_recipients_flattened() -> None:
    recipients = EmailRecipients(to=["a@example.com"], cc=["b@example.com"], bcc=["c@example.com"])
    assert recipients.flattened() == ["a@example.com", "b@example.com", "c@example.com"]


def test_send_email_uses_tls_and_attachments(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummySMTP:
        instances: ClassVar[list[DummySMTP]] = []

        def __init__(self, host: str, port: int, timeout: float | None = None, **_kwargs) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout
            self.starttls_called = False
            self.login_args: tuple[str, str] | None = None
            self.sent: tuple[object, list[str]] | None = None
            DummySMTP.instances.append(self)

        def __enter__(self) -> DummySMTP:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def set_debuglevel(self, _level: int) -> None:
            return None

        def starttls(self, *_args: object, **_kwargs: object) -> None:
            self.starttls_called = True

        def login(self, username: str, password: str) -> None:
            self.login_args = (username, password)

        def send_message(self, message: object, to_addrs: list[str]) -> None:
            self.sent = (message, to_addrs)

    monkeypatch.setattr(smtplib, "SMTP", DummySMTP)

    settings = EmailSettings(
        host="smtp.example.com",
        sender="noreply@example.com",
        username="user",
        password=SecretStr("pass"),
        use_tls=True,
        use_ssl=False,
    )
    service = EmailNotificationService(settings)
    recipients = EmailRecipients(to=["a@example.com"], cc=["b@example.com"])
    options = EmailMessageOptions(attachments=[EmailAttachment(filename="report.csv", content=b"data")])

    message_id = service.send_email(subject="Report", body="Daily report", recipients=recipients, options=options)

    smtp = DummySMTP.instances[0]
    assert smtp.starttls_called is True
    assert smtp.login_args == ("user", "pass")
    assert smtp.sent is not None
    message = smtp.sent[0]
    assert message["Message-ID"] == message_id
    assert any(part.get_filename() == "report.csv" for part in message.iter_attachments())


def test_send_email_uses_ssl(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummySMTPSSL:
        instances: ClassVar[list[DummySMTPSSL]] = []

        def __init__(self, host: str, port: int, timeout: float | None = None, **_kwargs) -> None:
            self.starttls_called = False
            self.sent: tuple[object, list[str]] | None = None
            DummySMTPSSL.instances.append(self)

        def __enter__(self) -> DummySMTPSSL:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def set_debuglevel(self, _level: int) -> None:
            return None

        def starttls(self, *_args: object, **_kwargs: object) -> None:
            self.starttls_called = True

        def login(self, *_args: object, **_kwargs: object) -> None:
            return None

        def send_message(self, message: object, to_addrs: list[str]) -> None:
            self.sent = (message, to_addrs)

    monkeypatch.setattr(smtplib, "SMTP_SSL", DummySMTPSSL)

    settings = EmailSettings(
        host="smtp.example.com",
        sender="noreply@example.com",
        use_tls=False,
        use_ssl=True,
    )
    service = EmailNotificationService(settings)
    recipients = EmailRecipients(to=["a@example.com"])

    service.send_email(subject="SSL", body="secure", recipients=recipients)

    smtp = DummySMTPSSL.instances[0]
    assert smtp.starttls_called is False
    assert smtp.sent is not None


def test_send_email_raises_after_retries() -> None:
    settings = EmailSettings(
        host="smtp.example.com",
        sender="noreply@example.com",
        use_tls=False,
        use_ssl=False,
        max_retries=2,
    )
    service = EmailNotificationService(settings)
    recipients = EmailRecipients(to=["a@example.com"])

    def fail_send(*_args: object, **_kwargs: object) -> None:
        raise smtplib.SMTPException("boom")

    service._send_via_smtp = fail_send  # type: ignore[method-assign]

    with pytest.raises(EmailDeliveryError):
        service.send_email(subject="Fail", body="oops", recipients=recipients)
