"""Frozen, isolated CPU policy v3 verification. No production writes."""
import argparse
from collections import Counter
import datetime
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import threading
import time
import urllib.request

from tools.local_care_board_trial import (cpu, guard_monitor, memory, port_available,
                                          service, sha, stats, video)
from tools.local_care_prototype import StreamClient
from tools.local_care_text_v3 import SemanticIntentClient
from tools.personalization_v5_text import run_demo
from tools.local_v5_recovery_trial import run_recovery


def capture_probe(operation, errors, name, default=None):
    """Record failed cleanup checks as failures while allowing evidence to save."""
    try:
        return operation()
    except Exception as error:
        errors[name] = type(error).__name__
        return default


def summarize_model(rows):
    valid = [x for x in rows if x['status'] == 'ok']
    times = [x['wall_seconds'] for x in valid]
    return {
        'total': len(rows), 'completed': len(valid), 'errors': len(rows) - len(valid),
        'correct': sum(x.get('intent') == x['expected'] for x in valid),
        'help_total': sum(x['expected'] == 'needs_help' for x in rows),
        'help_missed': sum(x['expected'] == 'needs_help' and
                           (x['status'] != 'ok' or x.get('intent') != 'needs_help') for x in rows),
        'wrong_okay': sum(x.get('intent') == 'okay' and x['expected'] != 'okay' for x in valid),
        'false_help': sum(x.get('intent') == 'needs_help' and x['expected'] != 'needs_help' for x in valid),
        'completed_within_5_seconds': sum(x['wall_seconds'] <= 5 for x in valid),
        'median_complete_seconds': statistics.median(times) if times else None,
        'max_complete_seconds': max(times) if times else None,
        'confusion': {label: dict(Counter(x.get('intent', 'error') if x['status'] == 'ok' else 'error'
                                        for x in rows if x['expected'] == label))
                      for label in ['okay', 'needs_help', 'unclear']},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    root = Path(parser.parse_args().session).resolve()
    manifest = json.loads((root / 'asset-manifest.json').read_text(encoding='utf-8'))
    runs = [{'id':'cold_v5','model_index':0}, {'id':'warm_v5','model_index':0}]
    assert sha(root / 'tools/local_care_text_v3.py') == manifest['v3_source_sha256']
    old = Path('/root/guardian-llm-lab/20261124-cpu-01')
    binary = old / 'build/bin/llama-server'
    assert sha(binary) == manifest['binary_sha256']
    for model in manifest['models']:
        weight = old / 'models' / model['file']
        assert weight.stat().st_size == model['bytes'] and sha(weight) == model['sha256']
    preparation = json.loads((root / 'results/preparation.json').read_text(encoding='utf-8'))
    production_before = json.loads((root / 'backup/production-files.before.json').read_text())
    unit_before = (root / 'backup/guardian-board.service.txt').read_text()
    initial = service()
    assert initial['MainPID'] == str(preparation['service_pid']) and initial['ActiveState'] == 'active'
    assert all(x['stats']['care_mode'] == 'off' for x in preparation['baseline'])
    assert not (root / 'results/trial.json').exists()
    started = time.monotonic()
    done, unsafe = threading.Event(), threading.Event()
    samples, monitor_errors = [], []
    http_requests = [0]
    process = None
    current_run = None
    phase = 'initial'
    baseline_fps = None
    result = {'synthetic': True, 'started_at': datetime.datetime.now().astimezone().isoformat(),
              'manifest': manifest, 'initial_service': initial, 'video_before': video(),
              'parameters': {'threads': 2, 'context': 1024, 'parallel': 1, 'gpu_layers': 0,
                             'thinking': False, 'formal_deadline_seconds': 5,
                             'diagnostic_deadline_seconds': 60}, 'runs': []}

    def stop_model():
        nonlocal process
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            process = None

    def monitor_failed(error):
        monitor_errors.append(type(error).__name__)
        unsafe.set()
        child = process
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def monitor():
        before = cpu()
        low, previous_run = 0, None
        with (root / 'results/resources.jsonl').open('x', encoding='utf-8') as stream:
            while not done.wait(3):
                after = cpu()
                total = sum(after) - sum(before)
                idle = after[3] + after[4] - before[3] - before[4]
                before = after
                available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                                     if line.startswith('MemAvailable:'))) * 1024
                row = {'elapsed': time.monotonic() - started, 'run_id': current_run,
                       'phase': phase, 'cpu_busy_percent': 100 * (total - idle) / total,
                       'mem_available_bytes': available, 'guardian_memory': memory(int(initial['MainPID']))}
                row['stats'] = stats()
                child = process
                if child is not None and child.poll() is None:
                    row['model_memory'] = memory(child.pid)
                if previous_run != current_run:
                    low = 0
                    previous_run = current_run
                state = row['stats']
                bad = not state.get('camera_connected') or (baseline_fps is not None and state['fps'] < baseline_fps * .9)
                low = low + 1 if bad else 0
                if low >= 3 or available < 2 * 1024**3 or row['guardian_memory'] is None or state.get('care_mode') != 'off':
                    unsafe.set()
                    row['safety_stop'] = True
                    monitor_failed(RuntimeError('Resource protection'))
                samples.append(row)
                stream.write(json.dumps(row) + '\n')
                stream.flush()

    def interrupted(signum, frame):
        raise SystemExit('Trial interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    watcher = threading.Thread(target=lambda: guard_monitor(monitor, monitor_failed), daemon=True)
    watcher.start()
    try:
        with (root / 'results/rows.jsonl').open('x', encoding='utf-8') as rows_file:
            for run in runs:
                assert not unsafe.is_set()
                current_run, baseline_fps, phase = run['id'], None, 'baseline'
                model = manifest['models'][run['model_index']]
                item = {'run_id': current_run, 'model_id': model['id'], 'rows': [], 'diagnostics': []}
                result['runs'].append(item)
                print(json.dumps({'stage': 'baseline', 'run': current_run, 'model': model['id']}), flush=True)
                time.sleep(31)
                base = [x for x in samples if x['run_id'] == current_run and x['phase'] == 'baseline']
                assert len(base) >= 9 and all(x['stats']['camera_connected'] and x['stats']['fps'] > 0 for x in base)
                baseline_fps = statistics.median(x['stats']['fps'] for x in base)
                item['baseline_fps_median'] = baseline_fps
                assert not unsafe.is_set() and port_available(18081)
                phase = 'load'
                command = ['nice', '-n', '10', str(binary), '-m', str(old / 'models' / model['file']),
                           '--alias', model['id'], '--host', '127.0.0.1', '--port', '18081', '-c', '1024',
                           '-t', '2', '-tb', '2', '-np', '1', '-ngl', '0', '--jinja', '--reasoning', 'off',
                           '--chat-template-kwargs', '{"enable_thinking":false}']
                t = time.monotonic()
                with (root / ('logs/' + current_run + '.log')).open('x') as log:
                    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                while time.monotonic() - t < 120:
                    assert process.poll() is None and not unsafe.is_set()
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:18081/health', timeout=2) as response:
                            if response.status == 200:
                                break
                    except Exception:
                        pass
                    time.sleep(.5)
                else:
                    raise TimeoutError('Model startup')
                item['ready_seconds'] = time.monotonic() - t
                listeners = [line.split()[1] for line in Path('/proc/net/tcp').read_text().splitlines()[1:]
                             if line.split()[3] == '0A' and line.split()[1].endswith(':46A1')]
                assert listeners == ['0100007F:46A1'], listeners
                client_type = SemanticIntentClient
                client = client_type('http://127.0.0.1:18081', model['id'])
                for kind, text in ([] if current_run == 'cold_v5' else [('first_prompt_and_warmup_cost', '这是一条独立的预热测试，我没有听懂你的问题。'),
                                   ('after_warmup', '我现在需要有人过来帮我一下。')]):
                    phase = kind
                    t = time.monotonic()
                    try:
                        http_requests[0] += 1
                        diagnostic = {'kind': kind, 'status': 'ok', **client.classify(text, timeout=60)}
                    except Exception as error:
                        diagnostic = {'kind': kind, 'status': 'error', 'error': type(error).__name__}
                    diagnostic['wall_seconds'] = time.monotonic() - t
                    item['diagnostics'].append(diagnostic)
                    print(json.dumps({'stage': 'diagnostic', 'run': current_run, **diagnostic}), flush=True)
                assert all(x['status'] == 'ok' for x in item['diagnostics']), 'Diagnostic format/transport validation failed'
                phase = 'formal'
                assert not unsafe.is_set()
                demo = run_demo(root / ('results/' + current_run), model_url='http://127.0.0.1:18081', model_id=model['id'])
                item['demo'] = demo
                http_requests[0] += demo['backend_attempts']
                for case, expected in zip(demo['cases'], ['okay','needs_help','needs_help']):
                    row = {'id':case['event_id'],'text':case['text'],'expected':expected,
                           'intent':{'ok':'okay'}.get(case['result']['response'],case['result']['response']),
                           'status':'ok','wall_seconds':case['wall_seconds']}
                    item['rows'].append(row)
                    rows_file.write(json.dumps(row,ensure_ascii=False)+'\n'); rows_file.flush()
                assert not unsafe.is_set()
                stop_model()
                phase = 'recovery'
                time.sleep(12)
                item['after_stats'] = stats()
        phase = 'process-recovery-tests'
        result['recovery_tests'] = run_recovery(root / 'results/process-recovery')
        result['completed'] = True
    finally:
        stop_model()
        phase = 'final-recovery'
        time.sleep(12)
        result['monitor_alive_before_stop'] = watcher.is_alive()
        done.set()
        watcher.join(timeout=8)
        result['monitor_errors'] = monitor_errors
        result['resource_sample_count'] = len(samples)
        result['last_resource_age_seconds'] = time.monotonic() - started - samples[-1]['elapsed'] if samples else None
        result['safety_triggered'] = unsafe.is_set()
        result['finished_at'] = datetime.datetime.now().astimezone().isoformat()
        cleanup_errors = {}
        result['final_stats'] = capture_probe(stats, cleanup_errors, 'stats')
        result['final_service'] = capture_probe(service, cleanup_errors, 'service')
        result['video_after'] = capture_probe(video, cleanup_errors, 'video')
        result['production_file_count'] = len(production_before)
        result['production_files_unchanged'] = capture_probe(
            lambda: all(sha(Path('/root/ai_guardian') / n) == h for n, h in production_before.items()),
            cleanup_errors, 'production_files', False)
        result['service_unit_unchanged'] = capture_probe(
            lambda: subprocess.check_output(['systemctl', 'cat', 'guardian-board.service'], text=True).strip() == unit_before,
            cleanup_errors, 'service_unit', False)
        result['model_port_closed'] = capture_probe(
            lambda: not [line for line in Path('/proc/net/tcp').read_text().splitlines()[1:]
                         if line.split()[3] == '0A' and line.split()[1].endswith(':46A1')],
            cleanup_errors, 'model_port', False)
        result['cleanup_errors'] = cleanup_errors
        result['http_requests_sent'] = http_requests[0]
        result['summaries'] = {run['run_id']: summarize_model(run['rows']) for run in result['runs']}
        with (root / 'results/trial.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'stage': 'finished', 'completed': result.get('completed', False),
                          'summaries': result['summaries'], 'safety': result['safety_triggered']}), flush=True)
    assert result['completed'] and not unsafe.is_set() and not monitor_errors
    assert not cleanup_errors, 'Cleanup checks failed; evidence retained'
    assert result['monitor_alive_before_stop'] and result['last_resource_age_seconds'] < 10
    assert result['production_files_unchanged'] and result['service_unit_unchanged'] and result['model_port_closed']
    assert result['final_service'] == initial and result['final_stats']['care_mode'] == 'off'
    assert result['final_stats']['camera_connected'] and result['video_after']['complete_jpeg']
    assert all(x['total'] == 3 for x in result['summaries'].values())


if __name__ == '__main__':
    main()
