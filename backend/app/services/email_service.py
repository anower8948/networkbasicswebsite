"""Outbound email.

Two backends behind one interface:

* ``console`` — logs the rendered message, including any action link. This is
  the development default so the verification and reset flows are fully
  clickable without an SMTP server anywhere in the loop.
* ``smtp`` — real delivery.

SMTP sending is blocking, so it runs in a worker thread via ``asyncio.to_thread``
rather than stalling the event loop for the duration of a network round trip.

Delivery failures are logged and swallowed, never raised to the caller. A
registration must not fail because a mail server was briefly unavailable — the
account exists and the user can request another verification message.
"""

from __future__ import annotations

import asyncio
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Email:
    """A rendered message ready to send."""

    to: str
    subject: str
    text_body: str
    html_body: str | None = None


class EmailBackend(ABC):
    @abstractmethod
    async def send(self, message: Email) -> None: ...


class ConsoleEmailBackend(EmailBackend):
    """Writes the message to the application log."""

    async def send(self, message: Email) -> None:
        logger.info(
            "EMAIL (console backend)\n  To:      %s\n  Subject: %s\n%s",
            message.to,
            message.subject,
            message.text_body,
            extra={"email_to": message.to, "email_subject": message.subject},
        )


class SMTPEmailBackend(EmailBackend):
    """Delivers over SMTP."""

    async def send(self, message: Email) -> None:
        await asyncio.to_thread(self._send_blocking, message)

    def _send_blocking(self, message: Email) -> None:
        mail = EmailMessage()
        mail["From"] = settings.EMAIL_FROM
        mail["To"] = message.to
        mail["Subject"] = message.subject
        mail.set_content(message.text_body)
        if message.html_body:
            mail.add_alternative(message.html_body, subtype="html")

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as client:
            if settings.SMTP_USE_TLS:
                client.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            client.send_message(mail)


def _build_backend() -> EmailBackend:
    return SMTPEmailBackend() if settings.EMAIL_BACKEND == "smtp" else ConsoleEmailBackend()


class EmailService:
    """Renders and dispatches the platform's transactional email."""

    def __init__(self, backend: EmailBackend | None = None) -> None:
        self.backend = backend or _build_backend()

    async def _dispatch(self, message: Email) -> None:
        try:
            await self.backend.send(message)
        except Exception as exc:  # noqa: BLE001 — delivery must never break a request
            logger.error(
                "Failed to send email",
                extra={"email_to": message.to, "subject": message.subject, "error": str(exc)},
            )

    async def send_email_verification(self, *, to: str, name: str, token: str) -> None:
        link = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={token}"
        await self._dispatch(
            Email(
                to=to,
                subject="Confirm your email address",
                text_body=(
                    f"Hi {name},\n\n"
                    "Welcome to the Network Learning Platform. Confirm your email "
                    "address to unlock your certificates and progress tracking:\n\n"
                    f"{link}\n\n"
                    f"This link expires in {settings.EMAIL_VERIFICATION_TTL_HOURS} hours.\n\n"
                    "If you did not create this account, you can ignore this message."
                ),
                html_body=_wrap_html(
                    heading="Confirm your email address",
                    body=(
                        f"<p>Hi {_escape(name)},</p>"
                        "<p>Welcome to the Network Learning Platform. Confirm your email "
                        "address to unlock your certificates and progress tracking.</p>"
                    ),
                    action_label="Confirm email address",
                    action_url=link,
                    footer=(
                        f"This link expires in {settings.EMAIL_VERIFICATION_TTL_HOURS} hours. "
                        "If you did not create this account, you can ignore this message."
                    ),
                ),
            )
        )

    async def send_password_reset(self, *, to: str, name: str, token: str) -> None:
        link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
        await self._dispatch(
            Email(
                to=to,
                subject="Reset your password",
                text_body=(
                    f"Hi {name},\n\n"
                    "We received a request to reset your password. Use this link to "
                    "choose a new one:\n\n"
                    f"{link}\n\n"
                    f"This link expires in {settings.PASSWORD_RESET_TTL_MINUTES} minutes "
                    "and can be used once.\n\n"
                    "If you did not request this, no action is needed — your password "
                    "has not changed."
                ),
                html_body=_wrap_html(
                    heading="Reset your password",
                    body=(
                        f"<p>Hi {_escape(name)},</p>"
                        "<p>We received a request to reset your password. "
                        "Choose a new one using the button below.</p>"
                    ),
                    action_label="Reset password",
                    action_url=link,
                    footer=(
                        f"This link expires in {settings.PASSWORD_RESET_TTL_MINUTES} minutes "
                        "and can be used once. If you did not request this, no action is "
                        "needed — your password has not changed."
                    ),
                ),
            )
        )

    async def send_password_changed_notice(self, *, to: str, name: str) -> None:
        """Told after the fact, so a victim of account takeover learns of it."""
        await self._dispatch(
            Email(
                to=to,
                subject="Your password was changed",
                text_body=(
                    f"Hi {name},\n\n"
                    "Your Network Learning Platform password was just changed, and all "
                    "other sessions were signed out.\n\n"
                    "If this was not you, reset your password immediately at "
                    f"{settings.FRONTEND_URL.rstrip('/')}/forgot-password"
                ),
            )
        )


def _escape(value: str) -> str:
    """Minimal HTML escaping for interpolated user-controlled names."""
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _wrap_html(*, heading: str, body: str, action_label: str, action_url: str, footer: str) -> str:
    """Table-based layout, because email clients do not support modern CSS."""
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:32px 16px;background:#f4f6fb;
               font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1c1f26;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="max-width:520px;background:#ffffff;border-radius:16px;padding:36px;">
          <tr><td>
            <h1 style="margin:0 0 18px;font-size:21px;font-weight:600;">{heading}</h1>
            <div style="font-size:15px;line-height:1.6;color:#3c4250;">{body}</div>
            <p style="margin:28px 0;">
              <a href="{action_url}"
                 style="display:inline-block;background:#2f7bf6;color:#ffffff;
                        text-decoration:none;padding:13px 26px;border-radius:10px;
                        font-size:15px;font-weight:500;">{action_label}</a>
            </p>
            <p style="margin:0;font-size:13px;line-height:1.6;color:#7a8196;">{footer}</p>
            <p style="margin:18px 0 0;font-size:12px;color:#9aa1b4;word-break:break-all;">
              If the button does not work, paste this into your browser:<br />{action_url}
            </p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
