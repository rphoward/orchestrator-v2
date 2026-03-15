import os
from google.adk.agents.llm_agent import Agent

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
        Executes the ADK Agent asynchronously.
        """
        # Prioritize GEMINI_API_KEY if testing live routing, fallback to GOOGLE_API_KEY
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "mock_key")
        if api_key == "mock_key":
            return f"[MOCK {self.name}] Acknowledged: '{user_input}'. Please elaborate."

        # Execute using ADK's native async run method
        response_stream = self.run_async(prompt=user_input)

        response_text = ""
        async for event in response_stream:
            # ADK streams back events. We capture the model's text generation.
            if hasattr(event, 'model_response') and event.model_response:
                for part in event.model_response.parts:
                    if part.text:
                        response_text += part.text

        return response_text


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
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "mock_key")
        if api_key == "mock_key":
             return "[MOCK SYNTHESIS] Architecture specified based on all inputs."

        prompt = f"Synthesize the following session data into a final architectural specification:\n\n{session_data}"
        response_stream = self.run_async(prompt=prompt)

        response_text = ""
        async for event in response_stream:
            if hasattr(event, 'model_response') and event.model_response:
                for part in event.model_response.parts:
                    if part.text:
                        response_text += part.text

        return response_text
