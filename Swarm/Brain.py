from google.adk.agents.llm_agent import Agent

class BrainFactory:
    """
    Brain (Specwriter / Synthesizer).
    Uses google-adk native Agent functionality.
    """
    @staticmethod
    def create_brain() -> Agent:
        return Agent(
            model='gemini-3.1-pro-preview',
            name='brain_synthesizer',
            description="Deep thinking synthesizer for creating the Architectural Spec.",
            instruction=(
                "You are the Brain, the Master Synthesizer of the Swarm Architecture. "
                "You process the entire conversational context of the founder interview "
                "and output a structured JSON representing the core ethos and domain specific discoveries "
                "for an Architectural Specification.\n\n"
                "Action: Synthesize the context into a structured JSON string containing two keys: \n"
                "1. 'core_ethos' (string) - The fundamental vision.\n"
                "2. 'domains' (object) - A mapping of discovered business domains (e.g., 'BrandSpine', 'CustomerReality') to a summary string.\n\n"
                "Return ONLY the raw JSON string."
            )
        )
