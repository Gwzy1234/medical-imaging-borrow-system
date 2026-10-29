"""会话存储按应用实例隔离的回归测试。"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db, users
from app.main import create_app


class SessionScopeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.clients = []
        self.tokens = {}

        for name in ("a", "b"):
            db_path = root / f"{name}.db"
            client = TestClient(create_app(db_path))
            client.__enter__()
            conn = db.connect(db_path)
            try:
                users.create_user(
                    conn, username="admin", password="admin123", role="admin"
                )
            finally:
                conn.close()
            self.clients.append(client)
            self.tokens[name] = client.post(
                "/auth/login", json={"username": "admin", "password": "admin123"}
            ).json()["token"]

    def tearDown(self):
        for client in self.clients:
            client.__exit__(None, None, None)
        self._tmp.cleanup()

    @staticmethod
    def auth(token):
        return {"Authorization": f"Bearer {token}"}

    def test_token_from_one_app_is_rejected_by_another(self):
        response = self.clients[1].get("/materials", headers=self.auth(self.tokens["a"]))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "authentication_error")

    def test_each_app_accepts_its_own_token(self):
        for index, name in enumerate(("a", "b")):
            response = self.clients[index].get(
                "/materials", headers=self.auth(self.tokens[name])
            )
            self.assertEqual(response.status_code, 200)
