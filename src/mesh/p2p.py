import asyncio, json, base64
import websockets
from typing import Dict, List, Callable, Awaitable
from nacl.public import PrivateKey as CurvePriv, PublicKey as CurvePub, Box
from nacl.signing import SigningKey
from nacl.utils import random as nacl_random
from ..secure.crypto import ed25519_to_curve25519, b64, b64d

class P2P:
    def __init__(self, peer_id: str, nexus_url: str, ed_sk: SigningKey):
        self.peer_id, self.nexus, self.ws = peer_id, nexus_url.rstrip("/"), None
        self.peers: List[str] = []
        self.peer_curve_pubs: Dict[str, str] = {}
        self.msg_handlers: Dict[str, Callable[[dict], Awaitable[None]]] = {}
        self.ed_sk, self.ed_vk = ed_sk, ed_sk.verify_key
        self.curve_sk, self.curve_pk = ed25519_to_curve25519(self.ed_sk, self.ed_vk)

    async def connect(self):
        uri = f"{self.nexus}/ws/{self.peer_id}"
        self.ws = await websockets.connect(uri)
        await self._announce_pubkey()
        asyncio.create_task(self._listen())

    async def _announce_pubkey(self):
        if self.ws: await self.ws.send(json.dumps({"type": "pubkey", "pubkey": b64(bytes(self.curve_pk))}))

    async def _listen(self):
        while self.ws:
            try:
                msg = json.loads(await self.ws.recv())
                t = msg.get("type")
                if t == "peer_update": self.peers = [p for p in msg.get("peers", []) if p != self.peer_id]
                elif t == "pubkey": self.peer_curve_pubs[msg["peer"]] = msg["pubkey"]
                elif (h := self.msg_handlers.get(t)): await h(msg)
            except websockets.ConnectionClosed:
                await asyncio.sleep(3); await self.connect()

    def on(self, msg_type: str, handler: Callable[[dict], Awaitable[None]]): self.msg_handlers[msg_type] = handler

    def _box_for(self, peer: str) -> Box | None:
        if (pk_b64 := self.peer_curve_pubs.get(peer)): return Box(self.curve_sk, CurvePub(b64d(pk_b64)))
        return None

    async def send_encrypted(self, to_peer: str, msg_type: str, payload: dict):
        if not self.ws: return "Error: not connected"
        if not (box := self._box_for(to_peer)): return f"Error: peer key for {to_peer} unknown"
        nonce = nacl_random(Box.NONCE_SIZE)
        ct = box.encrypt(json.dumps(payload).encode(), nonce).ciphertext
        envelope = {"to": to_peer, "type": msg_type, "nonce": b64(nonce), "ciphertext": b64(ct), "sender_pub": b64(bytes(self.curve_pk))}
        await self.ws.send(json.dumps(envelope))

    def decrypt_from(self, sender_pub_b64: str, nonce_b64: str, ct_b64: str) -> dict | None:
        try:
            box = Box(self.curve_sk, CurvePub(b64d(sender_pub_b64)))
            return json.loads(box.decrypt(b64d(ct_b64), b64d(nonce_b64)))
        except Exception: return None