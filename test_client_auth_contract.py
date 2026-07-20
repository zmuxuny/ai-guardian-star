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
        self.assertRegex(login, r"updatePasswordHash\([a-zA-Z]+\.id,\s*['\"]{2}\)")

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

    def test_server_session_fields_survive_release_property_obfuscation(self):
        rules = source("entry/obfuscation-rules.txt")
        for field in ("accessToken", "refreshToken"):
            self.assertRegex(rules, rf"(?m)^\s+{field}\s*$")

    def test_login_has_no_local_auth_fallback(self):
        text = source("entry/src/main/ets/pages/Login.ets")
        self.assertIn("handleRegister", text)
        self.assertIn("CloudService.getInstance().register", text)
        self.assertRegex(text, r"passwordHash:\s*['\"]{2}")
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

    def test_remember_me_uses_asset_store_instead_of_plaintext_preferences(self):
        cloud = source("entry/src/main/ets/common/CloudService.ets")
        login = source("entry/src/main/ets/pages/Login.ets")
        self.assertIn("@kit.AssetStoreKit", cloud)
        self.assertIn("asset.Tag.SECRET", cloud)
        self.assertIn("asset.Tag.ALIAS", cloud)
        self.assertIn("asset.ConflictResolution.OVERWRITE", cloud)
        self.assertNotIn("PREF_KEY_REFRESH_TOKEN", cloud)
        self.assertIn("@State rememberMe: boolean", login)
        self.assertIn("Checkbox({ name: 'rememberMe'", login)
        self.assertIn("this.rememberMe = value", login)
        self.assertRegex(login, r"\.login\(uname,\s*pwd,\s*this\.rememberMe\)")

    def test_persisted_refresh_token_is_restored_and_rotated(self):
        cloud = source("entry/src/main/ets/common/CloudService.ets")
        index = source("entry/src/main/ets/pages/Index.ets")
        self.assertIn("restorePersistedSession", cloud)
        self.assertIn("await cloud.restorePersistedSession()", index)
        self.assertRegex(cloud, r"login\(username:\s*string,\s*passwordHash:\s*string,\s*rememberMe:\s*boolean")
        self.assertIn("await this.persistSession()", cloud)
        refresh_success = cloud.index("this.refreshToken = result.refreshToken")
        rotated_save = cloud.index("await this.persistSession()", refresh_success)
        self.assertGreater(rotated_save, refresh_success)

    def test_explicit_logout_and_unchecked_login_forget_persisted_session(self):
        cloud = source("entry/src/main/ets/common/CloudService.ets")
        login_start = cloud.index("public async login(")
        login_end = cloud.index("public async getMe", login_start)
        login = cloud[login_start:login_end]
        self.assertIn("await this.clearPersistedSession()", login)
        self.assertIn("if (rememberMe)", login)
        logout_start = cloud.index("public async logout(")
        logout_end = cloud.index("public async updateUser", logout_start)
        logout = cloud[logout_start:logout_end]
        self.assertIn("await this.clearPersistedSession()", logout)

    def test_registration_uses_server_sms_challenge_contract(self):
        cloud = source("entry/src/main/ets/common/CloudService.ets")
        login = source("entry/src/main/ets/pages/Login.ets")
        self.assertIn("'/api/otp/send'", cloud)
        self.assertIn("'/api/register'", cloud)
        for field in ("phone", "passwordHash", "verifyCode", "challengeId"):
            self.assertIn(field + ":", cloud)
        self.assertIn("@State registerMode: boolean", login)
        self.assertIn("@State verifyCode: string", login)
        self.assertIn("handleSendCode", login)
        self.assertIn("handleRegister", login)
        self.assertNotIn("手机号验证尚未开放", login)
        self.assertRegex(
            cloud,
            r"requestRaw\('/api/otp/send',[^\n]+20000,\s*false\)",
        )
        self.assertRegex(
            cloud,
            r"requestRaw\('/api/register',[^\n]+20000,\s*false\)",
        )

    def test_transient_refresh_failure_does_not_forget_remembered_session(self):
        cloud = source("entry/src/main/ets/common/CloudService.ets")
        refresh_start = cloud.index("private async performRefresh")
        refresh_end = cloud.index("private parseResult", refresh_start)
        refresh = cloud[refresh_start:refresh_end]
        self.assertIn("response.responseCode === 400 || response.responseCode === 401", refresh)


if __name__ == "__main__":
    unittest.main()
