import json
import sqlite3
from typing import Optional, List
from contextlib import contextmanager
from Infrastructure.Repositories.SessionRepository import SessionRepository
from Domain.Entities.InterviewSession import InterviewSession, Founder, Message, ArchitecturalSpec

DB_PATH = 'orchestrator_v2.db'

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute('PRAGMA journal_mode=WAL;')
        # We store the entire Domain Entity as a serialized JSON object
        # because the database is just an I/O detail.
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data JSON NOT NULL
            )
        ''')

class SQLiteSessionRepository(SessionRepository):
    """
    SQLite implementation of the SessionRepository interface.
    This acts as the translation layer between our Domain Entities and the DB.
    """

    def __init__(self):
        init_db()

    def _serialize(self, session: InterviewSession) -> str:
        # Convert dataclass to a dictionary suitable for JSON storage
        data = {
            "id": session.id,
            "status": session.status,
            "context_index": session.context_index,
            "founder": {
                "id": session.founder.id,
                "name": session.founder.name,
                "startup_name": session.founder.startup_name,
                "vision": session.founder.vision
            },
            "spec": {
                "id": session.spec.id,
                "domains": session.spec.domains,
                "core_ethos": session.spec.core_ethos
            },
            "messages": [{"role": m.role, "content": m.content, "metadata": m.metadata} for m in session.messages]
        }
        return json.dumps(data)

    def _deserialize(self, row_id: int, raw_data: str) -> InterviewSession:
        data = json.loads(raw_data)

        founder = Founder(
            id=data.get("founder", {}).get("id"),
            name=data.get("founder", {}).get("name"),
            startup_name=data.get("founder", {}).get("startup_name"),
            vision=data.get("founder", {}).get("vision")
        )

        spec = ArchitecturalSpec(
            id=data.get("spec", {}).get("id"),
            domains=data.get("spec", {}).get("domains", {}),
            core_ethos=data.get("spec", {}).get("core_ethos")
        )

        messages = [Message(role=m["role"], content=m["content"], metadata=m.get("metadata", {})) for m in data.get("messages", [])]

        session = InterviewSession(
            id=row_id, # Always trust the SQL primary key instead of the JSON payload key
            founder=founder,
            messages=messages,
            spec=spec,
            status=data.get("status", "active"),
            context_index=data.get("context_index", {})
        )
        return session

    def save(self, session: InterviewSession) -> None:
        """Atomic sync back to the Session Repository to prevent memory collisions."""
        with get_db() as conn:
            if session.id == 0 or session.id is None:
                temp_data = self._serialize(session)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO sessions (data) VALUES (?)", (temp_data,))
                session.id = cursor.lastrowid

                # Now that we have the real ID, re-serialize and update
                serialized_data = self._serialize(session)
                conn.execute("UPDATE sessions SET data = ? WHERE id = ?", (serialized_data, session.id))
            else:
                serialized_data = self._serialize(session)
                # Check if it actually exists first just in case
                row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session.id,)).fetchone()
                if row:
                     conn.execute("UPDATE sessions SET data = ? WHERE id = ?", (serialized_data, session.id))
                else:
                     conn.execute("INSERT INTO sessions (id, data) VALUES (?, ?)", (session.id, serialized_data))

    def find_by_id(self, session_id: int) -> Optional[InterviewSession]:
        with get_db() as conn:
            row = conn.execute("SELECT id, data FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row:
                return self._deserialize(row['id'], row['data'])
            return None

    def delete(self, session_id: int) -> None:
        with get_db() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def get_all(self) -> List[InterviewSession]:
        sessions = []
        with get_db() as conn:
            rows = conn.execute("SELECT id, data FROM sessions").fetchall()
            for row in rows:
                sessions.append(self._deserialize(row['id'], row['data']))
        return sessions
