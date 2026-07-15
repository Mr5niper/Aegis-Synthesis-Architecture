import sqlite3
from datetime import datetime
from pathlib import Path
from ..utils.db import configure_sqlite

class ConversationMemory:
    def __init__(self, db_path: str):
        Path(Path(db_path).parent).mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        configure_sqlite(self.conn)
        c = self.conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY, session_id TEXT, ts TEXT, user TEXT, assistant TEXT, context TEXT)")
        self.conn.commit()

    def add_message(self, session_id: str, user: str, assistant: str, context: str):
        c = self.conn.cursor()
        c.execute("INSERT INTO conversations(session_id,ts,user,assistant,context) VALUES(?,?,?,?,?)",
                  (session_id, datetime.utcnow().isoformat(), user, assistant, context))
        self.conn.commit()

    def get_recent_context(self, session_id: str, n: int = 6) -> str:
        c = self.conn.cursor()
        c.execute("SELECT user, assistant FROM conversations WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, n))
        pairs = reversed(c.fetchall())
        return "\n\n".join([f"User: {u}\nAssistant: {a}" for u, a in pairs])

    def get_recent_turns(self, session_id: str, n: int = 6) -> list:
        """Same recent window as get_recent_context, but as chat-style turns:
        [{'role':'user','content':...},{'role':'assistant','content':...}, ...],
        oldest first. The reply model reads THIS (so prior turns -- including the
        assistant's own earlier answers, which hold whatever was looked up -- are
        seen as real dialogue it can refer back to), while the search-decision
        classifier reads get_recent_context. Both come from the same rows and the
        same n, so the decider and the conversation stay in sync. Empty fields are
        skipped so a malformed row cannot inject a blank turn."""
        c = self.conn.cursor()
        c.execute("SELECT user, assistant FROM conversations WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, n))
        rows = list(reversed(c.fetchall()))
        turns = []
        for u, a in rows:
            if u:
                turns.append({"role": "user", "content": u})
            if a:
                turns.append({"role": "assistant", "content": a})
        return turns