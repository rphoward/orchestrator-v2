"""
errors.py - Custom Exception Classes
═════════════════════════════════════
LAYER 1 — no imports from our code (sits alongside database.py)

WHO IMPORTS ME:
  - Every module raises these errors
  - app.py catches them and maps to HTTP status codes

WHY THIS EXISTS:
  Before this, every error was a generic Exception turned into a string
  like "⚠️ AI Error: <something>". The frontend couldn't tell the
  difference between "your API key expired" and "the model name is wrong."

  Now each module raises a SPECIFIC error type. app.py catches it,
  knows exactly what went wrong, and returns a clear message + the
  right HTTP status code. The frontend can show helpful, actionable
  messages instead of cryptic dumps.

USAGE PATTERN:
  In a module:
      from errors import ModelError
      raise ModelError("gemini-3.1-flash-lite-preview is deprecated")

  In app.py:
      try:
          result = route_and_send(session_id, msg)
      except ModelError as e:
          return jsonify({"error": str(e), "error_type": "model_error"}), 502
"""


class OrchestratorError(Exception):
    """
    Base class for all Orchestrator errors.
    Every custom error below inherits from this, so app.py can catch
    OrchestratorError to handle ALL our custom errors in one block,
    or catch a specific subclass for targeted handling.
    """
    pass


class APIKeyError(OrchestratorError):
    """
    The Gemini API key is missing, invalid, or expired.
    Typical trigger: 401/403 from the Gemini API.
    Frontend should tell the user to check their .env file.
    """
    pass


class ModelError(OrchestratorError):
    """
    Something wrong with the model itself — deprecated, not found,
    or returned an unexpected response format.
    Frontend should tell the user to check the Model Registry.
    """
    pass


class AgentNotFoundError(OrchestratorError):
    """
    The requested agent_id doesn't exist in the database.
    Shouldn't happen in normal use — indicates a bug or bad request.
    """
    pass


class RateLimitError(OrchestratorError):
    """
    The Gemini API returned a rate limit / quota error.
    Frontend should tell the user to wait and retry.
    """
    pass


class AIResponseError(OrchestratorError):
    """
    The Gemini API call succeeded but returned something unusable —
    empty response, malformed JSON from router, safety filter block, etc.
    """
    pass


class RoutingError(OrchestratorError):
    """
    The router failed to classify the input.
    The system will fall back to Agent 1, but this signals the router
    model may need attention.
    """
    pass


class ValidationError(OrchestratorError):
    """
    Input validation failed — message too long, missing required fields,
    invalid parameter values, path traversal attempt, etc.
    """
    pass
