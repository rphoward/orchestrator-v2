from datetime import datetime, UTC
from typing import Literal
from pydantic import BaseModel, Field
from uuid import UUID, uuid4

class Message(BaseModel):
    """Value Object representing a single conversation utterance."""
    id: UUID = Field(default_factory=uuid4)
    agent_id: int
    role: Literal["user", "assistant", "system"]
    content: str
    message_type: Literal["chat", "init", "summary"] = "chat"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RoutingLog(BaseModel):
    """Value Object recording a routing decision."""
    id: UUID = Field(default_factory=uuid4)
    input_text: str
    agent_id: int
    agent_name: str
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
