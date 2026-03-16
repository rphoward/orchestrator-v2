from typing import List, Optional, Literal
from datetime import datetime, UTC
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

class InterviewSession(BaseModel):
    """
    AGGREGATE ROOT: Manages the lifecycle of an interview session.
    Protects invariants for adding messages and routing logs.
    """
    id: Optional[int] = None  # None until persisted by the repository
    name: str = "New Session"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Internal collections (Child Entities)
    messages: List[Message] = Field(default_factory=list)
    routing_logs: List[RoutingLog] = Field(default_factory=list)

    def add_message(self, agent_id: int, role: Literal["user", "assistant", "system"], content: str, message_type: Literal["chat", "init", "summary"] = "chat") -> Message:
        """Business logic to add a message and update internal state."""
        msg = Message(
            agent_id=agent_id,
            role=role,
            content=content,
            message_type=message_type
        )
        self.messages.append(msg)
        self._touch()
        return msg

    def log_routing_decision(self, input_text: str, agent_id: int, agent_name: str, reason: str) -> RoutingLog:
        """Records a routing event in the session's history."""
        log = RoutingLog(
            input_text=input_text,
            agent_id=agent_id,
            agent_name=agent_name,
            reason=reason
        )
        self.routing_logs.append(log)
        self._touch()
        return log

    def _touch(self) -> None:
        """Internal invariant: any mutation updates the timestamp."""
        self.updated_at = datetime.now(UTC)
