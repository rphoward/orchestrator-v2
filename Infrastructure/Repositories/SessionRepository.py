from typing import Optional, List
from abc import ABC, abstractmethod
from Domain.Entities.InterviewSession import InterviewSession

class SessionRepository(ABC):
    """
    Abstract Base Class for the Session Repository.
    This defines the contract for persisting InterviewSession entities,
    ensuring our domain logic never touches SQL directly.
    """

    @abstractmethod
    def save(self, session: InterviewSession) -> None:
        """Saves a session to the data store, inserting if new or updating if existing."""
        pass

    @abstractmethod
    def find_by_id(self, session_id: str) -> Optional[InterviewSession]:
        """Retrieves a session by its unique ID."""
        pass

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Deletes a session from the data store."""
        pass

    @abstractmethod
    def get_all(self) -> List[InterviewSession]:
        """Retrieves all sessions."""
        pass
