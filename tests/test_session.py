import unittest

from topic_pulse_v2.session import SessionManager, SessionStatus


class SessionTests(unittest.TestCase):
    def test_create_session_activates_by_default(self):
        manager = SessionManager()

        session = manager.create(context={"user_id": "u1"})

        self.assertEqual(session.status, SessionStatus.ACTIVE)
        self.assertEqual(manager.get_context(session.id, "user_id"), "u1")

    def test_context_and_data_can_be_updated(self):
        manager = SessionManager()
        session = manager.create()

        manager.set_context(session.id, "topic", "agent")
        manager.set_data(session.id, "turn_count", 1)

        self.assertEqual(manager.get_context(session.id, "topic"), "agent")
        self.assertEqual(manager.get_data(session.id, "turn_count"), 1)

    def test_valid_and_invalid_state_transitions(self):
        manager = SessionManager()
        session = manager.create()

        paused = manager.transition(session.id, SessionStatus.PAUSED)
        self.assertEqual(paused.status, SessionStatus.PAUSED)

        manager.transition(session.id, SessionStatus.CLOSED)
        with self.assertRaises(ValueError):
            manager.transition(session.id, SessionStatus.ACTIVE)

    def test_list_and_delete_sessions(self):
        manager = SessionManager()
        session = manager.create()

        self.assertEqual(len(manager.list()), 1)
        manager.delete(session.id)

        self.assertEqual(manager.list(), [])


if __name__ == "__main__":
    unittest.main()
