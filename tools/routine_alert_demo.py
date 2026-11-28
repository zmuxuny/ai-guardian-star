"""用作息 CSV 产生三类 v5 提醒，可生成或发布 App MQTT 样例。"""

import argparse
import json
import sys
import tempfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

if __package__:
    from . import late_wakeup_demo as replay
else:
    import late_wakeup_demo as replay


DAYTIME_INACTIVITY = "daytime_inactivity"
NIGHT_BATHROOM_STAY = "night_bathroom_stay"
ALERT_TYPES = ("late_wakeup", DAYTIME_INACTIVITY, NIGHT_BATHROOM_STAY)
MQTT_TOPIC = "ai_guardian/alerts/routine"


def episodes(
    samples: Iterable[replay.Observation],
    matching_zone: Callable[[replay.Observation], str | None],
    duration: timedelta,
) -> Iterator[datetime]:
    """连续证据用来触发，已触发后需有确认离开或恢复活动才能重新提醒。"""
    previous = None
    zone = None
    since = None
    alerted = False
    for sample in sorted(samples, key=lambda row: row.timestamp):
        now = sample.timestamp
        if previous is not None and now - previous != replay.SAMPLE_INTERVAL:
            since = None
        previous = now
        if sample.state == "absent" or sample.zone == "unknown":
            since = None
            continue
        matched = matching_zone(sample)
        if matched != zone:
            zone, since, alerted = matched, None, False
        if zone is None:
            continue
        if since is None:
            since = now
        if not alerted and now - since >= duration:
            alerted = True
            yield now


def daytime_zone(sample: replay.Observation) -> str | None:
    if time(9) <= sample.timestamp.time() < time(20) and sample.state in {"sitting", "lying"}:
        return sample.zone
    return None


def nighttime_bathroom(sample: replay.Observation) -> str | None:
    clock = sample.timestamp.time()
    if sample.zone == "bathroom" and (clock >= time(22) or clock < time(6)):
        return sample.zone
    return None


def detect(
    samples: dict[datetime, replay.Observation], typical: time
) -> list[dict[str, str]]:
    by_day: dict[date, dict[datetime, replay.Observation]] = {}
    for timestamp, sample in samples.items():
        by_day.setdefault(timestamp.date(), {})[timestamp] = sample

    alerts = []
    for day in by_day.values():
        result = replay.replay_day(day, typical)
        if result.reminder:
            alerts.append(result.reminder)
    for now in episodes(samples.values(), daytime_zone, timedelta(hours=2)):
        alerts.append(replay.routine_reminder(
            DAYTIME_INACTIVITY, now, "白天在同一区域连续观测到坐姿或躺姿，已满 120 分钟。"
        ))
    for now in episodes(samples.values(), nighttime_bathroom, timedelta(minutes=30)):
        alerts.append(replay.routine_reminder(
            NIGHT_BATHROOM_STAY, now, "夜间连续观测到在卫生间区域，已满 30 分钟。"
        ))
    return sorted(alerts, key=lambda alert: replay.read_timestamp(alert["timestamp"]))


def simulated_routine(day: date, scenario: str, overnight_start: date) -> Iterator[replay.Observation]:
    departure = time(9) if scenario in {"late_wakeup", "missing"} else time(7, 10)
    for sample in replay.simulate_day(day, departure):
        clock = sample.timestamp.time()
        if scenario == "missing" and clock in {time(8, 30), time(14), time(23, 45), time(0)}:
            continue
        at_night = clock >= time(23, 30) if day == overnight_start else clock < time(0, 15)
        if scenario in {DAYTIME_INACTIVITY, "missing"} and time(13) <= clock < time(15, 15):
            yield replace(sample, state="sitting")
        elif scenario in {NIGHT_BATHROOM_STAY, "missing"} and at_night:
            yield replace(sample, zone="bathroom", state="standing")
        elif sample.zone == "living_room" and clock.minute >= 40:
            yield replace(sample, state="standing")
        else:
            yield sample


def generate(directory: Path) -> None:
    replay.generate_fixtures(directory)
    first = date(2026, 11, 24)
    for scenario in ("normal", *ALERT_TYPES, "missing"):
        days = (first, first + timedelta(days=1)) if scenario in {NIGHT_BATHROOM_STAY, "missing"} else (first,)
        replay.write_samples(
            directory / f"routine-{scenario}.csv",
            (sample for day in days for sample in simulated_routine(day, scenario, first)),
        )


def mqtt_payload(reminder: dict[str, str], preview_time: datetime | None = None) -> dict[str, str]:
    if preview_time is not None:
        reminder = replay.routine_reminder(
            reminder["alert_type"], preview_time, f"模拟样例 · {reminder['reason']}"
        )
    return {
        "event": "routine_alert",
        **{key: reminder[key] for key in ("schema_version", "event_id", "alert_type", "timestamp", "reason")},
    }


def publish_local(payloads: list[dict[str, str]], port: int) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError as error:
        raise ValueError("发布到测试 broker 需要 requirements-edge.txt 中的 paho-mqtt") from error
    client = mqtt.Client()
    client.connect("127.0.0.1", port, keepalive=10)
    client.loop_start()
    try:
        for payload in payloads:
            receipt = client.publish(MQTT_TOPIC, json.dumps(payload, ensure_ascii=False), qos=1, retain=False)
            receipt.wait_for_publish(timeout=3)
            if not receipt.is_published():
                raise ValueError("测试 broker 尚未确认 MQTT 发布")
    finally:
        client.disconnect()
        client.loop_stop()


def run(directory: Path, args: argparse.Namespace) -> None:
    typical, _ = replay.typical_departure(replay.read_samples(args.history or directory / "history.csv"))
    if args.observations is None:
        alerts = []
        expected = {"normal": 0, **dict.fromkeys(ALERT_TYPES, 1), "missing": 0}
        for scenario, count in expected.items():
            found = detect(replay.read_samples(directory / f"routine-{scenario}.csv"), typical)
            if len(found) != count or any(alert["alert_type"] != scenario for alert in found):
                raise ValueError(f"{scenario} 预期 {count} 条，实际 {len(found)} 条")
            print(f"{scenario} {len(found)}", file=sys.stderr)
            alerts.extend(found)
    else:
        alerts = detect(replay.read_samples(args.observations), typical)
    preview_time = datetime.now(replay.LOCAL_TZ) if args.mqtt_preview else None
    payloads = [mqtt_payload(alert, preview_time) if args.mqtt else alert for alert in alerts]
    for payload in payloads:
        print(json.dumps(payload, ensure_ascii=False))
    if args.publish_port is not None:
        publish_local(payloads, args.publish_port)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    csv = parser.add_mutually_exclusive_group()
    csv.add_argument("--generate", type=Path, help="在新目录保留模拟 CSV")
    csv.add_argument("--history", type=Path, help="已有离床基线 CSV")
    parser.add_argument("--observations", type=Path, help="已有作息 CSV，可含多个自然日")
    parser.add_argument("--mqtt", action="store_true", help="输出供 App 解析的 MQTT JSON")
    parser.add_argument("--mqtt-preview", action="store_true", help="把 MQTT 演示消息时间设为当前时间")
    parser.add_argument("--publish-port", type=int, help="发布至 127.0.0.1 的测试 broker")
    args = parser.parse_args()
    if (args.history is None) != (args.observations is None):
        parser.error("--history 与 --observations 应同时提供")
    if args.publish_port is not None and not (args.mqtt and 1 <= args.publish_port <= 65535):
        parser.error("--publish-port 需要 --mqtt 和有效端口")
    if args.mqtt_preview and (not args.mqtt or args.observations is not None):
        parser.error("--mqtt-preview 仅用于内置 MQTT 模拟作息")
    try:
        if args.history:
            run(args.history.parent, args)
        elif args.generate:
            args.generate.mkdir(parents=True)
            generate(args.generate)
            run(args.generate, args)
        else:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                generate(path)
                run(path, args)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
