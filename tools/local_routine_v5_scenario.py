"""Synthetic CSV rule output through both real HTTP implementations and a real model."""
from datetime import date, datetime, time as wall_time, timedelta
import json
import threading
import time
import urllib.error
import urllib.request

from src.personalization_v5 import Store
from tools import late_wakeup_demo as replay
from tools import personalization_http as peer_http
from tools import routine_alert_demo as routine
from tools.personalization_routine_peer import RoutinePeer
from tools.local_care_text_v3 import SemanticIntentClient
from tools.personalization_v5_text import Server, prepared_session, post, flush_outbox


class ReplayClock:
    def __init__(self):
        self.now = replay.at(date(2026, 11, 24), wall_time(10, 30))
    def __call__(self):
        return self.now


def run_demo(root, *, model_url, model_id, stop_backend, restart_backend):
    root.mkdir()
    fixtures = root/'fixtures'
    fixtures.mkdir()
    routine.generate(fixtures)
    history = root/'history-nine.csv'
    replay.write_samples(history, (row for offset in range(14)
                                  for row in replay.simulate_day(date(2026, 11, 10)+timedelta(days=offset), wall_time(9))))
    clock = ReplayClock()
    app = peer_http.Personalization(root/'personalization.sqlite', clock, 'routine-synthetic')
    scanner = RoutinePeer(app, history)
    assert scanner.typical == wall_time(9)
    model = Store(root/'model.sqlite', 'routine-synthetic', 'model', clock=lambda: clock().timestamp())
    session, gate = prepared_session(model, SemanticIntentClient(model_url, model_id), policy='v4-fast')
    decisions = []
    original = session.classify
    def observed(text, *, timeout):
        value = original(text, timeout=timeout)
        decisions.append(value)
        return value
    session.classify = observed
    server = Server(model, session, readiness=gate)
    stop = threading.Event()
    worker = None
    cases = []

    def wait_ready():
        start = time.monotonic()
        while time.monotonic()-start < 75:
            try:
                with urllib.request.urlopen(server.url+'/health/ready', timeout=3) as response:
                    health = json.load(response)
                if health['ready']:
                    return time.monotonic()-start
            except urllib.error.HTTPError as error:
                assert error.code == 503
                error.close()
            time.sleep(.1)
        raise TimeoutError('readiness deadline')

    def register(name, kind, day):
        if kind == 'late_wakeup':
            rows = replay.simulate_day(day, wall_time(12))
            clock.now = replay.at(day, wall_time(10, 30))
        elif kind == routine.DAYTIME_INACTIVITY:
            rows = routine.simulated_routine(day, kind, day)
            clock.now = replay.at(day, wall_time(15))
        else:
            previous = day-timedelta(days=1)
            rows = (row for current in (previous, day)
                    for row in routine.simulated_routine(current, kind, previous))
            clock.now = replay.at(day, wall_time(0))
        path = root/(name+'.csv')
        replay.write_samples(path, rows)
        scan = scanner.scan(path)
        assert scan['registered'] == 1 and not scan['expired'], scan
        key = scan['events'][0]['event_id']
        saved = app.queued(key)[0]['payload']
        payload = json.loads(saved)
        assert payload['alert_type'] == kind
        assert replay.read_timestamp(payload['timestamp']) == clock()
        reopened = peer_http.Personalization(app.path, clock, app.device)
        rescan = RoutinePeer(reopened, history).scan(path)
        assert rescan['registered'] == 0 and rescan['duplicates'] == 1
        assert reopened.queued(key)[0]['payload'] == saved and len(reopened.queued(key)) == 1
        app.flush(server.http.server_port)
        assert app.queued(key)[0]['state'] == 'acked'
        action = session.tick(key, prompt_available=gate.ready)
        assert action['kind'] == 'prompt'
        print(json.dumps({'stage': 'rule_prompt', 'alert_type': kind, 'event_id': key}), flush=True)
        session.displayed(key)
        return key, payload, scan

    def answer(key, text):
        return post(server.url+'/text/v1/answers', {'event_id': key, 'text': text}, timeout=7)

    try:
        server.start()
        worker = threading.Thread(target=gate.run, args=(stop,), daemon=True)
        worker.start()
        initial_wait = wait_ready()
        before = gate.snapshot()
        session_id, gate_id = id(session), id(gate)
        with peer_http.serve(peer_http.RESULTS, app.receive) as result_port:
            receiver = 'http://127.0.0.1:'+str(result_port)
            for name, kind, day, text, expected in (
                ('late-denial', 'late_wakeup', date(2026, 11, 24), '我没有说我需要帮助。', 'unclear'),
                ('day-help', routine.DAYTIME_INACTIVITY, date(2026, 11, 24), '我想找人来看看我。', 'needs_help'),
                ('night-help', routine.NIGHT_BATHROOM_STAY, date(2026, 11, 25), '我现在起不来，帮帮我。', 'needs_help'),
                ('late-ok', 'late_wakeup', date(2026, 11, 25), '我现在没事，谢谢关心。', 'ok'),
            ):
                key, payload, scan = register(name, kind, day)
                first = len(decisions)
                started = time.monotonic()
                code, value = answer(key, text)
                prompts = 1
                if expected == 'unclear':
                    assert code == 202
                    assert session.tick(key)['attempt'] == 2
                    session.displayed(key)
                    prompts = 2
                    code, value = answer(key, text)
                elapsed = time.monotonic()-started
                assert code == 200 and value['response'] == expected, (name, code, value)
                flush_outbox(model, receiver)
                assert app.summary(key)['current'] == value
                assert peer_http.post(result_port, peer_http.RESULTS, value)[1]['disposition'] == 'duplicate'
                assert post(server.url+peer_http.REMINDERS, payload)[1]['disposition'] == 'duplicate'
                cases.append({'event_id': key, 'alert_type': kind, 'reminder': payload,
                              'text': text, 'result': value, 'prompts': prompts,
                              'wall_seconds': elapsed, 'policy_decisions': decisions[first:],
                              'rescan_and_reopen_duplicate': True})
            key, payload, scan = register('outage-day', routine.DAYTIME_INACTIVITY, date(2026, 11, 25))
            stop_backend()
            first = len(decisions)
            count_before = gate.snapshot()['classification_calls']
            started = time.monotonic()
            code, value = answer(key, '我想找人来看看我。')
            assert code == 202 and not gate.ready
            outage = {'event_id': key, 'reminder': payload, 'failed_answer_http': code,
                      'failed_answer': value, 'failure_wall_seconds': time.monotonic()-started,
                      'after_failure': gate.snapshot()}
            started = time.monotonic()
            code, help_result = answer(key, '我现在起不来，帮帮我。')
            assert code == 200 and help_result['response'] == 'needs_help'
            outage.update(help_result=help_result, help_wall_seconds=time.monotonic()-started,
                          policy_decisions=decisions[first:],
                          classification_attempts=gate.snapshot()['classification_calls']-count_before)
            flush_outbox(model, receiver)
            assert app.summary(key)['current'] == help_result
            restart_backend()
            recovery_wait = wait_ready()
            after = gate.snapshot()
            assert id(session) == session_id and id(gate) == gate_id
            assert after['warm_calls'] > before['warm_calls'] and after['probe_calls'] > before['probe_calls']
            key, payload, scan = register('recovered-night', routine.NIGHT_BATHROOM_STAY, date(2026, 11, 26))
            first = len(decisions)
            started = time.monotonic()
            code, value = answer(key, '我想找人来看看我。')
            elapsed = time.monotonic()-started
            assert code == 200 and value['response'] == 'needs_help'
            flush_outbox(model, receiver)
            assert app.summary(key)['current'] == value
            assert app.summary(outage['event_id'])['current'] == help_result
            cases.append({'event_id': key, 'alert_type': routine.NIGHT_BATHROOM_STAY, 'reminder': payload,
                          'text': '我想找人来看看我。', 'result': value, 'prompts': 1,
                          'wall_seconds': elapsed, 'policy_decisions': decisions[first:],
                          'rescan_and_reopen_duplicate': True})
            assert scanner.scan(fixtures/'routine-normal.csv')['registered'] == 0
            assert scanner.scan(fixtures/'routine-missing.csv')['registered'] == 0
            with app.transaction() as db:
                help_tasks = db.execute('SELECT COUNT(*) FROM help_tasks').fetchone()[0]
                pending = db.execute("SELECT COUNT(*) FROM outbox WHERE state='pending'").fetchone()[0]
            assert help_tasks == 4 and pending == 0 and not model.pending()
        stop.set()
        worker.join(timeout=3)
        final = gate.snapshot()
        output = {'synthetic': True, 'mode': 'CSV_rules_and_peer_HTTP_with_real_model',
                  'clock': 'shared replay wall clock; real monotonic request/session deadlines',
                  'baseline_departure': '09:00', 'late_threshold': '10:30',
                  'initial_wait_seconds': initial_wait, 'recovery_wait_seconds': recovery_wait,
                  'before': before, 'after': after, 'final_counters': final,
                  'same_session_and_gate': True, 'help_tasks': help_tasks, 'outage': outage,
                  'normal_and_missing_no_new_events': True,
                  'backend_attempts': sum(final[k] for k in ('warm_calls','probe_calls','classification_calls')),
                  'cases': cases}
        (root/'result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
        return output
    finally:
        stop.set()
        if worker:
            worker.join(timeout=1)
        server.close()
