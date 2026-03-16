"""
app.py - Interview Orchestrator Web Server
═══════════════════════════════════════════
LAYER 5 (the roof) — Flask routes, HTTP ↔ logic.

REFACTOR #3: Typed Error Handling
  Orchestration endpoints now catch specific error types and return
  appropriate HTTP status codes with an 'error_type' field the
  frontend can use to show targeted messages:
    - APIKeyError    → 401 + "api_key_error"
    - RateLimitError → 429 + "rate_limit_error"  
    - ModelError     → 502 + "model_error"
    - AgentNotFoundError → 404 + "agent_not_found"
    - ValidationError → 400 + "validation_error"
    - OrchestratorError → 500 + "orchestrator_error" (catch-all)

REFACTOR #5: Prompt Cache Invalidation
  When a prompt is saved through Settings, app.py calls
  invalidate_prompt_cache() so the next agent call picks up
  the new prompt from disk instead of using the stale cache.
"""

import os
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

# ── Layer 1: Database ─────────────────────────────────────────────
from database import (
    init_db, seed_agents,
    get_agents, get_all_agents, get_agent, update_agent,
    get_conversation, get_all_conversations, get_routing_logs,
    export_config, import_config,
    create_session, get_sessions, delete_session, get_session, update_session
)

# ── Layer 1: Errors ───────────────────────────────────────────────
from errors import (
    OrchestratorError, APIKeyError, RateLimitError,
    ModelError, AgentNotFoundError, ValidationError, AIResponseError
)

# ── Layer 2: Model Registry ──────────────────────────────────────
from model_registry import (
    load_model_registry_from_file, get_model_registry, save_model_registry,
    get_router_model, set_router_model,
    get_thinking_level, set_thinking_level,
    get_temperature, set_temperature
)

# ── Layer 3: Agent Communication ──────────────────────────────────
# (Legacy imports removed)

# ── Layer 4: Session Workflows ────────────────────────────────────
import asyncio
from Infrastructure.repositories import SQLiteSessionRepository, SQLiteAgentRepository
from Infrastructure.Swarm.agents import DomainAgent
from Infrastructure.Swarm.dispatcher import SwarmDispatcher

# Initialize Repositories and Swarm
session_repo = SQLiteSessionRepository()
agent_repo = SQLiteAgentRepository()

def _build_dispatcher():
    """Lazily load agents with current prompts from the repository."""
    agents_dict = {}
    for a in agent_repo.get_all():
        if not a.is_synthesizer:
            prompt = agent_repo.get_system_prompt_for_agent(a.id)
            # Ensure name is a valid python identifier for ADK
            clean_name = a.name.lower().replace(" ", "_")
            agents_dict[a.id] = DomainAgent(agent_id=a.id, name=clean_name, system_prompt=prompt, model_id=a.model)
    return SwarmDispatcher(agents=agents_dict)


app = Flask(__name__, static_folder="static")

# ── Validation Constants ──────────────────────────────────────────
MAX_MESSAGE_LENGTH = 10_000
PROMPTS_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "prompts"))


# ── Typed Error → HTTP Response Mapping ───────────────────────────
# This is the core of #3. Instead of a generic "except Exception",
# each error type maps to a specific HTTP status code and a machine-
# readable error_type the frontend can use for conditional UI.

def error_response(e):
    """
    Maps a typed OrchestratorError to the right HTTP response.
    Returns (json_response, status_code).
    
    The frontend receives:
      {"error": "human message", "error_type": "machine_type"}
    
    error_type lets the frontend show contextual help:
      - "api_key_error" → "Check your .env file"
      - "rate_limit_error" → "Wait and retry"
      - "model_error" → "Check Model Registry"
    """
    if isinstance(e, APIKeyError):
        return jsonify({"error": str(e), "error_type": "api_key_error"}), 401
    
    if isinstance(e, RateLimitError):
        return jsonify({"error": str(e), "error_type": "rate_limit_error"}), 429
    
    if isinstance(e, ModelError):
        return jsonify({"error": str(e), "error_type": "model_error"}), 502
    
    if isinstance(e, AgentNotFoundError):
        return jsonify({"error": str(e), "error_type": "agent_not_found"}), 404
    
    if isinstance(e, ValidationError):
        return jsonify({"error": str(e), "error_type": "validation_error"}), 400
    
    if isinstance(e, AIResponseError):
        return jsonify({"error": str(e), "error_type": "ai_response_error"}), 502
    
    # Catch-all for any OrchestratorError subclass we didn't handle
    if isinstance(e, OrchestratorError):
        return jsonify({"error": str(e), "error_type": "orchestrator_error"}), 500
    
    # Truly unknown error
    return jsonify({"error": str(e), "error_type": "unknown_error"}), 500


@app.route("/")
def index(): return send_from_directory("static", "index.html")

@app.route("/static/<path:filename>")
def serve_static(filename): return send_from_directory("static", filename)


# ── Session API ──────────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def api_get_sessions():
    return jsonify(get_sessions())

@app.route("/api/sessions", methods=["POST"])
def api_create_session():
    data = request.json or {}
    name = data.get("name", f"Interview {datetime.now().strftime('%b %d, %H:%M')}")
    session_id = create_session(name)
    return jsonify({"id": session_id, "name": name})

@app.route("/api/sessions/<int:session_id>", methods=["DELETE"])
def api_delete_session(session_id):
    delete_session(session_id)
    return jsonify({"status": "ok"})


# ── Orchestration API ─────────────────────────────────────────────

@app.route("/api/sessions/<int:session_id>/send", methods=["POST"])
def api_send(session_id):
    data = request.json
    if not data or not data.get("message", "").strip():
        return jsonify({"error": "No message provided", "error_type": "validation_error"}), 400

    msg = data["message"].strip()

    if len(msg) > MAX_MESSAGE_LENGTH:
        return jsonify({
            "error": f"Message too long. Maximum {MAX_MESSAGE_LENGTH} characters.",
            "error_type": "validation_error"
        }), 400

    try:
        # Load Aggregate Root
        session = session_repo.get_by_id(session_id)
        if not session:
             return jsonify({"error": "Session not found", "error_type": "validation_error"}), 404

        # Route and Send using V2 Swarm Dispatcher
        dispatcher = _build_dispatcher()
        result = asyncio.run(dispatcher.process_input(session, msg))
        
        # Smart Session Renaming
        if session.name.startswith("Interview "):
            new_title = msg[:25] + ("..." if len(msg) > 25 else "")
            session.name = new_title
            result["session_renamed"] = new_title
            
        # Save mutated Aggregate Root
        session_repo.save(session)

        return jsonify(result)
    except OrchestratorError as e:
        return error_response(e)
    except Exception as e:
        return jsonify({"error": str(e), "error_type": "unknown_error"}), 500

@app.route("/api/sessions/<int:session_id>/send-manual", methods=["POST"])
def api_send_manual(session_id):
    data = request.json
    if not data or not data.get("message", "").strip() or not data.get("agent_id"):
        return jsonify({"error": "Missing parameters", "error_type": "validation_error"}), 400

    msg = data["message"].strip()
    agent_id = data["agent_id"]

    if len(msg) > MAX_MESSAGE_LENGTH:
        return jsonify({
            "error": f"Message too long. Maximum {MAX_MESSAGE_LENGTH} characters.",
            "error_type": "validation_error"
        }), 400

    try:
        session = session_repo.get_by_id(session_id)
        if not session:
            return jsonify({"error": "Session not found", "error_type": "validation_error"}), 404

        dispatcher = _build_dispatcher()
        agent = dispatcher.muscle_agents.get(agent_id)
        if not agent:
            return jsonify({"error": f"Agent {agent_id} not found", "error_type": "agent_not_found"}), 404

        history = session.messages[-5:] if session.messages else []

        # Async invocation
        response = asyncio.run(agent.generate_response(msg, history=history))

        session.add_message(agent_id=agent_id, role="user", content=msg)
        session.add_message(agent_id=agent_id, role="assistant", content=response)
        session_repo.save(session)

        return jsonify({
            "agent_id": agent_id,
            "agent_name": agent.name,
            "response": response
        })
    except OrchestratorError as e:
        return error_response(e)
    except Exception as e:
        return jsonify({"error": str(e), "error_type": "unknown_error"}), 500

@app.route("/api/sessions/<int:session_id>/initialize", methods=["POST"])
def api_initialize(session_id):
    """
    Sends the opening instruction to all active Muscle Agents.
    """
    try:
        session = session_repo.get_by_id(session_id)
        if not session:
             return jsonify({"error": "Session not found", "error_type": "validation_error"}), 404

        dispatcher = _build_dispatcher()
        results = {}

        init_message = (
            "You are helping a friendly, approachable business consultant who works "
            "with small business owners — not corporate executives. Keep the vibe warm, professional, "
            "and encouraging.\n\n"
            "Begin the session. Provide your opening output using your "
            "required format, including your first suggested question "
            "for the consultant to ask the founder."
        )

        async def init_all():
            for agent_id, agent in dispatcher.muscle_agents.items():
                try:
                    response = await agent.generate_response(init_message)
                    session.add_message(agent_id=agent_id, role="system", content=init_message, message_type="init")
                    session.add_message(agent_id=agent_id, role="assistant", content=response, message_type="init")
                    results[agent_id] = response
                except Exception as e:
                    results[agent_id] = f"⚠️ Failed to initialize: {e}"

        asyncio.run(init_all())
        session_repo.save(session)

        return jsonify({"status": "ok", "agents": results})
    except OrchestratorError as e:
        return error_response(e)
    except Exception as e:
        return jsonify({"error": str(e), "error_type": "unknown_error"}), 500

@app.route("/api/sessions/<int:session_id>/finalize", methods=["POST"])
def api_finalize(session_id):
    data = request.json or {}
    try:
        session = session_repo.get_by_id(session_id)
        if not session:
             return jsonify({"error": "Session not found", "error_type": "validation_error"}), 404

        dispatcher = _build_dispatcher()
        result = asyncio.run(dispatcher.finalize_session(session, force=data.get("force", False)))
        return jsonify(result)
    except OrchestratorError as e:
        return error_response(e)
    except Exception as e:
        return jsonify({"error": str(e), "error_type": "unknown_error"}), 500

@app.route("/api/sessions/<int:session_id>/conversations", methods=["GET"])
def api_get_conversations(session_id):
    session = session_repo.get_by_id(session_id)
    if not session:
        return jsonify([])

    agent_id = request.args.get("agent_id", type=int)

    # We must match the V1 format for the frontend exactly
    formatted_messages = []
    dispatcher = _build_dispatcher()

    for msg in session.messages:
         if agent_id and msg.agent_id != agent_id:
             continue

         agent = dispatcher.muscle_agents.get(msg.agent_id)
         agent_name = agent.name if agent else f"Agent {msg.agent_id}"

         formatted_messages.append({
             "id": str(msg.id), # UUID to string
             "session_id": session.id,
             "agent_id": msg.agent_id,
             "agent_name": agent_name,
             "role": msg.role,
             "content": msg.content,
             "message_type": msg.message_type,
             "timestamp": msg.timestamp.isoformat()
         })

    return jsonify(formatted_messages)

@app.route("/api/sessions/<int:session_id>/routing-logs", methods=["GET"])
def api_routing_logs(session_id):
    session = session_repo.get_by_id(session_id)
    if not session:
        return jsonify([])

    limit = request.args.get("limit", 20, type=int)

    formatted_logs = []
    # Reverse to show newest first, up to limit
    for log in reversed(session.routing_logs[-limit:]):
        formatted_logs.append({
            "id": str(log.id),
            "session_id": session.id,
            "input_text": log.input_text,
            "agent_id": log.agent_id,
            "agent_name": log.agent_name,
            "reason": log.reason,
            "timestamp": log.timestamp.isoformat()
        })

    return jsonify(formatted_logs)


# ── Model Registry API ────────────────────────────────────────────

@app.route("/api/models", methods=["GET"])
def api_get_models():
    return jsonify(get_model_registry())

@app.route("/api/models", methods=["PUT"])
def api_save_models():
    data = request.json
    if not data or "models" not in data:
        return jsonify({"error": "Expected {\"models\": [...]}", "error_type": "validation_error"}), 400
    
    try:
        save_model_registry(data)
        return jsonify({"status": "ok", "count": len(data["models"])})
    except ValidationError as e:
        return error_response(e)
    except Exception as e:
        return jsonify({"error": str(e), "error_type": "unknown_error"}), 500


# ── Agent Configuration API ───────────────────────────────────────

@app.route("/api/agents", methods=["GET"])
def api_get_agents():
    agents = get_all_agents()
    for agent in agents:
        try:
            with open(os.path.join(PROMPTS_DIR, agent["prompt_file"]), "r", encoding="utf-8") as f:
                agent["prompt"] = f.read()
        except FileNotFoundError: agent["prompt"] = "(Prompt file not found)"
    return jsonify(agents)

@app.route("/api/agents/<int:agent_id>", methods=["PUT"])
def api_update_agent(agent_id):
    data = request.json
    if not data:
        return jsonify({"error": "No data provided", "error_type": "validation_error"}), 400

    update_agent(
        agent_id,
        data.get("name", ""),
        data.get("model", "gemini-3.1-flash-lite-preview")
    )

    if "prompt" in data:
        agent = get_agent(agent_id)
        if agent:
            # Path traversal guard (#7)
            prompt_path = os.path.realpath(
                os.path.join(PROMPTS_DIR, agent["prompt_file"])
            )
            if not prompt_path.startswith(PROMPTS_DIR + os.sep):
                return jsonify({"error": "Invalid prompt file path.", "error_type": "validation_error"}), 400

            # Only write if it's a valid string, to prevent corruption of the prompt file
            if not isinstance(data["prompt"], str):
                 return jsonify({"error": "Prompt must be a string.", "error_type": "validation_error"}), 400

            try:
                with open(prompt_path, "w", encoding="utf-8") as f:
                    f.write(data["prompt"])
                
                # In V2, prompts are loaded directly via SQLiteAgentRepository,
                # so the file write above is sufficient. No cache invalidation needed.
                
            except IOError as e:
                return jsonify({"error": f"Failed to save prompt: {str(e)}", "error_type": "unknown_error"}), 500

    return jsonify({"status": "ok"})

@app.route("/api/config/router-model", methods=["GET", "PUT"])
def api_router_model():
    if request.method == "GET": return jsonify({"model": get_router_model()})
    data = request.json
    if not data or "model" not in data:
        return jsonify({"error": "Missing 'model' field", "error_type": "validation_error"}), 400
    if not isinstance(data["model"], str) or not data["model"].strip():
        return jsonify({"error": "'model' field must be a valid non-empty string", "error_type": "validation_error"}), 400
    set_router_model(data["model"].strip())
    return jsonify({"status": "ok", "model": data["model"].strip()})

@app.route("/api/config/thinking-level/<int:agent_id>", methods=["GET", "PUT"])
def api_thinking_level(agent_id):
    if request.method == "GET": return jsonify({"thinking_level": get_thinking_level(agent_id) or ""})
    
    data = request.json
    if not data:
        return jsonify({"error": "No data provided", "error_type": "validation_error"}), 400
    level = data.get("thinking_level", "")
    
    if level and not isinstance(level, str):
        return jsonify({
             "error": "Invalid thinking level type. Must be a string.",
             "error_type": "validation_error"
        }), 400

    if level and level.upper() not in ("MINIMAL", "LOW", "MEDIUM", "HIGH", ""):
        return jsonify({
            "error": "Invalid thinking level. Use MINIMAL, LOW, MEDIUM, HIGH, or empty.",
            "error_type": "validation_error"
        }), 400
        
    set_thinking_level(agent_id, level)
    return jsonify({"status": "ok", "agent_id": agent_id, "thinking_level": level})

@app.route("/api/config/temperature/<int:agent_id>", methods=["GET", "PUT"])
def api_temperature(agent_id):
    if request.method == "GET":
        return jsonify({"temperature": get_temperature(agent_id) or ""})
    
    data = request.json
    if not data:
        return jsonify({"error": "No data provided", "error_type": "validation_error"}), 400
    
    temp = data.get("temperature", "")
    if temp != "" and temp is not None:
        try:
            temp_float = float(temp)
            if temp_float < 0.0 or temp_float > 2.0:
                return jsonify({"error": "Temperature must be between 0.0 and 2.0", "error_type": "validation_error"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Temperature must be a number", "error_type": "validation_error"}), 400
    
    set_temperature(agent_id, temp)
    return jsonify({"status": "ok", "agent_id": agent_id, "temperature": temp})

@app.route("/api/export-config", methods=["GET"])
def api_export_config():
    agents = get_all_agents()
    for agent in agents:
        try:
            with open(os.path.join(PROMPTS_DIR, agent["prompt_file"]), "r", encoding="utf-8") as f:
                agent["prompt"] = f.read()
        except FileNotFoundError: agent["prompt"] = ""
    return jsonify(agents)

@app.route("/api/import-config", methods=["POST"])
def api_import_config():
    data = request.json
    try:
        import_config(data)
        for ad in data:
            if "prompt" in ad and "prompt_file" in ad:
                path = os.path.realpath(
                    os.path.join(PROMPTS_DIR, ad["prompt_file"])
                )
                if not path.startswith(PROMPTS_DIR + os.sep):
                    continue
                with open(path, "w", encoding="utf-8") as f:
                    f.write(ad["prompt"])
        
        return jsonify({"status": "ok"})
    except Exception as e: return jsonify({"error": str(e), "error_type": "unknown_error"}), 500


# ── Startup ───────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.getenv("GEMINI_API_KEY"): print("⚠️ GEMINI_API_KEY missing!")
    
    init_db()
    seed_agents()
    load_model_registry_from_file()
    
    print("\n🎙️  Interview Orchestrator -> http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
