"""
session_ops.py - Session Workflow Orchestration
════════════════════════════════════════════════
LAYER 4 — sits on top of router.py, agent.py, database.py, errors.py

WHO CALLS ME:
  - app.py → route_and_send, send_manual, initialize_agents, finalize_session

WHAT I IMPORT:
  - router.py   → route_input()
  - agent.py    → send_to_agent()
  - database.py → data operations
  - errors.py   → typed error classes

REFACTOR #3: Typed Error Handling
  Each workflow now handles errors specifically:
  - route_and_send: catches RoutingError and falls back to Agent 1,
    but lets APIKeyError/RateLimitError bubble up to app.py
  - finalize_session: catches per-agent errors and records the type
  - send_manual/initialize: let typed errors bubble up to app.py

  app.py catches OrchestratorError at the top level and returns
  the right HTTP status code + error_type to the frontend.
"""

from router import route_input
from agent import send_to_agent
from database import (
    get_agents, get_agent, get_conversation, save_routing_log
)
from errors import (
    OrchestratorError, RoutingError, APIKeyError, RateLimitError,
    ModelError, AgentNotFoundError, AIResponseError
)


COACH_PERSONA = """You are helping a friendly, approachable business consultant who works
with small business owners — not corporate executives. Keep the vibe warm, professional,
and encouraging."""


# ── Workflow: Route and Send (Auto-Route) ─────────────────────────

def route_and_send(session_id, user_input):
    """
    The main auto-routing workflow.

    Error strategy:
      - Routing errors → fall back to Agent 1 (conversation must not stall)
      - API key / rate limit errors from routing → bubble up (can't do anything)
      - Agent send errors → bubble up to app.py for proper HTTP response
    """
    # Step 1: Route
    try:
        routing = route_input(user_input)
    except (APIKeyError, RateLimitError, ModelError):
        # These are infrastructure problems — can't recover, let app.py handle
        raise
    except RoutingError:
        # Router failed but we can still send to the default agent
        routing = {"id": 1, "reason": "Default routing (router unavailable)"}
    except OrchestratorError:
        routing = {"id": 1, "reason": "Default routing (error)"}

    agent_id = routing["id"]
    agent = get_agent(agent_id)
    agent_name = agent["name"] if agent else "Unknown"

    # Step 2: Log the routing decision
    save_routing_log(session_id, user_input, agent_id, agent_name, routing["reason"])

    # Step 3: Send to agent (let errors bubble up — app.py handles them)
    reply = send_to_agent(session_id, agent_id, user_input)

    return {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "routing_reason": routing["reason"],
        "response": reply
    }


# ── Workflow: Manual Send ─────────────────────────────────────────

def send_manual(session_id, agent_id, user_input):
    """
    Direct send to a specific agent.
    Lets all typed errors bubble up to app.py.
    """
    agent = get_agent(agent_id)
    if not agent:
        raise AgentNotFoundError(f"Agent {agent_id} not found")

    reply = send_to_agent(session_id, agent_id, user_input)

    return {
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "response": reply
    }


# ── Workflow: Initialize Session ──────────────────────────────────

def initialize_agents(session_id):
    """
    Sends opening message to each agent.
    Catches per-agent errors so one failing agent doesn't block the others.

    HARDENING: If a rate limit is hit, stop calling remaining agents
    (they'll fail too). Mark them as skipped so the user sees what happened.
    """
    agents = get_agents()
    results = {}
    rate_limited = False  # Flag to stop wasting calls after a rate limit

    init_message = (
        f"{COACH_PERSONA}\n\n"
        "Begin the session. Provide your opening output using your "
        "required format, including your first suggested question "
        "for the consultant to ask the founder."
    )

    for agent in agents:
        # If we already hit a rate limit, skip remaining agents
        if rate_limited:
            results[agent["id"]] = "⚠️ Skipped — rate limit hit on a previous agent. Wait a moment and create a new session."
            continue

        try:
            results[agent["id"]] = send_to_agent(
                session_id, agent["id"], init_message, message_type="init"
            )
        except APIKeyError as e:
            # API key is bad for ALL agents — no point continuing
            raise
        except RateLimitError as e:
            results[agent["id"]] = "⚠️ Rate limit reached. Wait a moment and try again."
            rate_limited = True  # Stop calling remaining agents
        except ModelError as e:
            results[agent["id"]] = f"⚠️ Model error — check Model Registry. ({e})"
        except OrchestratorError as e:
            results[agent["id"]] = f"⚠️ Failed to initialize: {e}"
        except Exception as e:
            results[agent["id"]] = f"⚠️ Unexpected error: {str(e)}"

    return results


# ── Workflow: Finalize Session ────────────────────────────────────

def finalize_session(session_id, force=False):
    """
    The grand finale. Three phases with typed error handling.

    Per-agent errors during extraction are caught and recorded with
    their specific type, so the frontend can display actionable messages.
    API key errors during extraction abort the entire finalization
    (no point continuing if the key is bad).
    """
    agents = get_agents()
    payloads = {}
    errors = []

    # Fetch all conversations ONCE upfront (#8)
    agent_histories = {}
    for agent in agents:
        agent_histories[agent["id"]] = get_conversation(session_id, agent["id"])

    # Phase 1: Pre-flight Audit
    if not force:
        sparse_agents = []
        for agent in agents:
            history = agent_histories[agent["id"]]
            user_chats = [
                m for m in history
                if m["message_type"] == "chat" and m["role"] == "user"
            ]
            if len(user_chats) < 1:
                sparse_agents.append({"id": agent["id"], "name": agent["name"]})

        if sparse_agents:
            return {"status": "warning", "sparse_agents": sparse_agents}

    # Phase 2: Extraction
    summary_trigger = "Summarize the findings. Focus strictly on the data gathered so far."
    rate_limited = False  # Stop calling after a rate limit hit

    for agent in agents:
        history = agent_histories[agent["id"]]
        user_chats = [
            m for m in history
            if m["message_type"] == "chat" and m["role"] == "user"
        ]

        if len(user_chats) < 1:
            payloads[agent["id"]] = (
                f"[{agent['name'].upper()} PAYLOAD]\n"
                "Insufficient data — forced partial report. "
                "No substantive conversation occurred."
            )
            continue

        if rate_limited:
            errors.append(f"{agent['name']}: Skipped — rate limit hit")
            payloads[agent["id"]] = (
                f"[{agent['name'].upper()} PAYLOAD]\n"
                "Skipped — rate limit hit on a previous agent."
            )
            continue

        try:
            payloads[agent["id"]] = send_to_agent(
                session_id, agent["id"], summary_trigger,
                message_type="summary",
                preloaded_history=history
            )
        except APIKeyError:
            # Bad key = all subsequent calls will also fail — abort
            raise
        except RateLimitError as e:
            errors.append(f"{agent['name']}: Rate limit — wait and retry")
            payloads[agent["id"]] = (
                f"[{agent['name'].upper()} PAYLOAD]\n"
                "Rate limit reached during summarization. Retry shortly."
            )
            rate_limited = True  # Don't waste calls on remaining agents
        except ModelError as e:
            errors.append(f"{agent['name']}: Model unavailable — check registry")
            payloads[agent["id"]] = (
                f"[{agent['name'].upper()} PAYLOAD]\n"
                f"Model error: {e}"
            )
        except OrchestratorError as e:
            errors.append(f"{agent['name']}: {e}")
            payloads[agent["id"]] = (
                f"[{agent['name'].upper()} PAYLOAD]\n"
                f"Error during summarization: {e}"
            )

    # Phase 3: Grand Synthesis
    # If we were rate limited during extraction, don't waste another call
    if rate_limited:
        synthesis = "⚠️ Synthesis skipped — rate limit was hit during extraction. Wait a moment and retry finalization."
        errors.append("Grand Synthesis: Skipped due to rate limit")
    else:
        synthesis_input = (
            "Here are the four discovery payloads from the interview session. "
            "Some may contain insufficient data. Generate the complete "
            "Architecture Specification based on available information, "
            "degrading gracefully where data is missing.\n\n"
        )
        for agent in agents:
            synthesis_input += (
                f"--- FROM {agent['name'].upper()} (Agent {agent['id']}) ---\n"
                f"{payloads.get(agent['id'], 'No data.')}\n\n"
            )

        try:
            synthesis = send_to_agent(session_id, 5, synthesis_input, message_type="summary")
        except APIKeyError:
            raise
        except RateLimitError:
            synthesis = "⚠️ Rate limit reached during synthesis. Wait a moment and retry finalization."
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
