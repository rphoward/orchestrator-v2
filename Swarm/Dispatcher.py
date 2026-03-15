from Swarm.Muscle import MuscleFactory
from Swarm.Brain import BrainFactory
from google.adk.agents.llm_agent import Agent

class DispatcherFactory:
    """
    Dispatcher (The Swarm Router).
    Utilizes the ADK framework to define the root agent and manage sub-agents/tools.
    """
    @staticmethod
    def create_swarm() -> Agent:
        brand_muscle = MuscleFactory.create_muscle("BrandSpine")
        customer_muscle = MuscleFactory.create_muscle("CustomerReality")
        tech_muscle = MuscleFactory.create_muscle("Technical")
        general_muscle = MuscleFactory.create_muscle("General")

        brain = BrainFactory.create_brain()

        return Agent(
            name="dispatcher_root",
            model="gemini-3.1-flash-lite-preview",
            description="The semantic load-balancer for the founder interview session.",
            instruction=(
                "You are the Swarm Dispatcher. Your job is to analyze the founder's input "
                "and pass control to the correct Domain Agent (Muscle) to generate the next question. "
                "If the session is explicitly marked as final, pass control to the brain_synthesizer."
            ),
            sub_agents=[
                brand_muscle,
                customer_muscle,
                tech_muscle,
                general_muscle,
                brain
            ]
        )
