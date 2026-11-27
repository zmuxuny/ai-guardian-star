import unittest
from tools.local_care_text_v4_fast import classify_reply


class FastClarificationTests(unittest.TestCase):
    def evaluate(self,text):
        calls=[]
        out=classify_reply(text,lambda value:calls.append(value) or {'intent':'needs_help'})
        self.assertTrue(out['preserve_alert']);self.assertFalse(out['auto_cancel'])
        return out,calls

    def test_complete_denial_goes_to_clarification_without_model(self):
        for text in ('我没有说我需要帮助。','我并没有说我需要家人过来帮忙。',
                     '我未曾表示需要医生来扶我。','我不曾要求你来帮我拿东西。',
                     '我没请求过有人来陪我。','我不是说现在需要你来搭把手。',
                     '我并非提出要你帮我联系家人。','我没有说我想找人陪着我。',
                     '我并没有表示我需要人帮一下。','我没有说我需要帮助，谢谢关心。',
                     '我并没有说我目前需要旁边有个人过来帮我联系家人。'):
            with self.subTest(text=text):
                out,calls=self.evaluate(text)
                self.assertEqual(out['intent'],'unclear');self.assertEqual(calls,[])

    def test_independent_help_remains_help(self):
        out,calls=self.evaluate('我没说我需要帮助，但我现在起不来。')
        self.assertEqual(out['intent'],'needs_help');self.assertEqual(calls,[])

    def test_unresolved_or_weak_current_clause_is_not_swallowed(self):
        out,calls=self.evaluate('我没有说我需要帮助，我想找人来看看我。')
        self.assertEqual(out['intent'],'needs_help');self.assertEqual(len(calls),1)
        _,calls=self.evaluate('我状态很好，刚晒完衣服，现在不需要帮助。')
        self.assertEqual(len(calls),1)
