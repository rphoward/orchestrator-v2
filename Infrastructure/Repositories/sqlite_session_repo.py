import os
import sqlite3
from typing import List, Optional
from datetime import datetime, UTC
from Domain.Session.aggregate import InterviewSession
from Domain.Session.entities import Message, RoutingLog
from Domain.Core.entities import Agent
from Infrastructure.Repositories.interfaces import SessionRepository, AgentRepository

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "orchestrator.db")

class SQLiteSessionRepository(SessionRepository):
    """
    Concrete implementation of the SessionRepository interface.
    Handles atomic persistence of the InterviewSession Aggregate Root to SQLite.
    """

    def _get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def save(self, session: InterviewSession) -> InterviewSession:
        """Persists the ENTIRE aggregate root atomically."""
        conn = self._get_db()
        try:
            cursor = conn.cursor()

            # 1. Save or Update the Session Root
            if session.id is None:
                cursor.execute(
                    "INSERT INTO sessions (name, created_at, updated_at) VALUES (?, ?, ?)",
                    (session.name, session.created_at, session.updated_at)
                )
                session.id = cursor.lastrowid
            else:
                cursor.execute(
                    "UPDATE sessions SET name = ?, updated_at = ? WHERE id = ?",
                    (session.name, session.updated_at, session.id)
                )

            # 2. Save Messages (Only new ones, or delete/recreate. Since they are append-only, we can just insert based on count, but for true DDD, recreating or upserting based on a unique ID is safer. However, since our DB schema uses auto-incrementing integer IDs and our Domain uses UUIDs, we will do a simple delete-and-replace for the child entities to guarantee the aggregate state perfectly matches memory. This is standard for small aggregates).
            cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session.id,))
            for msg in session.messages:
                cursor.execute(
                    "INSERT INTO conversations (session_id, agent_id, role, content, message_type, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    (session.id, msg.agent_id, msg.role, msg.content, msg.message_type, msg.timestamp)
                )

            # 3. Save Routing Logs
            cursor.execute("DELETE FROM routing_logs WHERE session_id = ?", (session.id,))
            for log in session.routing_logs:
                cursor.execute(
                    "INSERT INTO routing_logs (session_id, input_text, agent_id, agent_name, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    (session.id, log.input_text, log.agent_id, log.agent_name, log.reason, log.timestamp)
                )

            conn.commit()
            return session
        finally:
            conn.close()

    def get_by_id(self, session_id: int) -> Optional[InterviewSession]:
        """Rehydrates the aggregate root from persistence."""
        conn = self._get_db()
        try:
            # 1. Fetch Session Root
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                return None

            session = InterviewSession(
                id=row["id"],
                name=row["name"],
                created_at=datetime.fromisoformat(row["created_at"]) if isinstance(row["created_at"], str) else row["created_at"],
                updated_at=datetime.fromisoformat(row["updated_at"]) if isinstance(row["updated_at"], str) else row["updated_at"]
            )

            # 2. Rehydrate Messages
            msg_rows = conn.execute("SELECT * FROM conversations WHERE session_id = ? ORDER BY timestamp ASC", (session_id,)).fetchall()
            for m_row in msg_rows:
                session.messages.append(
                    Message(
                        agent_id=m_row["agent_id"],
                        role=m_row["role"],
                        content=m_row["content"],
                        message_type=m_row["message_type"],
                        timestamp=datetime.fromisoformat(m_row["timestamp"]) if isinstance(m_row["timestamp"], str) else m_row["timestamp"]
                    )
                )

            # 3. Rehydrate Routing Logs
            log_rows = conn.execute("SELECT * FROM routing_logs WHERE session_id = ? ORDER BY timestamp ASC", (session_id,)).fetchall()
            for l_row in log_rows:
                session.routing_logs.append(
                    RoutingLog(
                        input_text=l_row["input_text"],
                        agent_id=l_row["agent_id"],
                        agent_name=l_row["agent_name"],
                        reason=l_row["reason"],
                        timestamp=datetime.fromisoformat(l_row["timestamp"]) if isinstance(l_row["timestamp"], str) else l_row["timestamp"]
                    )
                )

            return session
        finally:
            conn.close()

    def list_all(self) -> List[InterviewSession]:
        """Returns all sessions without full child-entity hydration for performance."""
        conn = self._get_db()
        try:
            rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
            sessions = []
            for row in rows:
                sessions.append(
                    InterviewSession(
                        id=row["id"],
                        name=row["name"],
                        created_at=datetime.fromisoformat(row["created_at"]) if isinstance(row["created_at"], str) else row["created_at"],
                        updated_at=datetime.fromisoformat(row["updated_at"]) if isinstance(row["updated_at"], str) else row["updated_at"]
                    )
                )
            return sessions
        finally:
            conn.close()

    def delete(self, session_id: int) -> None:
        """Deletes the entire session aggregate."""
        conn = self._get_db()
        try:
            # Foreign keys ON DELETE CASCADE will handle the child entities
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()


class SQLiteAgentRepository(AgentRepository):
    """
    Implementation of the AgentRepository.
    Loads Agent configurations from SQLite and reads the corresponding
    Markdown prompts directly from the filesystem.
    """

    def __init__(self):
        self.prompts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts")

    def _get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_prompt_content(self, filename: str) -> str:
        """Reads the physical markdown file from the prompts directory."""
        filepath = os.path.join(self.prompts_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return f"Error: Prompt file '{filename}' not found."

    def get_all(self) -> List[Agent]:
        conn = self._get_db()
        try:
            rows = conn.execute("SELECT * FROM agents ORDER BY id").fetchall()
            agents = []
            for row in rows:
                agents.append(
                    Agent(
                        id=row["id"],
                        name=row["name"],
                        prompt_file=row["prompt_file"],
                        model=row["model"],
                        is_synthesizer=bool(row["is_synthesizer"])
                    )
                )
            return agents
        finally:
            conn.close()

    def get_by_id(self, agent_id: int) -> Optional[Agent]:
        conn = self._get_db()
        try:
            row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if not row:
                return None
            return Agent(
                id=row["id"],
                name=row["name"],
                prompt_file=row["prompt_file"],
                model=row["model"],
                is_synthesizer=bool(row["is_synthesizer"])
            )
        finally:
            conn.close()

    def get_system_prompt_for_agent(self, agent_id: int) -> str:
        """Helper to fetch the Agent entity and load its markdown prompt."""
        agent = self.get_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found.")
        return self._load_prompt_content(agent.prompt_file)

    def save(self, agent: Agent) -> Agent:
        conn = self._get_db()
        try:
            conn.execute(
                "UPDATE agents SET name = ?, model = ?, prompt_file = ?, is_synthesizer = ? WHERE id = ?",
                (agent.name, agent.model, agent.prompt_file, int(agent.is_synthesizer), agent.id)
            )
            # We don't handle inserts right now because the Swarm agents are statically seeded 1-5
            conn.commit()
            return agent
        finally:
            conn.close()
