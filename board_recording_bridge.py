"""Cloud-side authenticated facade for recordings kept on the edge board.

The HarmonyOS client keeps its account-authenticated API. Only the cloud
service knows the board history token; the media bytes are streamed through it.
"""

import json
import os
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

DAY = 86_400_000
RETENTION_MS = 7 * DAY
PAGE = 200
MAX_PAGES = 12


class BoardRecordingUnavailable(RuntimeError):
    pass


def configured():
    return bool(os.environ.get('BOARD_RECORDING_BASE_URL'))


def _settings():
    base = os.environ.get('BOARD_RECORDING_BASE_URL', '').rstrip('/')
    token = os.environ.get('BOARD_RECORDING_TOKEN', '')
    parsed = urlsplit(base)
    try:
        port = parsed.port
    except ValueError:
        raise BoardRecordingUnavailable('board bridge is not configured') from None
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or port is None or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or not token):
        raise BoardRecordingUnavailable('board bridge is not configured')
    return base, token


def _open(path, query=None, timeout=8):
    base, token = _settings()
    url = base + path
    if query:
        url += '?' + urlencode(query)
    request = Request(url, headers={'Authorization': 'Bearer ' + token})
    try:
        return urlopen(request, timeout=timeout)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise BoardRecordingUnavailable(type(exc).__name__) from None


def _get_json(path, query=None):
    with _open(path, query) as response:
        try:
            return json.load(response)
        except (ValueError, UnicodeError):
            raise BoardRecordingUnavailable('invalid board response') from None


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace('+00:00', 'Z')


def _ms(value):
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000)


def _pages(path, start, end, extra=None):
    query = {'start': _iso(start), 'end': _iso(end), 'limit': PAGE}
    if extra:
        query.update(extra)
    for page in range(MAX_PAGES):
        query['offset'] = page * PAGE
        result = _get_json(path, query)
        items = result.get('items')
        if not isinstance(items, list):
            raise BoardRecordingUnavailable('invalid board index')
        yield from items
        if len(items) < PAGE:
            return
    raise BoardRecordingUnavailable('board index exceeds query bound')


def snapshot(as_of, kind):
    now = int(time.time() * 1000)
    as_of = min(int(as_of), now)
    available_start = max(as_of - RETENTION_MS, now - RETENTION_MS)
    end = as_of
    if end <= available_start:
        return {'success': True, 'asOf': as_of, 'windowStart': as_of - RETENTION_MS,
                'windowEnd': end, 'status': 'waiting', 'clips': [], 'eventCount': 0,
                'wholeSegments': False}
    status = _get_json('/api/history/status')
    target_kind = 'sit' if kind == 'sedentary' else kind
    query = {} if kind == 'all' else {'kind': target_kind}
    events = list(_pages('/api/history/events', available_start, end, query))
    clips = []
    for event in events:
        try:
            start_ms = _ms(event['started_at'])
            end_ms = _ms(event['ended_at']) if event.get('ended_at') else start_ms
            event_id = event['id']
            event_kind = event['kind']
            if (not isinstance(event_id, str) or not event_id.isascii()
                    or not all(character.isalnum() or character in '_-' for character in event_id)
                    or event_kind not in ('fall', 'sit', 'stranger')):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        try:
            detail = _get_json('/api/history/events/' + event_id)
        except BoardRecordingUnavailable:
            continue
        linked = detail.get('recordings')
        complete = next((row for row in linked or [] if row.get('state') == 'complete'), None)
        recording_id = complete.get('id') if isinstance(complete, dict) else ''
        if (recording_id and (not isinstance(recording_id, str) or not recording_id.isascii()
                or not all(character.isalnum() or character in '_-' for character in recording_id))):
            recording_id = ''
        clips.append({'id': event_id, 'segmentId': recording_id,
                      'startTime': start_ms, 'endTime': max(start_ms, end_ms),
                      'eventType': 'sedentary' if event_kind == 'sit' else event_kind,
                      'endUnconfirmed': not bool(event.get('ended_at')),
                      'downloadable': bool(recording_id)})
    return {'success': True, 'asOf': as_of, 'windowStart': as_of - RETENTION_MS,
            'windowEnd': end,
            'status': 'recording' if status.get('state') == 'running' else status.get('state', 'waiting'),
            'clips': sorted(clips, key=lambda row: row['startTime'], reverse=True),
            'eventCount': len(clips), 'wholeSegments': False}


def open_media(clip_id):
    if (not isinstance(clip_id, str) or not clip_id.isascii()
            or not all(character.isalnum() or character in '_-' for character in clip_id)):
        raise BoardRecordingUnavailable('invalid clip id')
    return _open('/api/history/recordings/' + clip_id + '/video', timeout=30)
