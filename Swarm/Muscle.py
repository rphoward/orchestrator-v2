from Infrastructure.LLMClients.GeminiClient import GeminiClient
from Domain.Entities.InterviewSession import InterviewSession
import os

class Muscle:
    """
    Muscle (Hydrators / Domain Agents).
    Operates on fast models (flash-lite) to execute rapid extraction and triaging.
    """
    def __init__(self):
        self.fast_model = "gemini-1.5-flash"  # As defined in gemini.md

    def act(self, session: InterviewSession, domain_need: str, context: str, user_input: str) -> str:
        """
        Executes the fast prompt and generates the next question for the consultant.
        """
        # Load the Gemini Client to use the genai SDK
        client = GeminiClient()

        system_instruction = (
            f"You are a fast, rapid extraction Domain Agent for the '{domain_need}' domain. "
            "Use the provided context to triage the founder's input and generate exactly one concise, "
            "follow-up question for the business consultant to ask."
        )

        prompt = (
            f"{context}\n\n"
            f"Founder Input: {user_input}\n\n"
            "Action: Output ONLY the follow-up question."
        )

        try:
             response_text = client.generate(
                  model_name=self.fast_model,
                  prompt=prompt,
                  system_instruction=system_instruction
             )
             return response_text.strip()
        except Exception as e:
             # Follow graceful degradation guidelines
             return "I see. Could you elaborate more on that point regarding your business?"
