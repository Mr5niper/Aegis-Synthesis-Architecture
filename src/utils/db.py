# src/utils/db.py
def configure_sqlite(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA temp_store=MEMORY;")
    cur.execute("PRAGMA mmap_size=30000000000;")
    cur.execute("PRAGMA busy_timeout=5000;")
    conn.commit()