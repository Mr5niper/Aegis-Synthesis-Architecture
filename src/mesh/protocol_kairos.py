import asyncio
from typing import Callable, Optional
from nacl.signing import SigningKey, VerifyKey
from .session import SessionManager
from ..secure.contacts import ContactManager

class Kairos:
    def __init__(self, sessions: SessionManager, contacts: ContactManager):
        self.sessions, self.contacts = sessions, contacts

    async def invite(self, peer_id: str, redacted_context: str, scope: dict, ttl_sec: int = 600) -> str:
        if not self.contacts.get_verify_key(peer_id): raise PermissionError("Peer not trusted")
        return await self.sessions.initiate(peer_id, redacted_context, scope, ttl_sec)