"""测试公共基类：每个测试用例使用独立的临时数据库。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, materials, users  # noqa: E402
from app.main import create_app  # noqa: E402


class DatabaseTest(unittest.TestCase):
    """建好表，并准备 admin / staff / viewer 和一份资料。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.db_path = self.tmp_dir / "test.db"
        self.conn = db.connect(self.db_path)
        db.init_schema(self.conn)

        self.admin = users.create_user(self.conn, username="admin", password="admin123", role="admin")
        self.staff = users.create_user(self.conn, username="staff", password="staff123", role="staff", actor=self.admin)
        self.viewer = users.create_user(self.conn, username="viewer", password="viewer123", role="viewer", actor=self.admin)

        self.material = materials.create_material(
            self.conn,
            material_code="IMG-001",
            title="胸部 CT 平扫",
            modality="CT",
            body_part="胸部",
            material_type="胶片",
            storage_location="一号库 A-01",
            actor=self.admin,
        )

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def material_status(self, material_id=None):
        material_id = self.material["id"] if material_id is None else material_id
        row = db.query_one(self.conn, "get_material_by_id", (material_id,))
        return row["status"]

    def insert_raw_record(self, due_at, material_id=None):
        """绕过服务层直接插一条借阅记录，用于构造特殊数据。"""
        material_id = self.material["id"] if material_id is None else material_id
        cursor = self.conn.execute(
            "INSERT INTO borrow_records (material_id, borrower_id, due_at) VALUES (?, ?, ?)",
            (material_id, self.staff["id"], due_at),
        )
        return cursor.lastrowid


class ApiTest(DatabaseTest):
    """在数据库基类之上再启动一个独立的 FastAPI 应用。"""

    def setUp(self):
        super().setUp()
        self.client = TestClient(create_app(self.db_path, backup_dir=self.tmp_dir / "backups"))
        self.client.__enter__()
        self.admin_token = self.login("admin", "admin123")
        self.staff_token = self.login("staff", "staff123")
        self.viewer_token = self.login("viewer", "viewer123")

    def tearDown(self):
        self.client.__exit__(None, None, None)
        super().tearDown()

    def login(self, username, password):
        response = self.client.post(
            "/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["token"]

    @staticmethod
    def auth(token):
        return {"Authorization": f"Bearer {token}"}
