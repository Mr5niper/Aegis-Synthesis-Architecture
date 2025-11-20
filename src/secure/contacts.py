import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional

class ContactManager:
    def __init__(self, db_path: str):
        Path(Path(db_path).parent).mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        c = self.conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS contacts(alias TEXT PRIMARY KEY, peer_id TEXT UNIQUE, verify_key_b64 TEXT, status TEXT DEFAULT 'pending')")
        self.conn.commit()

    def add_pending(self, alias: str, peer_id: str, vk_b64: str):
        c = self.conn.cursor()
        c.execute("INSERT OR IGNORE INTO contacts (alias, peer_id, verify_key_b64) VALUES (?, ?, ?)", (alias, peer_id, vk_b64))
        self.conn.commit()

    def trust_contact(self, peer_id: str):
        c = self.conn.cursor()
        c.execute("UPDATE contacts SET status='trusted' WHERE peer_id=?", (peer_id,)); self.conn.commit()

    def get_trusted_peers(self) -> List[Tuple[str, str, str]]:
        c = self.conn.cursor()
        c.execute("SELECT alias, peer_id, verify_key_b64 FROM contacts WHERE status='trusted'")
        return c.fetchall()

    def get_verify_key(self, peer_id: str) -> Optional[str]:
        c = self.conn.cursor()
        c.execute("SELECT verify_key_b64 FROM contacts WHERE status='trusted' AND peer_id=?", (peer_id,))
        return (row[0] if (row := c.fetchone()) else None)