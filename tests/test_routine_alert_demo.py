import tempfile
import unittest
from datetime import date, time, timedelta
from pathlib import Path

from tools import late_wakeup_demo as replay
from tools import routine_alert_demo as routine


class RoutineAlertDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.directory = Path(directory.name)
        routine.generate(cls.directory)
        cls.typical, _ = replay.typical_departure(replay.read_samples(cls.directory / "history.csv"))

    def detect(self, scenario):
        samples = replay.read_samples(self.directory / f"routine-{scenario}.csv")
        return routine.detect(samples, self.typical)

    def test_default_scenarios_and_rule_boundaries(self):
        expected = {
            "late_wakeup": "2026-11-24T08:30:00+08:00",
            routine.DAYTIME_INACTIVITY: "2026-11-24T15:00:00+08:00",
            routine.NIGHT_BATHROOM_STAY: "2026-11-25T00:00:00+08:00",
        }
        self.assertEqual(self.detect("normal"), [])
        self.assertEqual(self.detect("missing"), [])
        ids = set()
        for scenario, timestamp in expected.items():
            with self.subTest(scenario=scenario):
                alerts = self.detect(scenario)
                self.assertEqual(len(alerts), 1)
                alert = alerts[0]
                self.assertEqual(alert["timestamp"], timestamp)
                self.assertEqual(alert["alert_type"], scenario)
                self.assertEqual(alert["schema_version"], "2")
                self.assertEqual(replay.read_timestamp(alert["expires_at"]) - replay.read_timestamp(timestamp),
                                 timedelta(seconds=120))
                self.assertEqual(self.detect(scenario), alerts)
                ids.add(alert["event_id"])
        self.assertEqual(len(ids), 3)

    def test_gap_cannot_rearm_until_a_confirmed_exit(self):
        start = replay.at(date(2026, 11, 24), time(22))
        rows = [
            replay.Observation(start + timedelta(minutes=minute), "bathroom", "standing")
            for minute in range(0, 120, 5)
            if minute != 35
        ]
        rows.append(replay.Observation(start + timedelta(minutes=120), "living_room", "standing"))
        rows.extend(
            replay.Observation(start + timedelta(minutes=minute), "bathroom", "standing")
            for minute in range(125, 166, 5)
        )
        alerts = routine.detect({row.timestamp: row for row in rows}, self.typical)
        self.assertEqual([alert["timestamp"] for alert in alerts],
                         ["2026-11-24T22:30:00+08:00", "2026-11-25T00:35:00+08:00"])
        self.assertNotEqual(alerts[0]["event_id"], alerts[1]["event_id"])

    def test_absent_observation_breaks_the_proof(self):
        start = replay.at(date(2026, 11, 24), time(22))
        rows = [
            replay.Observation(start + timedelta(minutes=minute), "bathroom",
                               "absent" if minute == 15 else "standing")
            for minute in range(0, 46, 5)
        ]
        self.assertEqual(list(routine.episodes(rows, routine.nighttime_bathroom, timedelta(minutes=30))), [])

    def test_mqtt_preserves_event_identity_and_time_and_preview_reanchors(self):
        reminder, = self.detect("late_wakeup")
        body = routine.mqtt_payload(reminder)
        self.assertEqual(body, {
            "event": "routine_alert", "schema_version": "2", "event_id": reminder["event_id"],
            "alert_type": reminder["alert_type"], "timestamp": reminder["timestamp"], "reason": reminder["reason"],
        })
        wall = replay.at(date(2027, 1, 4), time(14))
        preview = routine.mqtt_payload(reminder, wall)
        self.assertEqual(preview["timestamp"], wall.isoformat())
        self.assertTrue(preview["reason"].startswith("模拟样例"))
        self.assertNotEqual(preview["event_id"], body["event_id"])
        self.assertEqual(routine.mqtt_payload(reminder), body)


if __name__ == "__main__":
    unittest.main()
