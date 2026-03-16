"""
Infrastructure/Swarm/agents.py — Domain Agent (Muscle)
═══════════════════════════════════════════════════════
The "Muscle" of the Swarm. Each DomainAgent is a specialized
conversational agent: a prompt + a model + execution logic.

THIS IS A CONVERSATIONAL FRAMEWORK, NOT AN AGENTIC ONE.
  The Interview Orchestrator routes human conversation to 4 specialized
  prompts, each with its own model and config. It's not autonomous
  tool-using agents — it's structured interviewing.

  google-genai handles the LLM calls directly. No ADK, no async
  framework fights, no dependencies that change every two weeks.
  If you ever need ADK features (MCP tools, A2A, etc.), you can
  wrap these agents later. But for conversation routing, this is
  all you need.

WHO CALLS ME:
  - session_ops.py (via SwarmDispatcher)

WHAT I IMPORT:
  - google.genai      → Gemini API client
  - model_registry    → per-agent thinking/temperature config
  - errors            → typed error classes
"""

import os
from google import genai
from google.genai import types

from model_registry import (
    get_model_config, get_default_model,
    get_thinking_level, get_temperature
)
from errors import (
    APIKeyError, RateLimitError,
    ModelError, AIResponseError
)


# ── Prompt Cache ─────────────────────────────────────────────────
# Ported from V1 agent.py. Maps filename → prompt text.
# Loaded on first access, invalidated when prompts are edited via Settings.

PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "prompts"
)

_prompt_cache = {}


def load_prompt(filename):
    """
    Reads a system prompt .md file, with in-memory caching.

    First call for a given filename: reads from disk, stores in cache.
    Subsequent calls: returns cached version (no disk I/O).

    filename: e.g. "1_brand_spine.md"
    returns:  the full text of the prompt file
    """
    if filename in _prompt_cache:
        return _prompt_cache[filename]

    filepath = os.path.realpath(os.path.join(PROMPTS_DIR, filename))

    # SECURITY: Verify resolved path is still inside prompts/ directory
    if not filepath.startswith(os.path.realpath(PROMPTS_DIR) + os.sep):
        raise AIResponseError(f"Invalid prompt file path: {filename}")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        raise AIResponseError(f"Prompt file not found: {filename}")

    _prompt_cache[filename] = content
    return content


def invalidate_prompt_cache(filename=None):
    """
    Clears the prompt cache. Called by app.py when a prompt is
    saved through the Settings UI.

    filename: if provided, only clears that one entry.
              if None, clears the entire cache (e.g., after config import).
    """
    if filename:
        _prompt_cache.pop(filename, None)
    else:
        _prompt_cache.clear()


# ── API Error Classification ─────────────────────────────────────
# Shared pattern: inspect Gemini exceptions and map to our typed errors.

def classify_api_error(e):
    """
    Inspects a Gemini API exception and returns the appropriate
    typed error. Used by both DomainAgent and the Dispatcher's router.
    """
    error_str = str(e).lower()

    if "api key" in error_str or "401" in error_str or "403" in error_str:
        return APIKeyError(f"Gemini API key error: {e}")

    if "quota" in error_str or "rate" in error_str or "429" in error_str:
        return RateLimitError(
            f"Rate limit reached. Please wait and retry. ({e})"
        )

    if "not found" in error_str or "404" in error_str or "deprecated" in error_str:
        return ModelError(
            f"Model not available — check the Model Registry. ({e})"
        )

    return AIResponseError(f"AI call failed: {e}")


# ── Generation Config Builder ────────────────────────────────────
# Ported from V1 agent.py. Builds the Gemini config with thinking
# levels and temperature overrides from model_registry.

def build_generation_config(agent_id, model_name, system_prompt):
    """
    Builds the Gemini GenerateContentConfig for an agent call.

    Temperature priority: agent override > model default > 1.0
    Thinking fallback:    agent setting > model default > MEDIUM > off
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
        config_kwargs["temperature"] = model_config.get(
            "default_temperature", 1.0
        )

    # ── Thinking ──
    supports_thinking = False
    if model_config:
        supports_thinking = model_config.get("supports_thinking", False)

    if supports_thinking:
        thinking_level_str = get_thinking_level(agent_id)

        # Fallback chain: agent setting → model default → MEDIUM (or HIGH for synthesis)
        if thinking_level_str is None:
            if model_config:
                thinking_level_str = model_config.get("default_thinking", "MEDIUM")
            else:
                thinking_level_str = "HIGH" if agent_id == 5 else "MEDIUM"

        if thinking_level_str == "" or thinking_level_str.upper() == "OFF":
            thinking_level_str = "MINIMAL"

        try:
            enum_level = getattr(
                types.ThinkingLevel, thinking_level_str.upper()
            )
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=enum_level
            )
        except AttributeError:
            # Invalid string → fall back to MEDIUM
            try:
                config_kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MEDIUM
                )
            except AttributeError:
                pass  # Model truly doesn't support thinking

    # Clamp temperature to valid range
    if "temperature" in config_kwargs:
        temp = config_kwargs["temperature"]
        config_kwargs["temperature"] = max(0.0, min(2.0, temp))

    return types.GenerateContentConfig(**config_kwargs)


# ── The DomainAgent ──────────────────────────────────────────────

class DomainAgent:
    """
    A domain-specific interview agent (Muscle).

    Each agent is: a prompt file + a model + execution config.
    The execute() method calls Gemini with the right thinking level,
    temperature, conversation history, and cross-agent context.

    This is a conversational agent, not an autonomous one.
    """

    def __init__(self, agent_id, name, prompt_file,
                 model_id="gemini-3.1-flash-lite-preview"):
        self.agent_id = agent_id
        self.name = name
        self.prompt_file = prompt_file
        self.model_id = model_id

        # Validate the prompt loads (cached after first load)
        load_prompt(prompt_file)

    def execute(self, user_input, history=None,
                cross_agent_context=None, message_type="chat"):
        """
        Sends a message to this agent via the Gemini API.

        Args:
            user_input:          The new message to send
            history:             List of prior messages (dicts: role, content)
            cross_agent_context: Recent msgs from OTHER agents (awareness)
            message_type:        'chat', 'init', or 'summary'

        Returns: The agent's response text (string)
        Raises:  APIKeyError, RateLimitError, ModelError, AIResponseError
        """
        # Get the API key
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise APIKeyError(
                "GEMINI_API_KEY is not set. Check your .env file."
            )

        client = genai.Client(api_key=api_key)

        # Load fresh prompt (uses cache, picks up edits via invalidation)
        system_prompt = load_prompt(self.prompt_file)

        # ── Cross-Agent Context Injection ──
        # The "Context Silo Heal" from V1 — lets each agent know
        # what the consultant discussed with OTHER agents recently.
        # Only injected during normal chat, not init or summary.
        if cross_agent_context and message_type == "chat":
            context_block = (
                "\n\n=== RECENT GLOBAL CONVERSATION CONTEXT ===\n"
                "For situational awareness, here is what the consultant "
                "recently discussed with OTHER agents. Use this to avoid "
                "repeating questions.\n\n"
            )
            for msg in cross_agent_context:
                speaker = (
                    "Consultant/Founder" if msg["role"] == "user"
                    else f"Agent ({msg['agent_name']})"
                )
                context_block += f"[{speaker}]: {msg['content']}\n"
            context_block += "==========================================\n"
            system_prompt += context_block

        # ── Build conversation contents from history ──
        contents = []
        if history:
            for msg in history:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part(text=msg["content"])]
                    )
                )

        # Add the new user message
        if user_input:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=user_input)]
                )
            )

        # Build generation config (thinking, temperature, system instruction)
        model_name = self.model_id or get_default_model()
        gen_config = build_generation_config(
            self.agent_id, model_name, system_prompt
        )

        # ── Make the API call ──
        try:
            response = client.models.generate_content(
                model=model_name,
                config=gen_config,
                contents=contents
            )
            reply = response.text
            if not reply:
                raise AIResponseError("Gemini returned an empty response")
            return reply

        except (APIKeyError, RateLimitError, ModelError, AIResponseError):
            raise  # Re-raise our typed errors as-is
        except Exception as e:
            raise classify_api_error(e)


class GrandSynthesisAgent(DomainAgent):
    """
    The "Brain" — uses a higher-capability model for deep synthesis.
    Same execution pattern as DomainAgent, just typically configured
    with gemini-3.1-pro-preview and higher thinking levels.
    """

    def __init__(self, agent_id=5, name="Grand Synthesis",
                 prompt_file="5_grand_synthesis.md",
                 model_id="gemini-3.1-pro-preview"):
        super().__init__(agent_id, name, prompt_file, model_id)
