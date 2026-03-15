import unittest
import json
import asyncio
from Domain.Entities.InterviewSession import InterviewSession, Message
from Infrastructure.Repositories.SQLiteSessionRepository import SQLiteSessionRepository
from Swarm.Memory import ContextCompiler
from Swarm.Dispatcher import DispatcherFactory
from google.adk.agents.llm_agent import Agent

class TestV2Architecture(unittest.TestCase):
    def setUp(self):
        self.repo = SQLiteSessionRepository()

    def test_entity_creation(self):
        session = InterviewSession()
        session.add_message("founder", "We are building an AI company.")
        self.assertEqual(len(session.messages), 1)
        self.assertEqual(session.messages[0].content, "We are building an AI company.")

    def test_repository_save_and_find(self):
        session = InterviewSession(id=0)
        session.add_message("founder", "Test DB.")
        self.repo.save(session)

        found = self.repo.find_by_id(session.id)
        self.assertIsNotNone(found)
        self.assertEqual(len(found.messages), 1)
        self.assertEqual(found.messages[0].content, "Test DB.")

        self.repo.delete(session.id)

    def test_adk_dispatcher_creation(self):
        dispatcher = DispatcherFactory.create_swarm()
        self.assertIsInstance(dispatcher, Agent)
        self.assertEqual(dispatcher.name, "dispatcher_root")
        self.assertEqual(len(dispatcher.sub_agents), 5)
        self.assertEqual(dispatcher.sub_agents[-1].name, "brain_synthesizer")

if __name__ == '__main__':
    unittest.main()
