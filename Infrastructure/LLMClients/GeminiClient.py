import os
from google import genai

class GeminiClient:
    """
    Singleton Wrapper for the Google GenAI SDK.
    Follows gemini.md guidelines for robust interactions and error handling.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GeminiClient, cls).__new__(cls)
            # Initialize the genai client from the environment variable GEMINI_API_KEY
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY environment variable is not set.")
            cls._instance.client = genai.Client(api_key=api_key)
        return cls._instance

    def generate(self, model_name: str, prompt: str, system_instruction: str = None) -> str:
        """Generates text from the specified Gemini model."""
        config = None
        if system_instruction:
            config = {"system_instruction": system_instruction}

        try:
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            return response.text
        except Exception as e:
             # Follows guidelines to wrap errors
            raise Exception(f"ModelError ({model_name}): {str(e)}")
