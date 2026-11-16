"""Pure, bounded region aggregation; input/output protocol v1, no real I/O."""
from collections import defaultdict

WINDOW_MS = 300000
MAX_TIME_MS = 253402300799999
MAX_EVENTS = 10000
MAX_QUERY_MS = 86400000
MAX_FRAGMENTS = 100000
KINDS = ('fall', 'sit', 'stranger')
FIELDS = ('event_id', 'person_id', 'model_version', 'region_id', 'kind', 'start_ms', 'end_ms')


def valid_id(value):
    return (isinstance(value, str) and 0 < len(value) <= 128 and value == value.strip()
            and all(ord(c) >= 32 and ord(c) != 127 for c in value))


def valid_time(value):
    return type(value) is int and 0 <= value <= MAX_TIME_MS


def query_bounds(start, end):
    if not valid_time(start) or not valid_time(end) or not 0 < end - start <= MAX_QUERY_MS:
        raise ValueError('query requires integer milliseconds, start < end, span <= 24 hours')
    return {'start_ms': start, 'end_ms': end, 'window_ms': WINDOW_MS}


def _invalid(row):
    if not isinstance(row, dict):
        return 'invalid_event'
    for name in FIELDS[:4]:
        if not valid_id(row.get(name)):
            return 'invalid_' + name
    if row.get('kind') not in KINDS:
        return 'invalid_kind'
    if not valid_time(row.get('start_ms')):
        return 'invalid_start_ms'
    if row.get('end_ms') is None:
        return 'open_event'
    if not valid_time(row.get('end_ms')):
        return 'invalid_end_ms'
    if row['end_ms'] < row['start_ms']:
        return 'reversed_interval'
    return None


def _union(intervals):
    total, right = 0, None
    for start, end in sorted(intervals):
        if right is None or start > right:
            total += end - start
        elif end > right:
            total += end - right
        right = end if right is None else max(right, end)
    return total


def aggregate(events, *, start_ms, end_ms):
    query = query_bounds(start_ms, end_ms)
    if not isinstance(events, (list, tuple)) or len(events) > MAX_EVENTS:
        raise ValueError('events must be a finite batch of at most 10000 rows')
    rejected, candidates = [], defaultdict(list)

    def reject(index, row, code):
        identity = row.get('event_id') if isinstance(row, dict) else None
        rejected.append({'input_index': index, 'event_id': identity if valid_id(identity) else None, 'code': code})

    for index, row in enumerate(events):
        invalid = _invalid(row)
        if invalid:
            reject(index, row, invalid)
        else:
            normalized = {key: row[key] for key in FIELDS}
            candidates[(row['person_id'], row['model_version'], row['event_id'])].append((index, normalized))
    accepted, duplicates = [], 0
    for key in sorted(candidates):
        rows = candidates[key]
        signatures = {tuple(row[field] for field in FIELDS) for _, row in rows}
        if len(signatures) > 1:
            for index, row in rows:
                reject(index, row, 'conflicting_duplicate')
        else:
            accepted.append(rows[0][1])
            duplicates += len(rows) - 1

    buckets, new_counts = {}, defaultdict(int)
    included, fragments = 0, 0
    for row in accepted:
        start, end = row['start_ms'], row['end_ms']
        if start_ms <= start < end_ms:
            new_counts[(row['model_version'], row['kind'])] += 1
        point = start == end
        if (point and not start_ms <= start < end_ms) or (not point and (end <= start_ms or start >= end_ms)):
            continue
        included += 1
        left, right = max(start, start_ms), min(end, end_ms)
        first = left // WINDOW_MS
        last = first if point else (right - 1) // WINDOW_MS
        fragments += last - first + 1
        if fragments > MAX_FRAGMENTS:
            raise ValueError('event/window fragment budget exceeded')
        for window in range(first, last + 1):
            key = row['model_version'], row['region_id'], row['kind'], window * WINDOW_MS
            bucket = buckets.setdefault(key, {'events': set(), 'people': set(), 'duration': 0, 'intervals': []})
            begin, finish = max(left, key[3]), min(right, key[3] + WINDOW_MS)
            bucket['events'].add((row['person_id'], row['event_id']))
            bucket['people'].add(row['person_id'])
            bucket['duration'] += finish - begin
            bucket['intervals'].append((begin, finish))
    groups = []
    for (model, region, kind, window), value in sorted(buckets.items()):
        groups.append({'model_version': model, 'region_id': region, 'kind': kind,
                       'window_start_ms': window, 'window_end_ms': window + WINDOW_MS,
                       'event_count': len(value['events']), 'person_count': len(value['people']),
                       'event_duration_ms': value['duration'], 'occupied_duration_ms': _union(value['intervals'])})
    return {'schema_version': 1, 'query': query,
            'summary': {'received': len(events), 'accepted': len(accepted), 'included': included,
                        'excluded': len(accepted) - included, 'duplicates': duplicates, 'rejected': len(rejected)},
            'groups': groups, 'rejected': sorted(rejected, key=lambda row: row['input_index']),
            'new_event_counts': [{'model_version': model, 'kind': kind, 'count': count}
                                 for (model, kind), count in sorted(new_counts.items())]}
