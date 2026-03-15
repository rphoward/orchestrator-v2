import os
import unittest
from unittest.mock import patch, MagicMock
from Domain.Session.aggregate import InterviewSession
from Infrastructure.Swarm.agents import DomainAgent, GrandSynthesisAgent
from Infrastructure.Swarm.dispatcher import SwarmDispatcher, RoutingDecision
from google.genai import types

class TestSemanticDispatcher(unittest.TestCase):
    def setUp(self):
        # 1. Initialize the Pure Domain Entity
        self.session = InterviewSession(name="Test Swarm Session")

        # 2. Setup Swarm Infrastructure (Muscle Agents)
        self.agents = {
            1: DomainAgent(agent_id=1, name="Brand Spine", system_prompt="You are Brand Spine."),
            2: DomainAgent(agent_id=2, name="Founder Invariants", system_prompt="You are Founder."),
            3: DomainAgent(agent_id=3, name="Customer Reality", system_prompt="You are Customer."),
            4: DomainAgent(agent_id=4, name="Architecture", system_prompt="You are Architecture.")
        }

        # 3. Setup Dispatcher
        self.dispatcher = SwarmDispatcher(agents=self.agents)

    def test_semantic_routing_fallback_mock(self):
        # Even without an API key, the mock behavior should correctly route and protect invariants
        user_input = "I want to build a brand that focuses on minimalism."
        response = self.dispatcher.process_input(self.session, user_input)

        self.assertEqual(len(self.session.messages), 2)
        self.assertEqual(len(self.session.routing_logs), 1)
        self.assertEqual(self.session.routing_logs[0].agent_id, 1) # Default mock fallback for 'brand'
        self.assertIn("MOCK Brand Spine", response)

    @patch('google.genai.models.Models.generate_content')
    def test_semantic_routing_live_structured_output(self, mock_generate_content):
        # Set a fake API key to trigger the live LLM logic path instead of the mock fallback
        os.environ["GEMINI_API_KEY"] = "fake_key_for_test"

        # Mock the LLM returning a structured JSON response saying it routed to Agent 3 (Customer)
        # Note: Since the DomainAgent *also* calls generate_content (which is patched globally here),
        # we need to make side_effect return the routing decision FIRST, and then the agent response SECOND.
        mock_routing_response = MagicMock()
        mock_routing_response.text = '{"agent_id": 3, "reason": "User is asking about their target audience."}'

        mock_agent_response = MagicMock()
        mock_agent_response.text = "[MOCK Customer Reality] Validated response."

        mock_generate_content.side_effect = [mock_routing_response, mock_agent_response]

        # Use an input that specifically targets Customer Reality
        user_input = "Our primary users are enterprise IT managers dealing with legacy systems."
        response = self.dispatcher.process_input(self.session, user_input)

        # Verify the Domain Entity State correctly captured the routing decision
        self.assertEqual(len(self.session.routing_logs), 1)

        log = self.session.routing_logs[0]
        self.assertEqual(log.agent_id, 3)
        self.assertEqual(log.agent_name, "Customer Reality")
        self.assertEqual(log.reason, "User is asking about their target audience.")

        # Verify that the generated response correctly came from the mocked Client using Agent 3
        self.assertIn("MOCK Customer Reality", response)

        # Cleanup
        del os.environ["GEMINI_API_KEY"]

if __name__ == '__main__':
    unittest.main()
