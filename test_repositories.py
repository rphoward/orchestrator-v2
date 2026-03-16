import unittest
import os
from datetime import datetime, UTC
from Domain.Session.aggregate import InterviewSession
from Infrastructure.Repositories.sqlite_session_repo import SQLiteSessionRepository, SQLiteAgentRepository
from database import init_db, seed_agents

class TestSQLiteRepositories(unittest.TestCase):
    def setUp(self):
        # Ensure schema and seeded agents are ready
        init_db()
        seed_agents()
        self.session_repo = SQLiteSessionRepository()
        self.agent_repo = SQLiteAgentRepository()

    def test_agent_repository_loads_prompts(self):
        # Fetch the Brand Spine Agent and its prompt
        agent = self.agent_repo.get_by_id(1)
        self.assertIsNotNone(agent)
        self.assertEqual(agent.name, "Brand Spine")

        prompt_content = self.agent_repo.get_system_prompt_for_agent(1)
        # Verify it actually loaded a real markdown file from the prompts directory
        self.assertIn("THE BRAND SPINE EXTRACTION", prompt_content)
        self.assertTrue(len(prompt_content) > 100)

    def test_session_repository_aggregate_persistence(self):
        # 1. Create a pure Python Domain Entity
        session = InterviewSession(name="DDD Persistence Test")
        session.add_message(agent_id=1, role="user", content="Hello, Brand Spine")
        session.add_message(agent_id=1, role="assistant", content="Hello founder.")
        session.log_routing_decision("Hello, Brand Spine", 1, "Brand Spine", "Routed to 1")

        # 2. Save the Aggregate Root
        saved_session = self.session_repo.save(session)
        self.assertIsNotNone(saved_session.id)

        # 3. Rehydrate the Aggregate Root
        rehydrated_session = self.session_repo.get_by_id(saved_session.id)

        # 4. Verify pure properties mapping
        self.assertEqual(rehydrated_session.name, "DDD Persistence Test")
        self.assertEqual(len(rehydrated_session.messages), 2)
        self.assertEqual(len(rehydrated_session.routing_logs), 1)

        self.assertEqual(rehydrated_session.messages[0].content, "Hello, Brand Spine")
        self.assertEqual(rehydrated_session.routing_logs[0].reason, "Routed to 1")

        # 5. Verify the date mapping (timezone-aware datetimes)
        self.assertTrue(isinstance(rehydrated_session.created_at, datetime))

        # 6. Delete the Aggregate
        self.session_repo.delete(saved_session.id)
        self.assertIsNone(self.session_repo.get_by_id(saved_session.id))

if __name__ == '__main__':
    unittest.main()
