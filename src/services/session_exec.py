from typing import Callable, Awaitable, Optional
from ..mesh.session import SessionManager
from ..tools.registry_async import AsyncToolRegistry
from ..memory.vector_store import LiteVectorStore
from ..core.config import AppConfig

class SessionExec:
    def __init__(self, sessions: SessionManager):
        self.sessions = sessions
        self.kb: Optional[LiteVectorStore] = None
        self.cfg: Optional[AppConfig] = None
        self.sessions.on_session_message = self._handle
    
    def register_kb(self, kb: LiteVectorStore): self.kb = kb
    def register_config(self, cfg: AppConfig): self.cfg = cfg

    async def _handle(self, session_id: str, msg: dict):
        if msg.get("type") != "task": return
        tool, args = msg.get("tool",""), msg.get("args",{})
        # Defensively restrict allowed tools from peers
        if tool not in ("kb_query","fetch_url","search_web"):
            return await self.sessions.send_session(session_id, {"type":"result","error":"tool not allowed"})
        # Create a temporary, restricted tool registry for this execution
        if self.kb and self.cfg:
            reg = AsyncToolRegistry(self.kb, self.cfg, peer_client=None)
            res = await reg.call(tool, args)
            await self.sessions.send_session(session_id, {"type":"result","result": res})