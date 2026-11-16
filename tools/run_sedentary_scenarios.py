"""Run deterministic simulated-input acceptance cases; stdout is complete JSON.

    python tools/run_sedentary_scenarios.py --output .tmp/sedentary-scenarios.json

Only the standard library is required. A failed checkpoint returns exit code 1
and still includes the scenario's partial transition and broadcast records.
"""

import argparse
from dataclasses import replace
from datetime import datetime, time
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sedentary_care import CareMachine, Config, Event, VirtualClock


def scenarios():
    cases = []

    def add(name, steps, broadcasts=(), state=None, config=None, origin=None):
        case = {'name': name, 'steps': steps, 'expected_broadcasts': list(broadcasts),
                'config': config or {}}
        if state is not None:
            case['expected_state'] = state
        if origin is not None:
            case['origin'] = origin
        cases.append(case)

    short = {'l0_seconds': 20}
    add('default_l0_l1_repeat_cap', [
        {'event': 'SIT'}, {'hold': 1799, 'expect': {'level': None, 'seated_seconds': 1799}},
        {'hold': 1, 'expect': {'level': 'L0'}}, {'hold': 299, 'expect': {'level': 'L0'}},
        {'hold': 1, 'expect': {'level': 'L1'}}, {'hold': 299, 'expect': {'phase': 'L1'}},
        {'hold': 1, 'expect': {'state': 'EXHAUSTED', 'counts': {'L0': 1, 'L1': 2}}},
        {'hold': 1000}], [(1800, 'L0'), (2100, 'L1'), (2400, 'L1')], 'EXHAUSTED')
    add('stand_at_l0_deadline', [{'event': 'SIT'}, {'after': 20, 'event': 'STAND'}],
        state='IDLE', config=short)
    add('new_episode_after_stand', [{'event': 'SIT'}, {'hold': 20}, {'event': 'STAND'},
        {'event': 'SIT'}, {'hold': 20}], [(20, 'L0'), (40, 'L0')], 'L0', short)

    for event in ('OCCLUDE', 'LOW_CONFIDENCE', 'MISSING', 'TARGET_LOST', 'DEVICE_ERROR'):
        add(f'{event.lower()}_short_freeze', [{'event': 'SIT'}, {'hold': 10},
            {'event': event}, {'after': 119, 'event': 'SIT', 'expect': {'seated_seconds': 10}},
            {'hold': 10}], [(139, 'L0')], 'L0', short)
        add(f'{event.lower()}_expiry', [{'event': 'SIT'}, {'hold': 10}, {'event': event},
            {'after': 119, 'event': event, 'expect': {'state': 'PAUSED', 'seated_seconds': 10}},
            {'after': 1, 'event': 'TIMEOUT', 'expect': {'seated_seconds': 0, 'level': None}}],
            state='IDLE', config=short)
    for seconds in (120, 121):
        add(f'recovery_at_{seconds}_starts_new_episode', [{'event': 'SIT'}, {'hold': 10},
            {'event': 'OCCLUDE'}, {'after': seconds, 'event': 'SIT',
             'expect': {'seated_seconds': 0}}, {'hold': 20}],
            [(30 + seconds, 'L0')], 'L0', short)
    add('no_observations_no_invented_sitting', [{'event': 'SIT'},
        {'after': 5000, 'event': 'TIMEOUT'}], state='IDLE')
    add('observation_timeout_wins_reminder_tie', [{'event': 'SIT'},
        {'after': 30, 'event': 'TIMEOUT'}], state='PAUSED', config={'l0_seconds': 30})
    add('heartbeat_refresh_at_expiry', [{'event': 'SIT'}, {'after': 30, 'event': 'SIT'}],
        [(30, 'L0')], 'L0', {'l0_seconds': 30})
    add('respond_at_l1_deadline', [{'event': 'SIT'}, {'hold': 20},
        {'after': 10, 'event': 'RESPOND'}, {'hold': 39}, {'hold': 1}],
        [(20, 'L0'), (70, 'L1')], 'L1',
        {'l0_seconds': 20, 'upgrade_seconds': 10, 'ack_seconds': 40})
    add('duplicate_response_no_extension', [{'event': 'SIT'}, {'hold': 20},
        {'event': 'RESPOND'}, {'hold': 20}, {'event': 'RESPOND'}, {'hold': 20}],
        [(20, 'L0'), (60, 'L1')], 'L1', {'l0_seconds': 20, 'ack_seconds': 40})
    add('response_while_paused', [{'event': 'SIT'}, {'hold': 20}, {'event': 'OCCLUDE'},
        {'event': 'RESPOND'}, {'after': 50, 'event': 'SIT'}, {'hold': 40}],
        [(20, 'L0'), (110, 'L1')], 'L1', {'l0_seconds': 20, 'ack_seconds': 40})
    add('explicit_defer', [{'event': 'SIT'}, {'hold': 20}, {'event': 'DEFER'}, {'hold': 40}],
        [(20, 'L0'), (60, 'L1')], 'L1', {'l0_seconds': 20, 'ack_seconds': 40})
    add('explicit_decline', [{'event': 'SIT'}, {'event': 'DECLINE'}, {'hold': 100}],
        state='EXHAUSTED', config=short)
    for event in ('NON_SIT', 'TARGET_CHANGED'):
        add(f'{event.lower()}_clears_person_episode', [{'event': 'SIT'}, {'hold': 20},
            {'event': 'OCCLUDE'}, {'event': event,
             'expect': {'seated_seconds': 0, 'level': None, 'counts': {'L0': 0, 'L1': 0}}}],
            [(20, 'L0')], 'IDLE', short)

    for stamp, audible in (('21:59:39', True), ('21:59:40', False),
                            ('06:59:39', False), ('06:59:40', True)):
        add(f'quiet_boundary_{stamp.replace(":", "")}', [{'event': 'SIT'}, {'hold': 20}],
            [(20, 'L0')] if audible else [], 'L0' if audible else 'SITTING', short,
            f'2026-11-16T{stamp}+08:00')
    add('quiet_end_one_pending_no_backlog', [{'event': 'SIT'}, {'hold': 119,
        'expect': {'pending_level': 'L0', 'counts': {'L0': 0, 'L1': 0}}}, {'hold': 1},
        {'hold': 30}], [(120, 'L0'), (150, 'L1')], 'L1',
        {'l0_seconds': 20, 'upgrade_seconds': 30}, '2026-11-16T06:58:00+08:00')
    add('l1_suppressed_until_next_morning', [{'event': 'SIT'}, {'hold': 20},
        {'after': 20, 'event': 'TIMEOUT', 'expect': {'pending_level': 'L1', 'level': 'L0'}},
        {'after': 32400, 'event': 'TIMEOUT'}, {'after': 300, 'event': 'TIMEOUT'}],
        [(20, 'L0'), (32440, 'L1'), (32740, 'L1')], 'EXHAUSTED',
        {'l0_seconds': 20, 'upgrade_seconds': 20, 'observation_ttl': 100000},
        '2026-11-16T21:59:20+08:00')
    add('cross_midnight_pending', [{'event': 'SIT'}, {'after': 25260, 'event': 'TIMEOUT'}],
        [(25260, 'L0')], 'L0', {'l0_seconds': 20, 'observation_ttl': 100000},
        '2026-11-16T23:59:00+08:00')
    add('daytime_quiet_window', [{'event': 'SIT'}, {'hold': 20,
        'expect': {'pending_level': 'L0'}}, {'after': 3600, 'event': 'TIMEOUT'}],
        [(3620, 'L0')], 'L0', {'l0_seconds': 20, 'observation_ttl': 100000,
                              'quiet_start': time(12), 'quiet_end': time(13)},
        '2026-11-16T11:59:40+08:00')
    for event in ('RESPOND', 'DEFER', 'STAND', 'DECLINE', 'TARGET_CHANGED'):
        add(f'quiet_pending_cancel_{event.lower()}', [{'event': 'SIT'}, {'hold': 20},
            {'event': event}, {'after': 40, 'event': 'TIMEOUT'}], config=short,
            origin='2026-11-16T06:59:00+08:00')
    add('quiet_end_while_target_lost', [{'event': 'SIT'}, {'hold': 20},
        {'event': 'TARGET_LOST'}, {'after': 50, 'event': 'TIMEOUT', 'expect': {'state': 'PAUSED'}},
        {'event': 'SIT'}], [(70, 'L0')], 'L0', short, '2026-11-16T06:59:00+08:00')
    add('quiet_pending_expires_while_lost', [{'event': 'SIT'}, {'hold': 20},
        {'event': 'TARGET_LOST'}, {'after': 120, 'event': 'TIMEOUT'}],
        state='IDLE', config=short, origin='2026-11-16T06:59:00+08:00')
    add('multi_day_replay_no_quiet', [{'event': 'SIT'}, {'after': 259200, 'event': 'TIMEOUT'}],
        [(20, 'L0'), (30, 'L1'), (40, 'L1')], 'EXHAUSTED',
        {'l0_seconds': 20, 'upgrade_seconds': 10, 'repeat_seconds': 10,
         'observation_ttl': 300000, 'quiet_start': None, 'quiet_end': None})
    add('idle_noop_events_are_recorded', [{'event': event} for event in
        ('TIMEOUT', 'STAND', 'NON_SIT', 'RESPOND', 'DEFER', 'DECLINE', 'TARGET_CHANGED')],
        state='IDLE')
    add('duplicate_response_after_quiet_cooldown', [{'event': 'SIT'}, {'hold': 10},
        {'event': 'RESPOND'}, {'hold': 10}, {'event': 'RESPOND',
         'expect': {'pending_level': 'L0', 'cooldown_seconds': None}}, {'hold': 40}],
        [(60, 'L0')], 'L0', {'l0_seconds': 10, 'ack_seconds': 10},
        '2026-11-16T06:59:00+08:00')

    # Literal expectations from the documented event matrix. Include each
    # reliable phase and each saved phase under PAUSED, for every input event.
    phases = ('IDLE', 'SITTING', 'L0', 'L1', 'ACK', 'EXHAUSTED')
    setups = ([], [{'event': 'SIT'}, {'hold': 10}],
              [{'event': 'SIT'}, {'hold': 20}],
              [{'event': 'SIT'}, {'hold': 40}],
              [{'event': 'SIT'}, {'hold': 20}, {'event': 'RESPOND'}],
              [{'event': 'SIT'}, {'hold': 60}])
    before_records = ([], [], [(20, 'L0')], [(20, 'L0'), (40, 'L1')],
                      [(20, 'L0')], [(20, 'L0'), (40, 'L1'), (60, 'L1')])
    phase_outcomes = {
        'SIT': ('SITTING', 'SITTING', 'L0', 'L1', 'ACK', 'EXHAUSTED'),
        'STAND': ('IDLE',) * 6, 'NON_SIT': ('IDLE',) * 6, 'TARGET_CHANGED': ('IDLE',) * 6,
        'RESPOND': ('IDLE', 'SITTING', 'ACK', 'ACK', 'ACK', 'EXHAUSTED'),
        'DEFER': ('IDLE', 'SITTING', 'ACK', 'ACK', 'ACK', 'EXHAUSTED'),
        'DECLINE': ('IDLE', 'EXHAUSTED', 'EXHAUSTED', 'EXHAUSTED', 'EXHAUSTED', 'EXHAUSTED'),
    }
    uncertain = {'OCCLUDE', 'LOW_CONFIDENCE', 'MISSING', 'TARGET_LOST', 'DEVICE_ERROR'}
    for index, phase in enumerate(phases):
        for paused in (False, True):
            for event in Event:
                expected_phase = phase_outcomes.get(event.value, phases)[index]
                expected_pause = event.value in uncertain or (paused and event.value not in
                    {'SIT', 'STAND', 'NON_SIT', 'TARGET_CHANGED'})
                setup = setups[index] + ([{'event': 'OCCLUDE'}] if paused else [])
                add(f'matrix_{"paused_" if paused else ""}{phase.lower()}_{event.value.lower()}',
                    setup + [{'event': event.value, 'expect': {'phase': expected_phase}}],
                    before_records[index], 'PAUSED' if expected_pause else expected_phase,
                    {'l0_seconds': 20, 'upgrade_seconds': 20, 'repeat_seconds': 20})
    return cases


def run_scenario(case):
    clock = VirtualClock(datetime.fromisoformat(case['origin']) if case.get('origin') else None)
    machine = CareMachine(clock, replace(Config(), **case.get('config', {})))
    checks = []

    def check(label, actual, expected):
        checks.append({'label': label, 'actual': actual, 'expected': expected,
                       'passed': actual == expected})
        if actual != expected:
            raise AssertionError(f'{label}: expected {expected!r}, got {actual!r}')

    error = None
    try:
        for index, step in enumerate(case['steps']):
            if 'hold' in step:
                # These are explicit trusted observations in the simulated input.
                remaining = step['hold']
                while remaining > 0:
                    delta = min(10, machine.config.observation_ttl / 2, remaining)
                    clock.advance(delta)
                    machine.handle(Event.SIT)
                    remaining -= delta
            else:
                clock.advance(step.get('after', 0))
                machine.handle(step['event'])
            for key, expected in step.get('expect', {}).items():
                check(f'step {index + 1}: {key}', machine.snapshot()[key], expected)
        report = machine.export()
        check('broadcast times and levels', [(r['at'], r['level']) for r in report['broadcasts']],
              [tuple(r) for r in case['expected_broadcasts']])
        for record in report['broadcasts']:
            expected = {
                'L0': ('sedentary.l0', '已经坐了一会儿，方便的话起来活动一下吧。'),
                'L1': ('sedentary.l1', '您已连续久坐，建议现在起身走动、舒展一下。'),
            }[record['level']]
            check(f'broadcast at {record["at"]}: content',
                  (record['text_id'], record['text']), expected)
        if 'expected_state' in case:
            check('final state', machine.state, case['expected_state'])
    except (AssertionError, ValueError, KeyError) as exc:
        error = str(exc)
    return {'name': case['name'], 'passed': error is None, 'error': error,
            'checks': checks, **machine.export()}


def run_all(cases=None):
    return [run_scenario(case) for case in (scenarios() if cases is None else cases)]


def main(argv=None, *, cases=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Also save the full UTF-8 JSON report')
    args = parser.parse_args(argv)
    results = run_all(cases)
    report = {'passed': all(r['passed'] for r in results), 'scenario_count': len(results),
              'scenarios': results}
    content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + '\n', encoding='utf-8')
    print(content)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
