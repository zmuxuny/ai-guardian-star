"""Offline, virtual-time behavior regressions for sedentary care."""

from dataclasses import replace
from datetime import datetime, time, timezone, timedelta
import json
import unittest

from src.sedentary_care import CareMachine, Config, Event, VirtualClock


def make(origin=None, **options):
    clock = VirtualClock(origin or datetime(2026, 11, 16, 12, tzinfo=timezone(timedelta(hours=8))))
    return clock, CareMachine(clock, replace(Config(), **options))


def hold(clock, machine, seconds):
    """Supply actual trusted sitting observations, not just elapsed time."""
    while seconds > 0:
        step = min(10, seconds)
        clock.advance(step)
        machine.handle(Event.SIT)
        seconds -= step


class CareTests(unittest.TestCase):
    def test_default_trigger_points_repeats_and_cap(self):
        c, m = make()
        m.handle(Event.SIT)
        hold(c, m, 1799)
        self.assertEqual(m.export()['broadcasts'], [])
        hold(c, m, 1)
        self.assertEqual(m.snapshot()['level'], 'L0')
        hold(c, m, 299)
        self.assertEqual(len(m.export()['broadcasts']), 1)
        hold(c, m, 1)
        self.assertEqual(m.snapshot()['level'], 'L1')
        hold(c, m, 300)
        self.assertEqual(m.snapshot()['state'], 'EXHAUSTED')
        hold(c, m, 1800)
        records = m.export()['broadcasts']
        self.assertEqual([(r['at'], r['level'], r['text_id']) for r in records], [
            (1800, 'L0', 'sedentary.l0'), (2100, 'L1', 'sedentary.l1'),
            (2400, 'L1', 'sedentary.l1')])
        self.assertTrue(all(r['text'] for r in records))

    def test_stand_at_deadline_cancels_then_new_episode(self):
        c, m = make(l0_seconds=20)
        m.handle(Event.SIT)
        c.advance(20)
        m.handle(Event.STAND)
        self.assertEqual(m.snapshot()['seated_seconds'], 0)
        self.assertEqual(m.export()['broadcasts'], [])
        m.handle(Event.SIT)
        hold(c, m, 20)
        self.assertEqual(m.export()['broadcasts'][0]['at'], 40)

    def test_all_uncertainty_reasons_freeze_without_extending_expiry(self):
        for event in (Event.OCCLUDE, Event.LOW_CONFIDENCE, Event.MISSING,
                      Event.TARGET_LOST, Event.DEVICE_ERROR):
            with self.subTest(event=event):
                c, m = make(l0_seconds=20)
                m.handle(Event.SIT)
                hold(c, m, 10)
                m.handle(event)
                c.advance(119)
                m.handle(event)
                self.assertEqual(m.snapshot()['seated_seconds'], 10)
                self.assertEqual(m.snapshot()['state'], 'PAUSED')
                c.advance(1)
                m.handle(Event.TIMEOUT)
                self.assertEqual(m.snapshot()['state'], 'IDLE')
                self.assertEqual(m.snapshot()['level'], None)
                self.assertTrue(any(t['event'] == 'uncertainty_expired' for t in m.export()['transitions']))

    def test_short_uncertainty_resumes_remaining_reminder_time(self):
        c, m = make(l0_seconds=20)
        m.handle(Event.SIT)
        hold(c, m, 10)
        m.handle(Event.OCCLUDE)
        c.advance(119)
        m.handle(Event.SIT)
        hold(c, m, 9)
        self.assertEqual(m.export()['broadcasts'], [])
        hold(c, m, 1)
        self.assertEqual(m.export()['broadcasts'][0]['at'], 139)

    def test_expiry_boundary_starts_new_episode(self):
        for duration in (120, 121):
            c, m = make(l0_seconds=20)
            m.handle(Event.SIT)
            hold(c, m, 10)
            m.handle(Event.OCCLUDE)
            c.advance(duration)
            m.handle(Event.SIT)
            self.assertEqual(m.snapshot()['seated_seconds'], 0)
            hold(c, m, 20)
            self.assertEqual(m.export()['broadcasts'][0]['at'], 30 + duration)

    def test_missing_observations_expire_at_exact_deadlines(self):
        c, m = make(l0_seconds=30)
        m.handle(Event.SIT)
        c.advance(5000)
        m.handle(Event.TIMEOUT)
        self.assertEqual(m.export()['broadcasts'], [])
        self.assertEqual(m.snapshot()['state'], 'IDLE')
        rows = m.export()['transitions']
        self.assertIn((30, 'observation_timeout'), [(r['at'], r['event']) for r in rows])
        self.assertIn((150, 'uncertainty_expired'), [(r['at'], r['event']) for r in rows])

    def test_response_cooldown_preserves_counts_and_does_not_extend(self):
        c, m = make(l0_seconds=20, ack_seconds=40, upgrade_seconds=10, repeat_seconds=10)
        m.handle(Event.SIT)
        hold(c, m, 20)
        m.handle(Event.RESPOND)
        hold(c, m, 20)
        m.handle(Event.RESPOND)
        hold(c, m, 19)
        self.assertEqual(len(m.export()['broadcasts']), 1)
        hold(c, m, 1)
        self.assertEqual(m.export()['broadcasts'][-1]['at'], 60)
        hold(c, m, 10)
        self.assertEqual(m.snapshot()['state'], 'EXHAUSTED')
        self.assertEqual(m.snapshot()['seated_seconds'], 70)

    def test_response_during_uncertainty_freezes_cooldown(self):
        c, m = make(l0_seconds=20, ack_seconds=40)
        m.handle(Event.SIT)
        hold(c, m, 20)
        m.handle(Event.OCCLUDE)
        m.handle(Event.RESPOND)
        c.advance(50)
        m.handle(Event.SIT)
        self.assertEqual(m.snapshot()['phase'], 'ACK')
        hold(c, m, 40)
        self.assertEqual(m.export()['broadcasts'][-1]['at'], 110)

    def test_non_sitting_target_change_and_decline(self):
        for event in (Event.STAND, Event.NON_SIT, Event.TARGET_CHANGED):
            c, m = make(l0_seconds=20)
            m.handle(Event.SIT)
            hold(c, m, 20)
            m.handle(event)
            self.assertEqual(m.snapshot()['state'], 'IDLE')
            self.assertEqual(m.snapshot()['counts'], {'L0': 0, 'L1': 0})
        c, m = make(l0_seconds=20)
        m.handle(Event.SIT)
        m.handle(Event.DECLINE)
        hold(c, m, 100)
        self.assertEqual(m.export()['broadcasts'], [])
        self.assertEqual(m.snapshot()['state'], 'EXHAUSTED')

    def test_snooze_is_distinct_and_noop_events_are_logged(self):
        c, m = make(l0_seconds=20, ack_seconds=40)
        for event in (Event.TIMEOUT, Event.RESPOND, Event.DEFER):
            m.handle(event)
        m.handle(Event.SIT)
        hold(c, m, 20)
        m.handle(Event.DEFER)
        self.assertEqual(m.snapshot()['phase'], 'ACK')
        self.assertIn('DEFER', [t['event'] for t in m.export()['transitions']])

    def test_quiet_start_inclusive_end_exclusive(self):
        for hour, minute, second, audible in ((21, 59, 39, True), (21, 59, 40, False),
                                               (6, 59, 39, False), (6, 59, 40, True)):
            origin = datetime(2026, 11, 16, hour, minute, second, tzinfo=timezone.utc)
            c, m = make(origin, l0_seconds=20)
            m.handle(Event.SIT)
            hold(c, m, 20)
            self.assertEqual(bool(m.export()['broadcasts']), audible)
            if not audible:
                self.assertEqual(m.snapshot()['pending_level'], 'L0')
                self.assertEqual(m.snapshot()['counts']['L0'], 0)

    def test_quiet_end_flushes_only_one_then_uses_actual_broadcast_time(self):
        origin = datetime(2026, 11, 16, 6, 58, tzinfo=timezone.utc)
        c, m = make(origin, l0_seconds=20, upgrade_seconds=30)
        m.handle(Event.SIT)
        hold(c, m, 119)
        self.assertEqual(m.export()['broadcasts'], [])
        hold(c, m, 1)
        self.assertEqual([(r['at'], r['level']) for r in m.export()['broadcasts']], [(120, 'L0')])
        hold(c, m, 30)
        self.assertEqual(m.export()['broadcasts'][-1]['at'], 150)

    def test_pending_cancelled_by_response_stand_and_expiry(self):
        for event in (Event.RESPOND, Event.STAND, Event.TARGET_CHANGED, Event.DECLINE):
            origin = datetime(2026, 11, 16, 6, 59, tzinfo=timezone.utc)
            c, m = make(origin, l0_seconds=20)
            m.handle(Event.SIT)
            hold(c, m, 20)
            m.handle(event)
            if event in (Event.STAND, Event.TARGET_CHANGED):
                c.advance(40)
                m.handle(Event.TIMEOUT)
            else:
                hold(c, m, 40)
            self.assertEqual(m.export()['broadcasts'], [])

    def test_pending_paused_across_quiet_end(self):
        origin = datetime(2026, 11, 16, 6, 59, tzinfo=timezone.utc)
        c, m = make(origin, l0_seconds=20)
        m.handle(Event.SIT)
        hold(c, m, 20)
        m.handle(Event.TARGET_LOST)
        c.advance(50)
        m.handle(Event.TIMEOUT)
        self.assertEqual(m.export()['broadcasts'], [])
        m.handle(Event.SIT)
        self.assertEqual(m.export()['broadcasts'][0]['at'], 70)

    def test_large_and_small_time_steps_are_equivalent(self):
        reports = []
        for steps in ([100], [1] * 100):
            c, m = make(l0_seconds=20, upgrade_seconds=10, repeat_seconds=10,
                        observation_ttl=1000, quiet_start=None, quiet_end=None)
            m.handle(Event.SIT)
            for step in steps:
                c.advance(step)
                m.handle(Event.TIMEOUT)
            reports.append(m.export())
        self.assertEqual(reports[0]['snapshot'], reports[1]['snapshot'])
        self.assertEqual(reports[0]['broadcasts'], reports[1]['broadcasts'])

    def test_invalid_inputs_rejected_without_processing_elapsed_time(self):
        c, m = make(l0_seconds=20)
        m.handle(Event.SIT)
        before = m.export()
        c.advance(20)
        with self.assertRaises(ValueError):
            m.handle('unrecognized')
        self.assertEqual(m.export(), before)
        for seconds in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                c.advance(seconds)
        for options in ({'l0_seconds': 0}, {'observation_ttl': -1}, {'max_l1': 0},
                        {'max_l1': 1.5}, {'quiet_start': time(7), 'quiet_end': time(7)},
                        {'quiet_start': None}, {'ack_seconds': float('nan')}):
            with self.assertRaises(ValueError):
                replace(Config(), **options)
        with self.assertRaises(ValueError):
            VirtualClock(datetime(2026, 11, 16))

    def test_json_exports_are_detached(self):
        c, m = make(l0_seconds=20)
        m.handle(Event.SIT)
        hold(c, m, 20)
        export = m.export()
        json.dumps(export, allow_nan=False)
        export['broadcasts'][0]['level'] = 'invalid'
        self.assertEqual(m.export()['broadcasts'][0]['level'], 'L0')

    def test_repeated_response_does_not_restart_expired_quiet_cooldown(self):
        origin = datetime(2026, 11, 16, 6, 59, tzinfo=timezone.utc)
        c, m = make(origin, l0_seconds=10, ack_seconds=10)
        m.handle(Event.SIT)
        hold(c, m, 10)
        m.handle(Event.RESPOND)
        hold(c, m, 10)
        self.assertEqual(m.snapshot()['pending_level'], 'L0')
        m.handle(Event.RESPOND)
        self.assertEqual(m.snapshot()['pending_level'], 'L0')
        self.assertEqual(m.snapshot()['cooldown_seconds'], None)
        hold(c, m, 40)
        self.assertEqual(m.export()['broadcasts'][0]['at'], 60)

    def test_injected_clock_going_backwards_is_rejected_atomically(self):
        c, m = make()
        m.handle(Event.SIT)
        hold(c, m, 10)
        before = m.export()

        class BackwardsClock:
            now = 9
            wall_at = c.wall_at

        m.clock = BackwardsClock()
        with self.assertRaises(ValueError):
            m.handle(Event.TIMEOUT)
        self.assertEqual(m.export(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
