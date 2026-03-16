import os
from google.adk.agents.llm_agent import Agent
from config import get_secure_api_key

class DomainAgent(Agent):
    """
    Muscle Agent built natively on the google-adk Agent class.
    Handles rapid extraction and domain-specific conversation logic.
    """
    # Because ADK Agents are typically Pydantic models themselves, we declare fields
    agent_id: int

    def __init__(self, agent_id: int, name: str, system_prompt: str, model_id: str = "gemini-3.1-flash-lite-preview", **kwargs):
        super().__init__(
            agent_id=agent_id,
            model=model_id,
            name=name,
            instruction=system_prompt,
            description=f"Handles questions and tasks related to {name}.",
            **kwargs
        )

    async def generate_response(self, user_input: str, history: list = None) -> str:
        """
        Executes the ADK Agent asynchronously, injecting historical context.
        """
        # Securely read from .env ONLY, avoiding global terminal state.
        api_key = get_secure_api_key()
        if api_key == "mock_key":
            return f"[MOCK {self.name}] Acknowledged: '{user_input}'. Please elaborate."

        # Build context-aware prompt from history
        full_prompt = ""
        if history:
            full_prompt += "--- RECENT CONVERSATION HISTORY ---\n"
            for msg in history:
                full_prompt += f"{msg.role.upper()}: {msg.content}\n"
            full_prompt += "-----------------------------------\n\n"

        full_prompt += f"USER: {user_input}\n\n"
        full_prompt += "Provide your response based strictly on the system instructions and the history above."

        # Execute using ADK's native async run method.
        # Since ADK relies on os.environ deep internally, we safely and temporarily
        # inject the .env key, run the agent, and immediately restore the environment
        # to prevent global leakage/billing risks.
        original_key = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = api_key
        try:
            response_stream = self.run_async(prompt=full_prompt)

            response_text = ""
            async for event in response_stream:
                if hasattr(event, 'model_response') and event.model_response:
                    for part in event.model_response.parts:
                        if part.text:
                            response_text += part.text

            return response_text
        finally:
            if original_key is not None:
                os.environ["GEMINI_API_KEY"] = original_key
            else:
                del os.environ["GEMINI_API_KEY"]


class GrandSynthesisAgent(Agent):
    """
    Brain Agent: Deep synthesis and architecture generation.
    Utilizes pro for reasoning.
    """
    def __init__(self, model_id: str = "gemini-3.1-pro-preview"):
        super().__init__(
            model=model_id,
            name="grand_synthesis",
            instruction="You are the Grand Synthesis Brain.",
            description="Performs deep synthesis on the gathered session data."
        )

    async def synthesize(self, session_data: str) -> str:
        api_key = get_secure_api_key()
        if api_key == "mock_key":
             return "[MOCK SYNTHESIS] Architecture specified based on all inputs."

        prompt = f"Synthesize the following session data into a final architectural specification:\n\n{session_data}"

        original_key = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = api_key
        try:
            response_stream = self.run_async(prompt=prompt)

            response_text = ""
            async for event in response_stream:
                if hasattr(event, 'model_response') and event.model_response:
                    for part in event.model_response.parts:
                        if part.text:
                            response_text += part.text

            return response_text
        finally:
            if original_key is not None:
                os.environ["GEMINI_API_KEY"] = original_key
            else:
                del os.environ["GEMINI_API_KEY"]
