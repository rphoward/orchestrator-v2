import os
from flask import Flask, request, jsonify, send_from_directory

# Load environment variables manually if python-dotenv isn't guaranteed
from dotenv import load_dotenv
load_dotenv()

from Infrastructure.Repositories.SQLiteSessionRepository import SQLiteSessionRepository
from Domain.Discovery.OODALoop import ExecutionLoop

app = Flask(__name__, static_folder="static")

# The Server (Roof)
# Wires the HTTP boundary to the new Swarm Dispatcher and OODA+S loop.
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

# ── Mocking V1 Endpoints for UI Compatibility ──

@app.route("/api/sessions", methods=["GET"])
def api_get_sessions():
    sessions = repository.get_all()
    # Map V2 Domain Entities back to the V1 dictionary format the UI expects
    result = [
        {
            "id": s.id,
            "name": f"Session {s.id}", # Use the int ID
            "created_at": "Just now",
            "updated_at": "Just now"
        } for s in sessions
    ]
    return jsonify(result)

@app.route("/api/sessions", methods=["POST"])
def api_create_session():
    # Pass 0 to create a new session; repository will auto-increment and update the id
    response_text = loop.process_input(0, "Hello, I want to build a startup.")

    # We must retrieve the newly created session to get its actual integer ID.
    # Since we don't return the ID from loop.process_input, we'll fetch the latest from the DB.
    # A cleaner V2 way would be to return the (session_id, response_text) tuple.
    sessions = repository.get_all()
    new_session = sessions[-1] if sessions else None

    if new_session:
        return jsonify({"id": new_session.id, "name": f"Session {new_session.id}"})
    return jsonify({"error": "Failed to create session"}), 500

@app.route("/api/sessions/<int:session_id>", methods=["DELETE"])
def api_delete_session(session_id):
    repository.delete(session_id)
    return jsonify({"status": "ok"})

@app.route("/api/sessions/<int:session_id>/initialize", methods=["POST"])
def api_initialize(session_id):
    # The UI expects an object/mapping where keys are agent names/ids and values are string status
    return jsonify({
        "status": "ok",
        "agents": {
            "Swarm Muscle": "Ready",
            "Swarm Brain": "Ready"
        }
    })

@app.route("/api/sessions/<int:session_id>/send", methods=["POST"])
def api_send(session_id):
    data = request.json
    if not data or not data.get("message", "").strip():
        return jsonify({"error": "No message provided", "error_type": "validation_error"}), 400

    msg = data["message"].strip()
    response_text = loop.process_input(session_id, msg)

    # Return mock routing info with exact keys expected by app.js
    return jsonify({
        "status": "success",
        "response": response_text,
        "agent_name": "Swarm Muscle",
        "routing_reason": "V2 OODA+S Loop Active"
    })

@app.route("/api/sessions/<int:session_id>/conversations", methods=["GET"])
def api_get_conversations(session_id):
    session = repository.find_by_id(session_id)
    if not session:
        return jsonify([])

    result = []
    for msg in session.messages:
        result.append({
            "role": "user" if msg.role == "founder" else "agent",
            "content": msg.content,
            "timestamp": "Just now"
        })
    return jsonify(result)

@app.route("/api/sessions/<int:session_id>/routing-logs", methods=["GET"])
def api_routing_logs(session_id):
    return jsonify([
        {"timestamp": "Now", "agent_name": "Swarm Muscle", "reason": "OODA+S Loop Executed"}
    ])

@app.route("/api/sessions/<int:session_id>/finalize", methods=["POST"])
def api_finalize(session_id):
    final_message = "I have nothing else to add. Let's wrap up."

    # True flag routes task to the Brain for grand synthesis
    response_text = loop.process_input(session_id, final_message, is_final=True)

    session = repository.find_by_id(session_id)

    # V1 app.js expects:
    # { "synthesis": "markdown...", "payloads": {"AgentName": "Markdown..."} }
    return jsonify({
        "status": "success",
        "synthesis": session.spec.core_ethos if session and session.spec else "Synthesis complete.",
        "payloads": session.spec.domains if session and session.spec else {}
    })

# The UI requires an /api/agents endpoint to load correctly. We mock it for V2.
@app.route("/api/agents", methods=["GET"])
def api_get_agents():
    return jsonify([
        {"id": 1, "name": "Swarm Muscle (Fast)", "role": "Extraction", "model": "gemini-1.5-flash", "prompt": ""},
        {"id": 2, "name": "Swarm Brain (Deep)", "role": "Synthesis", "model": "gemini-pro", "prompt": ""}
    ])

@app.route("/api/models", methods=["GET"])
def api_get_models():
    return jsonify({"models": [{"id": "gemini-pro", "name": "Gemini Pro"}, {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash"}]})

if __name__ == "__main__":
    app.run(port=5000, debug=True)
