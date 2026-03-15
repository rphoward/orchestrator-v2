# Global Agent Guidelines (V2 Swarm Architecture)

This document establishes the root "constitutional" guidelines for all Autonomous Swarm Agents within the Interview Orchestrator V2.

## 1. The Swarm Principles

All agents in this repository operate under the **Domain-Driven Design (DDD)** and **Swarm Architecture** ethos.

*   **No Database Dependency:** Agents must never write SQL directly or depend on the database layer. All persistent state must be managed via the `SessionRepository` interface using atomic syncs.
*   **The OODA+S Loop:** Agents must participate in the Observe, Orient, Decide, Act, Sync loop. They do not operate in a vacuum.
*   **Context Discipline:** Agents must not rely on static "last 6 messages" string appends. They must interact with the **Memory (Context Compiler)** to retrieve Lisp-nested context dynamically, loading *only* what is necessary (Orientation).

## 2. Agent Roles

*   **Dispatcher (The Swarm Router):**
    *   **Role:** Semantic load-balancer.
    *   **Responsibility:** Receives the founder input, navigates the session's memory tree, and dispatches to the correct domain (Brain or Muscle) based on context depth.
*   **Brain (Specwriter / Synthesizer):**
    *   **Role:** Deep thinker.
    *   **Responsibility:** Performs the Grand Synthesis phase using deep, slow, high-thinking models (e.g., `gemini-pro`). Focuses on long-term strategy and architectural specification.
*   **Muscle (Hydrators / Domain Agents):**
    *   **Role:** Rapid executor.
    *   **Responsibility:** Performs rapid extraction, triaging, and generates the next question for the consultant using fast models (e.g., `flash-lite`).

## 3. Global-to-Local Inheritance

Following the `gemini.md` coordination rules, these global guidelines apply to all agents. Specific domain folders (e.g., `Domain/Discovery/`, `Domain/Synthesis/`) may contain their own localized `agents.md` files that inherit from this global file.

Local `.md` files can extend or override specific behaviors for their domain but cannot violate the core Swarm Principles (e.g., a local agent cannot suddenly write to the DB directly).
