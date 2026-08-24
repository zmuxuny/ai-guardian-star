#!/usr/bin/env python3
"""Hardware-free MQTT event simulator for AI Guardian Star.

The HarmonyOS client classifies events from the ``event`` field of MQTT JSON
payloads. This tool lets contributors exercise that integration without the
physical edge-AI device.

Examples:
    python tools/device_simulator.py fall --dry-run
    python tools/device_simulator.py sequence --dry-run
    python tools/device_simulator.py fall --host 127.0.0.1 --port 1883 --no-tls

For authenticated/TLS brokers, prefer environment variables over command-line
secrets:
    GUARDIAN_MQTT_HOST
    GUARDIAN_MQTT_PORT
    GUARDIAN_MQTT_USERNAME
    GUARDIAN_MQTT_PASSWORD
    GUARDIAN_MQTT_CA_CERT
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_TOPIC = "ai_guardian/alerts/simulator"
EVENTS = ("normal", "fall", "sedentary", "stranger")
SEQUENCE = ("normal", "fall", "normal", "sedentary", "normal", "stranger", "normal")


@dataclass(frozen=True)
class BrokerConfig:
    host: str
    port: int
    topic: str
    username: str | None
    password: str | None
    ca_cert: str | None
    tls: bool


def build_payload(event: str) -> dict[str, object]:
    """Build a payload accepted by ``MqttParser.parseAlert``."""
    if event not in EVENTS:
        raise ValueError(f"unsupported event: {event}")
    return {
        "event": event,
        "source": "ai-guardian-star-simulator",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_id": str(uuid.uuid4()),
    }


def scenario_events(scenario: str) -> Iterable[str]:
    if scenario == "sequence":
        return SEQUENCE
    if scenario not in EVENTS:
        raise ValueError(f"unsupported scenario: {scenario}")
    return (scenario,)


def _optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _broker_config(args: argparse.Namespace) -> BrokerConfig:
    host = args.host or _optional_env("GUARDIAN_MQTT_HOST")
    if not host:
        raise SystemExit(
            "MQTT host is required when publishing. Pass --host or set "
            "GUARDIAN_MQTT_HOST. Use --dry-run if you only want to inspect payloads."
        )

    port_text = str(args.port or _optional_env("GUARDIAN_MQTT_PORT") or (8883 if not args.no_tls else 1883))
    try:
        port = int(port_text)
    except ValueError as exc:
        raise SystemExit(f"invalid MQTT port: {port_text}") from exc

    return BrokerConfig(
        host=host,
        port=port,
        topic=args.topic,
        username=args.username or _optional_env("GUARDIAN_MQTT_USERNAME"),
        password=args.password or _optional_env("GUARDIAN_MQTT_PASSWORD"),
        ca_cert=args.ca_cert or _optional_env("GUARDIAN_MQTT_CA_CERT"),
        tls=not args.no_tls,
    )


def _publish(config: BrokerConfig, payloads: Iterable[dict[str, object]], interval: float) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise SystemExit(
            "Publishing requires paho-mqtt. Install it with "
            "`pip install -r requirements-simulator.txt`."
        ) from exc

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"guardian-sim-{uuid.uuid4().hex[:8]}")
    if config.username:
        client.username_pw_set(config.username, config.password or "")

    if config.tls:
        if not config.ca_cert:
            raise SystemExit(
                "TLS is enabled but no CA certificate was provided. Set "
                "GUARDIAN_MQTT_CA_CERT / --ca-cert, or use --no-tls only for a local development broker."
            )
        ca_path = Path(config.ca_cert).expanduser()
        if not ca_path.is_file():
            raise SystemExit(f"CA certificate not found: {ca_path}")
        client.tls_set(ca_certs=str(ca_path), tls_version=ssl.PROTOCOL_TLS_CLIENT)

    client.connect(config.host, config.port, keepalive=30)
    client.loop_start()
    try:
        for payload in payloads:
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            info = client.publish(config.topic, encoded, qos=1)
            info.wait_for_publish()
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT publish failed with rc={info.rc}")
            print(f"published {config.topic}: {encoded}")
            if interval > 0:
                time.sleep(interval)
    finally:
        client.disconnect()
        client.loop_stop()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=(*EVENTS, "sequence"), help="event or demo sequence to emit")
    parser.add_argument("--dry-run", action="store_true", help="print payloads without connecting to MQTT")
    parser.add_argument("--host", help="MQTT broker host; alternatively set GUARDIAN_MQTT_HOST")
    parser.add_argument("--port", type=int, help="MQTT broker port")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help=f"publish topic (default: {DEFAULT_TOPIC})")
    parser.add_argument("--username", help="MQTT username; prefer GUARDIAN_MQTT_USERNAME")
    parser.add_argument("--password", help="MQTT password; prefer GUARDIAN_MQTT_PASSWORD")
    parser.add_argument("--ca-cert", help="CA certificate path; prefer GUARDIAN_MQTT_CA_CERT")
    parser.add_argument(
        "--no-tls",
        action="store_true",
        help="disable TLS for a local development broker; do not use for production",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between sequence events")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payloads = [build_payload(event) for event in scenario_events(args.scenario)]

    if args.dry_run:
        for payload in payloads:
            print(json.dumps(payload, ensure_ascii=False))
        return 0

    config = _broker_config(args)
    _publish(config, payloads, max(0.0, args.interval))
    return 0


if __name__ == "__main__":
    sys.exit(main())
