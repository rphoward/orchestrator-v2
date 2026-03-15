import os
from google import genai
from google.genai import types

def get_gemini_client():
    # Attempt to pull from environment or default
    api_key = os.environ.get("GEMINI_API_KEY", "mock_key")
    return genai.Client(api_key=api_key)

class DomainAgent:
    """
    Muscle Agent: Rapid extraction and domain-specific conversation logic.
    Utilizes flash-lite for speed.
    """
    def __init__(self, agent_id: int, name: str, system_prompt: str, model_id: str = "gemini-3.1-flash-lite-preview"):
        self.agent_id = agent_id
        self.name = name
        self.system_prompt = system_prompt
        self.model_id = model_id
        self._client = get_gemini_client()

    def generate_response(self, user_input: str, history: list = None) -> str:
        """
        Generates a response using the Gemini API.
        In a real scenario, `history` would be converted into a native Gemini format.
        """
        # We simulate the call if the API key is mock, or make a real call if available
        if os.environ.get("GEMINI_API_KEY", "mock_key") == "mock_key":
            return f"[MOCK {self.name}] Acknowledged: '{user_input}'. Please elaborate."

        # Real call using the new google-genai 0.3.0 SDK syntax
        contents = []
        if history:
             for msg in history:
                 role = 'user' if msg.role == 'user' else 'model'
                 contents.append(types.Content(role=role, parts=[types.Part.from_text(msg.content)]))

        contents.append(types.Content(role="user", parts=[types.Part.from_text(user_input)]))

        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            temperature=1.0,
        )

        response = self._client.models.generate_content(
            model=self.model_id,
            contents=contents,
            config=config,
        )
        return response.text

class GrandSynthesisAgent:
    """
    Brain Agent: Deep synthesis and architecture generation.
    Utilizes pro for reasoning.
    """
    def __init__(self, model_id: str = "gemini-3.1-pro-preview"):
        self.model_id = model_id
        self._client = get_gemini_client()

    def synthesize(self, session_data: str) -> str:
        if os.environ.get("GEMINI_API_KEY", "mock_key") == "mock_key":
             return "[MOCK SYNTHESIS] Architecture specified based on all inputs."

        prompt = f"Synthesize the following session data into a final architectural specification:\n\n{session_data}"
        config = types.GenerateContentConfig(
            system_instruction="You are the Grand Synthesis Brain.",
            temperature=1.0,
        )
        response = self._client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config=config,
        )
        return response.text
