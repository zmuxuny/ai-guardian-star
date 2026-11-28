import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from datetime import date, time, timedelta
from pathlib import Path
from uuid import UUID

from tools import late_wakeup_demo as demo


class LateWakeupDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        path = Path(directory.name)
        demo.generate_fixtures(path)
        cls.history = demo.read_samples(path / "history.csv")
        cls.scenarios = {
            name: demo.read_samples(path / f"{name}.csv") for name in demo.SCENARIOS
        }
        cls.typical, cls.history_days = demo.typical_departure(cls.history)
        cls.late_day = date(2026, 11, 24)

    def test_training_has_14_complete_days_and_excludes_evaluation(self):
        daily_counts = Counter(timestamp.date() for timestamp in self.history)
        self.assertEqual(len(daily_counts), 14)
        self.assertEqual(set(daily_counts.values()), {24 * 60 // 5})
        for day in daily_counts:
            expected = {
                demo.at(day, time()) + timedelta(minutes=5 * index) for index in range(288)
            }
            self.assertTrue(expected <= self.history.keys())
        dates = [next(iter(samples)).date() for samples in self.scenarios.values()]
        self.assertEqual(len(set(dates)), 3)
        self.assertTrue(set(dates).isdisjoint(daily_counts))
        self.assertEqual((self.typical, self.history_days), (time(7), 14))

    def test_three_independent_replays(self):
        for name, expected in (("normal", 0), ("late", 1), ("missing", 0)):
            with self.subTest(name=name):
                result = demo.replay_day(self.scenarios[name], self.typical)
                self.assertEqual(int(result.reminder is not None), expected)
                self.assertEqual(int(result.prompt is not None), expected)

    def test_v5_payload_and_same_identity_until_departure(self):
        result = demo.replay_day(self.scenarios["late"], self.typical)
        event_id = result.reminder["event_id"]
        self.assertEqual(str(UUID(event_id)), event_id)
        self.assertEqual(result.reminder, {
            "schema_version": "2",
            "event_id": event_id,
            "alert_type": "late_wakeup",
            "timestamp": "2026-11-24T08:30:00+08:00",
            "expires_at": "2026-11-24T08:32:00+08:00",
            "reason": "平时约 07:00 离开床区，今天 08:30 仍在床区。",
        })
        expected_slots = {
            demo.at(self.late_day, time(8, minute)): event_id for minute in range(30, 60, 5)
        }
        self.assertEqual(result.active_event_ids, expected_slots)
        self.assertEqual(demo.replay_day(self.scenarios["late"], self.typical), result)

    def test_expiration_uses_replayed_seconds_and_excludes_the_cutoff(self):
        reminder = demo.replay_day(self.scenarios["late"], self.typical).reminder
        expectations = ((time(8, 30), True), (time(8, 31, 59), True), (time(8, 32), False))
        for clock_time, expected in expectations:
            with self.subTest(time=clock_time):
                prompt = demo.mock_prompt(reminder, demo.at(self.late_day, clock_time))
                self.assertEqual(prompt is not None, expected)

    def test_missing_or_absent_before_trigger_suppresses_reminder(self):
        point = demo.at(self.late_day, time(8, 25))
        samples = self.scenarios["late"].copy()
        observation = samples.pop(point)
        self.assertIsNone(demo.replay_day(samples, self.typical).reminder)
        samples[point] = replace(observation, state="absent")
        self.assertIsNone(demo.replay_day(samples, self.typical).reminder)

    def test_discovered_baseline_moves_the_trigger(self):
        previous_day = date(2026, 10, 31)
        history = {
            sample.timestamp: sample for sample in demo.simulate_day(previous_day, time(7, 10))
        }
        typical, _ = demo.typical_departure(history)
        result = demo.replay_day(self.scenarios["late"], typical)
        self.assertEqual(result.reminder["timestamp"], "2026-11-24T08:40:00+08:00")


if __name__ == "__main__":
    unittest.main()
