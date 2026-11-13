"""Hardware-independent state shared by the board service and offline checks."""

import math


def create_mqtt_client(mqtt, client_id):
    """Use callback v2 when available, while supporting board images with Paho 1.x."""
    options = {"client_id": client_id}
    if hasattr(mqtt, "CallbackAPIVersion"):
        options["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
    return mqtt.Client(**options)


class StationaryTimer:
    """Measure continuous stillness independently of the short fall-motion history."""

    def __init__(self, pixel_threshold=20, max_gap=4.0):
        self.pixel_threshold = pixel_threshold
        self.max_gap = max_gap
        self.reset()

    def reset(self):
        self.anchor = None
        self.since = None
        self.last_seen = None
        self.samples = 0

    def update(self, box, now_ts):
        width = max(1.0, box[2] - box[0])
        height = max(1.0, box[3] - box[1])
        if height / width <= 0.45:
            self.reset()
            return
        center = ((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5)
        threshold = max(self.pixel_threshold, height * 0.12)
        interrupted = (self.last_seen is not None
                       and not 0 <= now_ts - self.last_seen <= self.max_gap)
        moved = (self.anchor is not None
                 and math.hypot(center[0] - self.anchor[0],
                                center[1] - self.anchor[1]) > threshold)
        if self.anchor is None or interrupted or moved:
            self.anchor = center
            self.since = now_ts
            self.samples = 0
        self.last_seen = now_ts
        self.samples += 1

    def duration(self, now_ts):
        if (self.since is None or self.samples < 2 or self.last_seen is None
                or not 0 <= now_ts - self.last_seen <= self.max_gap):
            return 0.0
        return max(0.0, now_ts - self.since)


class AlertEpisodeTracker:
    """Count one event per person and continuous episode, allowing brief missed detections."""

    def __init__(self, max_gap=4.0):
        self.max_gap = max_gap
        self.active = {}

    def update(self, alerts, now_ts):
        events = {"fall": [], "sit": [], "stranger": []}
        visible = {alert["id"]: alert for alert in alerts}
        current = {}
        for alert in alerts:
            kinds = []
            if "FALL" in alert.get("status", ""):
                kinds.append("fall")
            if alert.get("is_sitting"):
                kinds.append("sit")
            if alert.get("face_label") == "stranger":
                kinds.append("stranger")
            for kind in kinds:
                current[(kind, alert["id"])] = alert

        for key, last_seen in list(self.active.items()):
            person = visible.get(key[1])
            uncertain_identity = (key[0] == "stranger" and person is not None
                                  and not str(person.get("face_label", "")).startswith("known:"))
            if ((person is not None and key not in current and not uncertain_identity)
                    or not 0 <= now_ts - last_seen <= self.max_gap):
                del self.active[key]
            elif person is not None:
                self.active[key] = now_ts
        for key, alert in current.items():
            if key not in self.active:
                events[key[0]].append(alert)
            self.active[key] = now_ts
        return events
