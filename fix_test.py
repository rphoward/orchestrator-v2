import sqlite3
import json

DB_PATH = 'orchestrator_v2.db'
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, data FROM sessions").fetchall()
for row in rows:
    print(dict(row))
conn.close()
