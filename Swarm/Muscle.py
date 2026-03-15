from google.adk.agents.llm_agent import Agent

class MuscleFactory:
    """
    Muscle (Hydrators / Domain Agents).
    Uses google-adk native Agent functionality.
    """
    @staticmethod
    def create_muscle(domain_name: str) -> Agent:
        return Agent(
            model='gemini-3.1-flash-lite-preview',
            name=f'muscle_{domain_name.lower()}',
            description=f"Rapid extraction agent for the {domain_name} domain.",
            instruction=(
                f"You are a fast, rapid extraction Domain Agent for the '{domain_name}' domain. "
                "Use the provided context to triage the founder's input and generate exactly one concise, "
                "follow-up question for the business consultant to ask."
            )
        )
