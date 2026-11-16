"""One-command offline verification and replaceable source contract."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from src.shadow_fixtures import fixtures, FixtureSource, evaluate_source, run_case, run_all
from tools.run_shadow_scenarios import main


class ScenarioTests(unittest.TestCase):
    def test_all_fixtures_pass_and_repeat_identically(self):
        first = run_all()
        self.assertGreaterEqual(len(first), 12)
        self.assertEqual([r['name'] for r in first if not r['passed']], [])
        self.assertEqual(json.dumps(first, ensure_ascii=False), json.dumps(run_all(), ensure_ascii=False))
        for case in first:
            self.assertTrue(case['checks'])
            self.assertEqual(case['shadow']['status'], 'completed')
        mismatch = next(c for c in first if c['name'] == 'intentional_count_difference')
        self.assertFalse(mismatch['shadow']['comparison']['matched'])

    def test_alternative_source_requires_no_calculation_change(self):
        data = fixtures()[0]['batch']
        class AnotherSource:
            def read_batch(self):
                return deepcopy(data)
        self.assertEqual(evaluate_source(AnotherSource()), evaluate_source(FixtureSource(data)))

    def test_bad_expectation_preserves_actual_outputs_and_fails(self):
        case = deepcopy(fixtures()[0])
        case['groups'] = []
        result = run_case(case)
        self.assertFalse(result['passed'])
        self.assertTrue(result['shadow']['candidate']['groups'])

    def test_cli_utf8_export_exact_bytes_and_failure_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'result.json'
            with redirect_stdout(io.StringIO()) as output:
                code = main(['--output', str(target)])
            self.assertEqual(code, 0)
            self.assertEqual(target.read_text(encoding='utf-8'), output.getvalue())
            self.assertTrue(json.loads(output.getvalue())['passed'])
        case = deepcopy(fixtures()[0])
        case['groups'] = []
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main([], cases=[case]), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
