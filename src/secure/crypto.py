from pathlib import Path
from typing import Tuple
from nacl.public import PrivateKey as CurvePriv, PublicKey as CurvePub
from nacl.signing import SigningKey, VerifyKey
from nacl.bindings import crypto_sign_ed25519_sk_to_curve25519, crypto_sign_ed25519_pk_to_curve25519
import base64, hashlib

def b64(b: bytes) -> str: return base64.b64encode(b).decode()
def b64d(s: str) -> bytes: return base64.b64decode(s)

def load_or_create_keys(name: str, keys_dir: str) -> Tuple[SigningKey, VerifyKey]:
    key_dir = Path(keys_dir); key_dir.mkdir(parents=True, exist_ok=True)
    skf, pkf = key_dir / f"{name}.ed25519.sk", key_dir / f"{name}.ed25519.pk"
    if skf.exists() and pkf.exists():
        return SigningKey(b64d(skf.read_text())), VerifyKey(b64d(pkf.read_text()))
    sk = SigningKey.generate()
    skf.write_text(b64(bytes(sk))); pkf.write_text(b64(bytes(sk.verify_key)))
    return sk, sk.verify_key

def ed25519_to_curve25519(sk: SigningKey, vk: VerifyKey) -> Tuple[CurvePriv, CurvePub]:
    # SigningKey stores only the 32-byte seed, but NaCl needs the full 64-byte key
    # The full key is seed + public key
    full_sk = bytes(sk) + bytes(vk)  # 32 + 32 = 64 bytes
    
    csk = CurvePriv(crypto_sign_ed25519_sk_to_curve25519(full_sk))
    cvk = CurvePub(crypto_sign_ed25519_pk_to_curve25519(bytes(vk)))
    return csk, cvk

def verify_key_b64(vk: VerifyKey) -> str:
    return base64.b64encode(bytes(vk)).decode()

def verify_key_fingerprint(vk: VerifyKey) -> str:
    return hashlib.sha256(bytes(vk)).hexdigest()[:16]