# src/ui/consent.py
import asyncio
from typing import Dict

class ConsentBroker:
    def __init__(self):
        self._pending: Dict[str, asyncio.Future] = {}

    def create(self, request_id: str) -> asyncio.Future:
        fut = asyncio.get_event_loop().create_future()
        self._pending[request_id] = fut
        return fut

    def resolve(self, request_id: str, decision: bool):
        fut = self._pending.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(decision)