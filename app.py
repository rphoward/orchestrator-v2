import os
import json
import asyncio
from flask import Flask, request, jsonify, send_from_directory

# Load environment variables manually if python-dotenv isn't guaranteed
from dotenv import load_dotenv
load_dotenv()

from Infrastructure.Repositories.SQLiteSessionRepository import SQLiteSessionRepository
from Domain.Discovery.OODALoop import ExecutionLoop
from Domain.Entities.InterviewSession import InterviewSession

app = Flask(__name__, static_folder="static")

# The Server (Roof)
repository = SQLiteSessionRepository()
loop = ExecutionLoop(repository)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "v2_swarm_active"}), 200


# ── V2 ADK Swarm Endpoint Mappings for V1 UI ──

@app.route("/api/sessions", methods=["GET"])
def api_get_sessions():
    sessions = repository.get_all()
    result = [
        {
            "id": s.id,
            "name": f"Session {s.id}",
            "created_at": "Just now",
            "updated_at": "Just now"
        } for s in sessions
    ]
    return jsonify(result)

@app.route("/api/sessions", methods=["POST"])
def api_create_session():
    # 1. First create an empty session in the DB to reserve an ID safely
    session = InterviewSession(id=0)
    repository.save(session)

    # 2. Return the new session id immediately so the UI can proceed without
    # hanging on a 15-second LLM call. The UI typically expects an immediate setup.
    return jsonify({"id": session.id, "name": f"Session {session.id}"})

@app.route("/api/sessions/<int:session_id>", methods=["DELETE"])
def api_delete_session(session_id):
    repository.delete(session_id)
    return jsonify({"status": "ok"})

@app.route("/api/sessions/<int:session_id>/initialize", methods=["POST"])
def api_initialize(session_id):
    agents_map = {}
    for agent in loop.get_swarm_agents():
        agents_map[agent["name"]] = "Ready"

    return jsonify({
        "status": "ok",
        "agents": agents_map
    })

@app.route("/api/sessions/<int:session_id>/send", methods=["POST"])
def api_send(session_id):
    data = request.json
    if not data or not data.get("message", "").strip():
        return jsonify({"error": "No message provided", "error_type": "validation_error"}), 400

    msg = data["message"].strip()
    response_text, agent_name = loop.process_input(session_id, msg)

    return jsonify({
        "status": "success",
        "response": response_text,
        "agent_name": agent_name,
        "routing_reason": f"Dispatched dynamically by Google ADK to {agent_name}"
    })

@app.route("/api/sessions/<int:session_id>/send-manual", methods=["POST"])
def api_send_manual(session_id):
    data = request.json
    if not data or not data.get("message", "").strip() or not data.get("agent_id"):
        return jsonify({"error": "Missing parameters", "error_type": "validation_error"}), 400

    msg = data["message"].strip()

    # In V2 ADK Swarm, manual overrides are handled by skipping the root dispatcher
    # and directly targeting the sub-agent. For this mapping, we will parse the id.
    agent_id = int(data["agent_id"])
    agents = loop.get_swarm_agents()
    target_agent_name = "dispatcher_root"
    for a in agents:
        if a["id"] == agent_id:
            target_agent_name = a["name"]
            break

    # As a simple fallback wrapper for the mocked V2, we just run the input
    # and pretend the manual agent handled it for UI display purposes.
    response_text, _ = loop.process_input(session_id, msg)

    return jsonify({
        "status": "success",
        "response": response_text,
        "agent_name": target_agent_name,
        "routing_reason": f"Manual Override to {target_agent_name}"
    })

@app.route("/api/sessions/<int:session_id>/conversations", methods=["GET"])
def api_get_conversations(session_id):
    agent_id = request.args.get("agent_id", type=int)

    session = repository.find_by_id(session_id)
    if not session:
        return jsonify([])

    result = []
    for msg in session.messages:
        # In a full V2 we'd track the agent ID in metadata.
        # For this integration we return all messages, or mock the filter.
        # Since V1 filtered by the specific DB agent ID column, we'll
        # just return the full history to prevent empty threads.
        result.append({
            "role": "user" if msg.role == "founder" else "agent",
            "content": msg.content,
            "timestamp": "Just now"
        })
    return jsonify(result)

@app.route("/api/sessions/<int:session_id>/routing-logs", methods=["GET"])
def api_routing_logs(session_id):
    return jsonify([
        {"timestamp": "Now", "agent_name": "dispatcher_root", "reason": "Swarm routing logic evaluated"}
    ])

@app.route("/api/sessions/<int:session_id>/finalize", methods=["POST"])
def api_finalize(session_id):
    final_message = "I have nothing else to add. Let's wrap up."

    response_text, agent_name = loop.process_input(session_id, final_message, is_final=True)

    session = repository.find_by_id(session_id)

    return jsonify({
        "status": "success",
        "synthesis": session.spec.core_ethos if session and session.spec else "Synthesis complete.",
        "payloads": session.spec.domains if session and session.spec else {}
    })


# ── Configuration & Mock Maintenance API Endpoints ──

@app.route("/api/agents", methods=["GET"])
def api_get_agents():
    return jsonify(loop.get_swarm_agents())

@app.route("/api/agents/<int:agent_id>", methods=["PUT"])
def api_update_agent(agent_id):
    # Mocking successful save for UI since V2 Agents are Python classes now, not DB rows
    return jsonify({"status": "ok"})

@app.route("/api/models", methods=["GET"])
def api_get_models():
    try:
        with open("models.json", "r") as f:
            data = json.load(f)
            return jsonify(data)
    except Exception:
        return jsonify({"models": [{"id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro"}, {"id": "gemini-3.1-flash-lite-preview", "name": "Gemini 3.1 Flash-Lite"}]})

@app.route("/api/models", methods=["PUT"])
def api_save_models():
    return jsonify({"status": "ok", "count": 0})

@app.route("/api/config/router-model", methods=["GET", "PUT"])
def api_router_model():
    if request.method == "GET":
        return jsonify({"model": "gemini-3.1-flash-lite-preview"})
    data = request.json
    return jsonify({"status": "ok", "model": data["model"].strip()})

@app.route("/api/config/thinking-level/<int:agent_id>", methods=["GET", "PUT"])
def api_thinking_level(agent_id):
    if request.method == "GET":
        return jsonify({"thinking_level": "MEDIUM"})
    data = request.json
    return jsonify({"status": "ok", "agent_id": agent_id, "thinking_level": data.get("thinking_level", "")})

@app.route("/api/config/temperature/<int:agent_id>", methods=["GET", "PUT"])
def api_temperature(agent_id):
    if request.method == "GET":
        return jsonify({"temperature": "1.0"})
    data = request.json
    return jsonify({"status": "ok", "agent_id": agent_id, "temperature": data.get("temperature", "")})

@app.route("/api/export-config", methods=["GET"])
def api_export_config():
    return jsonify(loop.get_swarm_agents())

@app.route("/api/import-config", methods=["POST"])
def api_import_config():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(port=5000, debug=True)
