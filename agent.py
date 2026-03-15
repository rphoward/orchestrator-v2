"""
agent.py - Agent Communication
═══════════════════════════════
LAYER 3 — sits on top of model_registry.py, database.py, errors.py

WHO CALLS ME:
  - session_ops.py → send_to_agent()
  - app.py         → load_prompt(), invalidate_prompt_cache()

WHAT I IMPORT:
  - model_registry.py → model config helpers
  - database.py       → conversation operations
  - errors.py         → typed error classes
  - google.genai      → Gemini API client

REFACTOR #3: Typed Errors
  send_to_agent() now raises specific errors (APIKeyError, RateLimitError,
  ModelError, AgentNotFoundError) instead of returning "⚠️ AI Error: ..."
  strings. The caller (session_ops.py) decides how to handle each type.

REFACTOR #5: Prompt Caching
  System prompts are loaded from disk ONCE and cached in a dict.
  Subsequent calls use the cached version. The cache is invalidated
  when a prompt is saved through the Settings UI (app.py calls
  invalidate_prompt_cache()). This eliminates redundant disk reads —
  especially during finalization which calls send_to_agent() 5 times.
"""

import os
from google import genai
from google.genai import types
from model_registry import (
    get_model_config, get_default_model,
    get_thinking_level, get_temperature
)
from database import (
    get_agent, get_conversation, get_recent_global_context, save_message
)
from errors import (
    AgentNotFoundError, APIKeyError, RateLimitError,
    ModelError, AIResponseError
)

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# ── Prompt Cache (#5) ─────────────────────────────────────────────
# A simple dict mapping filename → prompt text.
# Loaded on first access, invalidated when prompts are edited.

_prompt_cache = {}

def load_prompt(filename):
    """
    Reads a system prompt .md file, with in-memory caching.
    
    First call for a given filename: reads from disk, stores in cache.
    Subsequent calls: returns cached version (no disk I/O).
    
    filename: e.g. "1_brand_spine.md"
    returns: the full text of the prompt file
    """
    # Check cache first
    if filename in _prompt_cache:
        return _prompt_cache[filename]
    
    # Not cached — load from disk
    filepath = os.path.realpath(os.path.join(PROMPTS_DIR, filename))
    
    # SECURITY: Verify resolved path is still inside prompts/ directory
    # Prevents reading arbitrary files if prompt_file is ever manipulated
    if not filepath.startswith(os.path.realpath(PROMPTS_DIR) + os.sep):
        raise AIResponseError(f"Invalid prompt file path: {filename}")
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        raise AIResponseError(f"Prompt file not found: {filename}")
    
    # Store in cache for next time
    _prompt_cache[filename] = content
    return content


def invalidate_prompt_cache(filename=None):
    """
    Clears the prompt cache. Called by app.py when a prompt is saved
    through the Settings UI.
    
    filename: if provided, only clears that one entry.
              if None, clears the entire cache.
    """
    if filename:
        _prompt_cache.pop(filename, None)
    else:
        _prompt_cache.clear()


# ── API Error Classification ──────────────────────────────────────

def _classify_api_error(e):
    """
    Inspects a Gemini API exception and returns the appropriate
    typed error. Shared pattern with router.py.
    """
    error_str = str(e).lower()
    
    if "api key" in error_str or "401" in error_str or "403" in error_str:
        return APIKeyError(f"Gemini API key error: {e}")
    
    if "quota" in error_str or "rate" in error_str or "429" in error_str:
        return RateLimitError(f"Rate limit reached. Please wait a moment and retry. ({e})")
    
    if "not found" in error_str or "404" in error_str or "deprecated" in error_str:
        return ModelError(f"Model not available — check the Model Registry. ({e})")
    
    return AIResponseError(f"AI call failed: {e}")


# ── Generation Config Builder ─────────────────────────────────────

def build_generation_config(agent_id, model_name, system_prompt):
    """
    Builds the Gemini GenerateContentConfig for an agent call.
    
    Temperature priority: agent override > model default > 1.0
    Thinking fallback: agent setting > model default > MEDIUM > off
    """
    config_kwargs = {
        "system_instruction": system_prompt
    }

    model_config = get_model_config(model_name)

    # ── Temperature ──
    agent_temp = get_temperature(agent_id)
    if agent_temp is not None and agent_temp != "":
        try:
            config_kwargs["temperature"] = float(agent_temp)
        except (ValueError, TypeError):
            pass
    elif model_config:
        config_kwargs["temperature"] = model_config.get("default_temperature", 1.0)

    # ── Thinking ──
    supports_thinking = False
    if model_config:
        supports_thinking = model_config.get("supports_thinking", False)

    if supports_thinking:
        thinking_level_str = get_thinking_level(agent_id)

        if thinking_level_str is None:
            if model_config:
                thinking_level_str = model_config.get("default_thinking", "MEDIUM")
            else:
                thinking_level_str = "HIGH" if agent_id == 5 else "MEDIUM"

        if thinking_level_str == "" or thinking_level_str.upper() == "OFF":
            thinking_level_str = "MINIMAL"

        try:
            # Only add thinking config if it's explicitly supported and valid
            enum_level = getattr(types.ThinkingLevel, thinking_level_str.upper())
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=enum_level
            )
        except AttributeError:
            # Fallback to MEDIUM if the string was invalid, but only if the model supports it
            try:
                config_kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MEDIUM
                )
            except AttributeError:
                pass

    # Basic bounds checking for temperature if present
    if "temperature" in config_kwargs:
        temp = config_kwargs["temperature"]
        if temp < 0.0:
            config_kwargs["temperature"] = 0.0
        elif temp > 2.0:
            config_kwargs["temperature"] = 2.0

    return types.GenerateContentConfig(**config_kwargs)


# ── Conversation Building ─────────────────────────────────────────

def build_conversation_contents(session_id, agent_id, system_prompt, new_message=None, message_type="chat", preloaded_history=None):
    """Builds the full conversation contents array for a Gemini API call."""
    if preloaded_history is not None:
        history = preloaded_history
    else:
        history = get_conversation(session_id, agent_id)

    # Cross-agent context injection
    if message_type == "chat" and agent_id != 5:
        global_context = get_recent_global_context(session_id, exclude_agent_id=agent_id, limit=6)
        if global_context:
            context_block = "\n\n=== RECENT GLOBAL CONVERSATION CONTEXT ===\n"
            context_block += "For situational awareness, here is what the consultant recently discussed with OTHER agents. Use this to avoid repeating questions.\n\n"
            for msg in global_context:
                speaker = "Consultant/Founder" if msg["role"] == "user" else f"Agent ({msg['agent_name']})"
                context_block += f"[{speaker}]: {msg['content']}\n"
            context_block += "==========================================\n"
            system_prompt += context_block

    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    if new_message:
        contents.append(types.Content(role="user", parts=[types.Part(text=new_message)]))

    return system_prompt, contents


# ── The Main Function: Send to Agent ──────────────────────────────

def send_to_agent(session_id, agent_id, user_input, message_type="chat", preloaded_history=None):
    """
    Sends a message to a specific agent and returns the AI response.
    
    REFACTOR #3: Now raises typed errors instead of returning error strings.
      - AgentNotFoundError: agent_id doesn't exist
      - APIKeyError: bad/missing API key
      - RateLimitError: quota exceeded
      - ModelError: model deprecated or unavailable
      - AIResponseError: other Gemini failures
    
    The caller (session_ops.py) catches these and decides what to do —
    either recover gracefully or let them bubble up to app.py.
    """
    agent = get_agent(agent_id)
    if not agent:
        raise AgentNotFoundError(f"Agent {agent_id} not found in database")

    model_name = agent["model"] or get_default_model()
    system_prompt = load_prompt(agent["prompt_file"])   # ← uses cache (#5)

    system_instruction, contents = build_conversation_contents(
        session_id, agent_id, system_prompt, user_input, message_type,
        preloaded_history=preloaded_history
    )

    if user_input:
        save_message(session_id, agent_id, "user", user_input, message_type)

    try:
        gen_config = build_generation_config(agent_id, model_name, system_instruction)
        response = client.models.generate_content(
            model=model_name,
            config=gen_config,
            contents=contents
        )
        reply = response.text
        if not reply:
            raise AIResponseError("Gemini returned an empty response")
    except (APIKeyError, RateLimitError, ModelError, AIResponseError):
        # Re-raise our own typed errors as-is
        raise
    except Exception as e:
        # Classify unknown exceptions into typed errors
        raise _classify_api_error(e)

    save_message(session_id, agent_id, "model", reply, message_type)
    return reply
