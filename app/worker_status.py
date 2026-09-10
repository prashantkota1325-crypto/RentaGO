"""In-process worker heartbeat registry for Year-1 operations monitoring."""

import threading
import time

_lock = threading.Lock()
_heartbeats = {}


def touch_worker(name):
    with _lock:
        _heartbeats[name] = time.time()


def snapshot(max_age=180):
    now = time.time()
    with _lock:
        return {name: {"status": "ok" if now - stamp <= max_age else "stale",
                       "age_seconds": round(now - stamp, 1)}
                for name, stamp in _heartbeats.items()}
