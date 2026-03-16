"""
dispatcher_cache.py - Cached Dispatcher Factory
════════════════════════════════════════════════
Sits between app.py (Layer 5) and the Swarm layer (Layer 4).

THE PROBLEM:
  In the original app.py, `_build_dispatcher()` is called on EVERY
  HTTP request. Each call:
    1. Hits the database to load all agents
    2. Hits the database AGAIN for each agent's system prompt
    3. Creates fresh DomainAgent objects
    4. Creates a fresh SwarmDispatcher

  For 4 agents, that's 5 DB queries per request (1 list + 4 prompts).
  On a "send" action, the frontend fires 3-4 API calls in quick
  succession, so you get ~20 DB queries just to render one response.

THE FIX:
  Build the dispatcher ONCE and cache it. Invalidate the cache only
  when something actually changes (prompt saved, model changed, etc.).
  This is a simple "cache-aside" pattern:

    Request comes in
        → Is there a cached dispatcher?
            YES → use it (zero DB queries)
            NO  → build one, cache it, use it

  Invalidation is explicit: when app.py saves a prompt or updates
  an agent config, it calls `invalidate()` to force a rebuild on
  the next request.

THREAD SAFETY NOTE:
  Flask's dev server (debug=True) uses threading. Python's GIL
  protects us from true race conditions on the cache dict, but
  we use a threading.Lock anyway because:
    1. It makes the intent explicit
    2. It's free (uncontested locks cost ~50 nanoseconds)
    3. It future-proofs for WSGI servers like gunicorn with threads

USAGE IN app.py:
  from dispatcher_cache import get_dispatcher, invalidate_dispatcher

  # In any route that needs the dispatcher:
  dispatcher = get_dispatcher()

  # In any route that changes agent config:
  invalidate_dispatcher()
"""

import threading
from Infrastructure.repositories import SQLiteAgentRepository
from Infrastructure.Swarm.agents import DomainAgent
from Infrastructure.Swarm.dispatcher import SwarmDispatcher


# ── The Cache ─────────────────────────────────────────────────────
# _cached_dispatcher holds either None (needs rebuild) or a
# SwarmDispatcher instance ready to use.
#
# _lock ensures only one thread builds the dispatcher if two
# requests arrive at the same time after an invalidation.

_cached_dispatcher = None
_lock = threading.Lock()


def _build_dispatcher_internal():
    """
    The actual build logic — pulled out of app.py so it lives
    in one place. Same logic as the original, just organized.

    Returns a fully hydrated SwarmDispatcher with all active
    DomainAgent instances loaded from the database.
    """
    # One repository instance per build. These are lightweight —
    # they just hold a DB path, not a persistent connection.
    agent_repo = SQLiteAgentRepository()

    agents_dict = {}

    # Step 1: Load all agent records from the database (1 query)
    all_agents = agent_repo.get_all()

    for a in all_agents:
        # Skip the Synthesizer agent — it's used in finalization,
        # not in the routing dispatcher. (Matches original logic.)
        if a.is_synthesizer:
            continue

        # Step 2: Load this agent's system prompt (1 query per agent)
        prompt = agent_repo.get_system_prompt_for_agent(a.id)

        # Step 3: Clean the name for ADK compatibility
        # ADK (Agent Development Kit) requires Python-identifier-safe
        # names. Spaces and special chars break it.
        clean_name = a.name.lower().replace(" ", "_")

        # Step 4: Create the DomainAgent wrapper
        agents_dict[a.id] = DomainAgent(
            agent_id=a.id,
            name=clean_name,
            system_prompt=prompt,
            model_id=a.model
        )

    # Step 5: Wrap all agents in the SwarmDispatcher
    return SwarmDispatcher(agents=agents_dict)


def get_dispatcher():
    """
    Returns a cached SwarmDispatcher. Builds one if the cache is empty.

    This is the function app.py calls instead of _build_dispatcher().

    Performance:
      - Cache HIT:  ~0ms (just returns the cached object)
      - Cache MISS: ~5-20ms (DB queries + object creation)
      - Original:   ~5-20ms on EVERY request

    So for a typical "send" action that triggers 3-4 API calls,
    we go from ~60-80ms of dispatcher overhead to ~0ms.
    """
    global _cached_dispatcher

    # Fast path: cache hit (no lock needed for reads in CPython
    # due to GIL, but we check inside the lock for correctness)
    if _cached_dispatcher is not None:
        return _cached_dispatcher

    # Slow path: cache miss — need to build
    with _lock:
        # Double-check after acquiring lock. Another thread might
        # have built it while we were waiting.
        if _cached_dispatcher is not None:
            return _cached_dispatcher

        _cached_dispatcher = _build_dispatcher_internal()
        return _cached_dispatcher


def invalidate_dispatcher():
    """
    Marks the cache as stale. The next call to get_dispatcher()
    will rebuild from the database.

    Call this whenever agent configuration changes:
      - Prompt saved (api_update_agent)
      - Model changed (api_update_agent)
      - Config imported (api_import_config)
      - Model registry saved (if it affects agent models)

    This is intentionally NOT an automatic rebuild. We just clear
    the cache and let the next request trigger the build. This way:
      1. We don't waste time rebuilding if no request comes
      2. The rebuild always has the latest data
      3. It's simple to reason about
    """
    global _cached_dispatcher

    with _lock:
        _cached_dispatcher = None