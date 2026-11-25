"""用模拟作息回放晚起提醒。运行 --help 查看 CSV 生成和回放选项。"""

import argparse
import csv
import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median_low
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, uuid5


LOCAL_TZ = timezone(timedelta(hours=8))
SAMPLE_INTERVAL = timedelta(minutes=5)
MORNING_START = time(6)
MORNING_END = time(10)
LATE_AFTER = timedelta(minutes=90)
REMINDER_TTL = timedelta(seconds=120)
CSV_FIELDS = ("timestamp", "zone", "state")
SCENARIOS = {"normal": "正常日", "late": "晚起日", "missing": "缺记录日"}


@dataclass(frozen=True)
class Observation:
    timestamp: datetime
    zone: str
    state: str


@dataclass
class ReplayResult:
    reminder: dict[str, str] | None = None
    prompt: str | None = None
    active_event_ids: dict[datetime, str] = field(default_factory=dict)


def at(day: date, clock_time: time) -> datetime:
    return datetime.combine(day, clock_time, LOCAL_TZ)


def simulate_day(
    day: date, departure: time, missing: time | None = None
) -> Iterator[Observation]:
    cursor = at(day, time())
    end = cursor + timedelta(days=1)
    while cursor < end:
        clock_time = cursor.time()
        if clock_time != missing:
            if clock_time < departure or clock_time >= time(22):
                zone, state = "bed", "lying"
            elif clock_time == departure:
                zone, state = "living_room", "standing"
            elif time(12) <= clock_time < time(12, 30):
                zone, state = "unknown", "absent"
            else:
                zone, state = "living_room", "sitting"
            yield Observation(cursor, zone, state)
        cursor += SAMPLE_INTERVAL


def write_samples(path: Path, samples: Iterable[Observation]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(CSV_FIELDS)
        for sample in samples:
            writer.writerow((sample.timestamp.isoformat(), sample.zone, sample.state))


def generate_fixtures(directory: Path) -> None:
    first_day = date(2026, 11, 1)
    # 06:45 至 07:15，每种离床时间出现两次。
    first_departure = at(first_day, time(6, 45))
    departures = [(first_departure + i * SAMPLE_INTERVAL).time() for i in range(7)]
    write_samples(
        directory / "history.csv",
        (
            sample
            for i, departure in enumerate(departures * 2)
            for sample in simulate_day(first_day + timedelta(days=i), departure)
        ),
    )
    write_samples(directory / "normal.csv", simulate_day(date(2026, 11, 23), time(7, 10)))
    write_samples(directory / "late.csv", simulate_day(date(2026, 11, 24), time(9)))
    write_samples(
        directory / "missing.csv", simulate_day(date(2026, 11, 25), time(9), missing=time(8, 30))
    )


def read_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.utcoffset() is None:
        raise ValueError("时间必须带时区")
    return timestamp.astimezone(LOCAL_TZ)


def read_samples(path: Path) -> dict[datetime, Observation]:
    samples = {}
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        if tuple(next(reader, ())) != CSV_FIELDS:
            raise ValueError(f"{path} 的表头应为 timestamp,zone,state")
        for row in reader:
            try:
                raw_timestamp, zone, state = row
                timestamp = read_timestamp(raw_timestamp)
                if not zone.strip() or state not in {"lying", "sitting", "standing", "absent"}:
                    raise ValueError("区域或状态无效")
                if timestamp.minute % 5 or timestamp.second or timestamp.microsecond:
                    raise ValueError("采样时间必须对齐到 5 分钟")
                if timestamp in samples:
                    raise ValueError("采样时间重复")
            except ValueError as error:
                raise ValueError(f"{path}:{reader.line_num} {error}") from error
            samples[timestamp] = Observation(timestamp, zone, state)
    return samples


def morning_samples(
    day: date, samples: dict[datetime, Observation]
) -> Iterator[Observation]:
    """从 06:00 回放连续的在床区记录，最多读到首次离开床区。"""
    start = at(day, MORNING_START)
    end = at(day, MORNING_END)
    cursor = start
    while cursor < end:
        sample = samples.get(cursor)
        if sample is None or sample.state == "absent" or sample.zone == "unknown":
            return
        if cursor == start and sample.zone != "bed":
            return
        yield sample
        if sample.zone != "bed":
            return
        cursor += SAMPLE_INTERVAL


def typical_departure(samples: dict[datetime, Observation]) -> tuple[time, int]:
    departures = [
        sample.timestamp.time()
        for day in sorted({timestamp.date() for timestamp in samples})
        for sample in morning_samples(day, samples)
        if sample.zone != "bed"
    ]
    if not departures:
        raise ValueError("历史作息中没有可确认的晨间离床记录")
    # 偶数天时选靠前的中间值，基线仍落在 5 分钟采样点上。
    return median_low(departures), len(departures)


def make_reminder(now: datetime, typical: time) -> dict[str, str]:
    timestamp = now.isoformat(timespec="seconds")
    event_id = uuid5(
        NAMESPACE_URL, f"https://github.com/zmuxuny/ai-guardian-star/late-wakeup-demo/{timestamp}"
    )
    return {
        "schema_version": "2",
        "event_id": str(event_id),
        "alert_type": "late_wakeup",
        "timestamp": timestamp,
        "expires_at": (now + REMINDER_TTL).isoformat(timespec="seconds"),
        "reason": f"平时约 {typical:%H:%M} 离开床区，今天 {now:%H:%M} 仍在床区。",
    }


def mock_prompt(reminder: dict[str, str], now: datetime) -> str | None:
    if read_timestamp(reminder["timestamp"]) <= now < read_timestamp(reminder["expires_at"]):
        return "您好，想问问您现在还好吗，需要帮助吗？"
    return None


def replay_day(samples: dict[datetime, Observation], typical: time) -> ReplayResult:
    days = {timestamp.date() for timestamp in samples}
    if len(days) != 1:
        raise ValueError("每个回放场景须包含单个自然日的采样记录")
    day = days.pop()
    threshold = at(day, typical) + LATE_AFTER
    result = ReplayResult()
    for sample in morning_samples(day, samples):
        now = sample.timestamp
        if sample.zone != "bed":
            break
        if now < threshold:
            continue
        if result.reminder is None:
            result.reminder = make_reminder(now, typical)
            result.prompt = mock_prompt(result.reminder, now)
        result.active_event_ids[now] = result.reminder["event_id"]
    return result


def run(directory: Path) -> None:
    typical, count = typical_departure(read_samples(directory / "history.csv"))
    print(f"基线 {typical:%H:%M}（{count} 天）", file=sys.stderr)
    for name, label in SCENARIOS.items():
        result = replay_day(read_samples(directory / f"{name}.csv"), typical)
        print(f"{label} {int(result.reminder is not None)} 条提醒", file=sys.stderr)
        if result.reminder is not None:
            print(json.dumps(result.reminder, ensure_ascii=False))
            print(f"  同一事件覆盖 {len(result.active_event_ids)} 个采样点", file=sys.stderr)
        if result.prompt is not None:
            started_at = next(iter(result.active_event_ids))
            print(f"  模拟问候 {started_at:%H:%M}  {result.prompt}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成 14 天模拟作息并回放 3 个独立场景。标准输出逐行写入 v5 提醒 JSON。"
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--generate", type=Path, help="在新目录保存 4 份 CSV 并立即回放")
    source.add_argument("--data-dir", type=Path, help="回放已有的 history、normal、late、missing CSV")
    args = parser.parse_args()
    try:
        if args.generate is not None:
            args.generate.mkdir(parents=True)
            generate_fixtures(args.generate)
            run(args.generate)
        elif args.data_dir is not None:
            run(args.data_dir)
        else:
            with TemporaryDirectory() as directory:
                data_dir = Path(directory)
                generate_fixtures(data_dir)
                run(data_dir)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
