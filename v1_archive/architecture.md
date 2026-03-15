# Interview Orchestrator Architecture

This document outlines the strict, layered architectural design of the Interview Orchestrator. The system operates as a stateful, multi-agent AI pipeline built on a robust, downward-flowing dependency model.

## 1. The 5-Layer Architectural Hierarchy

The backend is built using a strict layered structure. Dependencies only flow **downward**. No circular imports are allowed. This ensures predictable state, easy debugging, and safe database connections.

*   **Layer 5 (The Roof): `app.py`**
    *   **Role:** Web Server & API Gateway (Flask).
    *   **Responsibility:** Receives HTTP requests, maps them to Layer 4 workflows, and translates Layer 1 typed errors into specific HTTP status codes (e.g., 401, 429) and frontend `error_type` payloads.
*   **Layer 4 (Orchestration): `session_ops.py`**
    *   **Role:** Workflow Engine.
    *   **Responsibility:** Coordinates complex operations (`route_and_send`, `initialize_agents`, `finalize_session`). It calls the router (Layer 3) to pick an agent, logs the decision, and delegates the generation to `agent.py`. It handles workflow-level error logic (e.g., catching rate limits to prevent cascading failures).
*   **Layer 3 (Intelligence): `router.py` & `agent.py`**
    *   **Role:** The AI Communicators (Gemini API).
    *   **Responsibility (`router.py`):** Near-instant semantic classification. Uses a strict JSON schema and low temperature to determine which agent handles the user's input.
    *   **Responsibility (`agent.py`):** Builds the full context window. Loads prompts via an in-memory cache, builds the Gemini generation config (temperature, thinking levels), executes the cross-agent context injection, and translates raw API exceptions into typed internal errors.
*   **Layer 2 (Configuration): `model_registry.py`**
    *   **Role:** Model Capabilities & Settings Manager.
    *   **Responsibility:** Reads `models.json` on startup, syncs it to the SQLite `config` table, and provides safe helper functions for Layers 3-5 to lookup model rules (e.g., "Does this model support thinking?").
*   **Layer 1 (The Ground): `database.py` & `errors.py`**
    *   **Role (`database.py`):** Persistence & State. All DB access uses a `@contextmanager` (`with get_db() as conn:`) ensuring safe SQLite WAL connections that auto-close even on failure. Uses `executemany` for batch operations.
    *   **Role (`errors.py`):** Domain Error Classes. Defines typed exceptions (`APIKeyError`, `ModelError`, `ValidationError`) allowing the upper layers to implement specific recovery logic without parsing raw exception strings.

---

## 2. Multi-Agent Memory & Routing Patterns

The Orchestrator avoids the "context silo" problem (where isolated agents ask duplicate questions) through precise data flows.

### JIT Cross-Agent Context Injection
Instead of forcing all agents to share a single massive chat history, each agent maintains its own thread. However, at the exact moment an agent is called, `agent.py` performs a **Just-In-Time (JIT) memory injection**:
1.  It queries `database.py` for the last 6 messages across all *other* agents.
2.  It appends this as a read-only `=== RECENT GLOBAL CONVERSATION CONTEXT ===` block at the bottom of the System Prompt.
3.  The agent sees what the founder just discussed elsewhere, preventing redundant questions without polluting the agent's actual chat history.

### Deterministic Routing
The router is designed for speed and reliability, preventing conversation stalls:
1.  **Forced Minimal Thinking:** `router.py` forces `ThinkingLevel.MINIMAL` and `temperature=0.1` to ensure fast, predictable JSON outputs.
2.  **Graceful Degradation:** If the model hallucinates malformed JSON, or the API fails entirely with a `RoutingError`, `session_ops.py` catches it and defaults to Agent 1 ("Brand Spine"). The conversation never drops.

---

## 3. The Finalization Pipeline (Extraction to Synthesis)

When the user clicks "Finalize Report", the system executes a robust 3-phase OODA-like loop in `session_ops.py`:

1.  **Phase 1: Pre-flight Audit (Observe)**
    *   Scans the DB histories. If any agent has zero user interactions, the system pauses and returns a warning to the frontend, preventing hallucinated summaries.
2.  **Phase 2: Extraction (Orient & Decide)**
    *   If forced or approved, it loops through Agents 1-4.
    *   Empty agents are skipped entirely (no LLM call is made), replaced with a hardcoded "Insufficient data" marker to save tokens and prevent hallucination.
    *   Active agents are asked to summarize their specific domain based *only* on the gathered data.
3.  **Phase 3: Grand Synthesis (Act)**
    *   The 4 domain payloads are fed into Agent 5 (Grand Synthesis, running on a heavier model like `gemini-pro`). Agent 5 degrades gracefully, weaving the available data into the final Architecture Specification.

---

## 4. State Management (SQLite & Files)

### The Database (`orchestrator.db`)
*   **Multi-Session Topology:** All data is strictly bound to a `session_id`. The DB utilizes `PRAGMA foreign_keys = ON`. Deleting a session via `DELETE FROM sessions` triggers `ON DELETE CASCADE`, cleanly wiping all associated `conversations` and `routing_logs`.
*   **KV Config Store:** A generic `config` table stores application-wide settings (e.g., `router_model`, specific agent temperatures, and the full synced string of `models.json`).

### File Caching Mechanics
*   **`models.json` Sync:** On boot, `app.py` loads `models.json` and writes it to the `config` table. Edits via the Settings UI write back to both the DB and the file simultaneously.
*   **Prompt Caching:** To avoid reading `.md` files from disk 4+ times during Phase 2 Extraction, `agent.py` caches prompt contents in a dictionary. When a prompt is updated via the UI, `app.py` triggers `invalidate_prompt_cache()` to ensure the next run reads the fresh file.