"""Bounded CPU/RAM recorder. Reconnect on board loss, never generate filler frames."""
import json
import os
import shutil
import signal
import subprocess
import time
import uuid
import fcntl
from recording_store import ROOT, connect, prune, set_state

SOURCE = os.environ.get('RECORDING_SOURCE', 'http://127.0.0.1:6001/video_feed')
FFMPEG = os.environ.get('RECORDING_FFMPEG', '/opt/guardian-ffmpeg/bin/ffmpeg')
FFPROBE = os.environ.get('RECORDING_FFPROBE', '/opt/guardian-ffmpeg/bin/ffprobe')
stopping = False
process = None


def stop(_signal, _frame):
    global stopping
    stopping = True
    if process and process.poll() is None:
        process.terminate()


def run():
    global process
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Files left by a killed encoder are never advertised as playable recordings.
        for item in ROOT.glob('*.partial.mp4'):
            if not item.name.startswith('clip-'):
                item.unlink(missing_ok=True)
        while not stopping:
            prune()
            if shutil.disk_usage(ROOT).free < 2 * 1024 ** 3:
                set_state('disk_full')
                time.sleep(10)
                continue
            segment_id = uuid.uuid4().hex
            partial = ROOT / f'{segment_id}.partial.mp4'
            started = int(time.time() * 1000)
            set_state('connecting')
            # Input is the board's multipart MJPEG stream, with real arrival timestamps.
            command = [FFMPEG, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                       '-rw_timeout', '10000000', '-use_wallclock_as_timestamps', '1',
                       '-f', 'mpjpeg', '-i', SOURCE, '-t', '60', '-an',
                       '-vf', 'fps=8,scale=640:-2', '-c:v', 'libx264', '-preset', 'ultrafast',
                       '-threads', '1', '-b:v', '512k', '-maxrate', '768k', '-bufsize', '1024k',
                       '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(partial)]
            try:
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + 85
                while process.poll() is None:
                    if time.monotonic() > deadline:
                        raise subprocess.TimeoutExpired(command, 85)
                    set_state('recording' if partial.exists() and partial.stat().st_size > 1024 else 'connecting')
                    time.sleep(1)
                return_code = process.returncode
                process = None
                if partial.exists() and partial.stat().st_size > 1024:
                    info = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                                           '-of', 'json', str(partial)], capture_output=True, text=True, timeout=5, check=True)
                    duration_ms = int(float(json.loads(info.stdout)['format']['duration']) * 1000)
                    if duration_ms <= 0 or duration_ms > 65_000:
                        raise ValueError('invalid duration')
                    # Clamp wall start after connection/probe delay; no frame is claimed in the gap.
                    end = min(int(time.time() * 1000), started + 85_000)
                    start = max(started, end - duration_ms)
                    filename = f'{segment_id}.mp4'
                    partial.replace(ROOT / filename)
                    with connect() as db:
                        db.execute('INSERT INTO segments VALUES(?,?,?,?,?)',
                                   (segment_id, start, end, filename, (ROOT / filename).stat().st_size))
                    set_state('recording' if return_code == 0 else 'offline')
                else:
                    set_state('offline')
                    time.sleep(5)
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                if process and process.poll() is None:
                    process.kill()
                    process.wait()
                process = None
                set_state('offline')
                time.sleep(5)
            finally:
                partial.unlink(missing_ok=True)
        set_state('stopped')


if __name__ == '__main__':
    os.umask(0o077)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    run()
