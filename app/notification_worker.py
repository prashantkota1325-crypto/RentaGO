"""Durable notification outbox delivery with bounded retry behavior."""

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

from .config import settings
from .db import get_connection

log = logging.getLogger("rentago.notifications")
MAX_ATTEMPTS = 5


def _send_email(row):
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP credentials are not configured")
    message = MIMEText(row[7] or "", "plain", "utf-8")
    message["Subject"] = row[6] or "RentaGO Notification"
    message["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_USER))
    message["To"] = row[2]
    if settings.SMTP_SECURITY == "starttls":
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
    else:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)


def deliver_once():
    conn = get_connection(); cur = conn.cursor()
    delivered = 0
    try:
        cur.execute(
            "SELECT notification_id,channel,recipient_email,recipient_phone,attempts,created_dt,subject,body "
            "FROM notifications WHERE status IN ('Queued','Retry') AND NVL(attempts,0)<:1 "
            "AND (last_attempt IS NULL OR last_attempt <= SYSDATE-NUMTODSINTERVAL(POWER(2,NVL(attempts,0)),'MINUTE')) "
            "ORDER BY created_dt FETCH FIRST 50 ROWS ONLY", (MAX_ATTEMPTS,))
        rows = cur.fetchall()
        for row in rows:
            nid, channel, email, phone, attempts = row[0], (row[1] or "").lower(), row[2], row[3], int(row[4] or 0)
            try:
                if channel == "email":
                    if not email:
                        raise RuntimeError("Recipient email is empty")
                    _send_email(row)
                    status, error = "Sent", None
                elif channel == "whatsapp":
                    status, error = "Manual", "WhatsApp provider is not configured; use the stored wa.me link"
                else:
                    status, error = "Failed", f"Unsupported notification channel: {channel}"
            except Exception as exc:
                status, error = ("Failed" if attempts + 1 >= MAX_ATTEMPTS else "Retry", str(exc)[:1000])
            cur.execute(
                "UPDATE notifications SET status=:1, attempts=:2, last_attempt=SYSDATE, error_message=:3 WHERE notification_id=:4",
                (status, attempts + 1, error, nid),
            )
            if status == "Sent":
                delivered += 1
        conn.commit()
        return delivered
    finally:
        conn.close()


async def delivery_loop():
    log.info("Notification outbox worker started")
    while True:
        try:
            from .worker_status import touch_worker
            touch_worker("notifications")
            await asyncio.to_thread(deliver_once)
        except asyncio.CancelledError:
            log.info("Notification outbox worker stopped")
            raise
        except Exception:
            log.exception("Notification outbox delivery failed; retrying")
        from .worker_status import touch_worker
        touch_worker("notifications")
        await asyncio.sleep(60)
