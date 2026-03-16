import os
from dotenv import dotenv_values

def get_secure_api_key(mock_fallback: bool = True) -> str:
    """
    Reads the API key EXCLUSIVELY from the local .env file.
    Does NOT pull from global os.environ to prevent unintended billing/security risks.
    """
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    config = dotenv_values(env_path)

    # Check for GEMINI_API_KEY first, fallback to GOOGLE_API_KEY
    key = config.get("GEMINI_API_KEY") or config.get("GOOGLE_API_KEY")

    if not key and mock_fallback:
        return "mock_key"

    return key or ""
