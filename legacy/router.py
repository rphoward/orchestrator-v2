"""
router.py - Input Routing Engine
═════════════════════════════════
LAYER 3 — sits on top of model_registry.py, errors.py

WHO CALLS ME:
  - session_ops.py → route_input()

WHAT I IMPORT:
  - model_registry.py → get_router_model(), get_model_config()
  - errors.py         → RoutingError, APIKeyError, RateLimitError, ModelError
  - google.genai      → Gemini API client

REFACTOR #3: Typed Errors
  The router still defaults to Agent 1 on failure (the conversation must
  never stall), but now it raises SPECIFIC errors that session_ops.py
  can log or surface to the user, instead of burying everything in a
  generic string.
"""

import os
import json
from google import genai
from google.genai import types
from model_registry import get_router_model, get_model_config
from errors import RoutingError, APIKeyError, RateLimitError, ModelError

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

ROUTING_DIRECTIVE = """You are an interview routing engine. Analyze the consultant's input and determine which specialized agent should handle it.

AGENTS AND THEIR DOMAINS:
Agent 1 - BRAND SPINE: Identity, purpose, culture, employee behavior, differentiation, competition.
Agent 2 - FOUNDER INVARIANTS: Absolute rules, boundaries, constraints, past failures, compliance.
Agent 3 - CUSTOMER REALITY: Why customers buy, their struggles, workarounds, success metrics.
Agent 4 - ARCHITECTURE TRANSLATION: Operational processes, terminology, step-by-step workflows.

RULES:
- If the input is a greeting or general opener, route to Agent 1 (Brand Spine).
- Respond with ONLY a JSON object: {"id": <number>, "reason": "<brief explanation>"}
"""


def _classify_api_error(e):
    """
    Inspects a Gemini API exception and returns the appropriate
    typed error. This keeps the classification logic in one place.
    
    The google-genai SDK raises different exception types, but they
    all have string representations we can inspect for common patterns.
    """
    error_str = str(e).lower()
    
    if "api key" in error_str or "401" in error_str or "403" in error_str:
        return APIKeyError(f"Gemini API key error: {e}")
    
    if "quota" in error_str or "rate" in error_str or "429" in error_str:
        return RateLimitError(f"Gemini rate limit hit: {e}")
    
    if "not found" in error_str or "404" in error_str or "deprecated" in error_str:
        return ModelError(f"Model not available: {e}")
    
    # Default: it's a routing-specific error
    return RoutingError(f"Router classification failed: {e}")


def route_input(user_input):
    """
    Takes a founder's statement and returns which agent should handle it.
    
    Returns: {"id": 1-4, "reason": "brief explanation"}
    
    Error behavior:
      - JSON parse failures → defaults to Agent 1 with reason
      - API errors → raises typed error (APIKeyError, RateLimitError, etc.)
        BUT session_ops.py catches these and still defaults to Agent 1,
        while also surfacing the error type to the frontend.
    """
    model_name = get_router_model()
    config_kwargs = {
        "response_mime_type": "application/json",
        "temperature": 0.1
    }

    model_config = get_model_config(model_name)
    if model_config and model_config.get("supports_thinking"):
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.MINIMAL
        )

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[{
                "role": "user",
                "parts": [{"text": f"{ROUTING_DIRECTIVE}\n\nConsultant's input: \"{user_input}\""}]
            }],
            config=types.GenerateContentConfig(**config_kwargs)
        )
    except Exception as e:
        # Classify the API error into our typed system
        raise _classify_api_error(e)

    # Parse the router's JSON response
    try:
        decision = json.loads(response.text)
        agent_id = int(decision.get("id", 1))
    except (json.JSONDecodeError, ValueError, TypeError):
        # Router returned garbage — default to Agent 1 but don't crash
        return {"id": 1, "reason": "Default routing (unparseable router response)"}

    if agent_id < 1 or agent_id > 4:
        agent_id = 1

    return {
        "id": agent_id,
        "reason": decision.get("reason", "Routed by AI")
    }
