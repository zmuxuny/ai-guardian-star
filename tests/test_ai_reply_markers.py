"""AI 回复里的内部哨兵标记要在网关过滤掉。

wenxin_proxy 导入时会连数据库、读环境变量，这里只把过滤函数从源码里取出来单独测。
"""
import ast
import re
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "wenxin_proxy.py"


def _load_filter():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    keep = [n for n in tree.body
            if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_INTERNAL_MARKER_RE" for t in n.targets))
            or (isinstance(n, ast.FunctionDef) and n.name == "_strip_internal_markers")]
    ns = {"re": re}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(SRC), "exec"), ns)
    return ns["_strip_internal_markers"]


class StripMarkersTest(unittest.TestCase):
    def setUp(self):
        self.strip = _load_filter()

    def test_removes_bracketed_marker(self):
        raw = "建议每天散步 30 分钟。[SILENT_never_used_51bce0c785ca2f68081bfa7d91973934] 注意防滑。"
        self.assertEqual(self.strip(raw), "建议每天散步 30 分钟。 注意防滑。")

    def test_marker_only_becomes_empty(self):
        self.assertEqual(self.strip("[SILENT_never_used_abc123]"), "")

    def test_normal_text_untouched(self):
        raw = "老人近 7 天没有摔倒记录，\n久坐 2 次。"
        self.assertEqual(self.strip(raw), raw)


if __name__ == "__main__":
    unittest.main()
