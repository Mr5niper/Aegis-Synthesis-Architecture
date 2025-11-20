import time, asyncio
from typing import List, Tuple
from ..memory.graph_crdt import LWWGraph
from ..mesh.p2p import P2P

class SyncService:
    def __init__(self, graph: LWWGraph, p2p: P2P):
        self.graph, self.p2p = graph, p2p
        self.p2p.on("crdt_ops", self._on_ops)

    async def broadcast_relations(self, rels: List[Tuple[str,str,str,float]]):
        ops = [{"op":"upsert_relation","src":s,"rel":r,"dst":d,"ts":ts} for s,r,d,ts in rels]
        for peer in self.p2p.peers:
            await self.p2p.send_encrypted(peer, "crdt_ops", {"ops": ops})

    async def _on_ops(self, env: dict):
        payload = self.p2p.decrypt_from(env["sender_pub"], env["nonce"], env["ciphertext"])
        if payload:
            for op in payload.get("ops", []): self.graph.apply_op(op)