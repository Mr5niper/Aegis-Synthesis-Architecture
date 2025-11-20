import time, sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Tuple, List, Optional
from ..utils.db import configure_sqlite

@dataclass
class Rel:
    src: str; rel: str; dst: str; ts: float

class LWWGraph:
    def __init__(self, db_path: str):
        Path(Path(db_path).parent).mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        configure_sqlite(self.conn)
        self._setup()
        self._rels: Dict[Tuple[str, str, str], Rel] = self._load()

    def _setup(self):
        c = self.conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS relations(key TEXT PRIMARY KEY, src TEXT, rel TEXT, dst TEXT, ts REAL)")
        self.conn.commit()

    def _load(self) -> Dict[Tuple[str, str, str], Rel]:
        c = self.conn.cursor()
        c.execute("SELECT src, rel, dst, ts FROM relations")
        return {(r[0], r[1], r[2]): Rel(*r) for r in c.fetchall()}

    def upsert(self, src: str, rel: str, dst: str, ts: Optional[float] = None) -> Rel:
        key, ts = (src, rel, dst), ts or time.time()
        if not self._rels.get(key) or ts >= self._rels[key].ts:
            self._rels[key] = Rel(src, rel, dst, ts)
            c = self.conn.cursor()
            # FIX: Corrected typo in SQLite placeholder substitution from 'dst' to '{dst}'
            c.execute("INSERT OR REPLACE INTO relations (key, src, rel, dst, ts) VALUES (?, ?, ?, ?, ?)",
                      (f"{src}|{rel}|{dst}", src, rel, dst, ts))
            self.conn.commit()
        return self._rels[key]

    def apply_op(self, op: dict) -> bool:
        if op.get("op") == "upsert_relation":
            self.upsert(op["src"], op["rel"], op["dst"], float(op["ts"]))
            return True
        return False

    def facts_for_prompt(self, n: int = 10) -> str:
        top = sorted(self._rels.values(), key=lambda r: r.ts, reverse=True)[:n]
        return "\n".join([f"{r.src} {r.rel} {r.dst}" for r in top])