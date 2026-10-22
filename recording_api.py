"""Authenticated recording queries and bounded MP4 playback downloads."""
import fcntl
import hashlib
import os
import subprocess
import time
from flask import request, jsonify, g, send_file
from mqtt_access import allowed_users
from recording_store import ROOT, DAY, connect, snapshot

FFMPEG = os.environ.get('RECORDING_FFMPEG', '/opt/guardian-ffmpeg/bin/ffmpeg')


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
        if kind not in ('all', 'fall', 'sedentary'):
            return jsonify(success=False, message='录像筛选类型无效'), 400
        try:
            as_of = int(data.get('asOf', time.time() * 1000))
            if as_of < int(time.time() * 1000) - DAY:
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            return jsonify(success=False, message='请刷新查看最近24小时录像'), 400
        response = jsonify(snapshot(as_of, kind))
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
        try:
            kind = data['filter']
            if kind not in ('all', 'fall', 'sedentary'):
                raise ValueError()
            result = snapshot(int(data['asOf']), kind)
            clip = next((item for item in result['clips'] if item['id'] == data['clipId']), None)
        except (ValueError, KeyError, TypeError, OverflowError):
            clip = None
        if not clip:
            return jsonify(success=False, message='录像已过期或不在筛选范围，请刷新'), 404
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
