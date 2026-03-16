from pydantic import BaseModel

class Agent(BaseModel):
    """Structural Entity: Represents a Swarm Agent configuration."""
    id: int
    name: str
    prompt_file: str
    model: str = "gemini-3.1-flash-lite-preview"
    is_synthesizer: bool = False

class Config(BaseModel):
    """Structural Entity: System-wide configuration key-value pair."""
    key: str
    value: str
