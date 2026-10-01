"""Minimal SMTP delivery for security-critical email OTP messages."""

import smtplib
import ssl
import html
import os
from pathlib import Path
from email.utils import formataddr
from email.message import EmailMessage

from .config import settings

BRAND_SIGNATURE = (
    "RentaGO Technologies Pvt. Ltd.\n"
    "24 / 7 Customer Care No. 9923402200\n"
    "Email: info@rentago.co.in"
)
BRAND_LOGO_URL = os.environ.get(
    "RENTAGO_BRAND_LOGO_URL",
    "https://app.rentago.co.in/static/img/icon-512.png",
).strip()
BRAND_LOGO_FILE = Path(__file__).resolve().parent / "static" / "img" / "icon-512.png"


def build_email_message(to_address: str, subject: str, body: str,
                        append_signature: bool = True) -> EmailMessage:
    text_body = body.rstrip()
    if append_signature:
        text_body += f"\n\n{BRAND_SIGNATURE}"
    message = EmailMessage()
    message["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_USER))
    message["To"] = to_address
    message["Subject"] = subject
    if f"Logo: {BRAND_LOGO_URL}" not in text_body:
        text_body += f"\n\nLogo: {BRAND_LOGO_URL}"
    message.set_content(text_body)
    html_body = html.escape(text_body).replace("\n", "<br>")
    html_body += (
        '<br><br><div style="text-align:left">'
        '<img src="cid:rentago-logo" '
        'alt="RentaGO Technologies Pvt. Ltd." style="max-width:280px;height:auto">'
        "</div>"
    )
    message.add_alternative(html_body, subtype="html")
    if BRAND_LOGO_FILE.is_file():
        html_part = message.get_payload()[-1]
        html_part.add_related(
            BRAND_LOGO_FILE.read_bytes(), maintype="image", subtype="png",
            cid="<rentago-logo>", filename="rentago-logo.png",
        )
    return message


def send_email(to_address: str, subject: str, body: str) -> None:
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP credentials are not configured")
    message = build_email_message(to_address, subject, body)
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
