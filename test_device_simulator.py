import unittest

from tools.device_simulator import EVENTS, SEQUENCE, build_payload, scenario_events


class DeviceSimulatorTest(unittest.TestCase):
    def test_payload_matches_client_parser_contract(self):
        payload = build_payload("fall")
        self.assertEqual(payload["event"], "fall")
        self.assertEqual(payload["source"], "ai-guardian-star-simulator")
        self.assertIn("timestamp", payload)
        self.assertIn("message_id", payload)

    def test_all_single_event_scenarios(self):
        for event in EVENTS:
            self.assertEqual(tuple(scenario_events(event)), (event,))

    def test_sequence_contains_recovery_states(self):
        self.assertEqual(tuple(scenario_events("sequence")), SEQUENCE)
        self.assertGreaterEqual(SEQUENCE.count("normal"), 2)
        self.assertIn("fall", SEQUENCE)
        self.assertIn("sedentary", SEQUENCE)
        self.assertIn("stranger", SEQUENCE)

    def test_unknown_event_is_rejected(self):
        with self.assertRaises(ValueError):
            build_payload("unknown")
        with self.assertRaises(ValueError):
            tuple(scenario_events("unknown"))


if __name__ == "__main__":
    unittest.main()
