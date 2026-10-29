"""安全加固回归：登录限流、令牌失效、角色变更、大小写规则。"""

import unittest

from helpers import ApiTest, DatabaseTest
from app import auth, db, materials, users
from app.auth import LoginThrottle
from app.errors import AuthenticationError, ConflictError, RateLimited


class LoginThrottleUnitTests(unittest.TestCase):
    def test_blocks_after_failure_limit(self):
        throttle = LoginThrottle(max_failures=3, window_seconds=60)
        for _ in range(3):
            throttle.record_failure("key")
        with self.assertRaises(RateLimited) as context:
            throttle.check("key")
        self.assertGreater(context.exception.retry_after, 0)

    def test_success_resets_counter(self):
        throttle = LoginThrottle(max_failures=3, window_seconds=60)
        throttle.record_failure("key")
        throttle.reset("key")
        throttle.check("key")  # 不应抛异常

    def test_keys_are_independent(self):
        throttle = LoginThrottle(max_failures=2, window_seconds=60)
        throttle.record_failure("a")
        throttle.record_failure("a")
        throttle.check("b")  # 另一个 key 不受影响


class LoginThrottleServiceTests(DatabaseTest):
    def test_login_blocked_after_failures(self):
        throttle = LoginThrottle(max_failures=3, window_seconds=60)
        for _ in range(3):
            with self.assertRaises(AuthenticationError):
                auth.login(self.conn, "staff", "wrong-password", throttle=throttle, client="1.1.1.1")
        with self.assertRaises(RateLimited):
            auth.login(self.conn, "staff", "staff123", throttle=throttle, client="1.1.1.1")

    def test_success_clears_failures(self):
        throttle = LoginThrottle(max_failures=3, window_seconds=60)
        for _ in range(2):
            with self.assertRaises(AuthenticationError):
                auth.login(self.conn, "staff", "wrong-password", throttle=throttle, client="ip")
        auth.login(self.conn, "staff", "staff123", throttle=throttle, client="ip")
        # 成功之后计数清零，再失败一次不应该被限流
        with self.assertRaises(AuthenticationError):
            auth.login(self.conn, "staff", "wrong-password", throttle=throttle, client="ip")


class ApiLoginThrottleTests(ApiTest):
    def test_too_many_failures_returns_429(self):
        for _ in range(5):
            response = self.client.post(
                "/auth/login",
                json={"username": "viewer", "password": "bad-password"},
            )
            self.assertEqual(response.status_code, 401)
        blocked = self.client.post(
            "/auth/login",
            json={"username": "viewer", "password": "viewer123"},
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["code"], "too_many_attempts")
        self.assertIn("Retry-After", blocked.headers)


class TokenInvalidationTests(ApiTest):
    def test_disabled_user_token_rejected(self):
        conn = db.connect(self.db_path)
        try:
            users.disable_user(conn, self.staff["id"], self.admin)
        finally:
            conn.close()
        response = self.client.get("/materials", headers=self.auth(self.staff_token))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "authentication_error")

    def test_role_change_takes_effect_immediately(self):
        conn = db.connect(self.db_path)
        try:
            conn.execute("UPDATE users SET role = 'viewer' WHERE id = ?", (self.staff["id"],))
        finally:
            conn.close()
        response = self.client.post(
            "/borrows",
            headers=self.auth(self.staff_token),
            json={"material_id": self.material["id"]},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "permission_denied")

    def test_re_enable_does_not_restore_old_token(self):
        self.client.post(
            f"/users/{self.staff['id']}/disable",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(
            self.client.get("/materials", headers=self.auth(self.staff_token)).status_code, 401
        )

        self.client.post(
            f"/users/{self.staff['id']}/enable",
            headers=self.auth(self.admin_token),
        )
        # 停用已经吊销了旧令牌，重新启用也不能让它复活
        self.assertEqual(
            self.client.get("/materials", headers=self.auth(self.staff_token)).status_code, 401
        )

        fresh_token = self.login("staff", "staff123")
        self.assertEqual(
            self.client.get("/materials", headers=self.auth(fresh_token)).status_code, 200
        )


class CaseInsensitiveTests(DatabaseTest):
    def test_duplicate_username_ignoring_case(self):
        with self.assertRaises(ConflictError):
            users.create_user(
                self.conn, username="ADMIN", password="secret123", role="viewer", actor=self.admin
            )

    def test_login_ignores_username_case(self):
        session = auth.login(self.conn, "ADMIN", "admin123")
        self.assertEqual(session["user"]["username"], "admin")

    def test_duplicate_material_code_ignoring_case(self):
        with self.assertRaises(ConflictError):
            materials.create_material(
                self.conn,
                material_code="img-001",
                title="重复编号",
                modality="CT",
                body_part="胸部",
                material_type="胶片",
                storage_location="A-01",
                actor=self.admin,
            )

    def test_material_lookup_ignores_code_case(self):
        row = materials.get_material_by_code(self.conn, "img-001", self.admin)
        self.assertEqual(row["material_code"], "IMG-001")
