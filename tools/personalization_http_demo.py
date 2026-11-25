"""运行晚起 HTTP 模拟闭环，或对接本机实现 v5 的模型进程。"""

import argparse
import json
import multiprocessing
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep

if __package__:
    from . import late_wakeup_demo as replay
    from . import personalization_http as http
else:
    import late_wakeup_demo as replay
    import personalization_http as http


DEVICE = "demo-device"


@dataclass
class ReplayClock:
    now: datetime

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def replay_reminder(directory):
    replay.generate_fixtures(directory)
    typical, _ = replay.typical_departure(replay.read_samples(directory / "history.csv"))
    return replay.replay_day(replay.read_samples(directory / "late.csv"), typical).reminder


def finish_mock(model, event_id, answer, clock):
    require(model.start(event_id), "模拟问候未能开始")
    prompted_at = clock()
    print("  模拟文字问候  您好，想问问您现在还好吗，需要帮助吗？")
    clock.advance(20)
    require(model.finish(event_id, answer, prompted_at), "模拟结果未能保存")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def drop_once(seen):
    def filter_ack(ack):
        seen.append(ack)
        return None if len(seen) == 1 else ack
    return filter_ack


def make_pair(directory, reminder):
    directory.mkdir()
    clock = ReplayClock(datetime.fromisoformat(reminder["timestamp"]))
    app = http.Personalization(directory / "personalization.sqlite3", clock, DEVICE)
    model = http.MockModel(directory / "model.sqlite3", clock, DEVICE)
    app.register(reminder)
    return clock, app, model


def normal_case(directory, reminder, answer):
    event_id = reminder["event_id"]
    clock, app, model = make_pair(directory, reminder)
    with http.serve(http.REMINDERS, model.receive) as model_port:
        app.flush(model_port)
        require(app.queued(event_id)[0]["state"] == "acked", "提醒未收到有效回执")
        finish_mock(model, event_id, answer, clock)
        require(http.post(model_port, http.REMINDERS, reminder)[1]["disposition"] == "duplicate",
                "重复提醒应确认并沿用现有问答")
        require(not model.start(event_id), "重复提醒启动了第二次问答")

    with http.serve(http.RESULTS, app.receive) as result_port:
        model.flush(result_port)
        queued = model.queued(event_id)[0]
        require(queued["state"] == "acked", "结果未收到有效回执")
        result = json.loads(queued["payload"])
        require(http.post(result_port, http.RESULTS, result)[1]["disposition"] == "duplicate",
                "重复结果未得到 duplicate 回执")
    summary = app.summary(event_id)
    require(summary["current"]["response"] == answer and summary["current"]["revision"] == 1,
            "结果内容或版本不一致")
    require(len(summary["history"]) == 1 and summary["help_tasks"] == int(answer == "needs_help"),
            "结果历史或求助处置重复登记")
    print(f"  {answer} 回传通过，版本 1，待处置 {summary['help_tasks']} 条")


def flush_in_worker(db_path, now, result_port):
    model = http.MockModel(db_path, ReplayClock(now), DEVICE)
    model.recover()
    model.flush(result_port)


def restart_and_flush(db_path, clock, result_port):
    process = multiprocessing.get_context("spawn").Process(
        target=flush_in_worker, args=(db_path, clock(), result_port)
    )
    process.start()
    try:
        process.join(12)
        require(process.exitcode == 0, "模型补发子进程失败或超时")
    finally:
        if process.is_alive():
            process.terminate()
            process.join()
        process.close()


def lost_ack_case(directory, reminder):
    event_id = reminder["event_id"]
    clock, app, model = make_pair(directory, reminder)
    reminder_acks, result_acks = [], []
    with http.serve(http.REMINDERS, model.receive, ack_filter=drop_once(reminder_acks)) as port:
        app.flush(port)
        first = app.queued(event_id)[0]
        require(first["state"] == "pending", "提醒回执丢失后应保留待确认")
        clock.advance(4)
        app.flush(port)
        require(len(reminder_acks) == 1, "提醒在补发间隔前重复发送")
        clock.advance(1)
        app = http.Personalization(app.path, clock, DEVICE)
        app.flush(port)
        second = app.queued(event_id)[0]
        require(second["state"] == "acked" and first["payload"] == second["payload"],
                "提醒补发未沿用原载荷")
        require([ack["disposition"] for ack in reminder_acks] == ["accepted", "duplicate"],
                "提醒回执丢失场景次序错误")
        finish_mock(model, event_id, "needs_help", clock)

    with http.serve(http.RESULTS, app.receive, ack_filter=drop_once(result_acks)) as port:
        restart_and_flush(model.path, clock, port)
    first = model.queued(event_id)[0]
    require(first["state"] == "pending" and app.summary(event_id)["help_tasks"] == 1,
            "结果回执丢失时，模型应待确认，个性化端应已保存求助")
    clock.advance(5)
    app = http.Personalization(app.path, clock, DEVICE)
    with http.serve(http.RESULTS, app.receive, ack_filter=drop_once(result_acks)) as port:
        restart_and_flush(model.path, clock, port)
    second = model.queued(event_id)[0]
    require(second["state"] == "acked" and first["payload"] == second["payload"],
            "模型进程重启后未按原载荷补发结果")
    require([ack["disposition"] for ack in result_acks] == ["accepted", "duplicate"]
            and app.summary(event_id)["help_tasks"] == 1,
            "结果补发未正确去重")
    print("  提醒和结果回执丢失通过，模型换进程补发原载荷，待处置仍为 1 条")


def out_of_order_case(directory, reminder):
    event_id = reminder["event_id"]
    clock, app, model = make_pair(directory, reminder)
    with http.serve(http.REMINDERS, model.receive) as port:
        app.flush(port)
    finish_mock(model, event_id, "no_response", clock)
    clock.advance(240)
    require(model.late_reply(event_id, "needs_help", clock()), "窗口内的求助未保存")
    clock.advance(120)

    arrival = []

    def observe(ack):
        arrival.append(ack["revision"])
        return ack

    with http.serve(http.RESULTS, app.receive, ack_filter=observe) as port:
        model.flush(port, newest_first=True)
    summary = app.summary(event_id)
    require(arrival == [2, 1], "结果没有按 2→1 的顺序投递")
    require([item["revision"] for item in summary["history"]] == [1, 2], "没有保留两版结果")
    require(summary["current"]["revision"] == 2 and summary["current"]["response"] == "needs_help"
            and summary["help_tasks"] == 1, "当前版本或求助状态被旧结果覆盖")
    print("  结果乱序 2 → 1 通过，两版均留存，当前为 v2 needs_help，待处置 1 条")


def demo(directory):
    reminder = replay_reminder(directory)
    print(f"回放 {reminder['timestamp']}，提醒有效至 {reminder['expires_at']}")
    for answer in ("ok", "needs_help"):
        normal_case(directory / answer, reminder, answer)
    lost_ack_case(directory / "lost-ack", reminder)
    out_of_order_case(directory / "out-of-order", reminder)
    print("本机 HTTP 模拟验收通过。")


def peer(args):
    def wall_clock():
        return datetime.now(timezone.utc)

    app = http.Personalization(args.db, wall_clock, args.device_id)
    if args.send_sample:
        now = wall_clock().astimezone(replay.LOCAL_TZ)
        payload = replay.make_reminder(now, replay.time(7))
        payload["device_id"] = args.device_id
        app.register(payload)
        print(f"已登记模拟提醒 {payload['event_id']}，有效至 {payload['expires_at']}", flush=True)

    def receive(payload):
        disposition = app.receive(payload)
        if disposition == "accepted":
            current = app.summary(payload["event_id"])
            print(http.json_text({"event_id": payload["event_id"], **current}), flush=True)
        return disposition

    end = None if args.seconds is None else monotonic() + args.seconds
    with http.serve(http.RESULTS, receive, port=args.results_port) as port:
        print(f"结果接收端 http://127.0.0.1:{port}{http.RESULTS}", flush=True)
        while end is None or monotonic() < end:
            app.flush(args.model_port)
            sleep(0.25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="在新目录保留模拟 CSV 和 SQLite 记录")
    modes = parser.add_subparsers(dest="mode")
    peer_mode = modes.add_parser("peer", help="连接另一个本机 v5 模型进程")
    peer_mode.add_argument("--model-port", type=int, required=True)
    peer_mode.add_argument("--results-port", type=int, required=True)
    peer_mode.add_argument("--db", type=Path, required=True)
    peer_mode.add_argument("--device-id", default=DEVICE)
    peer_mode.add_argument("--send-sample", action="store_true", help="创建一条以当前时间触发的模拟晚起提醒")
    peer_mode.add_argument("--seconds", type=int, help="运行指定秒数后退出，默认持续运行")
    args = parser.parse_args()
    try:
        if args.mode == "peer":
            if not (1 <= args.model_port <= 65535 and 1 <= args.results_port <= 65535):
                parser.error("端口必须在 1～65535 之间")
            if args.model_port == args.results_port or not args.device_id.strip():
                parser.error("两个端口应不同，设备 ID 应非空")
            if args.seconds is not None and args.seconds <= 0:
                parser.error("运行秒数必须大于零")
            peer(args)
        elif args.output_dir is not None:
            args.output_dir.mkdir(parents=True)
            demo(args.output_dir)
        else:
            with tempfile.TemporaryDirectory() as directory:
                demo(Path(directory))
    except KeyboardInterrupt:
        return
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
