"""权限与登录测试：角色边界、停用、密码哈希、首个管理员规则。"""

import tempfile
import unittest
from pathlib import Path

from helpers import DatabaseTest
from app import auth, borrowing, db, materials, users
from app.errors import (
    AuthenticationError,
    ConflictError,
    PermissionDenied,
    ValidationError,
)


class PermissionTests(DatabaseTest):
    def test_viewer_cannot_borrow(self):
        with self.assertRaises(PermissionDenied):
            borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.viewer)

    def test_viewer_can_read_materials_and_history(self):
        self.assertEqual(len(materials.list_materials(self.conn, self.viewer)), 1)
        self.assertEqual(borrowing.list_borrow_history(self.conn, self.viewer), [])

    def test_viewer_cannot_create_material(self):
        with self.assertRaises(PermissionDenied):
            materials.create_material(
                self.conn, material_code="IMG-999", title="x", modality="CT",
                body_part="头部", material_type="胶片", storage_location="A-01",
                actor=self.viewer,
            )

    def test_staff_cannot_manage_users_or_materials(self):
        with self.assertRaises(PermissionDenied):
            users.list_users(self.conn, self.staff)
        with self.assertRaises(PermissionDenied):
            users.create_user(
                self.conn, username="x", password="secret123", role="viewer", actor=self.staff
            )
        with self.assertRaises(PermissionDenied):
            materials.disable_material(self.conn, self.material["id"], self.staff)

    def test_admin_can_list_users_without_password_hash(self):
        listed = users.list_users(self.conn, self.admin)
        self.assertEqual({row["username"] for row in listed}, {"admin", "staff", "viewer"})
        self.assertTrue(all("password_hash" not in row for row in listed))

    def test_user_can_only_read_own_profile(self):
        self.assertEqual(users.get_user(self.conn, self.viewer["id"], self.viewer)["username"], "viewer")
        with self.assertRaises(PermissionDenied):
            users.get_user(self.conn, self.staff["id"], self.viewer)

    def test_admin_cannot_disable_self(self):
        with self.assertRaises(ConflictError):
            users.disable_user(self.conn, self.admin["id"], self.admin)

    def test_login_and_logout(self):
        session = auth.login(self.conn, "staff", "staff123")
        self.assertEqual(auth.current_user(self.conn, session["token"])["username"], "staff")
        auth.logout(session["token"])
        with self.assertRaises(AuthenticationError):
            auth.current_user(self.conn, session["token"])

    def test_wrong_password_and_unknown_user_share_same_error(self):
        with self.assertRaises(AuthenticationError):
            auth.login(self.conn, "staff", "wrong-password")
        with self.assertRaises(AuthenticationError):
            auth.login(self.conn, "nobody", "whatever123")

    def test_disabled_user_cannot_login(self):
        users.disable_user(self.conn, self.staff["id"], self.admin)
        with self.assertRaises(AuthenticationError):
            auth.login(self.conn, "staff", "staff123")

    def test_double_disable_is_rejected(self):
        users.disable_user(self.conn, self.staff["id"], self.admin)
        with self.assertRaises(ConflictError):
            users.disable_user(self.conn, self.staff["id"], self.admin)

    def test_password_stored_as_hash(self):
        row = self.conn.execute(
            "SELECT password_hash FROM users WHERE username = 'admin'"
        ).fetchone()
        self.assertNotEqual(row["password_hash"], "admin123")
        self.assertTrue(row["password_hash"].startswith("pbkdf2_sha256$"))


class ValidationTests(DatabaseTest):
    def test_duplicate_username(self):
        with self.assertRaises(ConflictError):
            users.create_user(self.conn, username="staff", password="secret123", role="viewer", actor=self.admin)

    def test_invalid_role(self):
        with self.assertRaises(ValidationError):
            users.create_user(self.conn, username="x", password="secret123", role="owner", actor=self.admin)

    def test_short_password(self):
        with self.assertRaises(ValidationError):
            users.create_user(self.conn, username="x", password="123", role="viewer", actor=self.admin)

    def test_blank_material_field(self):
        with self.assertRaises(ValidationError):
            materials.create_material(
                self.conn, material_code="  ", title="x", modality="CT",
                body_part="头部", material_type="胶片", storage_location="A-01",
                actor=self.admin,
            )

    def test_duplicate_material_code(self):
        with self.assertRaises(ConflictError):
            materials.create_material(
                self.conn, material_code="IMG-001", title="重复编号", modality="CT",
                body_part="头部", material_type="胶片", storage_location="A-01",
                actor=self.admin,
            )

    def test_update_material_only_changes_given_fields(self):
        updated = materials.update_material(
            self.conn, self.material["id"], title="胸部 CT 增强", actor=self.admin
        )
        self.assertEqual(updated["title"], "胸部 CT 增强")
        self.assertEqual(updated["modality"], "CT")
        self.assertEqual(updated["storage_location"], "一号库 A-01")

    def test_disable_material_only_when_available(self):
        borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.staff)
        with self.assertRaises(ConflictError):
            materials.disable_material(self.conn, self.material["id"], self.admin)

    def test_enable_material_restores_available(self):
        materials.disable_material(self.conn, self.material["id"], self.admin)
        restored = materials.enable_material(self.conn, self.material["id"], self.admin)
        self.assertEqual(restored["status"], "available")

    def test_enable_available_material_is_conflict(self):
        with self.assertRaises(ConflictError):
            materials.enable_material(self.conn, self.material["id"], self.admin)

    def test_staff_cannot_enable_material(self):
        materials.disable_material(self.conn, self.material["id"], self.admin)
        with self.assertRaises(PermissionDenied):
            materials.enable_material(self.conn, self.material["id"], self.staff)

    def test_admin_can_delete_material_without_records(self):
        material_id = self.material["id"]
        materials.delete_material(self.conn, material_id, self.admin)
        self.assertIsNone(db.query_one(self.conn, "get_material_by_id", (material_id,)))

    def test_cannot_delete_material_with_borrow_history(self):
        borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.staff)
        with self.assertRaises(ConflictError):
            materials.delete_material(self.conn, self.material["id"], self.admin)
        self.assertIsNotNone(db.query_one(self.conn, "get_material_by_id", (self.material["id"],)))

    def test_force_delete_material_with_history(self):
        borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.staff)
        result = materials.delete_material(self.conn, self.material["id"], self.admin, force=True)
        self.assertEqual(result["deleted_records"], 1)
        self.assertIsNone(db.query_one(self.conn, "get_material_by_id", (self.material["id"],)))
        self.assertEqual(
            db.query_all(self.conn, "list_borrow_history"),
            [],
        )

    def test_staff_cannot_delete_material(self):
        with self.assertRaises(PermissionDenied):
            materials.delete_material(self.conn, self.material["id"], self.staff)


class BootstrapTests(unittest.TestCase):
    """空库上的首次初始化规则。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self._tmp.name) / "fresh.db")
        db.init_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_first_user_must_be_admin(self):
        with self.assertRaises(ValidationError):
            users.create_user(self.conn, username="first", password="secret123", role="staff")

    def test_second_user_requires_actor(self):
        users.create_user(self.conn, username="root", password="secret123", role="admin")
        with self.assertRaises(PermissionDenied):
            users.create_user(self.conn, username="other", password="secret123", role="viewer")
