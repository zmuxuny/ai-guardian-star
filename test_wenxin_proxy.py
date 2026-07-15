import ast
import unittest
from pathlib import Path

from security_utils import hash_password, password_needs_rehash, verify_password


source_path = Path(__file__).with_name("wenxin_proxy.py")
tree = ast.parse(source_path.read_text(encoding="utf-8"))
function_node = next(
    node for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name == "_build_context_summary"
)
namespace = {}
exec(compile(ast.Module(body=[function_node], type_ignores=[]), str(source_path), "exec"), namespace)
_build_context_summary = namespace["_build_context_summary"]
source_text = source_path.read_text(encoding="utf-8")


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


class PasswordSecurityTest(unittest.TestCase):
    def test_password_is_salted_and_verified(self):
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")

        self.assertTrue(first.startswith("scrypt$"))
        self.assertNotIn("correct horse battery staple", first)
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password(first, "correct horse battery staple"))
        self.assertFalse(verify_password(first, "wrong password"))
        self.assertFalse(password_needs_rehash(first))

    def test_legacy_plaintext_password_can_be_upgraded_after_login(self):
        self.assertTrue(verify_password("legacy-password", "legacy-password"))
        self.assertTrue(password_needs_rehash("legacy-password"))
        self.assertFalse(verify_password("legacy-password", "wrong-password"))

    def test_malformed_hash_fails_closed(self):
        self.assertFalse(verify_password("scrypt$broken", "anything"))


class ServerSecurityRegressionTest(unittest.TestCase):
    def test_login_response_never_returns_stored_password(self):
        self.assertNotIn('"passwordHash": row[\'password_hash\']', source_text)

    def test_generic_profile_update_cannot_change_password(self):
        update_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "api_update_user"
        )
        update_source = ast.get_source_segment(source_text, update_node) or ""
        self.assertNotIn("'passwordHash': 'password_hash'", update_source)

    def test_admin_user_list_does_not_select_password_hash(self):
        list_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "admin_list_users"
        )
        list_source = ast.get_source_segment(source_text, list_node) or ""
        self.assertNotIn("SELECT * FROM t_user", list_source)

    def test_cors_is_not_enabled_for_every_origin(self):
        self.assertNotIn("CORS(app)", source_text)

    def test_ai_gateway_limits_input_and_hides_upstream_error_bodies(self):
        ai_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "ai_chat"
        )
        ai_source = ast.get_source_segment(source_text, ai_node) or ""
        self.assertIn("AI_MAX_MESSAGE_LENGTH", ai_source)
        self.assertNotIn('"detail": coze_body', ai_source)
        self.assertNotIn('"detail": str(e)', ai_source)


class ClientSecurityRegressionTest(unittest.TestCase):
    def test_cloud_service_does_not_log_request_or_response_bodies(self):
        cloud_source = source_path.with_name("entry").joinpath(
            "src", "main", "ets", "common", "CloudService.ets"
        ).read_text(encoding="utf-8")
        self.assertNotIn("'body:'", cloud_source)
        self.assertNotIn("'响应内容:'", cloud_source)

    def test_email_is_existing_account_login_only(self):
        login_source = source_path.with_name("entry").joinpath(
            "src", "main", "ets", "pages", "Login.ets"
        ).read_text(encoding="utf-8")
        self.assertIn("邮箱仅支持已有账号登录", login_source)

    def test_shared_mqtt_password_is_not_shipped_in_the_app(self):
        config_source = source_path.with_name("entry").joinpath(
            "src", "main", "ets", "config.ets"
        ).read_text(encoding="utf-8")
        self.assertIn('export const MQTT_PASSWORD = "";', config_source)


if __name__ == "__main__":
    unittest.main()
