import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Tuple
from ..utils.db import configure_sqlite

class MemoryInbox:
    def __init__(self, db_path: str):
        Path(Path(db_path).parent).mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        configure_sqlite(self.conn)
        c = self.conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS pending(id INTEGER PRIMARY KEY, src TEXT, rel TEXT, dst TEXT, confidence REAL, created_at TEXT)")
        self.conn.commit()

    def add(self, src: str, rel: str, dst: str, conf: float = 0.8):
        c = self.conn.cursor()
        c.execute("INSERT INTO pending(src,rel,dst,confidence,created_at) VALUES (?,?,?,?,?)",
                  (src, rel, dst, conf, datetime.utcnow().isoformat()))
        self.conn.commit()

    def list_pending(self) -> List[Tuple[int, str, str, str]]:
        c = self.conn.cursor()
        c.execute("SELECT id,src,rel,dst FROM pending ORDER BY id")
        return c.fetchall()

    def pop(self, fact_ids: List[int]) -> List[Tuple[str, str, str, float]]:
        out, c = [], self.conn.cursor()
        for i in fact_ids:
            c.execute("SELECT src,rel,dst,confidence FROM pending WHERE id=?", (i,))
            row = c.fetchone()
            if row:
                out.append(row)
                c.execute("DELETE FROM pending WHERE id=?", (i,))
        self.conn.commit()
        return out