"""Pure weekly metrics. Fixed-offset civil weeks; no prose or risk inference.

Events belong to their start instant. Observations are half-open intervals,
split at civil period/week boundaries and unioned; overlaps never add time.
One sample = a clock minute with at least 30 valid observed seconds.
"""
from datetime import date, datetime, timedelta, timezone
import math
import heapq

PERIODS = ('night', 'morning', 'afternoon', 'evening')
KINDS = ('fall', 'sit', 'stranger')


def week_bounds(week_start, offset_minutes):
    if type(offset_minutes) is not int or not -840 <= offset_minutes <= 840 or offset_minutes % 15:
        raise ValueError('invalid fixed timezone offset')
    day = date.fromisoformat(week_start)
    if day.weekday() != 0 or day.isoformat() != week_start:
        raise ValueError('week_start must be an ISO Monday date')
    start = datetime.combine(day, datetime.min.time(), timezone(timedelta(minutes=offset_minutes))).timestamp()
    if start < 604800:
        raise ValueError('week is outside supported epoch range')
    return start, start + 604800


def metrics(events, observations, spans, confirmations, coverage=None):
    if coverage is not None:
        selected = {e['event_id'] for e in events if any(a<=e['started_at']<b for a,b in spans)}
        result = dict(coverage)
        result.update(event_count=len(selected),human_confirmed_count=len(selected & confirmations),
                      event_rate_per_hour=len(selected)*3600/result['effective_observation_seconds']
                      if result['effective_observation_seconds'] else None)
        return result
    observed = valid = known = weighted = 0.0
    minutes = {}
    for start, end in spans:
        rows = [o for o in observations if o['ended_at'] > start and o['started_at'] < end]
        changes = {start:[],end:[]}
        for identity,o in enumerate(rows):
            changes.setdefault(max(start,o['started_at']),[]).append((True,identity,o))
            changes.setdefault(min(end,o['ended_at']),[]).append((False,identity,o))
        edges = sorted(changes)
        active,good,scores = set(),set(),[]
        for a,b in zip(edges,edges[1:]):
            for added,identity,o in changes[a]:
                if added:
                    active.add(identity)
                    if o['valid']:
                        good.add(identity)
                        if o['quality'] is not None:
                            heapq.heappush(scores,(o['quality'],identity))
                else:
                    active.discard(identity)
                    good.discard(identity)
            if not active:
                continue
            observed += b-a
            if not good:
                continue
            valid += b-a
            while scores and scores[0][1] not in good:
                heapq.heappop(scores)
            if scores:
                known += b-a
                weighted += scores[0][0]*(b-a)
            cursor = a
            while cursor < b:
                minute = math.floor(cursor/60)
                stop = min(b, (minute+1)*60)
                minutes[minute] = minutes.get(minute, 0) + stop-cursor
                cursor = stop
    selected = {e['event_id']:e for e in events if any(a <= e['started_at'] < b for a,b in spans)}
    return dict(event_count=len(selected),
        human_confirmed_count=sum(identity in confirmations for identity in selected),
        effective_observation_seconds=float(valid), sample_count=sum(v >= 30 for v in minutes.values()),
        observation_status=('no_observations' if not observed else 'unusable_observations' if not valid else 'observed'),
        event_rate_per_hour=(len(selected)*3600/valid if valid else None),
        perception_quality=dict(valid_fraction=valid/observed if observed else None,
                                score=weighted/known if known else None,
                                score_coverage=known/valid if valid else None))


def aggregate(*, week_start, offset_minutes, regions, events, observations, confirmations, min_samples):
    start, end = week_bounds(week_start, offset_minutes)
    groups = []
    for region in regions:
        obs = [o for o in observations if o['region_id']==region]
        for period, name in enumerate(PERIODS):
            spans = [(start+d*86400+period*21600, start+d*86400+(period+1)*21600) for d in range(7)]
            previous_spans = [(a-604800,b-604800) for a,b in spans]
            current_coverage = metrics([],obs,spans,set())
            previous_coverage = metrics([],obs,previous_spans,set())
            for kind in KINDS:
                ev = [e for e in events if e['region_id']==region and e['kind']==kind]
                current = metrics(ev, [], spans, confirmations,current_coverage)
                previous = metrics(ev, [], previous_spans, confirmations,previous_coverage)
                status = ('no_observations' if current['observation_status']=='no_observations' else
                          'insufficient_samples' if min(current['sample_count'],previous['sample_count']) < min_samples else 'ready')
                trend = None
                if status == 'ready':
                    old, new = previous['event_rate_per_hour'], current['event_rate_per_hour']
                    delta = new-old
                    trend = dict(direction='up' if delta>0 else 'down' if delta<0 else 'flat',
                                 rate_delta=delta, relative_delta=delta/old if old else None)
                groups.append(dict(region_id=region, period_id=name, event_type=kind,
                                   current=current, previous=previous, trend_status=status, trend=trend))
    return dict(schema_version=1, week_start=week_start, offset_minutes=offset_minutes,
                start_at=start, end_at=end, min_samples=min_samples, groups=groups)
