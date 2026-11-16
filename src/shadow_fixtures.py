"""Reproducible dual-view scenarios and replaceable in-memory source adapter."""
from copy import deepcopy

if __package__:
    from .shadow_mode import ShadowRunner, TrackerBaseline, region_candidate
else:
    from shadow_mode import ShadowRunner, TrackerBaseline, region_candidate


class FixtureSource:
    def __init__(self, batch):
        self._batch = deepcopy(batch)

    def read_batch(self):
        return deepcopy(self._batch)


def evaluate_source(source):
    """Source seam: only read_batch() changes when real adapters are introduced.

    One finite replay uses a fresh baseline. Persistent trackers across batches
    can be supplied directly to ShadowRunner by a future owning application.
    """
    batch = source.read_batch()
    with ShadowRunner(TrackerBaseline(), region_candidate) as runner:
        legacy = runner.run(batch)
        runner.drain()
        return {'legacy': legacy, 'shadow': runner.reports()[0]}


def _event(name='e1', person='p1', region='room-a', kind='fall', start=0, end=1000, model='v1'):
    return dict(event_id=name, person_id=person, region_id=region, kind=kind,
                start_ms=start, end_ms=end, model_version=model)


def _alert(person=1, kind=None, face=None):
    result = {'id': person}
    if kind == 'fall':
        result['status'] = 'FALL'
    elif kind == 'sit':
        result['is_sitting'] = True
    if kind == 'stranger' or face is not None:
        result['face_label'] = face or 'stranger'
    return result


def _frame(at, *alerts, model='v1'):
    return dict(at_ms=at, model_version=model, alerts=list(alerts))


def fixtures():
    cases = []
    def add(name, events, frames, groups, *, start=0, end=600000, summary=None, matched=True, differences=None):
        cases.append({'name': name, 'batch': {'events': events, 'frames': frames,
                     'query': {'start_ms': start, 'end_ms': end}}, 'groups': groups,
                      'summary': summary or {}, 'matched': matched, 'differences': differences or []})

    # Expected group tuples are hand-calculated: model, region, kind, window,
    # event_count, person_count, duration sum, occupied union.
    add('regular_single_region', [_event()], [_frame(0, _alert(kind='fall')), _frame(1000, _alert())],
        [('v1', 'room-a', 'fall', 0, 1, 1, 1000, 1000)])
    add('two_regions_two_kinds', [_event(), _event('e2', 'p2', 'room-b', 'sit', 0, 2000)],
        [_frame(0, _alert(kind='fall'), _alert(2, 'sit')), _frame(1000, _alert(), _alert(2, 'sit')),
         _frame(2000, _alert(), _alert(2))],
        [('v1', 'room-a', 'fall', 0, 1, 1, 1000, 1000), ('v1', 'room-b', 'sit', 0, 1, 1, 2000, 2000)])
    add('overlapping_people', [_event(), _event('e2', 'p2', start=500, end=1500)],
        [_frame(0, _alert(kind='fall')), _frame(500, _alert(kind='fall'), _alert(2, 'fall')),
         _frame(1000, _alert(), _alert(2, 'fall')), _frame(1500, _alert(), _alert(2))],
        [('v1', 'room-a', 'fall', 0, 2, 2, 2000, 1500)])
    add('cross_five_minute_window', [_event(kind='sit', start=299000, end=301000)],
        [_frame(299000, _alert(kind='sit')), _frame(301000, _alert())],
        [('v1', 'room-a', 'sit', 0, 1, 1, 1000, 1000), ('v1', 'room-a', 'sit', 300000, 1, 1, 1000, 1000)])
    add('instant_at_window_boundary', [_event(start=300000, end=300000)],
        [_frame(300000, _alert(kind='fall')), _frame(300001, _alert())],
        [('v1', 'room-a', 'fall', 300000, 1, 1, 0, 0)])
    add('ends_exactly_at_window_boundary', [_event(start=299000, end=300000)],
        [_frame(299000, _alert(kind='fall')), _frame(300000, _alert())],
        [('v1', 'room-a', 'fall', 0, 1, 1, 1000, 1000)])
    add('query_clip_and_warmup', [_event(end=500), _event('warm', 'p2', kind='sit', start=500, end=1500),
        _event('later', 'p3', kind='sit', start=2500, end=3500), _event('out', start=3000, end=3000)],
        [_frame(0, _alert(kind='fall')), _frame(500, _alert(), _alert(2, 'sit')),
         _frame(1500, _alert(2)), _frame(2500, _alert(3, 'sit')), _frame(3500, _alert(3))],
        [('v1', 'room-a', 'sit', 0, 2, 2, 1000, 1000)], start=1000, end=3000,
        summary={'included': 2, 'excluded': 2})
    add('model_versions_isolated', [_event(end=1), _event(end=1, model='v2')],
        [_frame(0, _alert(kind='fall')), _frame(0, _alert(kind='fall'), model='v2'),
         _frame(1, _alert()), _frame(1, _alert(), model='v2')],
        [('v1', 'room-a', 'fall', 0, 1, 1, 1, 1), ('v2', 'room-a', 'fall', 0, 1, 1, 1, 1)])
    add('exact_duplicate', [_event(), _event()], [_frame(0, _alert(kind='fall')), _frame(1000, _alert())],
        [('v1', 'room-a', 'fall', 0, 1, 1, 1000, 1000)], summary={'duplicates': 1, 'accepted': 1})
    add('conflicting_duplicate', [_event(), _event(region='room-b')], [_frame(0, _alert(kind='fall'))], [],
        summary={'rejected': 2}, matched=False,
        differences=[dict(model_version='v1', kind='fall', legacy_count=1, shadow_count=0, delta=-1)])
    invalid = [None, _event('bool', start=True), _event('nan', start=float('nan')),
               _event('inf', end=float('inf')), _event('reversed', start=2, end=1),
               _event('open', end=None), _event('kind', kind='unknown'), _event('blank', region='')]
    add('invalid_rows_are_diagnosed', [_event()] + invalid,
        [_frame(0, _alert(kind='fall')), _frame(1000, _alert())],
        [('v1', 'room-a', 'fall', 0, 1, 1, 1000, 1000)], summary={'rejected': 8, 'accepted': 1})
    add('normal_then_recurrence', [_event('first', kind='sit'), _event('second', kind='sit', start=2000, end=3000)],
        [_frame(0, _alert(kind='sit')), _frame(1000, _alert()),
         _frame(2000, _alert(kind='sit')), _frame(3000, _alert())],
        [('v1', 'room-a', 'sit', 0, 2, 1, 2000, 2000)])
    add('four_seconds_tolerated', [_event(end=4001)],
        [_frame(0, _alert(kind='fall')), _frame(4000, _alert(kind='fall')), _frame(4001, _alert())],
        [('v1', 'room-a', 'fall', 0, 1, 1, 4001, 4001)])
    add('over_four_seconds_new_episode', [_event('first', end=0), _event('second', start=4001, end=4001)],
        [_frame(0, _alert(kind='fall')), _frame(4001, _alert(kind='fall'))],
        [('v1', 'room-a', 'fall', 0, 2, 1, 0, 0)])
    add('stranger_pending_known', [_event('first', kind='stranger', end=3000),
        _event('second', kind='stranger', start=4000, end=4500)],
        [_frame(0, _alert(kind='stranger')), _frame(1000, _alert(face='pending')),
         _frame(2000, _alert(kind='stranger')), _frame(3000, _alert(face='known:demo')),
         _frame(4000, _alert(kind='stranger')), _frame(4500, _alert(face='known:demo'))],
        [('v1', 'room-a', 'stranger', 0, 2, 1, 3500, 3500)])
    add('intentional_count_difference', [_event()],
        [_frame(0, _alert(kind='fall')), _frame(5000, _alert(kind='fall'))],
        [('v1', 'room-a', 'fall', 0, 1, 1, 1000, 1000)], matched=False,
        differences=[dict(model_version='v1', kind='fall', legacy_count=2, shadow_count=1, delta=-1)])
    add('empty_batch', [], [], [])
    return cases


def run_case(case):
    output = evaluate_source(FixtureSource(case['batch']))
    checks = []
    def check(label, actual, expected):
        checks.append({'label': label, 'actual': actual, 'expected': expected, 'passed': actual == expected})
    report = output['shadow']
    check('shadow completed', report['status'], 'completed')
    if report['status'] == 'completed':
        candidate = report['candidate']
        keys = ('model_version', 'region_id', 'kind', 'window_start_ms', 'event_count',
                'person_count', 'event_duration_ms', 'occupied_duration_ms')
        check('hand calculated region groups', [tuple(g[k] for k in keys) for g in candidate['groups']],
              [tuple(g) for g in case['groups']])
        check('comparison matched', report['comparison']['matched'], case['matched'])
        check('count differences', report['comparison']['differences'], case['differences'])
        for key, expected in case['summary'].items():
            check('summary ' + key, candidate['summary'][key], expected)
        summary = candidate['summary']
        check('row accounting', summary['received'], summary['accepted'] + summary['duplicates'] + summary['rejected'])
        check('inclusion accounting', summary['accepted'], summary['included'] + summary['excluded'])
    return {'name': case['name'], 'passed': all(c['passed'] for c in checks), 'checks': checks, **output}


def run_all(cases=None):
    return [run_case(case) for case in (fixtures() if cases is None else cases)]
