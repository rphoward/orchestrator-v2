# Orchestrator v2: Architectural Vision

This document outlines the evolutionary leap from the Interview Orchestrator's current 5-Layer N-Tier architecture (v1) toward a **Domain-Driven Design (DDD)** and **Autonomous Swarm** architecture (v2).

While v1 relies on a rigid, downward-flowing dependency model centralized around a database, v2 shifts the focus entirely to the Business Domain and utilizes OODA+S methodologies.

---

## 1. Core Ethos: Domain-Driven Design (DDD)

In v1, the database (`database.py`) was "The Ground"—Layer 1. Everything depended on it. In v2, the database is merely an I/O implementation detail.

*   **The Domain Center:** The core of the application will be pure Python Domain Entities (e.g., `InterviewSession`, `Founder`, `ArchitecturalSpec`). These entities own their business logic and protect their own invariants.
*   **Screaming Architecture:** File structures will no longer be named by technical function (`router.py`, `agent.py`). Instead, they will scream the business intent:
    *   `Domain/Discovery/`
    *   `Domain/Synthesis/`
    *   `Infrastructure/Repositories/`
    *   `Infrastructure/LLMClients/`
*   **The Repository Pattern:** Workflows will never write SQL directly. They will interact with a `SessionRepository` interface, allowing us to swap SQLite for Postgres or an in-memory mock seamlessly.

---

## 2. The Engine Topology (Swarm Architecture)

Borrowing from the Architect27 Master Template, the Orchestrator's rigid router will evolve into a dynamic swarm.

1.  **Dispatcher (The Swarm Router):** Replaces the static `router.py`. It doesn't just pick a 1-to-4 path; it acts as a semantic load-balancer, capable of dispatching tasks based on domain need and context depth.
2.  **Brain (Specwriter / Synthesizer):** Replaces Agent 5. Operates on deep, slow, high-thinking models (e.g., `gemini-pro`) to perform the Grand Synthesis phase.
3.  **Muscle (Hydrators / Domain Agents):** Replaces Agents 1-4. Operates on fast models (`flash-lite`) to execute rapid extraction and triaging.
4.  **Memory (Context Compiler):** Replaces the current "last 6 messages JIT injection" with a formal Pseudo-RAG Memory Indexing structure. Conversations are clustered and indexed, allowing agents to retrieve Lisp-nested context dynamically rather than relying on a static string append.

---

## 3. The Execution Loop: OODA+S

The v1 "Route and Send" function will be replaced by a formal **OODA+S** loop to handle founder inputs:

1.  **Observe:** Ingest the founder's statement and read the current `ContextIndex` for the session.
2.  **Orient:** The Dispatcher navigates the session's memory tree to load ONLY the necessary context (preventing context bloat).
3.  **Decide:** The Brain determines which domain (Brand Spine, Customer Reality, etc.) needs to address the input.
4.  **Act:** The Muscle (Domain Agent) executes the prompt and generates the next question for the consultant.
5.  **Sync:** Atomic write-back to the Domain Entity and the Session Repository to prevent memory collisions.

---

## 4. Advanced Tooling & Meta-Mutation

V2 will be built and maintained using advanced AI primitives (located in `v2_planning/prompts/`):

*   **Evolutionary Refactor Engine:** Used during development to guarantee that structural paradigms (like the move to DDD) are mathematically evaluated (Divergence -> Fitness -> Convergence) before implementation, preventing superficial rewrites.
*   **Clinical Incident Responder:** Used for debugging. When the complex swarm architecture exhibits chaotic behavior, this tool forces Cue Clustering and Minimax Triage to stabilize the system without breaking domain invariants.

---

*Note: This document serves as the conceptual blueprint for V2. The current V1 repository remains under the strict maintenance rules defined in `jules.md` and `architecture.md`.*