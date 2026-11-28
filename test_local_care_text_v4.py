import unittest
from tools.local_care_text_v4 import classify_reply


class NegationTests(unittest.TestCase):
    def test_denied_statement_is_not_current_help_even_if_model_suggests_it(self):
        for text in ('我没有说我需要帮助。','我不是说我需要帮助。','我没说我现在起不来。',
                     '我并非表示需要你来帮我。','我没有要求你帮我。',
                     '我没有说我需要家人帮我。','我没有说我需要医生帮我。',
                     '我没有说我想找人来看看我。'):
            with self.subTest(text=text):
                out=classify_reply(text,lambda _:{'intent':'needs_help'})
                self.assertEqual(out['intent'],'unclear')
                self.assertTrue(out['preserve_alert']);self.assertFalse(out['auto_cancel'])

    def test_independent_current_help_is_not_suppressed_by_denied_statement(self):
        for text in ('我没说我需要帮助，但我现在起不来。','我不是说我没事，我现在需要人帮忙。',
                     '我没有说我没事，我现在需要帮助。','我没说要找人，但请你来陪我。'):
            with self.subTest(text=text):
                self.assertEqual(classify_reply(text,lambda _:{'intent':'unclear'})['intent'],'needs_help')

    def test_negation_does_not_turn_into_positive_confirmation(self):
        for text in ('我没有说我需要帮助。','我不是说我不需要帮助。'):
            self.assertNotEqual(classify_reply(text,lambda _:{'intent':'okay'})['intent'],'okay')
