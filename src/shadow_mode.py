"""Actual AlertEpisodeTracker baseline and bounded, output-isolated shadow work."""
from concurrent.futures import ThreadPoolExecutor, wait
from copy import deepcopy
import json
import threading

if __package__:
    from .guardian_runtime import AlertEpisodeTracker
    from .region_aggregation import aggregate, KINDS, query_bounds, valid_id, valid_time
else:
    from guardian_runtime import AlertEpisodeTracker
    from region_aggregation import aggregate, KINDS, query_bounds, valid_id, valid_time


def region_candidate(batch):
    return aggregate(batch['events'], **batch['query'])


class TrackerBaseline:
    """Replay original helper unchanged. Retain one tracker per model between calls.

    counts are NEW events in this query, not lifetime counts or region-window
    overlap counts. Pre-query frames warm the original episode state.
    """
    def __init__(self):
        self.trackers = {}

    def __call__(self, batch):
        query = query_bounds(**{'start': batch['query']['start_ms'], 'end': batch['query']['end_ms']})
        frames = batch['frames']
        if not isinstance(frames, (list, tuple)) or len(frames) > 10000:
            raise ValueError('frames must be a finite batch of at most 10000 frames')
        for frame in frames:
            if (not isinstance(frame, dict) or not valid_time(frame.get('at_ms'))
                    or not valid_id(frame.get('model_version')) or not isinstance(frame.get('alerts'), list)
                    or len(frame['alerts']) > 1000):
                raise ValueError('invalid baseline frame')
        counts = {model: {kind: 0 for kind in KINDS} for model in {f['model_version'] for f in frames}}
        output = []
        for frame in frames:
            model, at = frame['model_version'], frame['at_ms']
            tracker = self.trackers.setdefault(model, AlertEpisodeTracker())
            events = tracker.update(frame['alerts'], at / 1000)
            if query['start_ms'] <= at < query['end_ms']:
                for kind in KINDS:
                    counts[model][kind] += len(events[kind])
            output.append({'at_ms': at, 'model_version': model, 'new_events': events})
        return {'counts': [{'model_version': model, 'kind': kind, 'count': counts[model][kind]}
                           for model in sorted(counts) for kind in KINDS], 'frames': output}


def compare_counts(legacy, candidate):
    left = {(r['model_version'], r['kind']): r['count'] for r in legacy['counts']}
    right = {(r['model_version'], r['kind']): r['count'] for r in candidate['new_event_counts']}
    differences = []
    for model, kind in sorted(left.keys() | right.keys()):
        old, new = left.get((model, kind), 0), right.get((model, kind), 0)
        if old != new:
            differences.append({'model_version': model, 'kind': kind, 'legacy_count': old,
                                'shadow_count': new, 'delta': new - old})
    return {'matched': not differences, 'differences': differences}


def _json_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _error(stage, exc):
    # Do not echo arbitrary input data or exception messages into reports.
    return {'stage': stage, 'code': type(exc).__name__}


class ShadowRunner:
    """run() returns the original result without waiting for candidate/sink work.

    candidate gets a snapshot taken before legacy executes. legacy receives the
    original argument and returns its original object. Exceptions from legacy
    propagate unchanged. Reports are separate JSON-ready copies.

    Call drain() before final export, then close(), or use a context manager.
    Callbacks must be cooperative: threads cannot forcibly terminate a hung
    callback. max_pending bounds queued+running shadow tasks; skipped reports
    remain internal and never synchronously call a potentially blocking sink.
    """
    def __init__(self, legacy, candidate, *, compare=compare_counts, sink=None, max_pending=8):
        if not all(callable(f) for f in (legacy, candidate, compare)) or (sink is not None and not callable(sink)):
            raise ValueError('legacy, candidate, compare and optional sink must be callable')
        if type(max_pending) is not int or max_pending < 1:
            raise ValueError('max_pending must be a positive integer')
        self.legacy, self.candidate, self.compare, self.sink = legacy, candidate, compare, sink
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='care-shadow')
        self._slots = threading.BoundedSemaphore(max_pending)
        self._lock = threading.Lock()
        self._records, self._futures = [], []
        self._closed = False

    def _set(self, record):
        with self._lock:
            self._records[record['sequence'] - 1] = record

    def _evaluate(self, snapshot, context, record):
        try:
            try:
                record['candidate'] = _json_copy(self.candidate(snapshot))
            except BaseException as exc:
                record['error'] = _error('candidate', exc)
            context['done'].wait()
            if context.get('error'):
                record['error'] = context['error']
            if record['error'] is None:
                try:
                    comparison = _json_copy(self.compare(deepcopy(context['legacy']), deepcopy(record['candidate'])))
                    if not isinstance(comparison, dict) or type(comparison.get('matched')) is not bool:
                        raise ValueError('comparison must contain a boolean matched')
                    comparison.setdefault('differences', [])
                    if not isinstance(comparison['differences'], list):
                        raise ValueError('comparison differences must be a list')
                    record['comparison'] = comparison
                except BaseException as exc:
                    record['error'] = _error('comparison', exc)
            record['status'] = 'failed' if record['error'] else 'completed'
            if self.sink is not None:
                try:
                    self.sink(deepcopy(record))
                except BaseException as exc:
                    record['status'], record['error'] = 'failed', _error('recorder', exc)
            self._set(record)
        finally:
            self._slots.release()

    def run(self, batch):
        with self._lock:
            record = {'schema_version': 1, 'sequence': len(self._records) + 1, 'status': 'pending',
                      'candidate': None, 'comparison': None, 'error': None}
            self._records.append(deepcopy(record))
            closed = self._closed
        context = None
        if closed or not self._slots.acquire(blocking=False):
            record['status'], record['error'] = 'skipped', {'stage': 'scheduling', 'code': 'closed' if closed else 'capacity'}
            self._set(record)
        else:
            try:
                snapshot = deepcopy(batch)
            except BaseException as exc:
                record['status'], record['error'] = 'failed', _error('input_snapshot', exc)
                self._set(record)
                self._slots.release()
            else:
                context = {'done': threading.Event()}
                try:
                    future = self._pool.submit(self._evaluate, snapshot, context, record)
                    with self._lock:
                        self._futures.append(future)
                except BaseException as exc:
                    context = None
                    record['status'], record['error'] = 'failed', _error('scheduling', exc)
                    self._set(record)
                    self._slots.release()
        try:
            result = self.legacy(batch)
            if context is not None:
                try:
                    context['legacy'] = deepcopy(result)
                except BaseException as exc:
                    context['error'] = _error('legacy_snapshot', exc)
            return result
        except BaseException as exc:
            if context is not None:
                context['error'] = _error('legacy', exc)
            raise
        finally:
            if context is not None:
                context['done'].set()

    def drain(self, timeout=None):
        with self._lock:
            futures = list(self._futures)
        _, pending = wait(futures, timeout=timeout)
        if pending:
            raise TimeoutError('shadow work is still pending')
        for future in futures:
            future.result()

    def reports(self):
        with self._lock:
            return deepcopy(self._records)

    def close(self):
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
