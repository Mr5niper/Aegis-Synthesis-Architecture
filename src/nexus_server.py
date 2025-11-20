# To run this separate server: uvicorn src.nexus_server:app --host 0.0.0.0 --port 7861
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from typing import Dict
import uvicorn

app = FastAPI(title="Aegis Nexus Relay")

class Manager:
    def __init__(self):
        self.conns: Dict[str, WebSocket] = {}

    async def connect(self, pid: str, ws: WebSocket):
        await ws.accept()
        self.conns[pid] = ws
        await self._broadcast_peers()

    def disconnect(self, pid: str):
        self.conns.pop(pid, None)

    async def _broadcast_peers(self):
        peers = list(self.conns.keys())
        for ws in self.conns.values():
            await ws.send_json({"type": "peer_update", "peers": peers})

    async def route(self, sender: str, message: dict):
        dst = message.get("to")
        if not dst or dst not in self.conns:
            return
        message["from"] = sender
        await self.conns[dst].send_json(message)

mgr = Manager()

@app.get("/health")
async def health_check():
    return JSONResponse({
        "status": "healthy",
        "connected_peers": len(mgr.conns),
        "peer_ids": list(mgr.conns.keys())
    })

@app.get("/")
async def root():
    return {"service": "Aegis Nexus Relay", "version": "1.0"}


@app.websocket("/ws/{peer_id}")
async def ws_endpoint(ws: WebSocket, peer_id: str):
    await mgr.connect(peer_id, ws)
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "pubkey":
                for w in mgr.conns.values():
                    await w.send_json({"type": "pubkey", "peer": peer_id, "pubkey": msg.get("pubkey")})
            else:
                await mgr.route(peer_id, msg)
    except WebSocketDisconnect:
        mgr.disconnect(peer_id)
        await mgr._broadcast_peers()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7861)