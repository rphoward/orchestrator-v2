from Infrastructure.LLMClients.GeminiClient import GeminiClient
from Domain.Entities.InterviewSession import InterviewSession
import os

class Brain:
    """
    Brain (Specwriter / Synthesizer).
    Operates on deep, slow, high-thinking models (gemini-pro) to perform the Grand Synthesis phase.
    """
    def __init__(self):
        self.deep_model = "gemini-pro"  # As defined in gemini.md

    def synthesize(self, session: InterviewSession) -> None:
        """
        Deeply analyzes the accumulated session context and updates the ArchitecturalSpec.
        """
        client = GeminiClient()

        system_instruction = (
            "You are the Brain, the Master Synthesizer of the Swarm Architecture. "
            "You process the entire conversational context of the founder interview "
            "and output a structured JSON representing the core ethos and domain specific discoveries "
            "for an Architectural Specification."
        )

        prompt = (
            f"Here is the context index mapping: {session.context_index}\n\n"
            "Action: Synthesize this into a structured JSON string containing two keys: "
            "1. 'core_ethos' (string) - The fundamental vision.\n"
            "2. 'domains' (object) - A mapping of discovered business domains (e.g., 'BrandSpine', 'CustomerReality') to a summary string."
        )

        try:
             response_text = client.generate(
                  model_name=self.deep_model,
                  prompt=prompt,
                  system_instruction=system_instruction
             )

             # Basic fallback parsing for JSON-like string (mocking a robust structured output parser)
             import json
             import re
             match = re.search(r'\{.*\}', response_text.replace('\n', ''))
             if match:
                 data = json.loads(match.group(0))
                 session.spec.core_ethos = data.get('core_ethos', '')
                 session.spec.domains = data.get('domains', {})

        except Exception as e:
             # Graceful degradation on synthesis failure
             print(f"Synthesis Exception: {e}")
             session.spec.core_ethos = "Synthesis encountered an error and could not be completed."
