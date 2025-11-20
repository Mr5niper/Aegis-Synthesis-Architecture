import time, json, hashlib, base64
from dataclasses import dataclass, asdict
from typing import Dict, Any
from nacl.signing import SigningKey, VerifyKey

def sha256_hex(s: str) -> str: return hashlib.sha256(s.encode()).hexdigest()

@dataclass
class ConsentToken:
    version: str; session_id: str; initiator_id: str; recipient_id: str
    scope: Dict[str, Any]; context_hash: str; exp: int; _sig: str = ""

    def sign(self, sk: SigningKey) -> dict:
        data = {k: v for k, v in asdict(self).items() if k != "_sig"}
        msg = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        sig = sk.sign(msg).signature
        out = dict(data); out["_sig"] = base64.b64encode(sig).decode(); return out

    @staticmethod
    def verify(vk: VerifyKey, obj: dict) -> bool:
        try:
            if int(obj.get("exp", 0)) < int(time.time()): return False
            data, sig_b64 = dict(obj), obj.pop("_sig", "")
            if not sig_b64: return False
            msg = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
            vk.verify(msg, base64.b64decode(sig_b64)); return True
        except Exception: return False

    @staticmethod
    def allows(obj: dict, tool: str, args: dict) -> bool:
        scope = obj.get("scope", {}); tools = scope.get("tools", [])
        if tools and tool not in tools: return False
        lim = scope.get("args", {})
        if "max_k" in lim and "k" in args and int(args["k"]) > int(lim["max_k"]): return False
        return True