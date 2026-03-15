from Domain.Entities.InterviewSession import InterviewSession, Message
from Infrastructure.Repositories.SessionRepository import SessionRepository
from Swarm.Dispatcher import Dispatcher
from Swarm.Memory import ContextCompiler
from Swarm.Muscle import Muscle
from Swarm.Brain import Brain

class ExecutionLoop:
    """
    The formal OODA+S loop handling founder inputs.
    Replaces the V1 'Route and Send' function.
    """

    def __init__(self, repository: SessionRepository):
        self.repository = repository
        self.memory = ContextCompiler()
        self.muscle = Muscle()
        self.brain = Brain()
        self.dispatcher = Dispatcher(self.memory, self.muscle, self.brain)

    def process_input(self, session_id: int, founder_statement: str, is_final: bool = False) -> str:
        """
        Executes the OODA+S loop for a single turn of conversation.
        Returns the response string.
        """

        # 1. Observe
        session = None
        if session_id > 0:
             session = self.repository.find_by_id(session_id)

        if not session:
            # First interaction (id=0 means new session)
            session = InterviewSession(id=0)

        founder_msg = Message(role="founder", content=founder_statement)
        session.add_message("founder", founder_statement)

        # Index the new message into the Pseudo-RAG Context
        self.memory.index_new_message(session, founder_msg)

        # 2. Orient
        # 3. Decide
        # 4. Act
        # The Dispatcher handles Orient, Decide, and Act internally based on Swarm principles
        response_text = self.dispatcher.route_task(session, founder_statement, is_final)

        consultant_msg = Message(role="consultant", content=response_text)
        session.add_message("consultant", response_text)

        # Index the response back into memory
        self.memory.index_new_message(session, consultant_msg)

        # 5. Sync
        # Atomic write-back to the Domain Entity and Session Repository
        self.repository.save(session)

        return response_text
