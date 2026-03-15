from Swarm.Muscle import Muscle
from Swarm.Brain import Brain
from Swarm.Memory import ContextCompiler
from Domain.Entities.InterviewSession import InterviewSession
import random

class Dispatcher:
    """
    Dispatcher (The Swarm Router).
    Replaces the static router.py. It acts as a semantic load-balancer.
    """
    def __init__(self, memory: ContextCompiler, muscle: Muscle, brain: Brain):
        self.memory = memory
        self.muscle = muscle
        self.brain = brain

    def decide_domain(self, user_input: str) -> str:
        """
        Determines which domain (Brand Spine, Customer Reality, Technical, etc.)
        needs to address the input.
        In a full implementation, this uses a fast LLM call for semantic classification.
        For this skeleton, we use lightweight heuristics to map the input.
        """
        user_input_lower = user_input.lower()
        if any(w in user_input_lower for w in ['customer', 'user', 'client']):
            return 'CustomerReality'
        elif any(w in user_input_lower for w in ['brand', 'vision', 'mission']):
            return 'BrandSpine'
        elif any(w in user_input_lower for w in ['tech', 'stack', 'data', 'cloud']):
            return 'Technical'
        else:
            return 'General'

    def orient(self, session: InterviewSession, domain_need: str) -> str:
        """Navigates the session's memory tree to load ONLY necessary context."""
        return self.memory.retrieve_context(session, domain_need)

    def route_task(self, session: InterviewSession, user_input: str, is_final: bool = False) -> str:
        """
        The central load-balancer logic.
        """
        if is_final:
            # If the session is ending, route to the Brain for Synthesis
            self.brain.synthesize(session)
            session.complete_session()
            return "Thank you for the session. I have synthesized your vision into the Architectural Specification."
        else:
            # For ongoing conversation, dispatch to a Domain Muscle
            domain_need = self.decide_domain(user_input)
            context = self.orient(session, domain_need)
            next_question = self.muscle.act(session, domain_need, context, user_input)
            return next_question
