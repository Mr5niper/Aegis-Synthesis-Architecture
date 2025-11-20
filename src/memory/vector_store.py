import sqlite3
from datetime import datetime
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
from ..utils.db import configure_sqlite

def _to_blob(vec: np.ndarray) -> bytes: return vec.astype(np.float32).tobytes()
def _from_blob(blob: bytes) -> np.ndarray: return np.frombuffer(blob, dtype=np.float32)

class LiteVectorStore:
    def __init__(self, db_path: str, embedding_model: str):
        Path(Path(db_path).parent).mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        configure_sqlite(self.conn)
        self.model = SentenceTransformer(embedding_model)
        c = self.conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, source TEXT, chunk_idx INTEGER, text TEXT, embedding BLOB, ts TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_source ON docs(source)")
        self.conn.commit()

    def add_document(self, text: str, source: str = "user", chunk_size: int = 500, overlap: int = 50) -> int:
        step = max(1, chunk_size - max(0, overlap))
        chunks = [text[i:i+chunk_size] for i in range(0, max(len(text), 1), step)]
        if not chunks:
            return 0
        embs = self.model.encode(chunks, normalize_embeddings=True)
        c = self.conn.cursor()
        for idx, (t, e) in enumerate(zip(chunks, embs)):
            c.execute(
                "INSERT INTO docs(source,chunk_idx,text,embedding,ts) VALUES (?,?,?,?,?)",
                (source, idx, t, _to_blob(e), datetime.utcnow().isoformat())
            )
        self.conn.commit()
        return len(chunks)

    def retrieve_context(self, query: str, k: int = 3) -> str:
        q = self.model.encode([query], normalize_embeddings=True)[0]
        c = self.conn.cursor()
        c.execute("SELECT text, embedding FROM docs")
        rows = c.fetchall()
        if not rows:
            return ""
        texts, sims = zip(*[(t, float(np.dot(q, _from_blob(blob)))) for t, blob in rows])
        import numpy as _np
        idxs = _np.argsort(sims)[::-1][:k]
        return "\n\n".join([texts[i] for i in idxs])