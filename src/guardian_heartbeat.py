"""Periodic MQTT heartbeat for reporting board process and camera health."""

import json
import threading
import time


DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 10.0
MIN_HEARTBEAT_INTERVAL_SECONDS = 5.0
MAX_HEARTBEAT_INTERVAL_SECONDS = 60.0


def heartbeat_interval(value):
    """Parse and bound the configured heartbeat interval."""
    try:
        interval = float(value)
    except (TypeError, ValueError):
        return DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    return min(MAX_HEARTBEAT_INTERVAL_SECONDS,
               max(MIN_HEARTBEAT_INTERVAL_SECONDS, interval))


def heartbeat_payload(device_id, sequence, status, now=None):
    """Build the stable JSON contract consumed by the HarmonyOS client."""
    status = status if isinstance(status, dict) else {}
    current_time = time.time() if now is None else float(now)
    return {
        "event": "heartbeat",
        "deviceId": str(device_id),
        "timestamp": int(current_time * 1000),
        "sequence": int(sequence),
        "cameraConnected": bool(status.get("cameraConnected", False)),
        "aiRunning": bool(status.get("aiRunning", False)),
    }


class MqttHeartbeatPublisher:
    """Publish immediately, then periodically until explicitly stopped."""

    def __init__(self, client, topic, device_id, status_provider,
                 interval_seconds=DEFAULT_HEARTBEAT_INTERVAL_SECONDS):
        self.client = client
        self.topic = topic
        self.device_id = device_id
        self.status_provider = status_provider
        self.interval_seconds = heartbeat_interval(interval_seconds)
        self._sequence = 0
        self._stop = threading.Event()
        self._thread = None

    def publish_once(self, now=None):
        self._sequence += 1
        try:
            status = self.status_provider()
        except Exception:
            status = {}
        payload = heartbeat_payload(self.device_id, self._sequence, status, now=now)
        result = self.client.publish(
            self.topic,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            qos=1,
            retain=False,
        )
        result_code = getattr(result, "rc", 0)
        if result_code != 0:
            raise RuntimeError(f"MQTT publish returned rc={result_code}")
        return result

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="mqtt-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=min(self.interval_seconds, 2.0))
        self._thread = None

    def _run(self):
        while not self._stop.is_set():
            try:
                self.publish_once()
            except Exception as exc:
                print(f"[MQTT] heartbeat publish failed: {type(exc).__name__}")
            self._stop.wait(self.interval_seconds)
