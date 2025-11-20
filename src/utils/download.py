from pathlib import Path
from tqdm import tqdm
import requests, hashlib

def sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()

def download_file(url: str, dest: Path, expected_sha256: str = ""):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(tmp, "wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=dest.name) as pbar:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk: f.write(chunk); pbar.update(len(chunk))
    if expected_sha256 and sha256sum(tmp).lower() != expected_sha256.lower():
        tmp.unlink(missing_ok=True); raise ValueError("SHA256 mismatch")
    tmp.replace(dest)