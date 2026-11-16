"""Run the five required local scenarios and export expected/actual evidence."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stdout

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_care_delivery as acceptance

CASES = {
    'restart': 'test_restart_resumes_same_event_without_counting_downtime_or_repeating_l0',
    'duplicate_feedback': 'test_duplicate_feedback_uses_original_id_and_occurrence_time',
    'revoke': 'test_revoke_hidden_and_retained_for_audit_and_sync',
    'offline_retry': 'test_offline_restart_then_retry_keeps_idempotency_key_until_ack',
    'shared_recording': 'test_two_real_state_events_share_one_real_recording_index',
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    acceptance.RESULTS.clear()
    suite = unittest.TestSuite(acceptance.DeliveryTests(method) for method in CASES.values())
    with redirect_stdout(sys.stderr):
        result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
    failed = {test._testMethodName for test, _ in result.errors + result.failures}
    rows = []
    for name, method in CASES.items():
        row = acceptance.RESULTS.get(name)
        rows.append({'name':name, 'test':method, 'passed': bool(row and row['expected']==row['actual'] and method not in failed),
                     **(row or {'error':'scenario_failed_before_final_assertions'})})
    report = {'schema_version':1, 'simulation_only':True,
              'passed':result.wasSuccessful() and all(r['passed'] for r in rows),
              'dependencies':{name:importlib.metadata.version(name) for name in ('numpy','fastapi','httpx')},
              'scenarios':rows}
    text = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    print(text, end='')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
