"""Durable in-process SLA/TAT evaluation loop.

The request-triggered sweep remains as a fallback, while this worker keeps
timers and escalations advancing when no operator has the dashboard open.
"""

import asyncio
import logging

from .db import get_connection
from .sla import run_sweep

log = logging.getLogger("rentago.sla")
SWEEP_SECONDS = 60


def run_sla_sweep_once():
    conn = get_connection()
    try:
        return run_sweep(conn, force=True)
    finally:
        conn.close()


async def sweep_loop():
    log.info("SLA/TAT evaluation worker started (%ss interval)", SWEEP_SECONDS)
    while True:
        try:
            from .worker_status import touch_worker
            touch_worker("sla")
            await asyncio.to_thread(run_sla_sweep_once)
        except asyncio.CancelledError:
            log.info("SLA/TAT evaluation worker stopped")
            raise
        except Exception:
            log.exception("SLA/TAT sweep failed; retrying on the next interval")
        from .worker_status import touch_worker
        touch_worker("sla")
        await asyncio.sleep(SWEEP_SECONDS)
