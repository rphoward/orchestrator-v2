from abc import ABC, abstractmethod
from typing import List, Optional
from Domain.Session.aggregate import InterviewSession
from Domain.Core.entities import Agent

class SessionRepository(ABC):
    """
    Interface for the InterviewSession Aggregate Root.
    The Infrastructure layer MUST implement this without leaking DB details.
    """

    @abstractmethod
    def save(self, session: InterviewSession) -> InterviewSession:
        """Persists the ENTIRE aggregate root (session + messages + logs) atomically."""
        pass

    @abstractmethod
    def get_by_id(self, session_id: int) -> Optional[InterviewSession]:
        """Rehydrates the aggregate root from persistence."""
        pass

    @abstractmethod
    def list_all(self) -> List[InterviewSession]:
        """Returns all sessions, typically without full child-entity hydration for performance."""
        pass

    @abstractmethod
    def delete(self, session_id: int) -> None:
        """Deletes the entire session aggregate."""
        pass

class AgentRepository(ABC):
    """Interface for managing Swarm Agents."""

    @abstractmethod
    def get_all(self) -> List[Agent]:
        pass

    @abstractmethod
    def get_by_id(self, agent_id: int) -> Optional[Agent]:
        pass

    @abstractmethod
    def save(self, agent: Agent) -> Agent:
        pass
