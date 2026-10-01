"""Process-local GPS display publisher for LAB single-process realtime use."""

import asyncio
from collections import defaultdict


_subscribers = defaultdict(set)


def subscribe(key):
    queue = asyncio.Queue()
    _subscribers[key].add(queue)
    return queue


def unsubscribe(key, queue):
    _subscribers[key].discard(queue)
    if not _subscribers[key]:
        _subscribers.pop(key, None)


def publish(key, event):
    for queue in tuple(_subscribers.get(key, ())):
        queue.put_nowait(event)
