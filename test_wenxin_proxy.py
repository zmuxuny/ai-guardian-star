import ast
import unittest
from pathlib import Path


source_path = Path(__file__).with_name("wenxin_proxy.py")
tree = ast.parse(source_path.read_text(encoding="utf-8"))
function_node = next(
    node for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name == "_build_context_summary"
)
namespace = {}
exec(compile(ast.Module(body=[function_node], type_ignores=[]), str(source_path), "exec"), namespace)
_build_context_summary = namespace["_build_context_summary"]


class AiAccessLevelTest(unittest.TestCase):
    def test_access_level_controls_health_context_detail(self):
        context = {
            "fallCount7d": 2,
            "sedentaryCount7d": 4,
            "lastFallDaysAgo": 0,
            "deviceOnline": True,
            "deviceConnected": True,
            "currentStatus": "检测到跌倒",
            "latestFallRecord": "2026.07.14 10:00:00",
            "latestSedentaryRecord": "2026.07.13 09:00:00",
        }

        basic = _build_context_summary({**context, "accessLevel": "basic"})
        privacy = _build_context_summary({**context, "accessLevel": "privacy"})
        full = _build_context_summary({**context, "accessLevel": "full"})

        self.assertEqual(basic, "")
        self.assertIn("近7天摔倒次数：2次", privacy)
        self.assertNotIn("检测到跌倒", privacy)
        self.assertNotIn("2026.07.14 10:00:00", privacy)
        self.assertIn("当前监护状态：检测到跌倒", full)
        self.assertIn("最近摔倒记录：2026.07.14 10:00:00", full)


if __name__ == "__main__":
    unittest.main()
