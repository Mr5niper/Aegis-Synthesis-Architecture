import asyncio
from typing import Callable, Awaitable, Any, Dict, List

class EventBus:
    def __init__(self):
        self._subs: Dict[str, List[Callable[[Any], Awaitable[None]]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str, handler: Callable[[Any], Awaitable[None]]):
        async with self._lock: self._subs.setdefault(topic, []).append(handler)

    async def publish(self, topic: str, payload: Any):
        for h in list(self._subs.get(topic, [])): asyncio.create_task(h(payload))
