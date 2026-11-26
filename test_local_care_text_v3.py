"""Development regressions from the preserved v2 verification failures."""
import unittest

from tools.local_care_text_v3 import SemanticIntentClient, classify_reply


class V3BoundaryTests(unittest.TestCase):
    def test_default_client_keeps_semantic_json_and_five_second_budget(self):
        client = SemanticIntentClient('http://127.0.0.1:12345', 'candidate')
        seen = []
        def complete(body, *, timeout):
            seen.append((body, timeout))
            return {'content': '{"intent":"needs_help"}'}
        client.complete = complete
        self.assertEqual(client.classify('输入')['intent'], 'needs_help')
        self.assertEqual(seen[0][1], 5)
        self.assertEqual(seen[0][0]['response_format']['json_schema']['schema']['type'], 'object')

    def assert_rule(self, text, expected):
        called = []
        result = classify_reply(text, lambda _: called.append(True) or {'intent': 'needs_help'})
        self.assertEqual(result['intent'], expected)
        self.assertEqual(called, [])
        self.assertFalse(result['auto_cancel'])
        self.assertTrue(result['preserve_alert'])

    def test_actual_companionship_request_is_not_an_unrelated_question(self):
        self.assert_rule('这次是我本人求助，能不能来陪我一会儿？', 'needs_help')
        self.assert_rule('能否请人来陪我？', 'needs_help')

    def test_polite_permission_is_distinct_from_a_hypothetical_event(self):
        self.assert_rule('假如能行，麻烦你来搭把手。', 'needs_help')
        self.assert_rule('如果哪天我需要帮助再说吧。', 'unclear')

    def test_nested_refusal_of_an_action_is_not_help(self):
        result = classify_reply('我并非需要你来扶我，只想问明天安排。', lambda _: {'intent': 'needs_help'})
        self.assertNotEqual(result['intent'], 'needs_help')

    def test_real_current_disability_still_precedes_refusal_of_call(self):
        self.assert_rule('我现在起不来不用叫家人。', 'needs_help')

    def test_unexplained_remainder_does_not_confirm_okay(self):
        self.assert_rule('我没事，我不确定现在是什么情况。', 'unclear')


if __name__ == '__main__':
    unittest.main()
