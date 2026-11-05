"""Outgoing email. Messages carry single-use links only; no other secrets are ever emailed."""

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from typing import Protocol

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    """Development only (refused when APP_ENV=production): prints the message to the API log."""

    async def send(self, message: EmailMessage) -> None:
        logger.warning(
            "DEVELOPMENT EMAIL (EMAIL_BACKEND=console)\nTo: %s\nSubject: %s\n\n%s",
            message.to,
            message.subject,
            message.text,
        )


class DisabledEmailSender:
    async def send(self, message: EmailMessage) -> None:
        logger.info("Email delivery is disabled; message %r not sent", message.subject)


class SmtpEmailSender:
    def __init__(self, config: Settings) -> None:
        self._config = config

    def _send_sync(self, message: EmailMessage) -> None:
        config = self._config
        mime = MimeMessage()
        mime["From"] = config.email_from
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        with smtplib.SMTP(
            config.smtp_host, config.smtp_port, timeout=config.smtp_timeout_seconds
        ) as client:
            if config.smtp_starttls:
                client.starttls(context=ssl.create_default_context())
            if config.smtp_username:
                client.login(config.smtp_username, config.smtp_password.get_secret_value())
            client.send_message(mime)

    async def send(self, message: EmailMessage) -> None:
        try:
            await asyncio.to_thread(self._send_sync, message)
        except (OSError, smtplib.SMTPException):
            # Never log the body: it contains a single-use link.
            logger.exception("Could not send email %r", message.subject)


def create_email_sender(config: Settings = settings) -> EmailSender:
    if config.email_backend == "smtp":
        return SmtpEmailSender(config)
    if config.email_backend == "console":
        return ConsoleEmailSender()
    return DisabledEmailSender()


def get_email_sender() -> EmailSender:
    return create_email_sender()
