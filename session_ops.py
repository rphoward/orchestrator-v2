"""
session_ops.py — Session Workflow Orchestration (V2)
════════════════════════════════════════════════════
Thin workflow layer between app.py and the Swarm + Repositories.

This is intentionally slim. It coordinates the "what happens when"
but doesn't own business logic (that's in the domain entities) or
persistence logic (that's in the repositories) or AI logic (that's
in the Swarm agents/dispatcher).

WHO CALLS ME:
  - app.py → route_and_send, send_manual, initialize_agents, finalize_session

WHAT I IMPORT:
  - Infrastructure.Swarm.dispatcher → get_dispatcher() (cached)
  - Infrastructure.repositories     → session & agent repos
  - database                        → get_conversation, save_message, etc.
                                      (still used for message-level ops
                                       that don't need the full aggregate)
  - errors                          → typed error classes

NOTE ON database.py:
  We still import from database.py for fine-grained message operations
  (save_message, get_conversation, get_recent_global_context, save_routing_log).
  The repositories handle session-level aggregate operations.
  This is the "hybrid DDD" — not strict, but the domain entities and
  repositories handle the structural stuff while database.py handles
  the granular CRUD that doesn't warrant full aggregate rehydration.
"""

from Infrastructure.Swarm.dispatcher import get_dispatcher
from database import (
    get_agents, get_agent, get_conversation,
    get_recent_global_context, save_message, save_routing_log
)
from errors import (
    OrchestratorError, RoutingError, APIKeyError, RateLimitError,
    ModelError, AgentNotFoundError, AIResponseError
)


# ── Shared Constants ─────────────────────────────────────────────

COACH_PERSONA = (
    "You are helping a friendly, approachable business consultant who "
    "works with small business owners — not corporate executives. Keep "
    "the vibe warm, professional, and encouraging."
)


# ── Workflow: Route and Send (Auto-Route) ────────────────────────

def route_and_send(session_id, user_input):
    """
    The main auto-routing workflow.

    1. Route: Ask the dispatcher which agent should handle this input
    2. Log:   Record the routing decision
    3. Send:  Execute the selected agent with conversation history
    4. Save:  Persist both the user message and agent response

    Error strategy:
      - Routing errors → fall back to Agent 1 (conversation must not stall)
      - API key / rate limit errors → bubble up (can't recover)
      - Agent errors → bubble up to app.py for proper HTTP response
    """
    dispatcher = get_dispatcher()

    # Step 1: Route
    try:
        routing = dispatcher.route(user_input)
    except (APIKeyError, RateLimitError, ModelError):
        # Infrastructure problems — can't recover
        raise
    except RoutingError:
        routing = {"id": 1, "reason": "Default routing (router unavailable)"}
    except OrchestratorError:
        routing = {"id": 1, "reason": "Default routing (error)"}

    agent_id = routing["id"]
    agent = dispatcher.get_agent(agent_id)

    if not agent:
        # Fallback if somehow the agent isn't in the dispatcher
        agent_id = 1
        agent = dispatcher.get_agent(1)
        routing["reason"] = f"Fallback — agent {routing['id']} not found"

    # Step 2: Log the routing decision
    save_routing_log(
        session_id, user_input, agent_id,
        agent.name, routing["reason"]
    )

    # Step 3: Load history and cross-agent context
    history = get_conversation(session_id, agent_id)
    cross_agent_context = get_recent_global_context(
        session_id, exclude_agent_id=agent_id, limit=6
    )

    # Step 4: Save user message BEFORE the API call
    save_message(session_id, agent_id, "user", user_input, "chat")

    # Step 5: Execute the agent
    reply = agent.execute(
        user_input,
        history=history,
        cross_agent_context=cross_agent_context,
        message_type="chat"
    )

    # Step 6: Save the agent's response
    save_message(session_id, agent_id, "model", reply, "chat")

    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "routing_reason": routing["reason"],
        "response": reply
    }


# ── Workflow: Manual Send ────────────────────────────────────────

def send_manual(session_id, agent_id, user_input):
    """
    Direct send to a specific agent (user chose manually).
    Lets all typed errors bubble up to app.py.
    """
    dispatcher = get_dispatcher()
    agent = dispatcher.get_agent(agent_id)

    if not agent:
        raise AgentNotFoundError(f"Agent {agent_id} not found")

    # Load history and context
    history = get_conversation(session_id, agent_id)
    cross_agent_context = get_recent_global_context(
        session_id, exclude_agent_id=agent_id, limit=6
    )

    # Save user message
    save_message(session_id, agent_id, "user", user_input, "chat")

    # Execute
    reply = agent.execute(
        user_input,
        history=history,
        cross_agent_context=cross_agent_context,
        message_type="chat"
    )

    # Save response
    save_message(session_id, agent_id, "model", reply, "chat")

    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "response": reply
    }


# ── Workflow: Initialize Session ─────────────────────────────────

def initialize_agents(session_id):
    """
    Sends opening message to each domain agent (not the synthesizer).
    Catches per-agent errors so one failing agent doesn't block the others.

    HARDENING: If a rate limit is hit, stop calling remaining agents
    (they'll fail too). Mark them as skipped.
    """
    dispatcher = get_dispatcher()
    muscle_agents = dispatcher.get_muscle_agents()
    results = {}
    rate_limited = False

    init_message = (
        f"{COACH_PERSONA}\n\n"
        "Begin the session. Provide your opening output using your "
        "required format, including your first suggested question "
        "for the consultant to ask the founder."
    )

    for agent_id in sorted(muscle_agents.keys()):
        agent = muscle_agents[agent_id]

        if rate_limited:
            results[agent_id] = (
                "⚠️ Skipped — rate limit hit on a previous agent. "
                "Wait a moment and create a new session."
            )
            continue

        try:
            # No history for init — fresh conversation
            reply = agent.execute(
                init_message,
                history=None,
                cross_agent_context=None,
                message_type="init"
            )

            # Save both the init message and response
            save_message(session_id, agent_id, "user", init_message, "init")
            save_message(session_id, agent_id, "model", reply, "init")

            results[agent_id] = reply

        except APIKeyError:
            # No API key = ALL agents will fail. Don't re-raise —
            # instead, report the error for this agent and skip the rest.
            # This lets the UI still transition to the conversation view
            # with error messages visible, which matters during dev.
            results[agent_id] = (
                "⚠️ GEMINI_API_KEY is not set. Check your .env file."
            )
            rate_limited = True  # Skip remaining agents (they'd fail too)
        except RateLimitError:
            results[agent_id] = (
                "⚠️ Rate limit reached. Wait a moment and try again."
            )
            rate_limited = True
        except ModelError as e:
            results[agent_id] = (
                f"⚠️ Model error — check Model Registry. ({e})"
            )
        except OrchestratorError as e:
            results[agent_id] = f"⚠️ Failed to initialize: {e}"
        except Exception as e:
            results[agent_id] = f"⚠️ Unexpected error: {str(e)}"

    return results


# ── Workflow: Finalize Session ───────────────────────────────────

def finalize_session(session_id, force=False):
    """
    The grand finale. Three phases:

    Phase 1: Pre-flight Audit
      Check that each agent has at least one user chat message.
      If not (and force=False), return a warning so the frontend
      can show the triage modal.

    Phase 2: Extraction
      Ask each agent to summarize their findings.

    Phase 3: Grand Synthesis
      Feed all payloads to the Brain agent for the final spec.
    """
    dispatcher = get_dispatcher()
    muscle_agents = dispatcher.get_muscle_agents()
    agents_list = get_agents()  # DB list for iteration order
    payloads = {}
    errors = []

    # Pre-fetch all conversation histories (one DB call per agent)
    agent_histories = {}
    for ag in agents_list:
        agent_histories[ag["id"]] = get_conversation(session_id, ag["id"])

    # ── Phase 1: Pre-flight Audit ──
    if not force:
        sparse_agents = []
        for ag in agents_list:
            history = agent_histories[ag["id"]]
            user_chats = [
                m for m in history
                if m["message_type"] == "chat" and m["role"] == "user"
            ]
            if len(user_chats) < 1:
                sparse_agents.append({"id": ag["id"], "name": ag["name"]})

        if sparse_agents:
            return {"status": "warning", "sparse_agents": sparse_agents}

    # ── Phase 2: Extraction ──
    summary_trigger = (
        "Summarize the findings. Focus strictly on the data gathered so far."
    )
    rate_limited = False

    for ag in agents_list:
        agent_id = ag["id"]
        agent = dispatcher.get_agent(agent_id)
        history = agent_histories[agent_id]

        user_chats = [
            m for m in history
            if m["message_type"] == "chat" and m["role"] == "user"
        ]

        # Skip agents with no conversation data
        if len(user_chats) < 1:
            payloads[agent_id] = (
                f"[{ag['name'].upper()} PAYLOAD]\n"
                "Insufficient data — forced partial report. "
                "No substantive conversation occurred."
            )
            continue

        if rate_limited:
            errors.append(f"{ag['name']}: Skipped — rate limit hit")
            payloads[agent_id] = (
                f"[{ag['name'].upper()} PAYLOAD]\n"
                "Skipped — rate limit hit on a previous agent."
            )
            continue

        if not agent:
            errors.append(f"{ag['name']}: Agent not found in dispatcher")
            payloads[agent_id] = (
                f"[{ag['name'].upper()} PAYLOAD]\n"
                "Agent not available."
            )
            continue

        try:
            reply = agent.execute(
                summary_trigger,
                history=history,
                cross_agent_context=None,
                message_type="summary"
            )
            save_message(session_id, agent_id, "user", summary_trigger, "summary")
            save_message(session_id, agent_id, "model", reply, "summary")
            payloads[agent_id] = reply

        except APIKeyError:
            raise  # Bad key = abort entirely
        except RateLimitError:
            errors.append(f"{ag['name']}: Rate limit — wait and retry")
            payloads[agent_id] = (
                f"[{ag['name'].upper()} PAYLOAD]\n"
                "Rate limit reached during summarization."
            )
            rate_limited = True
        except ModelError as e:
            errors.append(f"{ag['name']}: Model unavailable")
            payloads[agent_id] = (
                f"[{ag['name'].upper()} PAYLOAD]\nModel error: {e}"
            )
        except OrchestratorError as e:
            errors.append(f"{ag['name']}: {e}")
            payloads[agent_id] = (
                f"[{ag['name'].upper()} PAYLOAD]\n"
                f"Error during summarization: {e}"
            )

    # ── Phase 3: Grand Synthesis ──
    if rate_limited:
        synthesis = (
            "⚠️ Synthesis skipped — rate limit was hit during extraction. "
            "Wait a moment and retry finalization."
        )
        errors.append("Grand Synthesis: Skipped due to rate limit")
    else:
        brain = dispatcher.brain

        synthesis_input = (
            "Here are the four discovery payloads from the interview "
            "session. Some may contain insufficient data. Generate the "
            "complete Architecture Specification based on available "
            "information, degrading gracefully where data is missing.\n\n"
        )
        for ag in agents_list:
            synthesis_input += (
                f"--- FROM {ag['name'].upper()} (Agent {ag['id']}) ---\n"
                f"{payloads.get(ag['id'], 'No data.')}\n\n"
            )

        try:
            synthesis = brain.execute(
                synthesis_input,
                history=None,
                cross_agent_context=None,
                message_type="summary"
            )
            save_message(session_id, 5, "user", synthesis_input, "summary")
            save_message(session_id, 5, "model", synthesis, "summary")

        except APIKeyError:
            raise
        except RateLimitError:
            synthesis = (
                "⚠️ Rate limit reached during synthesis. "
                "Wait a moment and retry."
            )
            errors.append("Grand Synthesis: Rate limit")
        except OrchestratorError as e:
            synthesis = f"⚠️ Synthesis failed: {e}"
            errors.append(f"Grand Synthesis: {e}")

    return {
        "status": "success",
        "payloads": payloads,
        "synthesis": synthesis,
        "errors": errors
    }
