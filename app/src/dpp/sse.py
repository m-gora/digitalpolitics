"""Generic in-process SSE pub-sub mechanism. See arch-03.

Single-process pub/sub via asyncio queues. This is a prototype-scale
implementation: it does not work across multiple worker processes and does
not replay missed events on reconnect (clients refetch current state
instead, per arch-03).

This module only provides the reusable transport (Channel/Event). Each
domain module owns its own Channel instance and event names — arch-03:
"SSE channels are scoped by modules". See dpp.campaign.events for the
canvas module's channel.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class Event:
    event: str
    data: dict

    def to_sse(self) -> dict:
        return {"event": self.event, "data": json.dumps(self.data)}


class Channel:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: str, data: dict) -> None:
        message = Event(event=event, data=data)
        for queue in list(self._subscribers):
            await queue.put(message)

    async def stream(self) -> AsyncIterator[dict]:
        queue = self.subscribe()
        try:
            while True:
                message = await queue.get()
                yield message.to_sse()
        finally:
            self.unsubscribe(queue)
