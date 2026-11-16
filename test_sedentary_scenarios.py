"""The public one-command scenario runner must assert and export each case."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.run_sedentary_scenarios import run_all, run_scenario, main


class ScenarioRunnerTests(unittest.TestCase):
    def test_all_cases_have_assertions_transitions_and_broadcast_records(self):
        results = run_all()
        self.assertGreaterEqual(len(results), 25)
        self.assertEqual([r['name'] for r in results if not r['passed']], [])
        for result in results:
            with self.subTest(name=result['name']):
                self.assertTrue(result['checks'])
                self.assertTrue(result['transitions'])
                self.assertIsInstance(result['broadcasts'], list)
        self.assertEqual(results, run_all())

    def test_wrong_expectation_is_reported_with_trace(self):
        case = {'name': 'intentional_failure', 'steps': [{'event': 'SIT'}],
                'expected_state': 'EXHAUSTED', 'expected_broadcasts': []}
        result = run_scenario(case)
        self.assertFalse(result['passed'])
        self.assertIn('EXHAUSTED', result['error'])
        self.assertTrue(result['transitions'])

    def test_cli_exports_utf8_and_returns_failure_for_failed_case(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'scenarios.json'
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = main(['--output', str(target)])
            self.assertEqual(code, 0)
            data = json.loads(target.read_text(encoding='utf-8'))
            self.assertTrue(data['passed'])
            self.assertEqual(json.loads(output.getvalue()), data)
            self.assertIn('起来活动', target.read_text(encoding='utf-8'))
        bad = {'name': 'bad', 'steps': [{'event': 'SIT'}],
               'expected_state': 'EXHAUSTED', 'expected_broadcasts': []}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([], cases=[bad]), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
