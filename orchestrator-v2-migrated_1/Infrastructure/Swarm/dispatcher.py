"""
Infrastructure/Swarm/dispatcher.py — Swarm Dispatcher
══════════════════════════════════════════════════════
The semantic load-balancer. Routes user input to the right DomainAgent.

RESPONSIBILITIES:
  1. Build and cache the agent swarm (DomainAgent instances)
  2. Route user input via Gemini structured-output
  3. Dispatch execution to the selected agent
  4. Provide the Grand Synthesis agent for finalization

CACHE-ASIDE PATTERN (replaces the separate dispatcher_cache.py from patches):
  The dispatcher builds agents from the DB once and caches them.
  When agent config changes (prompt edit, model change, config import),
  call invalidate() to force a rebuild on the next request.
  This eliminates ~20 DB queries per user interaction.

WHO CALLS ME:
  - session_ops.py → get_dispatcher(), route(), dispatch()

WHAT I IMPORT:
  - Infrastructure.Swarm.agents   → DomainAgent, GrandSynthesisAgent
  - Infrastructure.repositories   → SQLiteAgentRepository
  - errors                        → typed error classes
  - google.genai                  → Gemini API (for routing only)
  - model_registry                → router model config
"""

import os
import json
import threading
from typing import Dict, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import Literal

from Infrastructure.Swarm.agents import DomainAgent, GrandSynthesisAgent, classify_api_error
from Infrastructure.repositories import SQLiteAgentRepository
from model_registry import get_router_model, get_model_config
from errors import (
    RoutingError, APIKeyError, RateLimitError, ModelError
)


# ── Routing Decision Schema ──────────────────────────────────────
# Gemini returns this as structured JSON output.

class RoutingDecision(BaseModel):
    """Structured output expected from the Semantic Router."""
    agent_id: Literal[1, 2, 3, 4] = Field(
        description=(
            "The ID of the specialized agent to handle the user's input: "
            "1 for Brand/Mission, 2 for Founder/Personal Constraints, "
            "3 for Customer/User needs, 4 for Architecture/Tech Stack."
        )
    )
    reason: str = Field(
        description="A short explanation of why this agent was chosen."
    )


# ── Routing Directive ────────────────────────────────────────────
# The system prompt that tells the router how to classify input.

ROUTING_DIRECTIVE = """You are an interview routing engine. Analyze the consultant's input and determine which specialized agent should handle it.

AGENTS AND THEIR DOMAINS:
Agent 1 - BRAND SPINE: Identity, purpose, culture, employee behavior, differentiation, competition.
Agent 2 - FOUNDER INVARIANTS: Absolute rules, boundaries, constraints, past failures, compliance.
Agent 3 - CUSTOMER REALITY: Why customers buy, their struggles, workarounds, success metrics.
Agent 4 - ARCHITECTURE TRANSLATION: Operational processes, terminology, step-by-step workflows.

RULES:
- If the input is a greeting or general opener, route to Agent 1 (Brand Spine).
- Respond with ONLY a JSON object: {"agent_id": <number>, "reason": "<brief explanation>"}
"""


class SwarmDispatcher:
    """
    The Dispatcher: semantic load-balancer for the agent swarm.

    Manages the OODA+S execution loop:
      Observe → Orient → Decide (route) → Act (agent execute) → Sync (persist)

    Includes the cache-aside pattern: agents are built once from DB,
    then served from cache until invalidated.
    """

    def __init__(self):
        """
        Builds the agent swarm from the database.
        Called once, then cached at module level via get_dispatcher().
        """
        self._agent_repo = SQLiteAgentRepository()
        self.muscle_agents: Dict[int, DomainAgent] = {}
        self.brain: Optional[GrandSynthesisAgent] = None

        # Load all agent configs from DB and create DomainAgent instances
        agent_configs = self._agent_repo.get_all()

        for config in agent_configs:
            if config.is_synthesizer:
                # Agent 5: Grand Synthesis (Brain)
                self.brain = GrandSynthesisAgent(
                    agent_id=config.id,
                    name=config.name,
                    prompt_file=config.prompt_file,
                    model_id=config.model,
                )
            else:
                # Agents 1-4: Domain Agents (Muscle)
                self.muscle_agents[config.id] = DomainAgent(
                    agent_id=config.id,
                    name=config.name,
                    prompt_file=config.prompt_file,
                    model_id=config.model,
                )

        # Fallback: if no brain was found in DB, create default
        if not self.brain:
            self.brain = GrandSynthesisAgent()

    def route(self, user_input):
        """
        Semantic routing: classifies user input → agent_id + reason.

        Uses Gemini structured output for deterministic JSON responses.
        Falls back to Agent 1 on any parse failure (conversation must
        never stall).

        Returns: dict with 'id' and 'reason' keys
        Raises:  APIKeyError, RateLimitError, ModelError (infra problems)
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise APIKeyError(
                "GEMINI_API_KEY is not set. Check your .env file."
            )

        client = genai.Client(api_key=api_key)
        model_name = get_router_model()

        # Build config — router always uses minimal thinking for speed
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
                    "parts": [{
                        "text": (
                            f"{ROUTING_DIRECTIVE}\n\n"
                            f"Consultant's input: \"{user_input}\""
                        )
                    }]
                }],
                config=types.GenerateContentConfig(**config_kwargs)
            )
        except Exception as e:
            raise classify_api_error(e)

        # Parse the router's JSON response
        try:
            decision = json.loads(response.text)
            agent_id = int(decision.get("agent_id", decision.get("id", 1)))
        except (json.JSONDecodeError, ValueError, TypeError):
            return {
                "id": 1,
                "reason": "Default routing (unparseable router response)"
            }

        # Clamp to valid range
        if agent_id < 1 or agent_id > 4:
            agent_id = 1

        return {
            "id": agent_id,
            "reason": decision.get("reason", "Routed by AI")
        }

    def get_agent(self, agent_id):
        """Returns a DomainAgent by ID, or None if not found."""
        if agent_id == 5 or (hasattr(self.brain, 'agent_id') and agent_id == self.brain.agent_id):
            return self.brain
        return self.muscle_agents.get(agent_id)

    def get_muscle_agents(self):
        """Returns dict of non-synthesizer agents {id: DomainAgent}."""
        return self.muscle_agents


# ═══════════════════════════════════════════════════════════════════
# MODULE-LEVEL CACHE (replaces dispatcher_cache.py)
# ═══════════════════════════════════════════════════════════════════
# The dispatcher is expensive to build (DB queries + prompt loads).
# Cache it at module level. Thread-safe via Lock.

_dispatcher_cache: Optional[SwarmDispatcher] = None
_cache_lock = threading.Lock()


def get_dispatcher() -> SwarmDispatcher:
    """
    Returns the cached SwarmDispatcher, building it if needed.
    Thread-safe: uses a lock so concurrent Flask requests don't
    race to build multiple dispatchers simultaneously.
    """
    global _dispatcher_cache

    if _dispatcher_cache is not None:
        return _dispatcher_cache

    with _cache_lock:
        # Double-check inside lock (another thread may have built it)
        if _dispatcher_cache is not None:
            return _dispatcher_cache

        _dispatcher_cache = SwarmDispatcher()
        return _dispatcher_cache


def invalidate_dispatcher():
    """
    Clears the cached dispatcher. Call this when agent config changes:
      - Prompt edited via Settings
      - Model changed via Settings
      - Config imported

    The next get_dispatcher() call will rebuild from the DB.
    """
    global _dispatcher_cache

    with _cache_lock:
        _dispatcher_cache = None
