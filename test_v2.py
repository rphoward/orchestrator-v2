import unittest
import json
from Domain.Entities.InterviewSession import InterviewSession, Message
from Infrastructure.Repositories.SQLiteSessionRepository import SQLiteSessionRepository
from Swarm.Memory import ContextCompiler
from Swarm.Dispatcher import Dispatcher
from Swarm.Muscle import Muscle
from Swarm.Brain import Brain

class TestV2Architecture(unittest.TestCase):
    def setUp(self):
        self.repo = SQLiteSessionRepository()

    def test_entity_creation(self):
        session = InterviewSession()
        session.add_message("founder", "We are building an AI company.")
        self.assertEqual(len(session.messages), 1)
        self.assertEqual(session.messages[0].content, "We are building an AI company.")

    def test_repository_save_and_find(self):
        session = InterviewSession(id=0)  # Explicitly set ID to 0 for a new autoincrement
        session.add_message("founder", "Test DB.")
        self.repo.save(session)

        found = self.repo.find_by_id(session.id)
        self.assertIsNotNone(found)
        self.assertEqual(len(found.messages), 1)
        self.assertEqual(found.messages[0].content, "Test DB.")

        self.repo.delete(session.id)

    def test_dispatcher_routing_logic(self):
        mem = ContextCompiler()
        dispatcher = Dispatcher(mem, Muscle(), Brain())

        domain_need = dispatcher.decide_domain("Our customer base is growing.")
        self.assertEqual(domain_need, "CustomerReality")

        domain_need2 = dispatcher.decide_domain("The tech stack uses python.")
        self.assertEqual(domain_need2, "Technical")

if __name__ == '__main__':
    unittest.main()
