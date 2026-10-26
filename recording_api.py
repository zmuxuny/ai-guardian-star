"""Authenticated recording queries and bounded MP4 playback downloads."""
import hashlib
import os
import subprocess
import time
from flask import request, jsonify, g, send_file, Response, stream_with_context
from mqtt_access import allowed_users
from recording_store import ROOT, DAY, connect, snapshot
import board_recording_bridge as board_bridge

FFMPEG = os.environ.get('RECORDING_FFMPEG', '/opt/guardian-ffmpeg/bin/ffmpeg')
RETENTION_MS = 7 * DAY
KINDS = ('all', 'fall', 'sedentary', 'stranger')


def _requested_window(data):
    """解析可选的日期窗口；两个字段都缺省时沿用整个留存窗口。"""
    if 'windowStart' not in data and 'windowEnd' not in data:
        return None, None
    if 'windowStart' not in data or 'windowEnd' not in data:
        raise ValueError()
    window_start = int(data['windowStart'])
    window_end = int(data['windowEnd'])
    if window_start >= window_end:
        raise ValueError()
    return window_start, window_end


def _snapshot(as_of, kind, window_start, window_end):
    """开发板模式下把日期窗口交给 bridge；本地回退模式也按窗口裁剪。"""
    if board_bridge.configured():
        return board_bridge.snapshot(as_of, kind, window_start, window_end)
    result = snapshot(as_of, kind)
    if window_start is None:
        return result
    available_start = max(window_start, result.get('windowStart', window_start))
    available_end = min(window_end, result.get('windowEnd', window_end), as_of)
    if available_start >= available_end:
        boundary = min(max(available_end, result.get('windowStart', available_end)),
                       result.get('windowEnd', available_end))
        result['clips'] = []
        result['eventCount'] = 0
        result['windowStart'] = boundary
        result['windowEnd'] = boundary
        return result
    clips = [clip for clip in result.get('clips', [])
             if available_start <= clip['startTime'] < available_end]
    result['clips'] = clips
    result['eventCount'] = len(clips)
    result['windowStart'] = available_start
    result['windowEnd'] = available_end
    return result


def register_recording_routes(app, bearer_required):
    def authorized():
        return g.current_username in allowed_users(os.environ.get('MQTT_USERS_FILE', '/etc/wenxin/mqtt-users.json'))

    @app.post('/api/recordings/query')
    @bearer_required
    def recording_query():
        if not authorized():
            return jsonify(success=False, message='当前账号未获准访问监护设备'), 403
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(success=False, message='请求格式无效'), 400
        kind = data.get('filter', 'all')
        if kind not in KINDS:
            return jsonify(success=False, message='录像筛选类型无效'), 400
        try:
            as_of = int(data.get('asOf', time.time() * 1000))
            if as_of < int(time.time() * 1000) - RETENTION_MS:
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            return jsonify(success=False, message='请刷新查看近7天异常录像'), 400
        try:
            window_start, window_end = _requested_window(data)
        except (ValueError, KeyError, TypeError, OverflowError):
            return jsonify(success=False, message='录像时间范围无效'), 400
        try:
            result = _snapshot(as_of, kind, window_start, window_end)
        except ValueError:
            return jsonify(success=False, message='录像时间范围无效'), 400
        except board_bridge.BoardRecordingUnavailable:
            return jsonify(success=False, message='开发板录像暂不可用，请稍后重试'), 503
        response = jsonify(result)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/api/recordings/media')
    @bearer_required
    def recording_media():
        if not authorized():
            return jsonify(success=False, message='当前账号未获准访问监护设备'), 403
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(success=False, message='请求格式无效'), 400
        kind = data.get('filter')
        if kind not in KINDS:
            return jsonify(success=False, message='录像筛选类型无效'), 400
        clip_id = data.get('clipId')
        if not isinstance(clip_id, str) or clip_id == '':
            return jsonify(success=False, message='请求格式无效'), 400
        try:
            as_of = int(data['asOf'])
            window_start, window_end = _requested_window(data)
        except (ValueError, KeyError, TypeError, OverflowError):
            return jsonify(success=False, message='请求格式无效'), 400
        try:
            result = _snapshot(as_of, kind, window_start, window_end)
        except ValueError:
            return jsonify(success=False, message='录像时间范围无效'), 400
        except board_bridge.BoardRecordingUnavailable:
            return jsonify(success=False, message='开发板录像暂不可用，请稍后重试'), 503
        clip = next((item for item in result.get('clips', []) if item['id'] == clip_id), None)
        if not clip:
            return jsonify(success=False, message='录像已过期或不在筛选范围，请刷新'), 404
        if not clip.get('downloadable', True) or not clip.get('segmentId'):
            return jsonify(success=False, message='异常视频正在生成，请稍后刷新'), 429
        if board_bridge.configured():
            try:
                source = board_bridge.open_media(clip['segmentId'])
            except board_bridge.BoardRecordingUnavailable:
                return jsonify(success=False, message='开发板录像暂不可用，请稍后重试'), 503

            def generate():
                with source:
                    while True:
                        chunk = source.read(65536)
                        if not chunk:
                            break
                        yield chunk

            response = Response(stream_with_context(generate()), mimetype='video/mp4')
            response.headers['Cache-Control'] = 'no-store'
            return response

        import fcntl
        with connect() as db:
            segment = db.execute('SELECT * FROM segments WHERE id=?', (clip['segmentId'],)).fetchone()
        source = ROOT / segment['filename']
        if not source.is_file() or source.parent != ROOT:
            return jsonify(success=False, message='录像文件暂不可用'), 404
        # Never send bytes before/after the requested interval (including the 24h boundary).
        duration = (clip['endTime'] - clip['startTime']) / 1000
        offset = (clip['startTime'] - segment['start_ms']) / 1000
        if offset > 0.01 or clip['endTime'] < segment['end_ms']:
            key = hashlib.sha256(clip['id'].encode()).hexdigest()
            target = ROOT / f'clip-{key}.mp4'
            with (ROOT / 'clip.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return jsonify(success=False, message='正在准备录像，请稍后重试'), 429
                if not target.exists():
                    partial = ROOT / f'clip-{key}.partial.mp4'
                    try:
                        subprocess.run([FFMPEG, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                                        '-ss', str(offset), '-i', str(source), '-t', str(duration), '-an',
                                        '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '1',
                                        '-crf', '25', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(partial)],
                                       check=True, timeout=25, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        partial.replace(target)
                    except (OSError, subprocess.SubprocessError):
                        partial.unlink(missing_ok=True)
                        return jsonify(success=False, message='录像准备失败，请稍后重试'), 503
                source = target
        response = send_file(source, mimetype='video/mp4', conditional=False, max_age=0)
        response.headers['Cache-Control'] = 'no-store'
        return response
