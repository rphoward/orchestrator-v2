import os
from typing import Dict, Any, Literal
from pydantic import BaseModel, Field
from Domain.Session.aggregate import InterviewSession
from Infrastructure.Swarm.agents import DomainAgent, GrandSynthesisAgent
from google.genai import types

class RoutingDecision(BaseModel):
    """Structured output expected from the Semantic Router."""
    agent_id: Literal[1, 2, 3, 4] = Field(description="The ID of the specialized agent to handle the user's input: 1 for Brand/Mission, 2 for Founder/Personal Constraints, 3 for Customer/User needs, 4 for Architecture/Tech Stack.")
    reason: str = Field(description="A short explanation of why this agent was chosen.")

class SwarmDispatcher:
    """
    Dispatcher: The semantic load-balancer.
    Manages the OODA+S (Observe, Orient, Decide, Act, Sync) execution loop.
    We inject the native ADK Agents (Muscle/Brain).
    """
    def __init__(self, agents: Dict[int, DomainAgent]):
        self.muscle_agents = agents
        self.brain = GrandSynthesisAgent()

        # If we had access to ADK's native `Router` or `AgentTeam` components,
        # we would initialize them here. Given the current documentation provided,
        # we will use the existing `genai` semantic structured output logic
        # to ensure deterministic mapping, but execute using ADK agents.
        from google import genai
        # Prioritize GEMINI_API_KEY if testing live routing, fallback to GOOGLE_API_KEY
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "mock_key")
        self._client = genai.Client(api_key=api_key)
        self.routing_model = "gemini-3.1-flash-lite-preview"

    async def process_input(self, session: InterviewSession, user_input: str) -> str:
        """
        Executes the OODA+S Loop.
        1. Observe: Ingest the input and session state.
        2. Orient: Load necessary context.
        3. Decide: Use semantic routing.
        4. Act: Execute the prompt using the ADK Muscle Agent.
        5. Sync: Write back to the Domain Entity.
        """
        # 1. Observe
        session_id = session.id
        current_messages = session.messages

        # 2. Orient
        history_context = current_messages[-5:] if current_messages else []

        # 3. Decide (Semantic Routing)
        decision = self._route(user_input, history_context)
        selected_agent_id = decision.agent_id
        selected_agent = self.muscle_agents.get(selected_agent_id)

        if not selected_agent:
            selected_agent_id = 1
            selected_agent = self.muscle_agents.get(1)
            decision.reason = f"Fallback routing due to missing agent {decision.agent_id}"

        session.log_routing_decision(
            input_text=user_input,
            agent_id=selected_agent_id,
            agent_name=selected_agent.name,
            reason=decision.reason
        )

        # 4. Act (Trigger ADK Agent)
        response = await selected_agent.generate_response(user_input, history=history_context)

        # 5. Sync
        session.add_message(agent_id=selected_agent_id, role="user", content=user_input)
        session.add_message(agent_id=selected_agent_id, role="assistant", content=response)

        return response

    def _route(self, user_input: str, history: list) -> RoutingDecision:
        """
        Semantic Router powered by Gemini Structured Outputs.
        """
        if os.environ.get("GEMINI_API_KEY", "mock_key") == "mock_key" and os.environ.get("GOOGLE_API_KEY", "mock_key") == "mock_key":
            lower_input = user_input.lower()
            if "founder" in lower_input or "personal" in lower_input:
                 return RoutingDecision(agent_id=2, reason="Mock routing: Founder keyword detected")
            elif "customer" in lower_input or "user" in lower_input:
                 return RoutingDecision(agent_id=3, reason="Mock routing: Customer keyword detected")
            elif "architecture" in lower_input or "tech" in lower_input or "system" in lower_input:
                 return RoutingDecision(agent_id=4, reason="Mock routing: Architecture keyword detected")
            return RoutingDecision(agent_id=1, reason="Mock routing: Default fallback")

        prompt = (
            "You are the Swarm Dispatcher. Analyze the latest user input and the recent conversation history.\n"
            "Route the input to one of the following Domain Agents:\n"
            "1: Brand Spine (Mission, Vision, Voice, Values)\n"
            "2: Founder Invariants (Personal constraints, time, capital, goals)\n"
            "3: Customer Reality (Target audience, pain points, market)\n"
            "4: Architecture Translation (Tech stack, systems, scalability)\n\n"
        )
        if history:
             prompt += "Recent History:\n"
             for msg in history:
                  prompt += f"{msg.role.upper()}: {msg.content}\n"

        prompt += f"\nLatest User Input: {user_input}\n"

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RoutingDecision,
            temperature=0.0,
        )

        response = self._client.models.generate_content(
            model=self.routing_model,
            contents=prompt,
            config=config,
        )

        import json
        try:
             parsed = json.loads(response.text)
             return RoutingDecision(**parsed)
        except Exception as e:
             return RoutingDecision(agent_id=1, reason=f"Fallback parsing error: {str(e)}")

    async def finalize_session(self, session: InterviewSession) -> str:
        data_dump = ""
        for msg in session.messages:
             data_dump += f"[{msg.role.upper()} - Agent {msg.agent_id}]: {msg.content}\n"

        # Trigger the ADK Brain Agent
        synthesis = await self.brain.synthesize(data_dump)
        return synthesis
