import unittest
from pathlib import Path


ROOT = Path(__file__).parent


def source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class ClientAuthContractTest(unittest.TestCase):
    def test_cloud_service_owns_memory_session_and_refreshes_once(self):
        text = source("entry/src/main/ets/common/CloudService.ets")
        self.assertIn("private accessToken", text)
        self.assertIn("private refreshToken", text)
        self.assertIn("Authorization", text)
        self.assertIn("Bearer ", text)
        self.assertIn("/api/refresh", text)
        self.assertIn("hasSession", text)
        self.assertIn("getMe", text)
        self.assertIn("logout", text)
        self.assertNotIn("preferences", text)

    def test_refresh_is_single_flight_and_each_request_replays_at_most_once(self):
        text = source("entry/src/main/ets/common/CloudService.ets")
        self.assertIn("private refreshPromise: Promise<boolean> | null = null", text)
        self.assertIn("if (this.refreshPromise !== null)", text)
        self.assertIn("this.refreshPromise = this.performRefresh()", text)
        self.assertIn("this.refreshPromise = null", text)
        self.assertRegex(text, r"retryAfterRefresh:\s*boolean")
        self.assertRegex(text, r"requestRaw\([^;]+false\s*\)")

    def test_login_identity_stays_stable_after_get_me(self):
        cloud = source("entry/src/main/ets/common/CloudService.ets")
        index = source("entry/src/main/ets/pages/Index.ets")
        login = source("entry/src/main/ets/pages/Login.ets")
        self.assertIn("private sessionUserKey: string = ''", cloud)
        self.assertIn("this.sessionUserKey = username", cloud)
        self.assertIn("getSessionUserKey", cloud)
        self.assertIn("const sessionUserKey = cloud.getSessionUserKey()", index)
        self.assertNotIn("setCurrentUsername(result.user.username)", index)
        self.assertNotIn("STORE_KEY_LOGGED_IN_USER, result.user.username", index)
        self.assertNotIn("putSync(PREF_KEY_LAST_USERNAME", login)

    def test_database_preserves_legacy_passwords_but_never_caches_new_ones(self):
        database = source("entry/src/main/ets/database/DatabaseHelper.ets")
        login = source("entry/src/main/ets/pages/Login.ets")
        self.assertIn("const DB_VERSION = 4", database)
        self.assertNotIn("if (currentVersion < 5)", database)
        self.assertNotRegex(database, r"UPDATE\s+t_user\s+SET\s+password_hash\s*=\s*''")
        self.assertIn("password_hash: ''", database)
        self.assertNotIn("password_hash: user.passwordHash", database)
        self.assertIn("updatePasswordHash(existing.id, '')", login)

    def test_password_change_always_logs_out_after_server_success(self):
        text = source("entry/src/main/ets/pages/Profile.ets")
        server_success = text.index("if (!cloudR.success)")
        logout = text.index("this.onSuccess()", server_success)
        local_clear = text.index("updatePasswordHash", server_success)
        self.assertLess(local_clear, logout)
        between = text[local_clear:logout]
        self.assertIn("catch", between)
        self.assertIn("console.warn", between)

    def test_legacy_local_only_account_requires_phone_migration(self):
        text = source("entry/src/main/ets/pages/Login.ets")
        self.assertIn("queryUserByIdentifier(uname)", text)
        self.assertIn("本机旧账号", text)
        self.assertIn("手机号", text)
        self.assertIn("迁移", text)
        self.assertNotRegex(text, r"existing\.passwordHash\s*(?:===|!==)")

    def test_ai_uses_cloud_authenticated_transport(self):
        text = source("entry/src/main/ets/common/WenxinService.ets")
        self.assertIn("CloudService", text)
        self.assertRegex(text, r"authenticatedPost\(\s*['\"]\/ai\/chat['\"]")
        self.assertNotIn("http.createHttp", text)

    def test_http_responses_are_requested_as_json_strings(self):
        text = source("entry/src/main/ets/common/CloudService.ets")
        self.assertIn("expectDataType: http.HttpDataType.STRING", text)

    def test_login_has_no_local_auth_or_registration_fallback(self):
        text = source("entry/src/main/ets/pages/Login.ets")
        self.assertIn("手机号验证尚未开放", text)
        self.assertIn("passwordHash: ''", text)
        self.assertNotIn("cloud.register", text)
        self.assertNotIn("existing.passwordHash", text)
        self.assertNotIn("网络不通", text)

    def test_session_consumers_do_not_treat_cached_identity_as_auth(self):
        index = source("entry/src/main/ets/pages/Index.ets")
        person = source("entry/src/main/ets/pages/person.ets")
        profile = source("entry/src/main/ets/pages/Profile.ets")
        self.assertIn("hasSession", index)
        self.assertIn("getMe", index)
        self.assertNotIn("PREF_KEY_LAST_USERNAME", index)
        self.assertNotIn("cloud.login", index)
        self.assertIn("CloudService.getInstance().logout", person)
        self.assertNotRegex(person, r"deleteInputPassword\.trim\(\)\s*!==\s*user\.passwordHash")
        self.assertNotRegex(person, r"deleteUser\([^\n]*currentUser")
        self.assertGreaterEqual(profile.count("暂不可用"), 2)
        self.assertNotIn("fields.phone", profile)
        self.assertNotIn("fields.email", profile)
        self.assertNotRegex(profile, r"changePassword\([^\n]*loginId")


if __name__ == "__main__":
    unittest.main()
