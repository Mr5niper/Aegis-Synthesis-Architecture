import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from ..utils.db import configure_sqlite

class WebCache:
    def __init__(self, db_path: str, ttl_minutes: int = 720):
        Path(Path(db_path).parent).mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        configure_sqlite(self.conn)
        self.ttl = timedelta(minutes=ttl_minutes)
        c = self.conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS web_cache(url TEXT PRIMARY KEY, fetched_at TEXT, text TEXT)")
        self.conn.commit()

    def get(self, url: str) -> str | None:
        c = self.conn.cursor()
        c.execute("SELECT fetched_at, text FROM web_cache WHERE url = ?", (url,))
        row = c.fetchone()
        if row and datetime.utcnow() - datetime.fromisoformat(row[0]) <= self.ttl:
            return row[1]
        return None

    def put(self, url: str, text: str):
        c = self.conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO web_cache(url, fetched_at, text) VALUES (?,?,?)",
            (url, datetime.utcnow().isoformat(), text)
        )
        self.conn.commit()