"""One-shot isolated synthetic board trial; never changes guardian services.

Requires a private, prepared directory containing backup/ and results/preparation.json.
Uses the separately pinned existing CPU binary/model. Not a production integration.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.request

from tools.local_care_prototype import StreamClient, classify_reply, request_body
from tools.local_llm_prep import parse_intent


def guard_monitor(operation, on_error):
    """Any monitoring exception must notify the owner, never silently pass."""
    try:
        operation()
    except Exception as error:
        on_error(error)


def port_available(port):
    """Check for an active listener without rejecting a closed TIME_WAIT socket."""
    with socket.socket() as probe:
        probe.settimeout(.5)
        return probe.connect_ex(('127.0.0.1', port)) != 0


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def stats():
    with urllib.request.urlopen('http://127.0.0.1:5000/api/stats', timeout=3) as response:
        data = json.load(response)
    return {**{k: data.get(k) for k in ('fps', 'camera_connected', 'mqtt_connected')},
            'care_mode': data.get('care', {}).get('mode')}


def video():
    with urllib.request.urlopen('http://127.0.0.1:5000/video_frame', timeout=4) as response:
        data = response.read(3 * 1024 * 1024)
        return {'http_status': response.status, 'bytes': len(data),
                'complete_jpeg': data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9')}


def memory(pid):
    try:
        return {line.split(':')[0]: int(line.split()[1]) * 1024
                for line in Path('/proc/%d/status' % pid).read_text().splitlines()
                if line.startswith(('VmRSS:', 'VmHWM:'))}
    except OSError:
        return None


def cpu():
    return [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]


def service():
    text = subprocess.check_output(['systemctl', 'show', 'guardian-board.service',
                                   '-p', 'MainPID', '-p', 'NRestarts', '-p', 'ActiveState'], text=True)
    return dict(line.split('=', 1) for line in text.splitlines())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    args = parser.parse_args()
    root = Path(args.session).resolve()
    old = Path('/root/guardian-llm-lab/20261124-cpu-01')
    prep = json.loads((root / 'results/preparation.json').read_text())
    baseline = statistics.median(row['stats']['fps'] for row in prep['baseline'])
    initial = service()
    assert initial['MainPID'] == str(prep['service_pid']) and initial['ActiveState'] == 'active'
    assert all(row['stats']['care_mode'] == 'off' for row in prep['baseline'])
    inputs_path = root / 'fixtures/local_llm/retest-2026-11-26/inputs.json'
    expected_path = inputs_path.with_name('expected.json')
    assert sha(inputs_path) == '78d3016aa9f9ba151b2030dd29ad01364d163d79dc6ca7b5c24cf3a5e7408bb3'
    assert sha(expected_path) == '381925cedfd27f7130fadb4ac02f7b178b5aa57f3515e9d9ed7ce8626215169e'
    cases = json.loads(inputs_path.read_text())['cases']
    expected = json.loads(expected_path.read_text())
    binary = old / 'build/bin/llama-server'
    model = old / 'models/qwen2.5-1.5b-instruct-q4_k_m.gguf'
    assert sha(binary) == '94028ef29551277f495715865aa6f056202d95622dcd2802293c065713d4a853'
    assert sha(model) == '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e'
    client = StreamClient('http://127.0.0.1:18081', 'care-15b')
    done = threading.Event()
    unsafe = threading.Event()
    process = None
    phase = 'prepared'
    samples = []
    monitor_errors = []
    result = {'synthetic': True, 'started_at': datetime.datetime.now().astimezone().isoformat(),
              'policy_version': 'experimental-care-text/1', 'protocol_integration': False,
              'initial_service': initial, 'baseline_fps_median': baseline,
              'input_sha256': sha(inputs_path), 'expected_sha256': sha(expected_path),
              'model_sha256': sha(model), 'binary_sha256': sha(binary),
              'measurements': [], 'rows': [], 'faults': [], 'video_before': video()}

    def monitor():
        before = cpu()
        low = 0
        with (root / 'results/resources.jsonl').open('x') as out:
            while not done.wait(3):
                after = cpu()
                total = sum(after) - sum(before)
                idle = after[3] + after[4] - before[3] - before[4]
                before = after
                available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                                     if line.startswith('MemAvailable:'))) * 1024
                row = {'phase': phase, 'elapsed': time.monotonic() - started,
                       'cpu_busy_percent': 100 * (total - idle) / total,
                       'mem_available_bytes': available, 'guardian_memory': memory(int(initial['MainPID']))}
                try:
                    row['stats'] = stats()
                except Exception as error:
                    row['stats'] = {'error': type(error).__name__}
                current = process
                if current is not None and current.poll() is None:
                    row['model_memory'] = memory(current.pid)
                s = row['stats']
                low = low + 1 if not s.get('camera_connected') or s.get('fps', 0) < baseline * .9 else 0
                if (low >= 3 or available < 2 * 1024**3 or row['guardian_memory'] is None
                        or s.get('care_mode') not in ('off', None)):
                    unsafe.set()
                    row['safety_stop'] = True
                    if current is not None and current.poll() is None:
                        os.killpg(current.pid, signal.SIGTERM)
                samples.append(row)
                out.write(json.dumps(row) + '\n')
                out.flush()

    def stop_model():
        nonlocal process
        if process is not None:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            process = None

    def start_model(label):
        nonlocal process, phase
        assert not unsafe.is_set()
        assert port_available(18081), 'Trial port has an active listener'
        phase = label + ':load'
        command = ['nice', '-n', '10', str(binary), '-m', str(model), '--alias', 'care-15b',
                   '--host', '127.0.0.1', '--port', '18081', '-c', '1024', '-t', '2', '-tb', '2',
                   '-np', '1', '-ngl', '0', '--jinja', '--reasoning', 'off',
                   '--chat-template-kwargs', '{"enable_thinking":false}']
        t = time.monotonic()
        with (root / ('logs/' + label + '.log')).open('x') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        while time.monotonic() - t < 120:
            assert process.poll() is None and not unsafe.is_set(), 'Model stopped during startup'
            try:
                with urllib.request.urlopen('http://127.0.0.1:18081/health', timeout=2) as response:
                    if response.status == 200:
                        break
            except Exception:
                pass
            time.sleep(.5)
        else:
            raise TimeoutError('startup')
        listeners = [line.split()[1] for line in Path('/proc/net/tcp').read_text().splitlines()[1:]
                     if line.split()[3] == '0A' and line.split()[1].endswith(':46A1')]
        assert listeners == ['0100007F:46A1'], listeners
        result['measurements'].append({'kind': label + ':ready', 'seconds': time.monotonic() - t})

    def measured(label, text, timeout=60, other_prefix=False):
        nonlocal phase
        phase = label
        body = request_body('care-15b', text)
        if other_prefix:
            body['messages'][0]['content'] = '这是一次独立的文字分类实验，请严格区分清楚、求助和不确定。' + body['messages'][0]['content']
        t = time.monotonic()
        try:
            output = client.complete(body, timeout=timeout)
            item = {'kind': label, 'success': True, **output, 'intent': parse_intent(output['content'])}
        except Exception as error:
            item = {'kind': label, 'success': False, 'error': type(error).__name__, 'seconds': time.monotonic() - t}
        result['measurements'].append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)

    def on_signal(signum, frame):
        raise SystemExit('trial interrupted')

    signal.signal(signal.SIGTERM, on_signal)
    started = time.monotonic()
    def monitor_failed(error):
        monitor_errors.append(type(error).__name__)
        unsafe.set()
        current = process
        if current is not None and current.poll() is None:
            try:
                os.killpg(current.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        print(json.dumps({'stage': 'monitor-error', 'error': type(error).__name__}), flush=True)
    watcher = threading.Thread(target=lambda: guard_monitor(monitor, monitor_failed), daemon=True)
    watcher.start()
    try:
        start_model('first-process')
        measured('first-prompt', '我只是歇一会儿，没有不舒服，不需要帮助。')
        measured('same-prefix', '请叫个人来扶一下我。')
        measured('changed-prefix', '我刚刚没有听清问题。', other_prefix=True)
        stop_model()
        start_model('prewarmed-process')
        measured('explicit-warmup-cost', '这是一条预热输入，无法判断。')
        measured('after-warmup', '我需要家里人来帮忙拿药。', timeout=10)
        with (root / 'results/rows.jsonl').open('x') as out:
            for index, case in enumerate(cases):
                assert not unsafe.is_set(), 'resource protection'
                row = {'id': case['id'], 'text': case['text'], 'expected': expected[case['id']]}
                order = ['raw', 'prototype'] if index % 2 == 0 else ['prototype', 'raw']
                row['order'] = order
                for kind in order:
                    phase = 'formal:' + kind
                    t = time.monotonic()
                    if kind == 'raw':
                        try:
                            row[kind] = {'status': 'ok', **client.classify(case['text'], timeout=10)}
                        except Exception as error:
                            row[kind] = {'status': 'error', 'error': type(error).__name__}
                    else:
                        acknowledgements = []
                        def emit(message):
                            acknowledgements.append({'elapsed': time.monotonic() - t, **message})
                        def infer(text):
                            prediction = client.classify(text, timeout=5)
                            row['prototype_model_timing'] = prediction
                            return prediction
                        row[kind] = classify_reply(case['text'], infer, emit=emit)
                        row['acknowledgements'] = acknowledgements
                    row[kind]['wall_seconds'] = time.monotonic() - t
                result['rows'].append(row)
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
                out.flush()
                print(json.dumps({'stage': 'case', 'id': case['id'], 'raw': row['raw'].get('intent'),
                                  'prototype': row['prototype']['intent'], 'source': row['prototype']['source']}), flush=True)
        phase = 'faults'
        disconnected = StreamClient('http://127.0.0.1:18082', 'missing')
        def truncated(text):
            body = request_body('care-15b', text)
            body['max_tokens'] = 1
            data = client.complete(body, timeout=10)
            return {'intent': parse_intent(data['content'])}
        for name, infer in [('disconnected', lambda text: disconnected.classify(text, timeout=1)),
                            ('tiny-deadline', lambda text: client.classify(text, timeout=.001)),
                            ('truncated-output', truncated)]:
            t = time.monotonic()
            data = classify_reply('这个问题容我想一下再告诉你。', infer)
            result['faults'].append({'fault': name, 'seconds': time.monotonic() - t, 'result': data})
            assert data['source'] == 'fallback' and data['intent'] == 'unclear'
            assert data['preserve_alert'] and not data['auto_cancel']
        result['completed'] = True
    finally:
        stop_model()
        phase = 'recovery'
        time.sleep(12)
        result['monitor_alive_before_stop'] = watcher.is_alive()
        done.set()
        watcher.join(timeout=8)
        result['finished_at'] = datetime.datetime.now().astimezone().isoformat()
        result['resource_samples'] = len(samples)
        result['monitor_errors'] = monitor_errors
        result['last_resource_age_seconds'] = time.monotonic() - started - samples[-1]['elapsed'] if samples else None
        result['safety_triggered'] = unsafe.is_set()
        result['final_stats'] = stats()
        result['final_service'] = service()
        result['video_after'] = video()
        manifest = json.loads((root / 'backup/production-files.before.json').read_text())
        result['production_file_count'] = len(manifest)
        result['production_files_unchanged'] = all(sha(Path('/root/ai_guardian') / name) == digest
                                                  for name, digest in manifest.items())
        result['service_unit_unchanged'] = subprocess.check_output(['systemctl', 'cat', 'guardian-board.service'], text=True).strip() == (root / 'backup/guardian-board.service.txt').read_text()
        listeners = [line.split()[1] for line in Path('/proc/net/tcp').read_text().splitlines()[1:]
                     if line.split()[3] == '0A' and line.split()[1].endswith(':46A1')]
        result['model_port_closed'] = not listeners
        (root / 'results/trial.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps({'stage': 'finished', 'completed': result.get('completed', False),
                          'safety': result['safety_triggered'], 'rows': len(result['rows']),
                          'production_unchanged': result['production_files_unchanged'],
                          'final_stats': result['final_stats']}), flush=True)
    assert result['completed'] and not unsafe.is_set()
    assert not monitor_errors and result['monitor_alive_before_stop'] and len(samples) >= 3
    assert result['last_resource_age_seconds'] is not None and result['last_resource_age_seconds'] < 10
    assert result['production_files_unchanged'] and result['service_unit_unchanged']
    assert result['final_service'] == initial and result['model_port_closed']
    assert result['video_after']['complete_jpeg'] and result['final_stats']['care_mode'] == 'off'


if __name__ == '__main__':
    main()
