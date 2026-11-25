import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from pathlib import Path

from tools import late_wakeup_demo as replay
from tools import personalization_http as http
from tools import personalization_http_demo as demo


class PersonalizationHttpTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        now = datetime(2026, 11, 24, 8, 30, tzinfo=replay.LOCAL_TZ)
        self.reminder = replay.make_reminder(now, time(7))
        self.event = self.reminder["event_id"]
        self.clock, self.app, self.model = demo.make_pair(self.path / "pair", self.reminder)

    def finish(self, answer="ok"):
        self.assertEqual(self.model.receive(self.reminder), "accepted")
        self.assertTrue(self.model.start(self.event))
        prompted = self.clock()
        self.clock.advance(20)
        self.assertTrue(self.model.finish(self.event, answer, prompted))

    def result(self, revision, response):
        return {
            "schema_version": "2", "event_id": self.event, "revision": revision,
            "status": "completed", "response": response, "timestamp": self.clock().isoformat(),
        }

    def test_result_confirms_event_even_after_missing_ack_and_expiry(self):
        lost = []
        with http.serve(http.REMINDERS, self.model.receive, ack_filter=demo.drop_once(lost)) as port:
            self.app.flush(port)
            self.assertTrue(self.model.start(self.event))
            self.clock.advance(20)
            self.model.finish(self.event, "needs_help", None)
            self.clock.advance(100)
            self.app.flush(port)
        self.assertEqual(len(lost), 1)
        self.assertEqual(self.app.queued(self.event)[0]["state"], "unconfirmed")
        with http.serve(http.RESULTS, self.app.receive) as port:
            self.model.flush(port)
        self.assertEqual(self.app.queued(self.event)[0]["state"], "confirmed_by_result")
        self.assertEqual(self.app.summary(self.event)["help_tasks"], 1)

    def test_late_reminder_ack_cannot_overwrite_result(self):
        def return_ack_after_result(ack):
            self.assertEqual(http.post(result_port, http.RESULTS, result)[0], 200)
            return ack

        result = self.result(1, "ok")
        with http.serve(http.RESULTS, self.app.receive) as result_port:
            with http.serve(http.REMINDERS, self.model.receive, ack_filter=return_ack_after_result) as port:
                self.app.flush(port)
        self.assertEqual(self.app.queued(self.event)[0]["state"], "confirmed_by_result")
        self.assertEqual(self.app.summary(self.event)["current"], result)

    def test_lower_revision_help_is_sticky_and_only_creates_one_task(self):
        with http.serve(http.RESULTS, self.app.receive) as port:
            for revision, response in ((3, "ok"), (1, "needs_help"), (2, "needs_help"), (4, "ok")):
                status, ack = http.post(port, http.RESULTS, self.result(revision, response))
                self.assertEqual((status, ack["disposition"]), (200, "accepted"))
            status, ack = http.post(port, http.RESULTS, self.result(1, "needs_help"))
            self.assertEqual((status, ack["disposition"]), (200, "duplicate"))
            with self.assertLogs(http.LOG, level="WARNING"):
                self.assertEqual(http.post(port, http.RESULTS, self.result(1, "ok"))[0], 409)
        reopened = http.Personalization(self.app.path, self.clock, demo.DEVICE)
        summary = reopened.summary(self.event)
        self.assertEqual([result["revision"] for result in summary["history"]], [1, 2, 3, 4])
        self.assertEqual(summary["current"]["revision"], 4)
        self.assertEqual(summary["help_tasks"], 1)

    def test_reminder_comparison_and_protocol_errors(self):
        with http.serve(http.REMINDERS, self.model.receive) as port:
            self.assertEqual(http.post(port, http.REMINDERS, self.reminder)[1]["disposition"], "accepted")
            self.clock.advance(121)
            copy = dict(self.reminder, extra="ignored")
            for field in ("timestamp", "expires_at"):
                copy[field] = http.instant(copy[field]).isoformat().replace("+00:00", "Z")
            self.assertEqual(http.post(port, http.REMINDERS, copy)[1]["disposition"], "duplicate")
            with self.assertLogs(http.LOG, level="WARNING"):
                self.assertEqual(http.post(port, http.REMINDERS, dict(copy, reason="变化"))[0], 409)
                self.assertEqual(http.post(port, http.REMINDERS, dict(copy, device_id=demo.DEVICE))[0], 409)
            self.assertEqual(http.post(port, http.REMINDERS, dict(copy, device_id="other"))[0], 400)
            self.assertEqual(http.post(port, http.REMINDERS, dict(copy, schema_version="5"))[0], 422)
            self.assertEqual(http.post(port, http.REMINDERS, dict(copy, schema_version=2))[0], 400)
            status, ack = http.post(port, http.REMINDERS, dict(copy, event_id="new"))
            self.assertEqual((status, ack["disposition"]), (200, "expired"))

    def test_invalid_result_ack_and_retry_delays(self):
        self.finish()
        attempts = []

        def filter_ack(ack):
            attempts.append(ack)
            invalid = [
                {key: value for key, value in ack.items() if key != "revision"},
                dict(ack, event_id="wrong"),
                dict(ack, disposition="expired"),
                dict(ack, revision=True),
            ]
            index = len(attempts) - 1
            return invalid[index] if index < len(invalid) else ack

        with http.serve(http.RESULTS, self.app.receive, ack_filter=filter_ack) as port:
            for wait in (5, 15, 30, 60):
                self.model.flush(port)
                queued = self.model.queued(self.event)[0]
                self.assertEqual(queued["state"], "pending")
                self.assertEqual(queued["last_error"], "invalid acknowledgement")
                self.assertEqual(queued["due"], self.clock().timestamp() + wait)
                self.clock.advance(wait)
            self.model.flush(port)
        self.assertEqual([ack["disposition"] for ack in attempts], ["accepted"] + ["duplicate"] * 4)
        self.assertEqual(self.model.queued(self.event)[0]["state"], "acked")
        self.assertEqual(len(self.app.summary(self.event)["history"]), 1)

    def test_result_validation_and_permanent_failure(self):
        self.finish()
        empty_app = http.Personalization(self.path / "empty.sqlite3", self.clock, demo.DEVICE)
        with http.serve(http.RESULTS, empty_app.receive) as port:
            self.assertEqual(http.post(port, http.RESULTS, self.result(True, "ok"))[0], 400)
            self.model.flush(port)
            self.clock.advance(30)
            self.model.flush(port)
        queued = self.model.queued(self.event)[0]
        self.assertEqual((queued["state"], queued["last_error"], queued["attempts"]), ("failed", "HTTP 404", 1))

    def test_simultaneous_reminders_only_reserve_one_prompt(self):
        payloads = [self.reminder, dict(self.reminder, event_id="other")]
        with http.serve(http.REMINDERS, self.model.receive) as port:
            with ThreadPoolExecutor(2) as pool:
                responses = list(pool.map(lambda body: http.post(port, http.REMINDERS, body), payloads))
            self.assertEqual(sorted(status for status, _ack in responses), [200, 503])
            winner = next(ack["event_id"] for status, ack in responses if status == 200)
            admitted = next(body for body in payloads if body["event_id"] == winner)
            self.assertEqual(http.post(port, http.REMINDERS, admitted)[1]["disposition"], "duplicate")
        self.assertTrue(self.model.start(winner))
        self.assertFalse(self.model.start(winner))

    def test_pending_expiry_and_session_timeout_never_prompt(self):
        for accept_at, expected in ((115, "expired_before_prompt"), (0, "session_timeout")):
            with self.subTest(accept_at=accept_at):
                clock, _app, model = demo.make_pair(self.path / str(accept_at), self.reminder)
                clock.advance(accept_at)
                self.assertEqual(model.receive(self.reminder), "accepted")
                clock.advance(120 - accept_at)
                self.assertFalse(model.start(self.event))
                result = json.loads(model.queued(self.event)[0]["payload"])
                self.assertEqual(result["error_code"], expected)
                self.assertNotIn("prompted_at", result)

    def test_running_without_result_recovers_as_interrupted(self):
        self.assertEqual(self.model.receive(self.reminder), "accepted")
        self.assertTrue(self.model.start(self.event))
        reloaded = http.MockModel(self.model.path, self.clock, demo.DEVICE)
        reloaded.recover()
        reloaded.recover()
        self.assertFalse(reloaded.start(self.event))
        queued = reloaded.queued(self.event)
        self.assertEqual(len(queued), 1)
        self.assertEqual(json.loads(queued[0]["payload"])["error_code"], "interrupted")

    def test_retry_cutoff_preserves_failure_for_both_deadlines(self):
        self.finish("needs_help")
        self.clock.advance(http.RESULT_SECONDS)
        self.model.flush(1)
        queued = self.model.queued(self.event)[0]
        self.assertEqual((queued["state"], queued["last_error"], queued["attempts"]), ("failed", "deadline", 0))
        self.assertEqual(json.loads(queued["payload"])["response"], "needs_help")

        clock, _app, model = demo.make_pair(self.path / "abandoned", self.reminder)
        model.receive(self.reminder)
        self.assertTrue(model.start(self.event))
        clock.advance(120 + http.EVENT_GRACE)
        model.recover()
        model.flush(1)
        queued = model.queued(self.event)[0]
        self.assertEqual((queued["state"], queued["last_error"], queued["attempts"]), ("failed", "deadline", 0))

    def test_late_window_uses_first_result_even_after_restart(self):
        self.finish("no_response")
        self.clock.advance(240)
        model = http.MockModel(self.model.path, self.clock, demo.DEVICE)
        self.assertTrue(model.late_reply(self.event, "ok", self.clock()))
        self.clock.advance(61)
        self.assertFalse(model.late_reply(self.event, "needs_help", self.clock()))
        self.assertTrue(model.late_reply(self.event, "needs_help", self.clock() - timedelta(seconds=2)))
        self.assertEqual([row["revision"] for row in model.queued(self.event)], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
