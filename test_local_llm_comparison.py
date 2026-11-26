"""Coverage and scoring checks for the frozen two-package comparison."""
import unittest

from tools.local_llm_comparison import build_runs, summarize_model


class ComparisonTests(unittest.TestCase):
    def test_counterbalanced_schedule_covers_every_case_once_per_model(self):
        cases = [{'id': str(i), 'text': 'synthetic'} for i in range(36)]
        runs = build_runs(cases)
        self.assertEqual([x['model_index'] for x in runs], [0, 1, 1, 0])
        for model in [0, 1]:
            ids = [x['id'] for run in runs if run['model_index'] == model for x in run['cases']]
            self.assertEqual(sorted(ids), sorted(x['id'] for x in cases))
        self.assertEqual(runs[0]['cases'], runs[1]['cases'])
        self.assertEqual(runs[2]['cases'], runs[3]['cases'])

    def test_invalid_schedule_is_rejected_before_running(self):
        for cases in [[], [{'id': 'a'}], [{'id': 'a'}, {'id': 'a'}]]:
            with self.subTest(cases=cases), self.assertRaises(ValueError):
                build_runs(cases)

    def test_errors_remain_in_accuracy_and_help_denominators(self):
        rows = [
            {'expected': 'needs_help', 'status': 'error', 'wall_seconds': 10},
            {'expected': 'okay', 'status': 'ok', 'intent': 'okay', 'wall_seconds': 2},
            {'expected': 'unclear', 'status': 'ok', 'intent': 'okay', 'wall_seconds': 3},
        ]
        summary = summarize_model(rows)
        self.assertEqual(summary['total'], 3)
        self.assertEqual(summary['correct'], 1)
        self.assertEqual(summary['errors'], 1)
        self.assertEqual(summary['help_total'], 1)
        self.assertEqual(summary['help_missed'], 1)
        self.assertEqual(summary['wrong_okay'], 1)
        self.assertEqual(summary['completed_within_5_seconds'], 2)

    def test_valid_but_slow_result_is_not_a_budget_pass(self):
        row = {'expected': 'needs_help', 'status': 'ok', 'intent': 'needs_help', 'wall_seconds': 5.2}
        summary = summarize_model([row])
        self.assertEqual(summary['correct'], 1)
        self.assertEqual(summary['completed_within_5_seconds'], 0)

    def test_failed_result_cannot_become_semantically_correct(self):
        row = {'expected': 'okay', 'status': 'error', 'intent': 'okay', 'wall_seconds': .1}
        summary = summarize_model([row])
        self.assertEqual(summary['correct'], 0)
        self.assertEqual(summary['completed_within_5_seconds'], 0)


if __name__ == '__main__':
    unittest.main()
