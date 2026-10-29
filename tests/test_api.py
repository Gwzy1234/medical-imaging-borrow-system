"""接口层测试：用 FastAPI TestClient 直接发 HTTP 请求。"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db, materials, users
from app.main import create_app


class ApiTestCase(unittest.TestCase):
    """每个用例一个临时数据库和独立的应用实例。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "api.db"
        self.client = TestClient(create_app(self.db_path))
        self.client.__enter__()

        conn = db.connect(self.db_path)
        try:
            self.admin = users.create_user(conn, username="admin", password="admin123", role="admin")
            self.staff = users.create_user(conn, username="staff", password="staff123", role="staff", actor=self.admin)
            self.viewer = users.create_user(conn, username="viewer", password="viewer123", role="viewer", actor=self.admin)
            self.material = materials.create_material(
                conn,
                material_code="IMG-001",
                title="胸部 CT 平扫",
                modality="CT",
                body_part="胸部",
                material_type="胶片",
                storage_location="一号库 A-01",
                actor=self.admin,
            )
        finally:
            conn.close()

        self.admin_token = self.login("admin", "admin123")
        self.staff_token = self.login("staff", "staff123")
        self.viewer_token = self.login("viewer", "viewer123")

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self._tmp.cleanup()

    def login(self, username, password):
        response = self.client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["token"]

    @staticmethod
    def auth(token):
        return {"Authorization": f"Bearer {token}"}


class SystemAndAuthTests(ApiTestCase):
    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_login_returns_token_and_user(self):
        response = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        body = response.json()
        self.assertIn("token", body)
        self.assertEqual(body["user"]["role"], "admin")
        self.assertNotIn("password_hash", body["user"])

    def test_login_wrong_password_keeps_error_format(self):
        response = self.client.post("/auth/login", json={"username": "admin", "password": "bad"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "authentication_error")

    def test_missing_token_is_401(self):
        response = self.client.get("/materials")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "authentication_error")

    def test_me_and_logout(self):
        response = self.client.get("/auth/me", headers=self.auth(self.staff_token))
        self.assertEqual(response.json()["username"], "staff")

        logout = self.client.post("/auth/logout", headers=self.auth(self.staff_token))
        self.assertEqual(logout.status_code, 200)

        after = self.client.get("/auth/me", headers=self.auth(self.staff_token))
        self.assertEqual(after.status_code, 401)


class MaterialApiTests(ApiTestCase):
    def test_list_materials(self):
        response = self.client.get("/materials", headers=self.auth(self.viewer_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_list_available_materials(self):
        response = self.client.get("/materials/available", headers=self.auth(self.viewer_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["material_code"], "IMG-001")

    def test_admin_creates_material(self):
        response = self.client.post(
            "/materials",
            headers=self.auth(self.admin_token),
            json={
                "material_code": "IMG-002",
                "title": "头颅 MRI 增强",
                "modality": "MR",
                "body_part": "头部",
                "material_type": "光盘",
                "storage_location": "一号库 B-02",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["material_code"], "IMG-002")

    def test_viewer_cannot_create_material(self):
        response = self.client.post(
            "/materials",
            headers=self.auth(self.viewer_token),
            json={
                "material_code": "IMG-003",
                "title": "腹部超声",
                "modality": "US",
                "body_part": "腹部",
                "material_type": "光盘",
                "storage_location": "二号库 D-04",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "permission_denied")

    def test_update_material_partial(self):
        response = self.client.patch(
            f"/materials/{self.material['id']}",
            headers=self.auth(self.admin_token),
            json={"title": "胸部 CT 增强"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "胸部 CT 增强")
        self.assertEqual(response.json()["modality"], "CT")

    def test_missing_material_is_404(self):
        response = self.client.get("/materials/9999", headers=self.auth(self.admin_token))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")

    def test_admin_can_enable_disabled_material(self):
        disabled = self.client.post(
            f"/materials/{self.material['id']}/disable",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()["status"], "disabled")

        enabled = self.client.post(
            f"/materials/{self.material['id']}/enable",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(enabled.status_code, 200, enabled.text)
        self.assertEqual(enabled.json()["status"], "available")

    def test_staff_cannot_enable_material(self):
        self.client.post(
            f"/materials/{self.material['id']}/disable",
            headers=self.auth(self.admin_token),
        )
        response = self.client.post(
            f"/materials/{self.material['id']}/enable",
            headers=self.auth(self.staff_token),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "permission_denied")

    def test_admin_can_delete_material_without_records(self):
        deleted = self.client.delete(
            f"/materials/{self.material['id']}",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertTrue(deleted.json()["deleted"])

        missing = self.client.get(
            f"/materials/{self.material['id']}",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(missing.status_code, 404)

    def test_delete_material_with_borrow_history_is_409(self):
        borrowed = self.client.post(
            "/borrows",
            headers=self.auth(self.staff_token),
            json={"material_id": self.material["id"]},
        )
        self.assertEqual(borrowed.status_code, 200)

        deleted = self.client.delete(
            f"/materials/{self.material['id']}",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(deleted.status_code, 409)
        self.assertEqual(deleted.json()["code"], "conflict")
        self.assertIn("借阅记录", deleted.json()["message"])

    def test_force_delete_material_with_history(self):
        borrowed = self.client.post(
            "/borrows",
            headers=self.auth(self.staff_token),
            json={"material_id": self.material["id"]},
        )
        self.assertEqual(borrowed.status_code, 200)

        deleted = self.client.delete(
            f"/materials/{self.material['id']}?force=true",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()["deleted_records"], 1)

        missing = self.client.get(
            f"/materials/{self.material['id']}",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(missing.status_code, 404)
        history = self.client.get("/borrows/history", headers=self.auth(self.admin_token))
        self.assertEqual(history.json(), [])

    def test_staff_cannot_delete_material(self):
        response = self.client.delete(
            f"/materials/{self.material['id']}",
            headers=self.auth(self.staff_token),
        )
        self.assertEqual(response.status_code, 403)


class BorrowApiTests(ApiTestCase):
    def test_full_borrow_return_cycle(self):
        borrow = self.client.post(
            "/borrows",
            headers=self.auth(self.staff_token),
            json={"material_id": self.material["id"]},
        )
        self.assertEqual(borrow.status_code, 200, borrow.text)
        self.assertIsNone(borrow.json()["returned_at"])

        detail = self.client.get(f"/materials/{self.material['id']}", headers=self.auth(self.staff_token))
        self.assertEqual(detail.json()["status"], "borrowed")

        again = self.client.post(
            "/borrows",
            headers=self.auth(self.staff_token),
            json={"material_id": self.material["id"]},
        )
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["code"], "conflict")

        returned = self.client.post(
            f"/borrows/{self.material['id']}/return",
            headers=self.auth(self.staff_token),
        )
        self.assertEqual(returned.status_code, 200)
        self.assertEqual(returned.json()["status"], "available")

        detail = self.client.get(f"/materials/{self.material['id']}", headers=self.auth(self.staff_token))
        self.assertEqual(detail.json()["status"], "available")

        history = self.client.get("/borrows/history", headers=self.auth(self.viewer_token))
        self.assertEqual(len(history.json()), 1)

    def test_viewer_cannot_borrow(self):
        response = self.client.post(
            "/borrows",
            headers=self.auth(self.viewer_token),
            json={"material_id": self.material["id"]},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "permission_denied")

    def test_borrow_unknown_material(self):
        response = self.client.post(
            "/borrows",
            headers=self.auth(self.staff_token),
            json={"material_id": 9999},
        )
        self.assertEqual(response.status_code, 404)

    def test_return_without_active_record(self):
        response = self.client.post(
            f"/borrows/{self.material['id']}/return",
            headers=self.auth(self.staff_token),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "conflict")

    def test_active_borrow_endpoint(self):
        self.client.post(
            "/borrows",
            headers=self.auth(self.staff_token),
            json={"material_id": self.material["id"]},
        )
        response = self.client.get(f"/borrows/{self.material['id']}", headers=self.auth(self.viewer_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["borrower_id"], self.staff["id"])

        empty = self.client.get("/borrows/active", headers=self.auth(self.viewer_token))
        self.assertEqual(len(empty.json()), 1)


class UserApiTests(ApiTestCase):
    def test_admin_lists_users_without_hash(self):
        response = self.client.get("/users", headers=self.auth(self.admin_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 3)
        self.assertTrue(all("password_hash" not in row for row in response.json()))

    def test_staff_cannot_list_users(self):
        response = self.client.get("/users", headers=self.auth(self.staff_token))
        self.assertEqual(response.status_code, 403)

    def test_admin_creates_user(self):
        response = self.client.post(
            "/users",
            headers=self.auth(self.admin_token),
            json={"username": "newbie", "password": "secret123", "role": "viewer"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["username"], "newbie")

    def test_short_password_returns_422(self):
        response = self.client.post(
            "/users",
            headers=self.auth(self.admin_token),
            json={"username": "shorty", "password": "123", "role": "viewer"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_disable_user_blocks_login(self):
        response = self.client.post(
            f"/users/{self.viewer['id']}/disable",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["is_active"], 0)

        login = self.client.post("/auth/login", json={"username": "viewer", "password": "viewer123"})
        self.assertEqual(login.status_code, 401)

    def test_enable_user_allows_login_again(self):
        self.client.post(f"/users/{self.viewer['id']}/disable", headers=self.auth(self.admin_token))
        enabled = self.client.post(
            f"/users/{self.viewer['id']}/enable",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(enabled.status_code, 200)
        self.assertEqual(enabled.json()["is_active"], 1)

        login = self.client.post("/auth/login", json={"username": "viewer", "password": "viewer123"})
        self.assertEqual(login.status_code, 200)

    def test_enable_active_user_is_409(self):
        response = self.client.post(
            f"/users/{self.viewer['id']}/enable",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 409)

    def test_change_role_takes_effect_for_existing_token(self):
        changed = self.client.patch(
            f"/users/{self.staff['id']}/role",
            headers=self.auth(self.admin_token),
            json={"role": "viewer"},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["role"], "viewer")

        # staff 的旧令牌立刻按 viewer 权限执行
        borrow = self.client.post(
            "/borrows",
            headers=self.auth(self.staff_token),
            json={"material_id": self.material["id"]},
        )
        self.assertEqual(borrow.status_code, 403)

    def test_admin_cannot_change_own_role(self):
        response = self.client.patch(
            f"/users/{self.admin['id']}/role",
            headers=self.auth(self.admin_token),
            json={"role": "viewer"},
        )
        self.assertEqual(response.status_code, 409)

    def test_change_role_rejects_invalid_role(self):
        response = self.client.patch(
            f"/users/{self.viewer['id']}/role",
            headers=self.auth(self.admin_token),
            json={"role": "root"},
        )
        self.assertEqual(response.status_code, 422)


class ApiEdgeCaseTests(ApiTestCase):
    def test_huge_path_id_is_422_not_500(self):
        response = self.client.get(
            "/materials/99999999999999999999999999",
            headers=self.auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_huge_borrow_material_id_is_422(self):
        response = self.client.post(
            "/borrows",
            headers=self.auth(self.admin_token),
            json={"material_id": 99999999999999999999999999},
        )
        self.assertEqual(response.status_code, 422)

    def test_malformed_json_is_422(self):
        response = self.client.post(
            "/auth/login",
            content="{not json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_empty_patch_title_is_422(self):
        response = self.client.patch(
            f"/materials/{self.material['id']}",
            headers=self.auth(self.admin_token),
            json={"title": "   "},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_duplicate_username_is_409(self):
        response = self.client.post(
            "/users",
            headers=self.auth(self.admin_token),
            json={"username": "staff", "password": "secret123", "role": "viewer"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "conflict")

    def test_overdue_endpoint(self):
        # 直接往库里写一条已逾期的记录，构造测试数据
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO borrow_records (material_id, borrower_id, due_at) VALUES (?, ?, '2000-01-01 00:00:00')",
                (self.material["id"], self.staff["id"]),
            )
        finally:
            conn.close()

        response = self.client.get("/borrows/overdue", headers=self.auth(self.viewer_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
