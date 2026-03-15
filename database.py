"""
database.py - SQLite Database for Interview Orchestrator
Handles all database operations including new Multi-Session architecture.

REFACTOR #1: Safe Database Connections
---------------------------------------
All database functions now use 'with get_db() as conn:' to guarantee
connections are properly closed, even if an error occurs mid-query.
The get_db() function is now a context manager — Python's standard
pattern for "open something, use it, always close it."
"""

import sqlite3
import os
from contextlib import contextmanager  # <-- NEW: enables the 'with' pattern

DB_PATH = os.path.join(os.path.dirname(__file__), "orchestrator.db")


@contextmanager  # <-- This decorator turns our function into a context manager
def get_db():
    """
    Opens a database connection and guarantees it closes when done.
    
    Usage (before):
        conn = get_db()
        # ... do work ...
        conn.close()     # <-- if an error happens above, this never runs!
    
    Usage (after):
        with get_db() as conn:
            # ... do work ...
            # connection closes automatically, even on errors
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn          # <-- hands the connection to the 'with' block
    finally:
        conn.close()         # <-- ALWAYS runs, error or not


def init_db():
    with get_db() as conn:
        cursor = conn.cursor()

        # Schema Migration: Drop prototype tables if they lack session capabilities
        try:
            cursor.execute("SELECT id FROM sessions LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("DROP TABLE IF EXISTS conversations")
            cursor.execute("DROP TABLE IF EXISTS routing_logs")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                prompt_file TEXT NOT NULL,
                model TEXT DEFAULT 'gemini-2.5-flash',
                is_synthesizer INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                agent_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                message_type TEXT DEFAULT 'chat',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routing_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                input_text TEXT NOT NULL,
                agent_id INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.commit()


def seed_agents():
    with get_db() as conn:
        cursor = conn.cursor()

        count = cursor.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        if count == 0:
            agents = [
                (1, "Brand Spine",              "1_brand_spine.md",              "gemini-3.1-flash-lite-preview", 0),
                (2, "Founder Invariants",       "2_founder_extraction.md",       "gemini-3.1-flash-lite-preview", 0),
                (3, "Customer Reality",          "3_customer_reality.md",         "gemini-3.1-flash-lite-preview", 0),
                (4, "Architecture Translation",  "4_architecture_translation.md", "gemini-3.1-flash-lite-preview", 0),
                (5, "Grand Synthesis",           "5_grand_synthesis.md",          "gemini-3.1-pro-preview",        1),
            ]
            cursor.executemany(
                "INSERT INTO agents (id, name, prompt_file, model, is_synthesizer) VALUES (?, ?, ?, ?, ?)",
                agents
            )
            conn.commit()


# ── Session Operations ────────────────────────────────────────────

def create_session(name="New Session"):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sessions (name) VALUES (?)", (name,))
        session_id = cursor.lastrowid
        conn.commit()
        return session_id


def get_sessions():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_session(session_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


def update_session(session_id, name=None):
    with get_db() as conn:
        if name:
            conn.execute("UPDATE sessions SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (name, session_id))
        else:
            conn.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
        conn.commit()


def delete_session(session_id):
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()


# ── Agent Operations ──────────────────────────────────────────────

def get_agents():
    with get_db() as conn:
        agents = conn.execute("SELECT * FROM agents WHERE is_synthesizer = 0 ORDER BY id").fetchall()
        return [dict(a) for a in agents]


def get_all_agents():
    with get_db() as conn:
        agents = conn.execute("SELECT * FROM agents ORDER BY id").fetchall()
        return [dict(a) for a in agents]


def get_agent(agent_id):
    with get_db() as conn:
        agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return dict(agent) if agent else None


def update_agent(agent_id, name, model):
    with get_db() as conn:
        conn.execute("UPDATE agents SET name = ?, model = ? WHERE id = ?", (name, model, agent_id))
        conn.commit()


# ── Conversation Operations ───────────────────────────────────────

def save_message(session_id, agent_id, role, content, message_type="chat"):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversations (session_id, agent_id, role, content, message_type) VALUES (?, ?, ?, ?, ?)",
            (session_id, agent_id, role, content, message_type)
        )
        conn.commit()
    # update_session is called separately (it opens its own safe connection)
    update_session(session_id)


def get_conversation(session_id, agent_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE session_id = ? AND agent_id = ? ORDER BY timestamp ASC",
            (session_id, agent_id)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_conversations(session_id):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.*, a.name as agent_name
            FROM conversations c
            JOIN agents a ON c.agent_id = a.id
            WHERE c.session_id = ?
            ORDER BY c.timestamp ASC
        """, (session_id,)).fetchall()
        return [dict(r) for r in rows]


def get_recent_global_context(session_id, exclude_agent_id, limit=6):
    """Heal: Fetches recent interactions across OTHER agents to solve the Context Silo."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.role, c.content, a.name as agent_name
            FROM conversations c
            JOIN agents a ON c.agent_id = a.id
            WHERE c.session_id = ? AND c.agent_id != ? AND c.message_type = 'chat'
            ORDER BY c.timestamp DESC
            LIMIT ?
        """, (session_id, exclude_agent_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]  # Reversed to chronological order


# ── Routing Log Operations ────────────────────────────────────────

def save_routing_log(session_id, input_text, agent_id, agent_name, reason):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO routing_logs (session_id, input_text, agent_id, agent_name, reason) VALUES (?, ?, ?, ?, ?)",
            (session_id, input_text, agent_id, agent_name, reason)
        )
        conn.commit()


def get_routing_logs(session_id, limit=20):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM routing_logs WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Config Operations ─────────────────────────────────────────────

def get_config(key, default=None):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_config(key, value):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def export_config():
    return get_all_agents()


def import_config(agents_data):
    with get_db() as conn:
        for agent in agents_data:
            conn.execute(
                "UPDATE agents SET name = ?, model = ? WHERE id = ?",
                (agent.get("name", ""), agent.get("model", "gemini-2.5-flash"), agent.get("id"))
            )
        conn.commit()
