from typing import Dict, Any, List
from Domain.Entities.InterviewSession import InterviewSession, Message

class ContextCompiler:
    """
    The Memory module of the Swarm.
    Replaces static 'last 6 messages' with Pseudo-RAG Context Indexing.
    """

    def __init__(self):
        # We index context based on domain or depth instead of purely chronological
        pass

    def _cluster_message(self, session: InterviewSession, message: Message):
        """
        Dynamically clusters a new message into the session's context_index.
        In a full RAG implementation, this would generate embeddings.
        For pseudo-RAG, we categorize based on heuristic rules or lightweight LLM tags.
        """
        # A simple keyword-based pseudo-RAG clustering for this skeleton
        if not hasattr(session, 'context_index'):
            session.context_index = {}

        content_lower = message.content.lower()
        if 'customer' in content_lower or 'user' in content_lower:
            domain = 'CustomerReality'
        elif 'brand' in content_lower or 'vision' in content_lower:
            domain = 'BrandSpine'
        elif 'tech' in content_lower or 'stack' in content_lower or 'data' in content_lower:
            domain = 'Technical'
        else:
            domain = 'General'

        if domain not in session.context_index:
             session.context_index[domain] = []

        session.context_index[domain].append({"role": message.role, "content": message.content})


    def index_new_message(self, session: InterviewSession, message: Message):
        """Hooks into the entity's add_message to update the Lisp-nested context tree."""
        self._cluster_message(session, message)


    def retrieve_context(self, session: InterviewSession, domain_need: str) -> str:
        """
        Navigates the session's memory tree to load ONLY the necessary context,
        preventing context bloat.
        """
        if not session.context_index:
            return ""

        relevant_clusters = []

        # Always include some general context for grounding
        if 'General' in session.context_index:
             relevant_clusters.extend(session.context_index['General'][-3:]) # Keep the last 3 general turns

        # Pull in domain-specific deep context
        if domain_need in session.context_index:
             relevant_clusters.extend(session.context_index[domain_need])

        # Sort chronologically or format into Lisp-nested/structured context
        context_string = "\n".join([f"[{m['role'].upper()}]: {m['content']}" for m in relevant_clusters])
        return f"<Context>\n{context_string}\n</Context>"
