# Gemini & GenAI Architecture Coordination

This document governs the integration and usage of Google Generative AI within the Interview Orchestrator V2 Swarm Architecture.

## 1. SDK Usage

We utilize the `google-genai` Python library for connecting to the Gemini API and interacting with the models.

*   **API Interactions:** All interactions with the Gemini API (e.g., generating text, calling tools) must route through this SDK.
*   **API Keys:** API keys must be loaded from environment variables (e.g., `GEMINI_API_KEY`) and handled securely.
*   **Error Handling:** All SDK-related errors (e.g., rate limits, invalid requests) must be caught and wrapped in custom application-specific exceptions (`ModelError`, `APIKeyError`) before propagating up the call stack.

## 2. Model Selection (Brain vs. Muscle)

The V2 Swarm Architecture utilizes distinct models tailored for specific roles.

*   **Brain (Synthesizer):** Requires deep reasoning, long context comprehension, and complex synthesis.
    *   **Model:** `gemini-pro` (or equivalent deep-thinking model).
    *   **Usage:** Grand Synthesis, generating Architectural Specifications, long-term strategic analysis.
*   **Muscle (Domain Agents / Hydrators):** Requires speed, rapid extraction, and short-turnaround triaging.
    *   **Model:** `gemini-1.5-flash` (or equivalent fast model like `flash-lite`).
    *   **Usage:** Extracting specific data points from founder input, generating the immediate next question for the consultant, quick categorization.

## 3. Global-to-Local Coordination (The `.md` Hierarchy)

Just as our code structure screams intent (Screaming Architecture), our AI instructions follow a strict global-to-local inheritance pattern.

*   **Global Level (Root `gemini.md`, `agents.md`):** Defines the overarching rules for all models—SDK usage, error handling, base model assignments.
*   **Local Level (Domain Folders e.g., `Domain/Discovery/gemini.md`):** These localized `.md` files inherit from the global guidelines but provide domain-specific instructions. For example, the `Discovery` domain's `gemini.md` might dictate specific system prompts, few-shot examples, or temperature settings tailored exclusively for the Discovery Muscle agents.

When constructing a prompt or configuring a model instance, the system must respect the local `.md` configuration, falling back to the global `.md` for any unspecified parameters.
