import os
import unittest
from unittest.mock import patch, MagicMock
from Domain.Session.aggregate import InterviewSession
from Infrastructure.Swarm.agents import DomainAgent, GrandSynthesisAgent
from Infrastructure.Swarm.dispatcher import SwarmDispatcher, RoutingDecision
from google.genai import types

import asyncio

class TestSemanticDispatcher(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # 1. Initialize the Pure Domain Entity
        self.session = InterviewSession(name="Test Swarm Session")

        # 2. Setup Swarm Infrastructure (Muscle Agents)
        # Note: ADK agent names must be valid python identifiers (no spaces)
        # Using a mock repository to simulate loading real prompts
        from Infrastructure.Repositories.sqlite_session_repo import SQLiteAgentRepository

        self.repo = SQLiteAgentRepository()

        # Ensure database is initialized before tests access the repo
        from database import init_db, seed_agents
        init_db()
        seed_agents()

        # We manually fetch the prompts from the actual prompts directory for the test
        brand_prompt = self.repo.get_system_prompt_for_agent(1)
        founder_prompt = self.repo.get_system_prompt_for_agent(2)
        customer_prompt = self.repo.get_system_prompt_for_agent(3)
        architecture_prompt = self.repo.get_system_prompt_for_agent(4)

        self.agents = {
            1: DomainAgent(agent_id=1, name="brand_spine", system_prompt=brand_prompt),
            2: DomainAgent(agent_id=2, name="founder_invariants", system_prompt=founder_prompt),
            3: DomainAgent(agent_id=3, name="customer_reality", system_prompt=customer_prompt),
            4: DomainAgent(agent_id=4, name="architecture_translation", system_prompt=architecture_prompt)
        }

        # 3. Setup Dispatcher
        self.dispatcher = SwarmDispatcher(agents=self.agents)

    async def test_semantic_routing_fallback_mock(self):
        # Even without an API key, the mock behavior should correctly route and protect invariants
        user_input = "I want to build a brand that focuses on minimalism."
        response = await self.dispatcher.process_input(self.session, user_input)

        self.assertEqual(len(self.session.messages), 2)
        self.assertEqual(len(self.session.routing_logs), 1)
        self.assertEqual(self.session.routing_logs[0].agent_id, 1) # Default mock fallback for 'brand'
        self.assertIn("MOCK brand_spine", response)

    @patch('google.genai.models.Models.generate_content')
    async def test_semantic_routing_live_structured_output(self, mock_generate_content):
        # Set a fake API key to trigger the live LLM logic path instead of the mock fallback
        os.environ["GEMINI_API_KEY"] = "fake_key_for_test"

        # Mock the LLM returning a structured JSON response saying it routed to Agent 3 (Customer)
        mock_routing_response = MagicMock()
        mock_routing_response.text = '{"agent_id": 3, "reason": "User is asking about their target audience."}'

        # Mock the ADK async run method directly to avoid complex mocking of the native SDK streams
        with patch('Infrastructure.Swarm.agents.DomainAgent.run_async') as mock_run_async:
            async def mock_stream():
                class MockPart:
                    text = "[MOCK customer_reality] Validated response."
                class MockModelResponse:
                    parts = [MockPart()]
                class MockEvent:
                    model_response = MockModelResponse()
                yield MockEvent()

            mock_run_async.return_value = mock_stream()
            mock_generate_content.return_value = mock_routing_response

            # Use an input that specifically targets Customer Reality
            user_input = "Our primary users are enterprise IT managers dealing with legacy systems."
            response = await self.dispatcher.process_input(self.session, user_input)

        # Verify the Domain Entity State correctly captured the routing decision
        self.assertEqual(len(self.session.routing_logs), 1)

        log = self.session.routing_logs[0]
        self.assertEqual(log.agent_id, 3)
        self.assertEqual(log.agent_name, "customer_reality")
        self.assertEqual(log.reason, "User is asking about their target audience.")

        # Verify that the generated response correctly came from the mocked Client using Agent 3
        self.assertIn("MOCK customer_reality", response)

        # Cleanup
        del os.environ["GEMINI_API_KEY"]

if __name__ == '__main__':
    unittest.main()
