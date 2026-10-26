"""Cloud-side authenticated facade for recordings kept on the edge board.

The HarmonyOS client keeps its account-authenticated API. Only the cloud
service knows the board history token; the media bytes are streamed through it.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

DAY = 86_400_000
RETENTION_MS = 7 * DAY
PAGE = 200
MAX_PAGES = 12
# 固定上限：一个日期窗口内并发读取事件详情，绝不为每个事件单独建线程。
EVENT_WORKERS = 8
KINDS = ('all', 'fall', 'sedentary', 'stranger')
EVENT_KINDS = ('fall', 'sit', 'stranger')


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


def _clip_from_event(event):
    """把一个事件摘要和它的详情转成前端 clip；事件本身无效时返回 None。"""
    try:
        start_ms = _ms(event['started_at'])
        end_ms = _ms(event['ended_at']) if event.get('ended_at') else start_ms
        event_id = event['id']
        event_kind = event['kind']
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if (event_kind not in EVENT_KINDS or not isinstance(event_id, str) or not event_id.isascii()
            or not all(character.isalnum() or character in '_-' for character in event_id)):
        return None
    try:
        detail = _get_json('/api/history/events/' + event_id)
    except BoardRecordingUnavailable:
        return None
    linked = detail.get('recordings') if isinstance(detail, dict) else None
    if not isinstance(linked, list):
        linked = []
    complete = next((row for row in linked
                     if isinstance(row, dict) and row.get('state') == 'complete'), None)
    recording_id = complete.get('id') if complete else ''
    if (recording_id and (not isinstance(recording_id, str) or not recording_id.isascii()
            or not all(character.isalnum() or character in '_-' for character in recording_id))):
        recording_id = ''
    return {'id': event_id, 'segmentId': recording_id,
            'startTime': start_ms, 'endTime': max(start_ms, end_ms),
            'eventType': 'sedentary' if event_kind == 'sit' else event_kind,
            'endUnconfirmed': not bool(event.get('ended_at')),
            'downloadable': bool(recording_id)}


def snapshot(as_of, kind, window_start=None, window_end=None):
    """只返回 [retention_start, now] 与请求窗口交集内的事件。

    调用方可以只传 as_of（旧客户端，覆盖整个留存窗口），也可以传一个自然日范围。
    反向、零长度、未来以及完全晚于 asOf 的窗口抛 ValueError。
    格式合法但已经滚出留存范围的窗口返回空快照。
    """
    if kind not in KINDS:
        raise ValueError('unknown kind')
    now = int(time.time() * 1000)
    as_of = min(int(as_of), now)
    retention_start = now - RETENTION_MS
    if window_start is None:
        window_start = as_of - RETENTION_MS
    if window_end is None:
        window_end = as_of
    try:
        requested_start = int(window_start)
        requested_end = int(window_end)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('invalid window') from None
    if requested_start >= requested_end:
        raise ValueError('invalid window')
    if requested_start >= as_of:
        raise ValueError('invalid window')
    if requested_end <= retention_start:
        return {'success': True, 'asOf': as_of, 'windowStart': retention_start,
                'windowEnd': retention_start, 'status': 'waiting', 'clips': [],
                'eventCount': 0, 'wholeSegments': False}
    available_start = max(requested_start, retention_start)
    end = min(requested_end, as_of, now)
    if available_start >= end:
        # asOf 本身已早于当前留存起点时，不再访问板端，只返回空快照。
        boundary = min(max(end, retention_start), now)
        return {'success': True, 'asOf': as_of, 'windowStart': boundary,
                'windowEnd': boundary, 'status': 'waiting', 'clips': [],
                'eventCount': 0, 'wholeSegments': False}
    status = _get_json('/api/history/status')
    target_kind = 'sit' if kind == 'sedentary' else kind
    query = {} if kind == 'all' else {'kind': target_kind}
    events = list(_pages('/api/history/events', available_start, end, query))
    if events:
        with ThreadPoolExecutor(max_workers=EVENT_WORKERS) as pool:
            clips = [clip for clip in pool.map(_clip_from_event, events) if clip is not None]
    else:
        clips = []
    # 不依赖板端端点的边界包含规则；日期分组统一按 startTime 属于 [start, end)。
    clips = [clip for clip in clips if available_start <= clip['startTime'] < end]
    return {'success': True, 'asOf': as_of, 'windowStart': available_start,
            'windowEnd': end,
            'status': 'recording' if status.get('state') == 'running' else status.get('state', 'waiting'),
            'clips': sorted(clips, key=lambda row: row['startTime'], reverse=True),
            'eventCount': len(clips), 'wholeSegments': False}


def open_media(clip_id):
    if (not isinstance(clip_id, str) or not clip_id.isascii()
            or not all(character.isalnum() or character in '_-' for character in clip_id)):
        raise BoardRecordingUnavailable('invalid clip id')
    return _open('/api/history/recordings/' + clip_id + '/video', timeout=30)
