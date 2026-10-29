"""事务回滚与数据库连接生命周期测试。"""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from helpers import DatabaseTest
from app import borrowing, db, users
from app.errors import ConflictError
from app.main import create_app


class TransactionRollbackTests(DatabaseTest):
    def test_borrow_rolls_back_when_insert_fails(self):
        """第 2 步（写借阅记录）失败时，第 1 步的状态修改必须回滚。"""
        with patch.object(db, "execute", side_effect=[1, sqlite3.IntegrityError("boom")]):
            with self.assertRaises(ConflictError):
                borrowing.borrow_material(
                    self.conn, material_id=self.material["id"], actor=self.staff
                )

        self.assertEqual(self.material_status(), "available")
        self.assertEqual(db.query_all(self.conn, "list_borrow_history"), [])

    def test_return_rolls_back_when_status_update_fails(self):
        """第 3 步（恢复资料状态）失败时，归还时间也必须撤回。"""
        record = borrowing.borrow_material(
            self.conn, material_id=self.material["id"], actor=self.staff
        )

        with patch.object(db, "execute", side_effect=[1, RuntimeError("boom")]):
            with self.assertRaises(RuntimeError):
                borrowing.return_material(
                    self.conn, material_id=self.material["id"], actor=self.staff
                )

        self.assertEqual(self.material_status(), "borrowed")
        active = db.query_one(
            self.conn, "get_active_borrow_by_material", (self.material["id"],)
        )
        self.assertEqual(active["id"], record["id"])


class ConnectionLifecycleTests(unittest.TestCase):
    def test_connections_closed_after_requests(self):
        """请求结束后连接必须全部关闭：Windows 上还能删除数据库文件即为证据。"""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leak.db"
            with TestClient(create_app(db_path)) as client:
                conn = db.connect(db_path)
                try:
                    users.create_user(
                        conn, username="admin", password="admin123", role="admin"
                    )
                finally:
                    conn.close()

                token = client.post(
                    "/auth/login", json={"username": "admin", "password": "admin123"}
                ).json()["token"]
                headers = {"Authorization": f"Bearer {token}"}
                for _ in range(10):
                    response = client.get("/materials", headers=headers)
                    self.assertEqual(response.status_code, 200)

            # 如果还有未关闭的连接，Windows 会抛 PermissionError
            os.remove(db_path)
