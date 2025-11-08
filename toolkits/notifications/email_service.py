"""Configurable email notification service."""

from __future__ import annotations

import logging
import smtplib
import ssl
from collections.abc import Iterable, Mapping, MutableSequence, Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid

from pydantic import EmailStr, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class EmailSettings(BaseSettings):
    """Settings for the email notification service.

    Environment variables are automatically loaded using the ``EMAIL_`` prefix::

        EMAIL_HOST = smtp.gmail.com
        EMAIL_PORT = 587
        EMAIL_USERNAME = alice @ example.com
        EMAIL_PASSWORD = super - secret
        EMAIL_SENDER = "Alice <alice@example.com>"
        EMAIL_USE_TLS = true

    """

    model_config = SettingsConfigDict(env_prefix="EMAIL_", env_file=".env", extra="ignore")

    host: str = Field(..., description="SMTP host name or IP.")
    port: int = Field(default=587, ge=1, le=65535, description="SMTP port.")
    username: str | None = Field(default=None, description="SMTP username (optional).")
    password: SecretStr | None = Field(default=None, description="SMTP password (optional).")
    sender: EmailStr = Field(..., description="Default From address.")
    reply_to: EmailStr | None = Field(default=None, description="Optional Reply-To address.")
    use_tls: bool = Field(default=True, description="Upgrade connection to TLS via STARTTLS.")
    use_ssl: bool = Field(default=False, description="Use implicit SSL (mutually exclusive with use_tls).")
    timeout: float = Field(default=20.0, gt=0, description="SMTP socket timeout (seconds).")
    max_retries: int = Field(default=1, ge=1, le=5, description="Number of retries on transient errors.")

    def require_credentials(self) -> tuple[str, str] | None:
        if self.username and self.password:
            return self.username, self.password.get_secret_value()
        return None


@dataclass(slots=True)
class EmailAttachment:
    """Represents a file attachment."""

    filename: str
    content: bytes
    mimetype: str = "application/octet-stream"


@dataclass(slots=True)
class EmailRecipients:
    """Grouped To/Cc/Bcc recipients."""

    to: Sequence[EmailStr]
    cc: Sequence[EmailStr] | None = None
    bcc: Sequence[EmailStr] | None = None

    def flattened(self) -> list[str]:
        """Return all recipients as plain email strings."""
        combined: list[str] = [str(addr) for addr in self.to]
        if self.cc:
            combined.extend(str(addr) for addr in self.cc)
        if self.bcc:
            combined.extend(str(addr) for addr in self.bcc)
        return combined


@dataclass(slots=True)
class EmailMessageOptions:
    """Optional overrides for the email payload."""

    subtype: str = "plain"
    attachments: Sequence[EmailAttachment] | None = None
    headers: Mapping[str, str] | None = None
    reply_to: EmailStr | None = None


class EmailDeliveryError(RuntimeError):
    """Raised when the email service fails to deliver a message."""


class EmailNotificationService:
    """SMTP backed email delivery."""

    def __init__(self, settings: EmailSettings) -> None:
        self._settings = settings
        if self._settings.use_ssl and self._settings.use_tls:
            raise ValueError("use_ssl 与 use_tls 互斥，请只开启其中一个。")

    @property
    def settings(self) -> EmailSettings:
        return self._settings

    def send_email(
        self, *, subject: str, body: str, recipients: EmailRecipients, options: EmailMessageOptions | None = None
    ) -> str:
        """Send an email message.

        Args:
            subject: Email subject line.
            body: Email body content.
            recipients: Grouped To/Cc/Bcc recipients.
            options: Optional message overrides (subtype, attachments, headers, reply-to).

        Returns:
            The RFC822 Message-ID generated for the message.
        """

        if not recipients.to:
            raise ValueError("recipients 不能为空。")
        opts = options or EmailMessageOptions()

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = str(self._settings.sender)
        message["To"] = ", ".join(str(addr) for addr in recipients.to)
        if recipients.cc:
            message["Cc"] = ", ".join(str(addr) for addr in recipients.cc)
        resolved_reply_to = opts.reply_to or self._settings.reply_to
        if resolved_reply_to:
            message["Reply-To"] = str(resolved_reply_to)
        if opts.headers:
            for key, value in opts.headers.items():
                message[key] = value

        message.set_content(body, subtype=opts.subtype)
        message_id = make_msgid(domain=self._settings.host)
        message["Message-ID"] = message_id

        if opts.attachments:
            for attachment in opts.attachments:
                maintype, _, subtype_part = attachment.mimetype.partition("/")
                if not maintype or not subtype_part:
                    maintype, subtype_part = ("application", "octet-stream")
                message.add_attachment(
                    attachment.content, maintype=maintype, subtype=subtype_part, filename=attachment.filename
                )

        all_recipients: MutableSequence[str] = recipients.flattened()

        self._deliver(message, all_recipients)
        return message_id

    def _deliver(self, message: EmailMessage, recipients: Iterable[str]) -> None:
        attempt = 0
        last_error: Exception | None = None
        while attempt < self._settings.max_retries:
            attempt += 1
            try:
                self._send_via_smtp(message, recipients)
                logger.info("邮件发送成功：message_id=%s recipients=%s", message["Message-ID"], recipients)
                return
            except (smtplib.SMTPException, OSError) as exc:
                last_error = exc
                logger.warning("发送邮件失败（第 %d/%d 次尝试）：%s", attempt, self._settings.max_retries, exc)
        raise EmailDeliveryError("无法发送邮件") from last_error

    def _send_via_smtp(self, message: EmailMessage, recipients: Iterable[str]) -> None:
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if self._settings.use_ssl:
            smtp = smtplib.SMTP_SSL(
                self._settings.host, self._settings.port, timeout=self._settings.timeout, context=context
            )
        else:
            smtp = smtplib.SMTP(self._settings.host, self._settings.port, timeout=self._settings.timeout)

        with smtp:
            smtp.set_debuglevel(0)
            if not self._settings.use_ssl and self._settings.use_tls:
                smtp.starttls(context=context)
            credentials = self._settings.require_credentials()
            if credentials:
                smtp.login(*credentials)
            smtp.send_message(message, to_addrs=list(recipients))


__all__ = [
    "EmailAttachment",
    "EmailDeliveryError",
    "EmailNotificationService",
    "EmailSettings",
    "EmailRecipients",
    "EmailMessageOptions",
]
