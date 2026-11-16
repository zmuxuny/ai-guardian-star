"""The actual old helper remains the baseline; shadow failures cannot replace it."""
from copy import deepcopy
import json
import threading
import unittest

from src.guardian_runtime import AlertEpisodeTracker
from src.shadow_mode import ShadowRunner, TrackerBaseline, compare_counts, region_candidate


def frame(at, alerts, model='v1'):
    return {'at_ms': at, 'model_version': model, 'alerts': alerts}


def batch(frames=None, events=None, start=0, end=10000):
    return {'query': {'start_ms': start, 'end_ms': end}, 'frames': frames or [], 'events': events or []}


class BaselineTests(unittest.TestCase):
    def test_actual_helper_frames_and_counts_match_direct_execution(self):
        frames = [frame(0, [{'id': 1, 'status': 'FALL'}]),
                  frame(1000, [{'id': 1, 'status': 'FALL'}]),
                  frame(2000, [{'id': 1}]), frame(3000, [{'id': 1, 'is_sitting': True}])]
        tracker = AlertEpisodeTracker()
        expected = [tracker.update(f['alerts'], f['at_ms'] / 1000) for f in frames]
        result = TrackerBaseline()(batch(frames))
        self.assertEqual([f['new_events'] for f in result['frames']], expected)
        self.assertEqual(result['counts'], [dict(model_version='v1', kind='fall', count=1),
                                           dict(model_version='v1', kind='sit', count=1),
                                           dict(model_version='v1', kind='stranger', count=0)])

    def test_four_second_gap_stranger_pending_and_known(self):
        frames = [frame(0, [{'id': 1, 'face_label': 'stranger'}]),
                  frame(1000, [{'id': 1, 'face_label': 'pending'}]),
                  frame(2000, [{'id': 1, 'face_label': 'stranger'}]),
                  frame(3000, [{'id': 1, 'face_label': 'known:demo'}]),
                  frame(4000, [{'id': 1, 'face_label': 'stranger'}]),
                  frame(8000, [{'id': 1, 'face_label': 'stranger'}]),
                  frame(12001, [{'id': 1, 'face_label': 'stranger'}])]
        result = TrackerBaseline()(batch(frames, end=13000))
        self.assertEqual(result['counts'][-1]['count'], 3)

    def test_models_and_query_warmup_are_independent(self):
        frames = [frame(0, [{'id': 1, 'status': 'FALL'}]),
                  frame(1000, [{'id': 1, 'status': 'FALL'}]),
                  frame(1000, [{'id': 1, 'status': 'FALL'}], 'v2')]
        result = TrackerBaseline()(batch(frames, start=500))
        self.assertEqual(result['counts'][0]['count'], 0)
        self.assertEqual(result['counts'][3]['count'], 1)

    def test_compare_reports_intentional_nonzero_delta(self):
        result = compare_counts({'counts': [{'model_version': 'v1', 'kind': 'fall', 'count': 2}]},
                                {'new_event_counts': [{'model_version': 'v1', 'kind': 'fall', 'count': 1}]})
        self.assertFalse(result['matched'])
        self.assertEqual(result['differences'], [dict(model_version='v1', kind='fall',
                                                     legacy_count=2, shadow_count=1, delta=-1)])


class ShadowTests(unittest.TestCase):
    def test_shadow_runs_concurrently_and_original_return_identity_is_preserved(self):
        started, release = threading.Event(), threading.Event()
        result = {'unchanged': []}

        def candidate(value):
            started.set()
            if not release.wait(5):
                raise RuntimeError('test did not release candidate')
            return {'shadow': True}

        def legacy(value):
            self.assertTrue(started.wait(5))
            return result

        with ShadowRunner(legacy, candidate, compare=lambda a, b: {'matched': True}) as runner:
            try:
                returned = runner.run({})
                self.assertIs(returned, result)
                self.assertFalse(release.is_set())
            finally:
                release.set()
            runner.drain()
            self.assertEqual(runner.reports()[0]['status'], 'completed')

    def test_candidate_mutation_does_not_change_primary_input(self):
        source = {'items': [1]}
        def candidate(value):
            value['items'].append(99)
            return value
        def legacy(value):
            value['primary_change'] = True
            return value
        with ShadowRunner(legacy, candidate, compare=lambda a, b: {'matched': False}) as runner:
            self.assertIs(runner.run(source), source)
            runner.drain()
        self.assertEqual(source, {'items': [1], 'primary_change': True})
        self.assertEqual(runner.reports()[0]['candidate'], {'items': [1, 99]})

    def test_candidate_compare_and_sink_failures_are_isolated(self):
        def fail(*args):
            raise RuntimeError('injected failure')
        for stage in ('candidate', 'comparison', 'recorder'):
            kwargs = dict(candidate=lambda b: {}, compare=lambda a, b: {'matched': True}, sink=None)
            kwargs[{'candidate': 'candidate', 'comparison': 'compare', 'recorder': 'sink'}[stage]] = fail
            with ShadowRunner(lambda value: 'original', **kwargs) as runner:
                self.assertEqual(runner.run({}), 'original')
                runner.drain()
                record = runner.reports()[0]
                self.assertEqual(record['status'], 'failed')
                self.assertEqual(record['error']['stage'], stage)

    def test_queue_full_is_explicit_and_does_not_block_original(self):
        release = threading.Event()
        def candidate(value):
            release.wait(5)
            return {}
        with ShadowRunner(lambda value: value, candidate,
                          compare=lambda a, b: {'matched': True}, max_pending=1) as runner:
            try:
                runner.run(1)
                self.assertEqual(runner.run(2), 2)
                self.assertEqual(runner.reports()[1]['status'], 'skipped')
                self.assertEqual(runner.reports()[1]['error']['code'], 'capacity')
            finally:
                release.set()
            runner.drain()

    def test_primary_exception_is_not_swallowed(self):
        error = ValueError('original failure')
        def legacy(value):
            raise error
        with ShadowRunner(legacy, lambda b: {}) as runner:
            with self.assertRaises(ValueError) as caught:
                runner.run({})
            self.assertIs(caught.exception, error)
            runner.drain()
            self.assertEqual(runner.reports()[0]['error']['stage'], 'legacy')

    def test_bad_shadow_snapshot_does_not_prevent_original(self):
        class NotCopyable:
            def __deepcopy__(self, memo):
                raise TypeError('cannot copy')
        original = NotCopyable()
        with ShadowRunner(lambda b: b, lambda b: {}) as runner:
            self.assertIs(runner.run(original), original)
            self.assertEqual(runner.reports()[0]['error']['stage'], 'input_snapshot')

    def test_reports_are_detached_and_all_fields_present(self):
        with ShadowRunner(TrackerBaseline(), region_candidate) as runner:
            self.assertEqual(runner.run(batch())['counts'], [])
            runner.drain()
            report = runner.reports()[0]
            self.assertEqual(set(report), {'schema_version', 'sequence', 'status', 'candidate', 'comparison', 'error'})
            self.assertTrue(report['comparison']['matched'])
            report['status'] = 'changed'
            self.assertEqual(runner.reports()[0]['status'], 'completed')

    def test_mutating_comparator_cannot_corrupt_record_or_json_export(self):
        for raises in (False, True):
            def compare(old, new):
                new['not_json'] = {1}
                if raises:
                    raise RuntimeError('comparison failed after modifying its input')
                return {'matched': True}
            with ShadowRunner(lambda value: {'original': True}, lambda value: {'safe': [1]},
                              compare=compare) as runner:
                self.assertEqual(runner.run({}), {'original': True})
                runner.drain()
                record = runner.reports()[0]
                self.assertEqual(record['candidate'], {'safe': [1]})
                self.assertEqual(record['status'], 'failed' if raises else 'completed')
                json.dumps(record, allow_nan=False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
