"""数据库备份/恢复接口测试。"""

import sqlite3

from helpers import ApiTest


class BackupTests(ApiTest):
    def test_admin_can_download_database_backup(self):
        response = self.client.get("/backup/database", headers=self.auth(self.admin_token))
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/octet-stream", response.headers["content-type"])
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertTrue(response.content.startswith(b"SQLite format 3\x00"))

    def test_staff_cannot_backup_or_restore(self):
        download = self.client.get("/backup/database", headers=self.auth(self.staff_token))
        self.assertEqual(download.status_code, 403)
        restore = self.client.post(
            "/backup/restore",
            headers={**self.auth(self.staff_token), "Content-Type": "application/octet-stream"},
            content=b"SQLite format 3\x00",
        )
        self.assertEqual(restore.status_code, 403)

        empty = self.client.post(
            "/backup/restore",
            headers={**self.auth(self.staff_token), "Content-Type": "application/octet-stream"},
            content=b"",
        )
        self.assertEqual(empty.status_code, 403)

    def test_restore_roundtrip_and_forced_logout(self):
        backup = self.client.get("/backup/database", headers=self.auth(self.admin_token))
        self.assertEqual(backup.status_code, 200)

        created = self.client.post(
            "/materials",
            headers=self.auth(self.admin_token),
            json={
                "material_code": "RESTORE-NEW",
                "title": "恢复后应消失",
                "modality": "CT",
                "body_part": "头部",
                "material_type": "胶片",
                "storage_location": "恢复测试库",
            },
        )
        self.assertEqual(created.status_code, 201)

        restored = self.client.post(
            "/backup/restore",
            headers={**self.auth(self.admin_token), "Content-Type": "application/octet-stream"},
            content=backup.content,
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertTrue(restored.json()["safety_backup"].endswith(".db"))
        self.assertTrue((self.tmp_dir / "backups" / restored.json()["safety_backup"]).exists())

        # 恢复后旧令牌已被清空
        self.assertEqual(
            self.client.get("/materials", headers=self.auth(self.admin_token)).status_code, 401
        )

        fresh_token = self.login("admin", "admin123")
        materials = self.client.get("/materials", headers=self.auth(fresh_token)).json()
        codes = {item["material_code"] for item in materials}
        self.assertIn("IMG-001", codes)
        self.assertNotIn("RESTORE-NEW", codes)

    def test_invalid_backup_keeps_current_data(self):
        response = self.client.post(
            "/backup/restore",
            headers={**self.auth(self.admin_token), "Content-Type": "application/octet-stream"},
            content=b"this is not a sqlite database",
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

        materials = self.client.get("/materials", headers=self.auth(self.admin_token))
        self.assertEqual(materials.status_code, 200)
        self.assertEqual(len(materials.json()), 1)

    def test_empty_backup_is_422(self):
        response = self.client.post(
            "/backup/restore",
            headers={**self.auth(self.admin_token), "Content-Type": "application/octet-stream"},
            content=b"",
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_corrupted_sqlite_file_is_422(self):
        payload = b"SQLite format 3\x00" + b"corrupted-payload" * 50
        response = self.client.post(
            "/backup/restore",
            headers={**self.auth(self.admin_token), "Content-Type": "application/octet-stream"},
            content=payload,
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

        materials = self.client.get("/materials", headers=self.auth(self.admin_token))
        self.assertEqual(materials.status_code, 200)

    def test_backup_with_wrong_schema_is_422(self):
        path = self.tmp_dir / "wrong_schema.db"
        conn = sqlite3.connect(path)
        try:
            conn.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT,
                    role TEXT, is_active INTEGER
                );
                INSERT INTO users VALUES (1, 'admin', 'x', 'admin', 1);
                CREATE TABLE materials (id INTEGER PRIMARY KEY);
                CREATE TABLE borrow_records (
                    id INTEGER PRIMARY KEY, material_id INTEGER, borrower_id INTEGER
                );
                CREATE TABLE operation_logs (id INTEGER PRIMARY KEY);
                """
            )
            conn.commit()
        finally:
            conn.close()

        response = self.client.post(
            "/backup/restore",
            headers={**self.auth(self.admin_token), "Content-Type": "application/octet-stream"},
            content=path.read_bytes(),
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["code"], "validation_error")

        # 现有数据库没有被替换
        materials = self.client.get("/materials", headers=self.auth(self.admin_token))
        self.assertEqual(materials.status_code, 200)
        self.assertEqual(len(materials.json()), 1)

    def test_restore_clears_login_throttle(self):
        backup = self.client.get("/backup/database", headers=self.auth(self.admin_token))
        self.assertEqual(backup.status_code, 200)

        for _ in range(5):
            failed = self.client.post(
                "/auth/login", json={"username": "admin", "password": "wrong-password"}
            )
            self.assertEqual(failed.status_code, 401)

        restored = self.client.post(
            "/backup/restore",
            headers={**self.auth(self.admin_token), "Content-Type": "application/octet-stream"},
            content=backup.content,
        )
        self.assertEqual(restored.status_code, 200, restored.text)

        # 恢复后限流已清空，可以立即用正确密码登录
        login = self.client.post(
            "/auth/login", json={"username": "admin", "password": "admin123"}
        )
        self.assertEqual(login.status_code, 200, login.text)

    def test_old_backup_without_operation_logs_is_upgraded(self):
        backup = self.client.get("/backup/database", headers=self.auth(self.admin_token))
        path = self.tmp_dir / "old_backup.db"
        path.write_bytes(backup.content)
        conn = sqlite3.connect(path)
        try:
            conn.execute("DROP TABLE operation_logs")
            conn.commit()
        finally:
            conn.close()

        restored = self.client.post(
            "/backup/restore",
            headers={**self.auth(self.admin_token), "Content-Type": "application/octet-stream"},
            content=path.read_bytes(),
        )
        self.assertEqual(restored.status_code, 200, restored.text)

        fresh_token = self.login("admin", "admin123")
        logs = self.client.get("/logs", headers=self.auth(fresh_token))
        self.assertEqual(logs.status_code, 200)
        self.assertGreaterEqual(logs.json()["total"], 1)

    def test_requests_blocked_while_restoring(self):
        self.client.app.state.restoring = True
        try:
            blocked = self.client.get("/materials", headers=self.auth(self.admin_token))
            self.assertEqual(blocked.status_code, 503)
            self.assertEqual(blocked.json()["code"], "database_busy")
            self.assertEqual(self.client.get("/health").status_code, 200)
        finally:
            self.client.app.state.restoring = False

        self.assertEqual(
            self.client.get("/materials", headers=self.auth(self.admin_token)).status_code, 200
        )
