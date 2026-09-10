"""Minimal SMTP delivery for security-critical email OTP messages."""

import smtplib
import ssl
from email.utils import formataddr
from email.message import EmailMessage

from .config import settings


def send_email(to_address: str, subject: str, body: str) -> None:
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP credentials are not configured")
    message = EmailMessage()
    message["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_USER))
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body + "\n\nRentaGO Technologies Pvt. Ltd.")
    context = ssl.create_default_context()
    if settings.SMTP_SECURITY == "ssl":
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT,
                              context=context, timeout=20) as smtp:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
