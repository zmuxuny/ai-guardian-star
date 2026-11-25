"""v5 本机 HTTP 联调：提醒发件箱、结果接收和模拟模型。"""

import json
import logging
import socket
import sqlite3
from contextlib import closing, contextmanager, suppress
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread


VERSION = "2"
REMINDERS = "/personalization/v2/reminders"
RESULTS = "/personalization/v2/results"
REQUEST_TIMEOUT = 3
SESSION_SECONDS = 90
LATE_SECONDS = 300
CLASSIFY_SECONDS = 5
RESULT_SECONDS = 24 * 60 * 60
EVENT_GRACE = SESSION_SECONDS + LATE_SECONDS + CLASSIFY_SECONDS + RESULT_SECONDS
RESPONSES = {"ok", "needs_help", "unclear", "no_response"}
ERRORS = {"input_unavailable", "prompt_failed", "session_timeout", "expired_before_prompt", "interrupted"}
LOG = logging.getLogger(__name__)


class Rejected(ValueError):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


def json_text(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def instant(value):
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.utcoffset() is None:
        raise ValueError("time requires an offset")
    return moment.astimezone(timezone.utc)


def canonical(payload, route, device):
    """按定义字段比较内容，发送时使用原始载荷。"""
    if not isinstance(payload, dict):
        raise Rejected(400, "expected a JSON object")
    version = payload.get("schema_version")
    if not isinstance(version, str) or not version.strip():
        raise Rejected(400, "invalid schema_version")
    if version != VERSION:
        raise Rejected(422, "unsupported schema_version")

    required = ["schema_version", "event_id", "timestamp"]
    optional = ["device_id"]
    times = ["timestamp"]
    if route == REMINDERS:
        required += ["alert_type", "expires_at", "reason"]
        times.append("expires_at")
    else:
        revision = payload.get("revision")
        if type(revision) is not int or not 0 < revision < 2**63:
            raise Rejected(400, "invalid revision")
        required.append("status")
        optional.append("prompted_at")
        if "prompted_at" in payload:
            times.append("prompted_at")
        if payload.get("status") == "completed" and "error_code" not in payload:
            required.append("response")
        elif payload.get("status") == "error" and "response" not in payload:
            required.append("error_code")
        else:
            raise Rejected(400, "invalid result status or fields")

    values = {}
    for key in required + [key for key in optional if key in payload]:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise Rejected(400, f"invalid {key}")
        values[key] = value
    if values.get("device_id", device) != device:
        raise Rejected(400, "device_id does not match the binding")
    try:
        for key in times:
            values[key] = instant(values[key]).isoformat()
    except (ValueError, OverflowError) as error:
        raise Rejected(400, "invalid timestamp") from error
    if route == REMINDERS:
        if instant(values["expires_at"]) <= instant(values["timestamp"]):
            raise Rejected(400, "expires_at must follow timestamp")
    else:
        values["revision"] = revision
        if values.get("response", "ok") not in RESPONSES or values.get("error_code", "interrupted") not in ERRORS:
            raise Rejected(400, "invalid response or error_code")
    return values


def duplicate(saved, payload, route, device):
    if canonical(json.loads(saved), route, device) != canonical(payload, route, device):
        raise Rejected(409, "conflicting content for an existing message")
    return "duplicate"


def acknowledgement(payload, route, disposition):
    ack = {"schema_version": VERSION, "event_id": payload["event_id"], "disposition": disposition}
    if route == RESULTS:
        ack["revision"] = payload["revision"]
    return ack


def valid_ack(ack, payload, route):
    allowed = ("accepted", "duplicate", "expired") if route == REMINDERS else ("accepted", "duplicate")
    if not isinstance(ack, dict) or ack.get("disposition") not in allowed:
        return False
    return all(
        type(ack.get(key)) is type(value) and ack[key] == value
        for key, value in acknowledgement(payload, route, ack["disposition"]).items()
    )


@contextmanager
def serve(route, receive, port=0, ack_filter=None):
    """启动一个环回接收端。联调时可在事务完成后丢弃回执。"""
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                if self.path != route:
                    raise Rejected(404, "unknown path")
                self.connection.settimeout(REQUEST_TIMEOUT)
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536 or self.headers.get_content_type() != "application/json":
                    raise Rejected(400, "expected a JSON request body")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                json_text(payload).encode("utf-8")
                disposition = receive(payload)
                reply = acknowledgement(payload, route, disposition)
            except Rejected as error:
                if error.status == 409:
                    LOG.warning("%s: %s", route, error)
                self.send_json(error.status, {"error": str(error)})
                return
            except (ValueError, TimeoutError):
                self.send_json(400, {"error": "invalid JSON body"})
                return
            except sqlite3.OperationalError:
                LOG.exception("SQLite operation failed")
                self.send_json(503, {"error": "storage temporarily unavailable"})
                return

            if ack_filter is not None:
                reply = ack_filter(reply)
            if reply is None:
                self.close_connection = True
                with suppress(OSError):
                    self.connection.shutdown(socket.SHUT_WR)
                return
            self.send_json(200, reply)

        def send_json(self, status, payload):
            body = json_text(payload).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.close_connection = True

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
        worker.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            worker.join()


def post(port, route, payload):
    connection = HTTPConnection("127.0.0.1", port, timeout=REQUEST_TIMEOUT)
    with closing(connection):
        connection.request("POST", route, json_text(payload).encode("utf-8"),
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read(65537)
        try:
            body = json.loads(raw) if len(raw) <= 65536 else None
        except (ValueError, UnicodeError):
            body = None
        return response.status, body


class Store:
    """一个数据库绑定一个设备，每个出站请求使用持久化队列。"""

    def __init__(self, path, clock, device, schema, route):
        self.path = path
        self.clock = clock
        self.device = device
        self.route = route
        with closing(sqlite3.connect(path, timeout=1)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS binding (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    device TEXT NOT NULL, route TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    event_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                    deadline REAL NOT NULL, due REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'pending', last_error TEXT,
                    PRIMARY KEY(event_id, revision)
                );
            """ + schema)
            db.execute("INSERT OR IGNORE INTO binding VALUES (1, ?, ?)", (device, route))
            if db.execute("SELECT device, route FROM binding").fetchone() != (device, route):
                raise ValueError("database is bound to a different device or module")

    @contextmanager
    def transaction(self):
        with closing(sqlite3.connect(self.path, timeout=1)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            yield db

    def enqueue(self, db, payload, deadline, now):
        db.execute(
            "INSERT INTO outbox(event_id, revision, payload, deadline, due) VALUES (?, ?, ?, ?, ?)",
            (payload["event_id"], payload["revision"] if self.route == RESULTS else 0,
             json_text(payload), deadline, now),
        )

    def flush(self, port, newest_first=False):
        """发送这一时刻已到期的请求。应用每个实例使用一个发送循环。"""
        expired = "unconfirmed" if self.route == REMINDERS else "failed"
        with self.transaction() as db:
            now = self.clock().timestamp()
            db.execute(
                "UPDATE outbox SET state = ?, last_error = 'deadline' WHERE state = 'pending' AND deadline <= ?",
                (expired, now),
            )
            rows = db.execute(
                "SELECT * FROM outbox WHERE state = 'pending' AND due <= ? ORDER BY due, event_id, revision",
                (now,),
            ).fetchall()
        if newest_first:
            rows.sort(key=lambda row: row["revision"], reverse=True)
        for row in rows:
            self.send_one(port, row, expired)

    def send_one(self, port, row, expired):
        key = (row["event_id"], row["revision"])
        with self.transaction() as db:
            current = db.execute("SELECT * FROM outbox WHERE event_id = ? AND revision = ?", key).fetchone()
            if current["state"] != "pending" or current["due"] > self.clock().timestamp():
                return
        attempts = current["attempts"]
        due = current["due"]
        if self.clock().timestamp() >= current["deadline"]:
            state, detail = expired, "deadline"
        else:
            state, detail = self.try_delivery(port, json.loads(current["payload"]))
            attempts += 1
            backoff = (5, 15, 30, 30 if self.route == REMINDERS else 60)
            due = self.clock().timestamp() + backoff[min(attempts - 1, len(backoff) - 1)]
        with self.transaction() as db:
            db.execute(
                """UPDATE outbox SET attempts = ?, state = ?, due = ?, last_error = ?
                   WHERE event_id = ? AND revision = ? AND state = 'pending'""",
                (attempts, state, due, detail, *key),
            )

    def try_delivery(self, port, payload):
        try:
            status, ack = post(port, self.route, payload)
        except (OSError, HTTPException) as error:
            return "pending", type(error).__name__
        if status == 200:
            if valid_ack(ack, payload, self.route):
                return ("expired" if ack["disposition"] == "expired" else "acked"), None
            return "pending", "invalid acknowledgement"
        state = "pending" if status == 429 or 500 <= status < 600 else "failed"
        return state, f"HTTP {status}"

    def queued(self, event_id):
        with self.transaction() as db:
            rows = db.execute(
                "SELECT * FROM outbox WHERE event_id = ? ORDER BY revision", (event_id,)
            ).fetchall()
            return [dict(row) for row in rows]


class Personalization(Store):
    def __init__(self, path, clock, device):
        super().__init__(path, clock, device, """
            CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS results (
                event_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(event_id, revision)
            );
            CREATE TABLE IF NOT EXISTS help_tasks (
                event_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, recorded_at REAL NOT NULL
            );
        """, REMINDERS)

    def register(self, payload):
        canonical(payload, REMINDERS, self.device)
        event_id = payload["event_id"]
        with self.transaction() as db:
            saved = db.execute("SELECT payload FROM events WHERE event_id = ?", (event_id,)).fetchone()
            if saved is not None:
                return duplicate(saved["payload"], payload, REMINDERS, self.device)
            db.execute("INSERT INTO events VALUES (?, ?)", (event_id, json_text(payload)))
            self.enqueue(db, payload, instant(payload["expires_at"]).timestamp(), self.clock().timestamp())
            return "accepted"

    def receive(self, payload):
        canonical(payload, RESULTS, self.device)
        event_id, revision = payload["event_id"], payload["revision"]
        key = (event_id, revision)
        with self.transaction() as db:
            event = db.execute("SELECT payload FROM events WHERE event_id = ?", (event_id,)).fetchone()
            if event is None:
                raise Rejected(404, "event is not registered")
            saved = db.execute(
                "SELECT payload FROM results WHERE event_id = ? AND revision = ?", key
            ).fetchone()
            if saved is not None:
                return duplicate(saved["payload"], payload, RESULTS, self.device)
            if payload.get("device_id") != json.loads(event["payload"]).get("device_id"):
                raise Rejected(400, "result must mirror reminder device_id")
            db.execute("INSERT INTO results VALUES (?, ?, ?)", (*key, json_text(payload)))
            if payload.get("response") == "needs_help":
                db.execute("INSERT OR IGNORE INTO help_tasks VALUES (?, ?, ?)",
                           (*key, self.clock().timestamp()))
            db.execute(
                """UPDATE outbox SET state = 'confirmed_by_result'
                   WHERE event_id = ? AND state IN ('pending', 'unconfirmed', 'expired', 'failed')""",
                (event_id,),
            )
            return "accepted"

    def summary(self, event_id):
        with self.transaction() as db:
            results = db.execute(
                "SELECT payload FROM results WHERE event_id = ? ORDER BY revision", (event_id,)
            ).fetchall()
            task = db.execute("SELECT * FROM help_tasks WHERE event_id = ?", (event_id,)).fetchone()
            history = [json.loads(row["payload"]) for row in results]
            return {"current": history[-1] if history else None, "history": history,
                    "help_tasks": int(task is not None)}


class MockModel(Store):
    def __init__(self, path, clock, device):
        super().__init__(path, clock, device, """
            CREATE TABLE IF NOT EXISTS sessions (
                event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, accepted_at REAL NOT NULL,
                state TEXT NOT NULL, reply_until REAL
            );
        """, RESULTS)

    def receive(self, payload):
        canonical(payload, REMINDERS, self.device)
        event_id = payload["event_id"]
        with self.transaction() as db:
            saved = db.execute("SELECT payload FROM sessions WHERE event_id = ?", (event_id,)).fetchone()
            if saved is not None:
                return duplicate(saved["payload"], payload, REMINDERS, self.device)
            now = self.clock().timestamp()
            if now >= instant(payload["expires_at"]).timestamp():
                return "expired"
            if db.execute("SELECT 1 FROM sessions WHERE state IN ('pending', 'running') LIMIT 1").fetchone():
                raise Rejected(503, "one question is already queued or running")
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, 'pending', NULL)",
                       (event_id, json_text(payload), now))
            return "accepted"

    def start(self, event_id):
        """问候前记下可能已启动，调用者随后才显示固定话术。"""
        with self.transaction() as db:
            session = db.execute("SELECT * FROM sessions WHERE event_id = ?", (event_id,)).fetchone()
            if session is None or session["state"] != "pending":
                return False
            now = self.clock()
            reminder = json.loads(session["payload"])
            if now.timestamp() >= session["accepted_at"] + SESSION_SECONDS:
                self.save_result(db, reminder, 1, now, "session_timeout")
                return False
            if now >= instant(reminder["expires_at"]):
                self.save_result(db, reminder, 1, now, "expired_before_prompt")
                return False
            db.execute("UPDATE sessions SET state = 'running' WHERE event_id = ?", (event_id,))
            return True

    def finish(self, event_id, outcome, prompted_at):
        with self.transaction() as db:
            session = db.execute("SELECT * FROM sessions WHERE event_id = ?", (event_id,)).fetchone()
            if session is None or session["state"] != "running":
                return False
            now = self.clock()
            if now.timestamp() >= session["accepted_at"] + SESSION_SECONDS:
                outcome = "session_timeout"
            self.save_result(db, json.loads(session["payload"]), 1, now, outcome, prompted_at)
            return True

    def recover(self):
        with self.transaction() as db:
            rows = db.execute("SELECT payload FROM sessions WHERE state = 'running'").fetchall()
            for row in rows:
                self.save_result(db, json.loads(row["payload"]), 1, self.clock(), "interrupted")

    def late_reply(self, event_id, response, received_at):
        """注入已分类的模拟回话。超窗或无法关联由调用者处理。"""
        if response not in {"ok", "needs_help"}:
            return False
        with self.transaction() as db:
            session = db.execute("SELECT * FROM sessions WHERE event_id = ?", (event_id,)).fetchone()
            latest = db.execute(
                "SELECT * FROM outbox WHERE event_id = ? ORDER BY revision DESC LIMIT 1", (event_id,)
            ).fetchone()
            if latest is None:
                return False
            previous = json.loads(latest["payload"])
            now = self.clock()
            delay = (now - received_at).total_seconds()
            received = received_at.timestamp()
            first_result = session["reply_until"] - LATE_SECONDS
            if received >= session["reply_until"] or not 0 <= delay <= CLASSIFY_SECONDS:
                return False
            if received < first_result and not (
                previous.get("error_code") == "session_timeout" and response == "needs_help"
            ):
                return False
            if previous.get("response") == response:
                return True
            if previous.get("response") == "needs_help":
                return False
            self.save_result(db, json.loads(session["payload"]), latest["revision"] + 1,
                             now, response, previous.get("prompted_at"))
            return True

    def save_result(self, db, reminder, revision, now, outcome, prompted_at=None):
        event_id = reminder["event_id"]
        result = {"schema_version": VERSION, "event_id": event_id, "revision": revision,
                  "timestamp": now.isoformat()}
        if outcome in RESPONSES:
            result.update(status="completed", response=outcome)
        else:
            result.update(status="error", error_code=outcome)
        if "device_id" in reminder:
            result["device_id"] = reminder["device_id"]
        if prompted_at is not None:
            result["prompted_at"] = prompted_at if isinstance(prompted_at, str) else prompted_at.isoformat()
        canonical(result, RESULTS, self.device)
        end = min(now.timestamp() + RESULT_SECONDS, instant(reminder["expires_at"]).timestamp() + EVENT_GRACE)
        self.enqueue(db, result, end, now.timestamp())
        db.execute("UPDATE sessions SET state = 'finished', reply_until = COALESCE(reply_until, ?) WHERE event_id = ?",
                   (now.timestamp() + LATE_SECONDS, event_id))
