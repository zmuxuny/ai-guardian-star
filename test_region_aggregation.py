"""Hand-calculated offline region aggregation contracts."""
import copy
import json
import unittest

from src.region_aggregation import aggregate


def event(name='e1', person='p1', region='room-a', kind='fall', start=0, end=1000, model='v1'):
    return dict(event_id=name, person_id=person, region_id=region, kind=kind,
                start_ms=start, end_ms=end, model_version=model)


class RegionTests(unittest.TestCase):
    def calc(self, events, start=0, end=600000):
        return aggregate(events, start_ms=start, end_ms=end)

    def test_overlap_distinguishes_sum_people_and_coverage(self):
        result = self.calc([event(), event('e2', 'p2', start=500, end=1500),
                            event('e3', region='room-b', kind='sit', start=100, end=200)])
        self.assertEqual([(g['region_id'], g['kind'], g['event_count'], g['person_count'],
                           g['event_duration_ms'], g['occupied_duration_ms']) for g in result['groups']],
                         [('room-a', 'fall', 2, 2, 2000, 1500), ('room-b', 'sit', 1, 1, 100, 100)])

    def test_cross_window_count_is_separate_from_new_event_count(self):
        result = self.calc([event(start=299000, end=301000)])
        self.assertEqual([(g['window_start_ms'], g['event_count'], g['event_duration_ms'])
                          for g in result['groups']], [(0, 1, 1000), (300000, 1, 1000)])
        self.assertEqual(result['new_event_counts'], [{'model_version': 'v1', 'kind': 'fall', 'count': 1}])

    def test_end_boundary_instant_points_and_exclusion(self):
        result = self.calc([event(end=300000), event('instant', start=300000, end=300000),
                            event('outside', start=600000, end=600000)])
        self.assertEqual([(g['window_start_ms'], g['event_duration_ms']) for g in result['groups']],
                         [(0, 300000), (300000, 0)])
        self.assertEqual(result['summary']['excluded'], 1)

    def test_query_clipping_and_warm_event_not_counted_as_new(self):
        result = self.calc([event(start=500, end=1500), event('later', start=2500, end=3500)], 1000, 3000)
        self.assertEqual(result['groups'][0]['event_duration_ms'], 1000)
        self.assertEqual(result['groups'][0]['occupied_duration_ms'], 1000)
        self.assertEqual(result['groups'][0]['person_count'], 1)
        self.assertEqual(result['new_event_counts'][0]['count'], 1)

    def test_exact_duplicates_and_models_are_independent(self):
        first = event()
        result = self.calc([first, copy.deepcopy(first), event(model='v2')])
        self.assertEqual(result['summary'], dict(received=3, accepted=2, included=2,
                                                 excluded=0, duplicates=1, rejected=0))
        self.assertEqual([g['model_version'] for g in result['groups']], ['v1', 'v2'])

    def test_conflicting_duplicate_rejects_entire_key_independent_of_order(self):
        first, second = event(), event(region='room-b')
        for rows in ([first, first, second], [second, first, first]):
            result = self.calc(rows)
            self.assertEqual(result['groups'], [])
            self.assertEqual(result['summary']['rejected'], 3)
            self.assertEqual(result['summary']['duplicates'], 0)
            self.assertEqual([r['code'] for r in result['rejected']], ['conflicting_duplicate'] * 3)

    def test_invalid_inputs_are_explicit_and_json_remains_finite(self):
        rows = [None, event(start=True), event(start=float('nan')), event(end=float('inf')),
                event(start=-1), event(start=2, end=1), event(end=None), event(kind='unknown'),
                event(person=''), event(name=''), event(region=''), event(model='')]
        result = self.calc(rows)
        self.assertEqual([r['code'] for r in result['rejected']], [
            'invalid_event', 'invalid_start_ms', 'invalid_start_ms', 'invalid_end_ms',
            'invalid_start_ms', 'reversed_interval', 'open_event', 'invalid_kind',
            'invalid_person_id', 'invalid_event_id', 'invalid_region_id', 'invalid_model_version'])
        self.assertEqual(result['summary']['rejected'], 12)
        json.dumps(result, allow_nan=False)

    def test_schema_exact_types_empty_and_repeatable_bytes(self):
        result = self.calc([])
        self.assertEqual(set(result), {'schema_version', 'query', 'summary', 'groups', 'rejected', 'new_event_counts'})
        self.assertEqual(result['groups'], [])
        result = self.calc([event()])
        group = result['groups'][0]
        self.assertEqual(set(group), {'model_version', 'region_id', 'kind', 'window_start_ms',
                                     'window_end_ms', 'event_count', 'person_count',
                                     'event_duration_ms', 'occupied_duration_ms'})
        for key, value in group.items():
            self.assertIs(type(value), str if key in ('model_version', 'region_id', 'kind') else int)
        self.assertEqual(json.dumps(result, sort_keys=True), json.dumps(self.calc([event()]), sort_keys=True))

    def test_query_and_work_limits_are_rejected(self):
        for start, end in ((True, 100), (0, 0), (10, 1), (-1, 10), (0, float('inf')),
                           (0, 86400001)):
            with self.assertRaises(ValueError):
                self.calc([], start, end)
        with self.assertRaises(ValueError):
            self.calc([event()] * 10001)

    def test_input_is_unchanged_and_order_does_not_change_groups(self):
        rows = [event('e2', 'p2'), event('e1')]
        before = copy.deepcopy(rows)
        first = self.calc(rows)
        self.assertEqual(rows, before)
        self.assertEqual(first, self.calc(list(reversed(rows))))


if __name__ == '__main__':
    unittest.main(verbosity=2)
