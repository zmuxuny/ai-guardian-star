import json
from pathlib import Path
import unittest

from src.guardian_heartbeat import heartbeat_interval, heartbeat_payload, MqttHeartbeatPublisher


class FakeMqttClient:
    def __init__(self, result="published"):
        self.calls = []
        self.result = result

    def publish(self, topic, payload, qos, retain):
        self.calls.append((topic, payload, qos, retain))
        return self.result


class PublishResult:
    def __init__(self, rc):
        self.rc = rc


class GuardianHeartbeatTests(unittest.TestCase):
    def test_production_server_owns_heartbeat_lifecycle(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "ascend_board_server.py").read_text(
            encoding="utf-8")
        self.assertIn("heartbeat_publisher.start()", source)
        self.assertIn("heartbeat_publisher.stop()", source)
        self.assertIn('"ai_guardian/alerts/heartbeat"', source)

    def test_interval_is_bounded(self):
        self.assertEqual(heartbeat_interval("bad"), 10.0)
        self.assertEqual(heartbeat_interval("1"), 5.0)
        self.assertEqual(heartbeat_interval("120"), 60.0)

    def test_payload_reports_process_and_camera_state(self):
        payload = heartbeat_payload(
            "ascend_board",
            7,
            {"cameraConnected": True, "aiRunning": True},
            now=123.456,
        )
        self.assertEqual(payload, {
            "event": "heartbeat",
            "deviceId": "ascend_board",
            "timestamp": 123456,
            "sequence": 7,
            "cameraConnected": True,
            "aiRunning": True,
        })

    def test_publish_uses_existing_authorized_topic_with_qos_one(self):
        client = FakeMqttClient()
        publisher = MqttHeartbeatPublisher(
            client,
            "ai_guardian/alerts/heartbeat",
            "ascend_board",
            lambda: {"cameraConnected": True, "aiRunning": True},
        )

        result = publisher.publish_once(now=10)

        self.assertEqual(result, "published")
        self.assertEqual(len(client.calls), 1)
        topic, raw_payload, qos, retain = client.calls[0]
        self.assertEqual(topic, "ai_guardian/alerts/heartbeat")
        self.assertEqual(qos, 1)
        self.assertFalse(retain)
        self.assertEqual(json.loads(raw_payload)["event"], "heartbeat")

    def test_publish_failure_is_visible_to_the_heartbeat_loop(self):
        publisher = MqttHeartbeatPublisher(
            FakeMqttClient(PublishResult(4)),
            "ai_guardian/alerts/heartbeat",
            "ascend_board",
            lambda: {},
        )

        with self.assertRaisesRegex(RuntimeError, "rc=4"):
            publisher.publish_once(now=10)


if __name__ == "__main__":
    unittest.main()
