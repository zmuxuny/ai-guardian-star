import ast
import base64
import hashlib
import os
import runpy
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from security_utils import hash_password, password_needs_rehash, verify_password


os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key")
os.environ.setdefault("COZE_API_TOKEN", "test-coze-token")
os.environ.pop("ADMIN_ENABLED", None)
os.environ.pop("AI_RISK_CONTROL_READY", None)
os.environ.pop("ALIYUN_SMS_ENABLED", None)

try:
    import flask_cors  # noqa: F401
except ModuleNotFoundError:
    flask_cors = types.ModuleType("flask_cors")
    flask_cors.CORS = lambda *args, **kwargs: None
    sys.modules["flask_cors"] = flask_cors

import wenxin_proxy as proxy


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

    def test_account_errors_do_not_return_exception_text(self):
        with mock.patch.object(proxy, "get_db", side_effect=RuntimeError("DB_SECRET")):
            response = proxy.app.test_client().post(
                "/api/login",
                json={"username": "alice", "passwordHash": "password"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("DB_SECRET", response.get_data(as_text=True))

    def test_server_binds_only_to_loopback(self):
        with mock.patch.object(proxy.Flask, "run") as run:
            runpy.run_path(str(source_path), run_name="__main__")

        run.assert_called_once_with(host="127.0.0.1", port=8899, debug=False)


class AccountSessionSecurityTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        proxy.DB_PATH = str(Path(self.temp_dir.name) / "users.db")
        proxy.ADMIN_ENABLED = False
        proxy.AI_RISK_CONTROL_READY = False
        proxy.ALIYUN_SMS_ENABLED = False
        self.client = proxy.app.test_client()

    def create_user(self, username="alice", password="old-password"):
        conn = proxy.get_db()
        conn.execute(
            """
            INSERT INTO t_user
                (username, nickname, phone, password_hash, avatar_path, email, address, create_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                username.title(),
                f"phone-{username}",
                hash_password(password),
                f"/{username}.jpg",
                f"{username}@example.com",
                f"{username} address",
                1,
            ),
        )
        conn.commit()
        conn.close()

    def login(self, username="alice", password="old-password"):
        return self.client.post(
            "/api/login",
            json={"username": username, "passwordHash": password},
        )

    @staticmethod
    def bearer(token):
        return {"Authorization": f"Bearer {token}"}

    def test_registration_is_closed_without_touching_database(self):
        send = self.client.post(
            "/api/otp/send",
            json={"phone": "13340878619"},
        )
        response = self.client.post(
            "/api/register",
            json={"username": "new-user", "passwordHash": "password"},
        )

        self.assertEqual(send.status_code, 503)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Path(proxy.DB_PATH).exists())


    def test_login_issues_opaque_tokens_and_stores_only_sha256_hashes(self):
        self.create_user()

        response = self.login()

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        access_token = body["accessToken"]
        refresh_token = body["refreshToken"]
        self.assertNotEqual(access_token, refresh_token)
        self.assertNotIn(".", access_token)
        self.assertEqual(body["expiresIn"], 15 * 60)
        self.assertEqual(body["refreshExpiresIn"], 30 * 24 * 60 * 60)

        conn = proxy.get_db()
        row = conn.execute(
            "SELECT access_token_hash, refresh_token_hash, access_expires_at, refresh_expires_at "
            "FROM t_session"
        ).fetchone()
        conn.close()
        self.assertEqual(
            row["access_token_hash"], hashlib.sha256(access_token.encode()).hexdigest()
        )
        self.assertEqual(
            row["refresh_token_hash"], hashlib.sha256(refresh_token.encode()).hexdigest()
        )
        self.assertNotEqual(row["access_token_hash"], access_token)
        self.assertGreaterEqual(row["access_expires_at"], int(proxy.time.time()) + 14 * 60)
        self.assertGreaterEqual(row["refresh_expires_at"], int(proxy.time.time()) + 29 * 24 * 60 * 60)

    def test_refresh_atomically_rotates_both_tokens(self):
        self.create_user()
        first = self.login().get_json()

        response = self.client.post(
            "/api/refresh", json={"refreshToken": first["refreshToken"]}
        )

        self.assertEqual(response.status_code, 200)
        second = response.get_json()
        self.assertNotEqual(second["accessToken"], first["accessToken"])
        self.assertNotEqual(second["refreshToken"], first["refreshToken"])
        self.assertEqual(
            self.client.get(
                "/api/me", headers=self.bearer(first["accessToken"])
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/refresh", json={"refreshToken": first["refreshToken"]}
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                "/api/me", headers=self.bearer(second["accessToken"])
            ).status_code,
            200,
        )

    def test_logout_revokes_current_session(self):
        self.create_user()
        tokens = self.login().get_json()
        headers = self.bearer(tokens["accessToken"])

        self.assertEqual(self.client.post("/api/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/me", headers=headers).status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/refresh", json={"refreshToken": tokens["refreshToken"]}
            ).status_code,
            401,
        )

    def test_me_and_profile_update_use_authenticated_user_only(self):
        self.create_user("alice")
        self.create_user("bob")
        tokens = self.login("alice").get_json()
        headers = self.bearer(tokens["accessToken"])

        me = self.client.get("/api/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()["user"]["username"], "alice")

        spoof = self.client.post(
            "/api/updateUser",
            headers=headers,
            json={"username": "bob", "nickname": "Mallory"},
        )
        self.assertEqual(spoof.status_code, 200)

        updated = self.client.post(
            "/api/updateUser",
            headers=headers,
            json={"nickname": "Alice New", "avatarPath": "/new.jpg", "address": "new"},
        )
        self.assertEqual(updated.status_code, 200)
        conn = proxy.get_db()
        alice = conn.execute(
            "SELECT nickname, avatar_path, address FROM t_user WHERE username='alice'"
        ).fetchone()
        bob = conn.execute(
            "SELECT nickname FROM t_user WHERE username='bob'"
        ).fetchone()
        conn.close()
        self.assertEqual(tuple(alice), ("Alice New", "/new.jpg", "new"))
        self.assertEqual(bob["nickname"], "Bob")

    def test_profile_update_ignores_empty_sensitive_fields_and_rejects_values(self):
        self.create_user()
        headers = self.bearer(self.login().get_json()["accessToken"])

        response = self.client.post(
            "/api/updateUser",
            headers=headers,
            json={
                "phone": "",
                "email": None,
                "passwordHash": "  ",
                "newUsername": "",
                "address": "updated address",
            },
        )
        self.assertEqual(response.status_code, 200)

        for field, value in (
            ("phone", "new-phone"),
            ("email", "new@example.com"),
            ("passwordHash", "new-password"),
            ("newUsername", "renamed"),
            ("unexpected", "value"),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    "/api/updateUser",
                    headers=headers,
                    json={field: value},
                )
                self.assertEqual(response.status_code, 400)

        conn = proxy.get_db()
        row = conn.execute(
            "SELECT username, phone, email, password_hash, address "
            "FROM t_user WHERE username='alice'"
        ).fetchone()
        conn.close()
        self.assertEqual(row["username"], "alice")
        self.assertEqual(row["phone"], "phone-alice")
        self.assertEqual(row["email"], "alice@example.com")
        self.assertTrue(verify_password(row["password_hash"], "old-password"))
        self.assertEqual(row["address"], "updated address")

    def test_orphaned_session_cannot_authorize_or_refresh(self):
        self.create_user()
        tokens = self.login().get_json()
        conn = proxy.get_db()
        conn.execute("DELETE FROM t_user WHERE username='alice'")
        conn.commit()
        conn.close()

        self.assertEqual(
            self.client.get(
                "/api/me", headers=self.bearer(tokens["accessToken"])
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/refresh", json={"refreshToken": tokens["refreshToken"]}
            ).status_code,
            401,
        )

    def test_login_rechecks_account_before_issuing_session(self):
        real_verify = proxy.verify_password
        cases = (
            (
                "password-change",
                "UPDATE t_user SET password_hash=? WHERE username=?",
                (hash_password("new-password"), "password-change"),
            ),
            ("account-delete", "DELETE FROM t_user WHERE username=?", ("account-delete",)),
        )
        for username, sql, params in cases:
            with self.subTest(username=username):
                self.create_user(username)
                mutated = False

                def mutate_after_first_verification(stored, candidate):
                    nonlocal mutated
                    valid = real_verify(stored, candidate)
                    if valid and not mutated:
                        mutated = True
                        conn = proxy.sqlite3.connect(proxy.DB_PATH)
                        conn.execute(sql, params)
                        conn.commit()
                        conn.close()
                    return valid

                with mock.patch.object(
                    proxy, "verify_password", side_effect=mutate_after_first_verification
                ):
                    response = self.login(username)
                self.assertFalse(response.get_json()["success"])

        conn = proxy.get_db()
        sessions = conn.execute("SELECT COUNT(*) FROM t_session").fetchone()[0]
        conn.close()
        self.assertEqual(sessions, 0)

    def test_admin_rename_and_delete_revoke_all_user_sessions(self):
        proxy.ADMIN_ENABLED = True
        self.addCleanup(setattr, proxy, "ADMIN_ENABLED", False)
        with self.client.session_transaction() as admin_session:
            admin_session["admin_logged_in"] = True

        cases = (
            ("rename-me", "put", {"newUsername": "renamed"}),
            ("delete-me", "delete", None),
        )
        for username, method, body in cases:
            with self.subTest(method=method):
                self.create_user(username)
                tokens = [self.login(username).get_json() for _ in range(2)]
                response = getattr(self.client, method)(
                    f"/admin/api/users/{username}", json=body
                )
                self.assertEqual(response.status_code, 200)
                token = tokens[0]
                self.assertEqual(
                    self.client.get(
                        "/api/me", headers=self.bearer(token["accessToken"])
                    ).status_code,
                    401,
                )
                self.assertEqual(
                    self.client.post(
                        "/api/refresh", json={"refreshToken": token["refreshToken"]}
                    ).status_code,
                    401,
                )
            conn = proxy.get_db()
            sessions = conn.execute("SELECT COUNT(*) FROM t_session").fetchone()[0]
            conn.close()
            self.assertEqual(sessions, 0)

    def _enable_admin_session(self):
        proxy.ADMIN_ENABLED = True
        self.addCleanup(setattr, proxy, "ADMIN_ENABLED", False)
        with self.client.session_transaction() as admin_session:
            admin_session["admin_logged_in"] = True

    def test_admin_list_returns_status_metadata_without_password_or_avatar_path(self):
        self.create_user()
        self.login()
        conn = proxy.get_db()
        conn.execute(
            "UPDATE t_user SET avatar_data=?, avatar_mime=?, avatar_updated_at=? "
            "WHERE username='alice'",
            (b"avatar", "image/jpeg", 123),
        )
        conn.commit()
        conn.close()
        self._enable_admin_session()

        response = self.client.get("/admin/api/users")

        self.assertEqual(response.status_code, 200)
        user = response.get_json()["data"][0]
        self.assertEqual(user["password_scheme"], "scrypt")
        self.assertTrue(user["avatar_synced"])
        self.assertEqual(user["session_count"], 1)
        self.assertFalse(user["is_frozen"])
        self.assertNotIn("password_hash", user)
        self.assertNotIn("avatar_path", user)

    def test_admin_avatar_upload_and_delete_syncs_to_device_api(self):
        self.create_user()
        access_token = self.login().get_json()["accessToken"]
        self._enable_admin_session()
        image_bytes = b"\xff\xd8\xff\xe0admin-avatar\xff\xd9"
        encoded = base64.b64encode(image_bytes).decode("ascii")

        uploaded = self.client.post(
            "/admin/api/users/alice/avatar",
            json={"imageBase64": encoded, "mimeType": "image/jpeg"},
        )
        admin_copy = self.client.get("/admin/api/users/alice/avatar")
        device_copy = self.client.get(
            "/api/avatar", headers=self.bearer(access_token)
        )

        self.assertEqual(uploaded.status_code, 200)
        uploaded_at = uploaded.get_json()["updatedAt"]
        self.assertGreater(uploaded_at, 0)
        self.assertEqual(admin_copy.status_code, 200)
        self.assertEqual(admin_copy.data, image_bytes)
        self.assertEqual(admin_copy.content_type, "image/jpeg")
        self.assertEqual(device_copy.status_code, 200)
        self.assertTrue(device_copy.get_json()["hasAvatar"])
        self.assertEqual(device_copy.get_json()["imageBase64"], encoded)

        deleted = self.client.delete("/admin/api/users/alice/avatar")
        deleted_for_device = self.client.get(
            "/api/avatar", headers=self.bearer(access_token)
        )

        self.assertEqual(deleted.status_code, 200)
        self.assertGreaterEqual(deleted.get_json()["updatedAt"], uploaded_at)
        self.assertEqual(
            self.client.get("/admin/api/users/alice/avatar").status_code, 404
        )
        self.assertEqual(deleted_for_device.status_code, 200)
        self.assertTrue(deleted_for_device.get_json()["success"])
        self.assertFalse(deleted_for_device.get_json()["hasAvatar"])
        self.assertNotIn("imageBase64", deleted_for_device.get_json())
        conn = proxy.get_db()
        avatar = conn.execute(
            "SELECT avatar_data, avatar_mime, avatar_path FROM t_user WHERE username='alice'"
        ).fetchone()
        conn.close()
        self.assertIsNone(avatar["avatar_data"])
        self.assertIsNone(avatar["avatar_mime"])
        self.assertEqual(avatar["avatar_path"], "")

    def test_admin_password_reset_uses_1234_and_revokes_sessions(self):
        self.create_user()
        tokens = self.login().get_json()
        self._enable_admin_session()

        response = self.client.post(
            "/admin/api/users/alice/reset-password",
            json={"newPassword": "replacement-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password", response.get_data(as_text=True).lower())
        conn = proxy.get_db()
        row = conn.execute(
            "SELECT password_hash FROM t_user WHERE username='alice'"
        ).fetchone()
        sessions = conn.execute(
            "SELECT COUNT(*) FROM t_session WHERE username='alice'"
        ).fetchone()[0]
        conn.close()
        self.assertTrue(verify_password(row["password_hash"], "1234"))
        self.assertFalse(verify_password(row["password_hash"], "replacement-password"))
        self.assertFalse(verify_password(row["password_hash"], "old-password"))
        self.assertEqual(sessions, 0)
        self.assertEqual(
            self.client.post(
                "/api/refresh", json={"refreshToken": tokens["refreshToken"]}
            ).status_code,
            401,
        )

    def test_admin_freeze_revokes_sessions_and_blocks_login_until_unfrozen(self):
        self.create_user()
        tokens = self.login().get_json()
        self._enable_admin_session()

        frozen = self.client.post(
            "/admin/api/users/alice/freeze", json={"frozen": True}
        )

        self.assertEqual(frozen.status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/me", headers=self.bearer(tokens["accessToken"])
            ).status_code,
            401,
        )
        self.assertEqual(self.login().status_code, 403)

        unfrozen = self.client.post(
            "/admin/api/users/alice/freeze", json={"frozen": False}
        )
        self.assertEqual(unfrozen.status_code, 200)
        self.assertTrue(self.login().get_json()["success"])

    def test_admin_page_uses_click_opened_drawer_and_has_no_avatar_path_field(self):
        self.assertIn('id="detailDrawer"', proxy._ADMIN_HTML)
        self.assertIn("translateX(100%)", proxy._ADMIN_HTML)
        self.assertIn("openDetails", proxy._ADMIN_HTML)
        self.assertIn("重置密码", proxy._ADMIN_HTML)
        self.assertNotIn("avatar_path", proxy._ADMIN_HTML)

    def test_admin_page_offers_avatar_upload_and_delete_controls(self):
        self.assertIn('id="avatarFile"', proxy._ADMIN_HTML)
        self.assertIn("uploadSelectedAvatar", proxy._ADMIN_HTML)
        self.assertIn("confirmDeleteAvatar", proxy._ADMIN_HTML)

    def test_protected_endpoints_reject_missing_bearer_token(self):
        cases = [
            ("get", "/api/me", None),
            ("post", "/api/logout", None),
            ("post", "/api/updateUser", {"nickname": "x"}),
            (
                "post",
                "/api/changePassword",
                {"oldPasswordHash": "old", "newPasswordHash": "new"},
            ),
            ("post", "/api/deleteUser", {"passwordHash": "old"}),
            ("post", "/ai/chat", {"message": "hello"}),
        ]
        for method, path, body in cases:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, json=body)
                self.assertEqual(response.status_code, 401)

    def test_password_change_revokes_all_user_sessions(self):
        self.create_user()
        first = self.login().get_json()
        second = self.login().get_json()

        response = self.client.post(
            "/api/changePassword",
            headers=self.bearer(first["accessToken"]),
            json={"oldPasswordHash": "old-password", "newPasswordHash": "new-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/me", headers=self.bearer(second["accessToken"])
            ).status_code,
            401,
        )
        self.assertEqual(self.login(password="old-password").get_json()["success"], False)
        self.assertEqual(self.login(password="new-password").get_json()["success"], True)

    def test_concurrent_password_changes_accept_old_password_only_once(self):
        self.create_user()
        tokens = [self.login().get_json()["accessToken"] for _ in range(2)]
        start = threading.Barrier(2)
        both_verified = threading.Barrier(2)
        responses = []
        real_hash_password = proxy.hash_password

        def hash_after_both_requests_verified(password):
            try:
                both_verified.wait(timeout=1)
            except threading.BrokenBarrierError:
                pass
            return real_hash_password(password)

        def change_password(token, new_password):
            start.wait()
            response = proxy.app.test_client().post(
                "/api/changePassword",
                headers=self.bearer(token),
                json={
                    "oldPasswordHash": "old-password",
                    "newPasswordHash": new_password,
                },
            )
            responses.append(response)

        with mock.patch.object(proxy, "hash_password", hash_after_both_requests_verified):
            threads = [
                threading.Thread(target=change_password, args=(token, f"new-{index}"))
                for index, token in enumerate(tokens)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(len(responses), 2)
        self.assertEqual(
            sum(bool(response.get_json()["success"]) for response in responses), 1
        )

    def test_delete_ignores_spoofed_username_and_revokes_sessions(self):
        self.create_user("alice")
        self.create_user("bob")
        tokens = self.login("alice").get_json()

        response = self.client.post(
            "/api/deleteUser",
            headers=self.bearer(tokens["accessToken"]),
            json={"username": "bob", "passwordHash": "old-password"},
        )

        self.assertEqual(response.status_code, 200)
        conn = proxy.get_db()
        users = [row["username"] for row in conn.execute("SELECT username FROM t_user")]
        sessions = conn.execute(
            "SELECT COUNT(*) AS count FROM t_session WHERE username='alice'"
        ).fetchone()["count"]
        conn.close()
        self.assertEqual(users, ["bob"])
        self.assertEqual(sessions, 0)

    def test_contact_code_rejects_value_owned_by_another_account(self):
        self.create_user("alice")
        self.create_user("bob")
        conn = proxy.get_db()
        conn.execute("UPDATE t_user SET phone=? WHERE username='bob'", ("13340878619",))
        conn.commit()
        conn.close()
        token = self.login().get_json()["accessToken"]

        with mock.patch.object(proxy, "_send_sms_verification") as send_sms:
            response = self.client.post(
                "/api/contact/otp/send",
                headers=self.bearer(token),
                json={"kind": "phone", "value": "13340878619"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(send_sms.called)

    def test_phone_contact_code_shares_registration_sms_budget(self):
        self.create_user()
        token = self.login().get_json()["accessToken"]
        proxy.ALIYUN_SMS_ENABLED = True
        old_daily_limit = proxy.ALIYUN_SMS_DAILY_LIMIT
        proxy.ALIYUN_SMS_DAILY_LIMIT = 1
        self.addCleanup(setattr, proxy, "ALIYUN_SMS_ENABLED", False)
        self.addCleanup(setattr, proxy, "ALIYUN_SMS_DAILY_LIMIT", old_daily_limit)
        now = int(proxy.time.time())
        conn = proxy.get_db()
        conn.execute(
            """
            INSERT INTO t_sms_challenge
                (challenge_hash, phone, purpose, requester_ip, sent_at, expires_at)
            VALUES ('existing-registration', '13300000000', 'register', '127.0.0.1', ?, ?)
            """,
            (now, now + proxy.SMS_CODE_TTL),
        )
        conn.commit()
        conn.close()

        with mock.patch.object(proxy, "_send_sms_verification") as send_sms:
            response = self.client.post(
                "/api/contact/otp/send",
                headers=self.bearer(token),
                json={"kind": "phone", "value": "13340878619"},
            )

        self.assertEqual(response.status_code, 429)
        self.assertFalse(send_sms.called)

    def test_registration_code_shares_contact_sms_budget(self):
        proxy.ALIYUN_SMS_ENABLED = True
        old_daily_limit = proxy.ALIYUN_SMS_DAILY_LIMIT
        proxy.ALIYUN_SMS_DAILY_LIMIT = 1
        self.addCleanup(setattr, proxy, "ALIYUN_SMS_ENABLED", False)
        self.addCleanup(setattr, proxy, "ALIYUN_SMS_DAILY_LIMIT", old_daily_limit)
        now = int(proxy.time.time())
        conn = proxy.get_db()
        conn.execute(
            """
            INSERT INTO t_contact_challenge
                (challenge_hash, username, kind, value, requester_ip, sent_at, expires_at)
            VALUES ('existing-contact', 'alice', 'phone', '13300000000',
                    '127.0.0.1', ?, ?)
            """,
            (now, now + proxy.SMS_CODE_TTL),
        )
        conn.commit()
        conn.close()

        with mock.patch.object(proxy, "_send_sms_verification") as send_sms:
            response = self.client.post(
                "/api/otp/send",
                json={"phone": "13340878619"},
            )

        self.assertEqual(response.status_code, 429)
        self.assertFalse(send_sms.called)

    def test_phone_contact_update_requires_matching_one_time_code(self):
        self.create_user()
        token = self.login().get_json()["accessToken"]
        proxy.ALIYUN_SMS_ENABLED = True
        self.addCleanup(setattr, proxy, "ALIYUN_SMS_ENABLED", False)

        with mock.patch.object(proxy, "_send_sms_verification"), mock.patch.object(
            proxy, "_check_sms_verification", return_value=True
        ):
            sent = self.client.post(
                "/api/contact/otp/send",
                headers=self.bearer(token),
                json={"kind": "phone", "value": "13340878619"},
            )
            self.assertEqual(sent.status_code, 200)
            changed = self.client.post(
                "/api/contact/update",
                headers=self.bearer(token),
                json={
                    "kind": "phone",
                    "value": "13340878619",
                    "verifyCode": "123456",
                    "challengeId": sent.get_json()["challengeId"],
                },
            )
            replay = self.client.post(
                "/api/contact/update",
                headers=self.bearer(token),
                json={
                    "kind": "phone",
                    "value": "13340878619",
                    "verifyCode": "123456",
                    "challengeId": sent.get_json()["challengeId"],
                },
            )

        self.assertEqual(sent.status_code, 200)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(replay.status_code, 400)
        conn = proxy.get_db()
        row = conn.execute("SELECT phone FROM t_user WHERE username='alice'").fetchone()
        conn.close()
        self.assertEqual(row["phone"], "13340878619")

    def test_email_contact_update_verifies_server_generated_code(self):
        self.create_user()
        token = self.login().get_json()["accessToken"]
        proxy.EMAIL_OTP_ENABLED = True
        self.addCleanup(setattr, proxy, "EMAIL_OTP_ENABLED", False)

        with mock.patch.object(proxy, "_send_email_verification", create=True) as send_email:
            sent = self.client.post(
                "/api/contact/otp/send",
                headers=self.bearer(token),
                json={"kind": "email", "value": "alice-new@example.com"},
            )
            self.assertEqual(sent.status_code, 200)
            code = send_email.call_args.args[1]
            changed = self.client.post(
                "/api/contact/update",
                headers=self.bearer(token),
                json={
                    "kind": "email",
                    "value": "alice-new@example.com",
                    "verifyCode": code,
                    "challengeId": sent.get_json()["challengeId"],
                },
            )

        self.assertEqual(changed.status_code, 200)
        conn = proxy.get_db()
        row = conn.execute("SELECT email FROM t_user WHERE username='alice'").fetchone()
        conn.close()
        self.assertEqual(row["email"], "alice-new@example.com")

    def test_avatar_round_trips_across_independent_sessions(self):
        self.create_user()
        first_token = self.login().get_json()["accessToken"]
        image_bytes = b"\xff\xd8\xff\xe0guardian-avatar\xff\xd9"
        encoded = base64.b64encode(image_bytes).decode("ascii")

        uploaded = self.client.post(
            "/api/avatar",
            headers=self.bearer(first_token),
            json={"imageBase64": encoded, "mimeType": "image/jpeg"},
        )
        second_token = self.login().get_json()["accessToken"]
        downloaded = self.client.get(
            "/api/avatar",
            headers=self.bearer(second_token),
        )

        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.get_json()["imageBase64"], encoded)

    def test_ai_is_fail_closed_before_any_upstream_call(self):
        self.create_user()
        tokens = self.login().get_json()

        with mock.patch.object(
            proxy.requests, "post", side_effect=AssertionError("upstream called")
        ) as upstream:
            response = self.client.post(
                "/ai/chat",
                headers=self.bearer(tokens["accessToken"]),
                json={"message": "hello"},
            )

        self.assertEqual(response.status_code, 503)
        upstream.assert_not_called()

    def test_ai_requires_moderation_provider_before_coze(self):
        self.create_user()
        tokens = self.login().get_json()
        proxy.AI_RISK_CONTROL_READY = True
        self.addCleanup(setattr, proxy, "AI_RISK_CONTROL_READY", False)

        with mock.patch.object(proxy.requests, "post") as upstream:
            response = self.client.post(
                "/ai/chat",
                headers=self.bearer(tokens["accessToken"]),
                json={"message": "普通健康咨询"},
            )

        self.assertEqual(response.status_code, 503)
        upstream.assert_not_called()

    def test_local_crisis_response_bypasses_paid_services(self):
        self.create_user()
        tokens = self.login().get_json()
        proxy.AI_RISK_CONTROL_READY = True
        proxy.ALIYUN_MODERATION_ENABLED = True
        self.addCleanup(setattr, proxy, "AI_RISK_CONTROL_READY", False)
        self.addCleanup(setattr, proxy, "ALIYUN_MODERATION_ENABLED", False)

        with mock.patch.object(proxy, "_moderate_text") as moderation, \
             mock.patch.object(proxy.requests, "post") as upstream:
            response = self.client.post(
                "/ai/chat",
                headers=self.bearer(tokens["accessToken"]),
                json={"message": "我想自杀"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("120", response.get_json()["reply"])
        moderation.assert_not_called()
        upstream.assert_not_called()

    def test_high_risk_input_never_reaches_coze(self):
        self.create_user()
        tokens = self.login().get_json()
        proxy.AI_RISK_CONTROL_READY = True
        proxy.ALIYUN_MODERATION_ENABLED = True
        self.addCleanup(setattr, proxy, "AI_RISK_CONTROL_READY", False)
        self.addCleanup(setattr, proxy, "ALIYUN_MODERATION_ENABLED", False)

        with mock.patch.object(
            proxy, "_moderate_text", return_value={"risk_level": "high", "advice": ""}
        ) as moderation, mock.patch.object(proxy.requests, "post") as upstream:
            response = self.client.post(
                "/ai/chat",
                headers=self.bearer(tokens["accessToken"]),
                json={"message": "测试高风险输入"},
            )

        self.assertEqual(response.status_code, 422)
        moderation.assert_called_once()
        upstream.assert_not_called()

    def test_safe_ai_reply_is_moderated_before_return(self):
        self.create_user()
        tokens = self.login().get_json()
        proxy.AI_RISK_CONTROL_READY = True
        proxy.ALIYUN_MODERATION_ENABLED = True
        self.addCleanup(setattr, proxy, "AI_RISK_CONTROL_READY", False)
        self.addCleanup(setattr, proxy, "ALIYUN_MODERATION_ENABLED", False)
        coze_response = mock.Mock()
        coze_response.iter_lines.return_value = [
            'data: {"type":"answer","content":{"answer":"请规律作息。"},"finish":true}'
        ]

        with mock.patch.object(
            proxy,
            "_moderate_text",
            side_effect=[
                {"risk_level": "none", "advice": ""},
                {"risk_level": "none", "advice": ""},
            ],
        ) as moderation, mock.patch.object(
            proxy.requests, "post", return_value=coze_response
        ) as upstream:
            response = self.client.post(
                "/ai/chat",
                headers=self.bearer(tokens["accessToken"]),
                json={"message": "如何改善睡眠"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["reply"], "请规律作息。")
        self.assertEqual(moderation.call_count, 2)
        self.assertEqual(moderation.call_args_list[0].args[0], "llm_query_moderation")
        self.assertEqual(moderation.call_args_list[1].args[0], "llm_response_moderation")
        upstream.assert_called_once()

    def test_admin_routes_are_disabled_by_default(self):
        self.assertEqual(self.client.get("/admin").status_code, 404)

    def test_admin_login_cookie_is_restricted_to_https_same_site_requests(self):
        proxy.ADMIN_ENABLED = True
        self.addCleanup(setattr, proxy, "ADMIN_ENABLED", False)
        old_password = proxy.ADMIN_PASSWORD
        proxy.ADMIN_PASSWORD = "test-admin-password"
        self.addCleanup(setattr, proxy, "ADMIN_PASSWORD", old_password)

        response = self.client.post(
            "/admin/login",
            data={"password": "test-admin-password"},
        )

        self.assertEqual(response.status_code, 302)
        cookie = response.headers["Set-Cookie"]
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)

class SmsRegistrationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        proxy.DB_PATH = str(Path(self.temp_dir.name) / "users.db")
        proxy.ALIYUN_SMS_ENABLED = True
        self.addCleanup(setattr, proxy, "ALIYUN_SMS_ENABLED", False)
        self.client = proxy.app.test_client()

    def send_code(self, phone="13340878619"):
        with mock.patch.object(proxy, "_send_sms_verification") as send:
            response = self.client.post("/api/otp/send", json={"phone": phone})
        return response, send

    def create_user(self, phone="13340878619"):
        conn = proxy.get_db()
        conn.execute(
            """
            INSERT INTO t_user
                (username, nickname, phone, password_hash, avatar_path, email, address, create_time)
            VALUES (?, ?, ?, ?, '', '', '', ?)
            """,
            (phone, "existing", phone, hash_password("old-password"), 1),
        )
        conn.commit()
        conn.close()

    def test_send_code_stores_only_an_opaque_challenge_hash(self):
        response, send = self.send_code()

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["expiresIn"], 300)
        self.assertGreaterEqual(len(body["challengeId"]), 32)
        send.assert_called_once_with("13340878619", body["challengeId"])

        conn = proxy.get_db()
        row = conn.execute(
            "SELECT challenge_hash, phone, purpose FROM t_sms_challenge"
        ).fetchone()
        conn.close()
        self.assertEqual(row["challenge_hash"], proxy._token_hash(body["challengeId"]))
        self.assertNotEqual(row["challenge_hash"], body["challengeId"])
        self.assertEqual(row["phone"], "13340878619")
        self.assertEqual(row["purpose"], "register")

    def test_send_code_rejects_invalid_phone_and_local_repeats(self):
        with mock.patch.object(proxy, "_send_sms_verification") as send:
            invalid = self.client.post("/api/otp/send", json={"phone": "123"})
            first = self.client.post("/api/otp/send", json={"phone": "13340878619"})
            repeated = self.client.post("/api/otp/send", json={"phone": "13340878619"})

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(repeated.status_code, 429)
        self.assertEqual(send.call_count, 1)

    def test_provider_failure_still_counts_toward_rate_limits(self):
        with mock.patch.object(
            proxy, "_send_sms_verification", side_effect=RuntimeError("provider unavailable")
        ):
            failed = self.client.post("/api/otp/send", json={"phone": "13340878619"})
        with mock.patch.object(proxy, "_send_sms_verification") as send:
            retried = self.client.post("/api/otp/send", json={"phone": "13340878619"})

        self.assertEqual(failed.status_code, 500)
        self.assertEqual(retried.status_code, 429)
        send.assert_not_called()

    def test_existing_phone_is_rate_limited_without_calling_provider(self):
        self.create_user()
        with mock.patch.object(proxy, "_send_sms_verification") as send:
            first = self.client.post("/api/otp/send", json={"phone": "13340878619"})
            repeated = self.client.post("/api/otp/send", json={"phone": "13340878619"})

        self.assertEqual(first.status_code, 409)
        self.assertEqual(repeated.status_code, 429)
        send.assert_not_called()

    def test_registration_accepts_four_character_password(self):
        send_response, _ = self.send_code()
        body = send_response.get_json()
        with mock.patch.object(proxy, "_check_sms_verification", return_value=True) as check:
            response = self.client.post(
                "/api/register",
                json={
                    "phone": "13340878619",
                    "passwordHash": "1234",
                    "verifyCode": "123456",
                    "challengeId": body["challengeId"],
                },
            )

        self.assertEqual(response.status_code, 200)
        check.assert_called_once()

    def test_global_daily_budget_stops_additional_send_cost(self):
        old_limit = proxy.ALIYUN_SMS_DAILY_LIMIT
        proxy.ALIYUN_SMS_DAILY_LIMIT = 1
        self.addCleanup(setattr, proxy, "ALIYUN_SMS_DAILY_LIMIT", old_limit)
        with mock.patch.object(proxy, "_send_sms_verification") as send:
            first = self.client.post("/api/otp/send", json={"phone": "13340878619"})
            blocked = self.client.post("/api/otp/send", json={"phone": "13900000000"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(send.call_count, 1)

    def test_global_monthly_budget_stops_additional_send_cost(self):
        now = 1785240000
        conn = proxy.get_db()
        conn.execute(
            """
            INSERT INTO t_sms_challenge
                (challenge_hash, phone, purpose, requester_ip, sent_at, expires_at)
            VALUES ('older-send', '13340878619', 'register', '127.0.0.1', ?, ?)
            """,
            (now - 10 * 24 * 60 * 60, now),
        )
        conn.commit()
        conn.close()

        with mock.patch.object(proxy, "ALIYUN_SMS_MONTHLY_LIMIT", 1, create=True):
            with mock.patch.object(proxy.time, "time", return_value=now):
                with mock.patch.object(proxy, "_send_sms_verification") as send:
                    blocked = self.client.post(
                        "/api/otp/send", json={"phone": "13900000000"}
                    )

        self.assertEqual(blocked.status_code, 429)
        send.assert_not_called()

    def test_registration_requires_matching_one_time_challenge(self):
        send_response, _ = self.send_code()
        challenge = send_response.get_json()["challengeId"]
        payload = {
            "phone": "13340878619",
            "passwordHash": "new-password",
            "verifyCode": "123456",
            "challengeId": challenge,
        }

        with mock.patch.object(proxy, "_check_sms_verification", return_value=True) as check:
            response = self.client.post("/api/register", json=payload)
            replay = self.client.post("/api/register", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["user"]["username"], "13340878619")
        self.assertEqual(body["user"]["phone"], "13340878619")
        self.assertIn("accessToken", body)
        self.assertIn("refreshToken", body)
        self.assertEqual(replay.status_code, 400)
        check.assert_called_once_with("13340878619", "123456", challenge)

        conn = proxy.get_db()
        user = conn.execute(
            "SELECT username, phone, password_hash FROM t_user WHERE username=?",
            ("13340878619",),
        ).fetchone()
        consumed = conn.execute(
            "SELECT consumed_at FROM t_sms_challenge WHERE challenge_hash=?",
            (proxy._token_hash(challenge),),
        ).fetchone()
        conn.close()
        self.assertTrue(verify_password(user["password_hash"], "new-password"))
        self.assertIsNotNone(consumed["consumed_at"])

    def test_wrong_code_counts_attempt_and_can_be_retried(self):
        send_response, _ = self.send_code()
        challenge = send_response.get_json()["challengeId"]
        payload = {
            "phone": "13340878619",
            "passwordHash": "new-password",
            "verifyCode": "000000",
            "challengeId": challenge,
        }

        with mock.patch.object(proxy, "_check_sms_verification", return_value=False):
            response = self.client.post("/api/register", json=payload)

        self.assertEqual(response.status_code, 400)
        conn = proxy.get_db()
        row = conn.execute(
            "SELECT failed_attempts, checking_at, consumed_at FROM t_sms_challenge"
        ).fetchone()
        conn.close()
        self.assertEqual(row["failed_attempts"], 1)
        self.assertIsNone(row["checking_at"])
        self.assertIsNone(row["consumed_at"])

    def test_stale_verification_cannot_clear_new_reservation(self):
        send_response, _ = self.send_code()
        challenge = send_response.get_json()["challengeId"]
        payload = {
            "phone": "13340878619",
            "passwordHash": "new-password",
            "verifyCode": "000000",
            "challengeId": challenge,
        }

        def replace_reservation(*_args):
            conn = proxy.get_db()
            old_owner = conn.execute(
                "SELECT checking_at FROM t_sms_challenge"
            ).fetchone()["checking_at"]
            conn.execute(
                "UPDATE t_sms_challenge SET checking_at=?",
                (old_owner + 31,),
            )
            conn.commit()
            conn.close()
            return False

        with mock.patch.object(proxy, "_check_sms_verification", side_effect=replace_reservation):
            response = self.client.post("/api/register", json=payload)

        self.assertEqual(response.status_code, 400)
        conn = proxy.get_db()
        row = conn.execute(
            "SELECT failed_attempts, checking_at FROM t_sms_challenge"
        ).fetchone()
        conn.close()
        self.assertEqual(row["failed_attempts"], 0)
        self.assertIsNotNone(row["checking_at"])


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

    def test_ai_api_uses_https_domain(self):
        config_source = source_path.with_name("entry").joinpath(
            "src", "main", "ets", "config.ets"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'export const ECS_BASE_URL = "https://api.aistar.asia";',
            config_source,
        )


if __name__ == "__main__":
    unittest.main()
