import asyncio, json
from typing import Dict, Any
from ..mesh.session import SessionManager
from ..memory.vector_store import LiteVectorStore

class SessionTools:
    def __init__(self, sessions: SessionManager, kb: LiteVectorStore):
        self.sessions, self.kb = sessions, kb

    async def delegate_in_session(self, args: Dict[str, Any]) -> str:
        sid, tool, t_args = args.get("session_id", ""), args.get("tool", ""), args.get("args", {})
        if not (sid and tool): return "ArgError: session_id and tool required."
        await self.sessions.send_session(sid, {"type": "task", "tool": tool, "args": t_args})
        return "Task sent to session peer."

    async def kb_share_in_session(self, args: Dict[str, Any]) -> str:
        sid, text, src = args.get("session_id", ""), args.get("text", ""), args.get("source", "session")
        if not (sid and text): return "ArgError: session_id and text required."
        await self.sessions.send_session(sid, {"type": "share_text", "text": text, "source": src})
        return "Shared with session peer."