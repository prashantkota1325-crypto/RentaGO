"""Fleet, driver, and vendor compliance expiry SLA publisher."""

import asyncio
import logging
from datetime import datetime, timedelta

from .db import get_connection
from .sla_engine import emit_start

log = logging.getLogger("rentago.compliance")
LOOKAHEAD_DAYS = 30


def publish_expiry_events():
    conn = get_connection(); cur = conn.cursor()
    cutoff = datetime.now() + timedelta(days=LOOKAHEAD_DAYS)
    def expiry_datetime(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            from .audit import _parse_oracle_dt
            return _parse_oracle_dt(value)
        return datetime.combine(value, datetime.min.time())
    created = 0
    try:
        cur.execute(
            "SELECT vehicle_id, insurance_exp, permit_exp, fitness_exp, puc_exp FROM vehicles "
            "WHERE status IS NULL OR UPPER(status)='ACTIVE'")
        for vehicle_id, insurance, permit, fitness, puc in cur.fetchall():
            for field, expiry in (("INSURANCE", insurance), ("PERMIT", permit), ("FITNESS", fitness), ("PUC", puc)):
                expiry_dt = expiry_datetime(expiry)
                if expiry_dt and expiry_dt <= cutoff:
                    priority = "P0" if expiry_dt <= datetime.now() else "P1"
                    if emit_start(conn, "VEHICLE_COMPLIANCE_EXPIRY", "VEHICLE",
                                  f"{vehicle_id}:{field}", department="Compliance",
                                  context={"document_type": field, "expiry_date": str(expiry),
                                           "incident_priority": priority, "policy_category": "Compliance"}):
                        created += 1
        cur.execute(
            "SELECT driver_id, license_expiry FROM drivers WHERE status IS NULL OR UPPER(status)='ACTIVE'")
        for driver_id, expiry in cur.fetchall():
            expiry_dt = expiry_datetime(expiry)
            if expiry_dt and expiry_dt <= cutoff:
                priority = "P0" if expiry_dt <= datetime.now() else "P1"
                if emit_start(conn, "DRIVER_LICENSE_EXPIRY", "DRIVER", str(driver_id), department="Compliance",
                              context={"expiry_date": str(expiry), "incident_priority": priority, "policy_category": "Compliance"}):
                    created += 1
        conn.commit()
        return created
    finally:
        conn.close()


async def compliance_loop():
    log.info("Compliance expiry worker started")
    while True:
        try:
            from .worker_status import touch_worker
            touch_worker("compliance")
            await asyncio.to_thread(publish_expiry_events)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Compliance expiry sweep failed; retrying later")
        from .worker_status import touch_worker
        touch_worker("compliance")
        for _ in range(60):
            from .worker_status import touch_worker
            touch_worker("compliance")
            await asyncio.sleep(60)
