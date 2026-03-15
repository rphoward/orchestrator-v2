from Domain.Entities.InterviewSession import InterviewSession, Message
from Infrastructure.Repositories.SessionRepository import SessionRepository
from Swarm.Dispatcher import DispatcherFactory
from Swarm.Memory import ContextCompiler
import json
import asyncio
from typing import Tuple

class ExecutionLoop:
    """
    The formal OODA+S loop handling founder inputs.
    Replaces the V1 'Route and Send' function.
    Leverages the google-adk Agent.run_async() for true swarm execution.
    """

    def __init__(self, repository: SessionRepository):
        self.repository = repository
        self.memory = ContextCompiler()
        self.swarm_root = DispatcherFactory.create_swarm()

    async def _run_swarm(self, session: InterviewSession, user_input: str, is_final: bool) -> Tuple[str, str]:
        # Orient: Get context
        context = self.memory.retrieve_context(session, "General")

        if is_final:
            prompt = f"FINAL SYNTHESIS REQUIRED.\nContext:\n{context}\n\nPlease transfer control to the brain_synthesizer to output the JSON spec."
        else:
            prompt = f"Context:\n{context}\n\nFounder Input: {user_input}\n\nPlease analyze this input and transfer control to the appropriate muscle agent to generate exactly one follow-up question."

        try:
            # Using the google-adk run_async to let the root agent automatically decide
            # and transfer to the correct sub-agent.
            result = await self.swarm_root.run_async(prompt)
            # Find the name of the final agent that answered
            agent_name = "dispatcher_root"
            if result.message and result.message.agent_name:
                agent_name = result.message.agent_name

            return result.message.content, agent_name
        except Exception as e:
            if is_final:
                return '{"core_ethos": "Error synthesizing", "domains": {}}', "brain_synthesizer"
            return f"Swarm encountered an error: {str(e)}", "dispatcher_root"

    def process_input(self, session_id: int, founder_statement: str, is_final: bool = False) -> Tuple[str, str]:
        """
        Executes the OODA+S loop for a single turn of conversation.
        Returns a tuple: (response_text, agent_name)
        """
        # 1. Observe
        session = None
        if session_id > 0:
             session = self.repository.find_by_id(session_id)

        if not session:
            session = InterviewSession(id=0)

        founder_msg = Message(role="founder", content=founder_statement)
        session.add_message("founder", founder_statement)

        self.memory.index_new_message(session, founder_msg)

        # 2. Orient, 3. Decide, 4. Act
        response_text, agent_name = asyncio.run(self._run_swarm(session, founder_statement, is_final))

        if is_final:
            try:
                import re
                match = re.search(r'\{.*\}', response_text.replace('\n', ''))
                if match:
                    data = json.loads(match.group(0))
                    session.spec.core_ethos = data.get('core_ethos', '')
                    session.spec.domains = data.get('domains', {})
            except Exception as e:
                session.spec.core_ethos = "Failed to parse spec."
        else:
            consultant_msg = Message(role="consultant", content=response_text)
            session.add_message("consultant", response_text)
            self.memory.index_new_message(session, consultant_msg)

        # 5. Sync
        self.repository.save(session)

        return response_text, agent_name

    def get_swarm_agents(self) -> list:
        """Returns the dynamically defined agents in the Swarm."""
        agents_data = []
        agents_data.append({
            "id": 0,
            "name": self.swarm_root.name,
            "role": "Dispatcher",
            "model": self.swarm_root.model,
            "prompt": self.swarm_root.instruction
        })

        for idx, agent in enumerate(self.swarm_root.sub_agents, 1):
             role = "Synthesis" if "brain" in agent.name else "Extraction"
             agents_data.append({
                 "id": idx,
                 "name": agent.name,
                 "role": role,
                 "model": agent.model,
                 "prompt": agent.instruction
             })
        return agents_data
