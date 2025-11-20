import asyncio, json, base64, uuid, time
from typing import Dict, Optional, Callable, Awaitable
from nacl.public import PrivateKey as CurvePriv, PublicKey as CurvePub, Box
from nacl.utils import random as nacl_random
from .p2p import P2P
from ..secure.crypto import b64, b64d
from ..secure.consent import ConsentToken, sha256_hex
from nacl.signing import SigningKey, VerifyKey

class Session:
    def __init__(self, sid: str, peer: str, priv: CurvePriv, pub: CurvePub, consent: dict):
        self.session_id, self.peer_id, self.box, self.consent, self.created_at = sid, peer, Box(priv, pub), consent, time.time()

class SessionManager:
    def __init__(self, p2p: P2P, own_sk: SigningKey, contacts_verify: Callable[[str], Optional[VerifyKey]]):
        self.p2p, self.own_sk, self.get_peer_verify = p2p, own_sk, contacts_verify
        self.sessions: Dict[str, Session] = {}
        self.p2p.on("kairos_invite", self._on_invite); self.p2p.on("kairos_accept", self._on_accept)
        self.p2p.on("kairos_reject", self._on_reject); self.p2p.on("kairos_session_msg", self._on_session_msg)
        self._pending_inv: Dict[str, tuple] = {}
        self.on_consent_request: Optional[Callable[[str, str, dict], Awaitable[bool]]] = None
        self.on_session_message: Optional[Callable[[str, dict], Awaitable[None]]] = None

    async def start_maintenance(self, max_age_sec: int = 1800):
        while True:
            await asyncio.sleep(60)
            now = time.time()
            stale = [sid for sid, s in self.sessions.items() if now - s.created_at > max_age_sec]
            for sid in stale:
                self.sessions.pop(sid, None)

    async def initiate(self, peer_id: str, ctx: str, scope: dict, ttl_sec: int = 600) -> str:
        sid = f"ses-{uuid.uuid4().hex[:8]}"
        token = ConsentToken("1", sid, self.p2p.peer_id, peer_id, scope, sha256_hex(ctx), int(time.time())+ttl_sec)
        consent = token.sign(self.own_sk)
        eph_priv = CurvePriv.generate()
        await self.p2p.send_encrypted(peer_id, "kairos_invite", {"session_id": sid, "consent": consent, "eph_pub": b64(bytes(eph_priv.public_key))})
        fut = asyncio.get_event_loop().create_future()
        self._pending_inv[sid] = (fut, eph_priv, consent)
        if not await asyncio.wait_for(fut, timeout=60): raise TimeoutError("Invite not accepted")
        return sid

    async def _on_invite(self, env: dict):
        payload = self.p2p.decrypt_from(env["sender_pub"], env["nonce"], env["ciphertext"])
        peer_id, sid, consent, eph_pub = env["from"], payload["session_id"], payload["consent"], payload["eph_pub"]
        vk = self.get_peer_verify(peer_id)
        reject = lambda: self.p2p.send_encrypted(peer_id, "kairos_reject", {"session_id": sid})
        if not vk or not ConsentToken.verify(vk, consent): return await reject()
        approved = await self.on_consent_request(peer_id, sid, consent) if self.on_consent_request else True
        if not approved: return await reject()
        my_priv = CurvePriv.generate()
        self.sessions[sid] = Session(sid, peer_id, my_priv, CurvePub(b64d(eph_pub)), consent)
        await self.p2p.send_encrypted(peer_id, "kairos_accept", {"session_id": sid, "eph_pub": b64(bytes(my_priv.public_key))})

    async def _on_accept(self, env: dict):
        payload = self.p2p.decrypt_from(env["sender_pub"], env["nonce"], env["ciphertext"])
        sid, peer_pub_b64 = payload["session_id"], payload["eph_pub"]
        if not (pending := self._pending_inv.get(sid)): return
        fut, my_priv, consent = pending
        self.sessions[sid] = Session(sid, env["from"], my_priv, CurvePub(b64d(peer_pub_b64)), consent)
        fut.set_result(True); self._pending_inv.pop(sid, None)

    async def _on_reject(self, env: dict):
        payload = self.p2p.decrypt_from(env["sender_pub"], env["nonce"], env["ciphertext"])
        if (pending := self._pending_inv.get(payload["session_id"])):
            pending[0].set_result(False); self._pending_inv.pop(payload["session_id"], None)
    
    async def send_session(self, sid: str, payload: dict):
        if not (sess := self.sessions.get(sid)): raise ValueError("Unknown session")
        nonce = nacl_random(Box.NONCE_SIZE)
        ct = sess.box.encrypt(json.dumps(payload).encode(), nonce)
        await self.p2p.send_encrypted(sess.peer_id, "kairos_session_msg", {"session_id": sid, "nonce_s": b64(nonce), "ciphertext_s": b64(ct.ciphertext)})

    async def _on_session_msg(self, env: dict):
        payload = self.p2p.decrypt_from(env["sender_pub"], env["nonce"], env["ciphertext"])
        if not (sess := self.sessions.get(payload["session_id"])): return
        inner = sess.box.decrypt(b64d(payload["ciphertext_s"]), b64d(payload["nonce_s"]))
        if self.on_session_message: await self.on_session_message(payload["session_id"], json.loads(inner))