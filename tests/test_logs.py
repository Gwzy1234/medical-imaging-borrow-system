"""操作日志接口与 CSV 导出测试。"""

from datetime import datetime, timedelta, timezone

from helpers import ApiTest


def material_payload(code="LOG-001"):
    return {
        "material_code": code,
        "title": "日志测试资料",
        "modality": "CT",
        "body_part": "头部",
        "material_type": "胶片",
        "storage_location": "测试库 L-01",
    }


class OperationLogTests(ApiTest):
    def test_admin_actions_are_logged_and_exported(self):
        created = self.client.post(
            "/materials", headers=self.auth(self.admin_token), json=material_payload()
        )
        self.assertEqual(created.status_code, 201, created.text)
        material_id = created.json()["id"]

        borrowed = self.client.post(
            "/borrows", headers=self.auth(self.admin_token), json={"material_id": material_id}
        )
        self.assertEqual(borrowed.status_code, 200, borrowed.text)
        returned = self.client.post(
            f"/borrows/{material_id}/return", headers=self.auth(self.admin_token)
        )
        self.assertEqual(returned.status_code, 200, returned.text)

        response = self.client.get("/logs", headers=self.auth(self.admin_token))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body["total"], 4)
        actions = [item["action"] for item in body["items"]]
        for expected in ("登录", "新增资料", "借阅资料", "归还资料"):
            self.assertIn(expected, actions)
        self.assertTrue(any(item["username"] == "admin" for item in body["items"]))

        exported = self.client.get("/logs/export.csv", headers=self.auth(self.admin_token))
        self.assertEqual(exported.status_code, 200)
        self.assertIn("text/csv", exported.headers["content-type"])
        self.assertIn("attachment", exported.headers["content-disposition"])
        self.assertTrue(exported.content.startswith(b"\xef\xbb\xbf"))

        text = exported.content.decode("utf-8-sig")
        self.assertIn("时间(UTC)", text)
        self.assertIn("客户端IP", text)
        self.assertIn("新增资料", text)
        self.assertIn("LOG-001", text)

    def test_failed_login_is_logged_with_ip(self):
        failed = self.client.post(
            "/auth/login", json={"username": "admin", "password": "wrong-password"}
        )
        self.assertEqual(failed.status_code, 401)

        logs = self.client.get("/logs", headers=self.auth(self.admin_token)).json()
        failures = [item for item in logs["items"] if item["action"] == "登录失败"]
        self.assertTrue(failures)
        self.assertTrue(failures[0]["ip"])
        self.assertIn("admin", failures[0]["detail"])

    def test_staff_cannot_read_or_export_logs(self):
        for url in ("/logs", "/logs/export.csv"):
            response = self.client.get(url, headers=self.auth(self.staff_token))
            self.assertEqual(response.status_code, 403, url)
            self.assertEqual(response.json()["code"], "permission_denied")

    def test_log_filters_and_filtered_export(self):
        created = self.client.post(
            "/materials", headers=self.auth(self.admin_token), json=material_payload()
        )
        self.assertEqual(created.status_code, 201)

        by_action = self.client.get(
            "/logs?action=新增资料", headers=self.auth(self.admin_token)
        ).json()
        self.assertTrue(by_action["items"])
        self.assertTrue(all(item["action"] == "新增资料" for item in by_action["items"]))

        by_user = self.client.get(
            "/logs?username=staff", headers=self.auth(self.admin_token)
        ).json()
        self.assertTrue(by_user["items"])
        self.assertTrue(all(item["username"] == "staff" for item in by_user["items"]))

        day = by_action["items"][0]["created_at"][:10]
        by_date = self.client.get(
            f"/logs?start={day}&end={day}", headers=self.auth(self.admin_token)
        ).json()
        self.assertGreaterEqual(by_date["total"], len(by_action["items"]))

        exported = self.client.get(
            "/logs/export.csv?action=新增资料", headers=self.auth(self.admin_token)
        )
        self.assertEqual(exported.status_code, 200)
        text = exported.content.decode("utf-8-sig")
        self.assertIn("新增资料", text)
        self.assertIn("LOG-001", text)
        self.assertNotIn("登录失败", text)

    def test_archive_logs_exports_and_deletes(self):
        before = (
            datetime.now(timezone.utc) + timedelta(minutes=1)
        ).strftime("%Y-%m-%d %H:%M:%S")
        archived = self.client.post(
            "/logs/archive",
            headers=self.auth(self.admin_token),
            json={"before": before},
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        result = archived.json()
        self.assertGreaterEqual(result["archived_count"], 1)
        archive_path = self.tmp_dir / "backups" / result["file"]
        self.assertTrue(archive_path.exists())
        self.assertTrue(archive_path.read_bytes().startswith(b"\xef\xbb\xbf"))

        remaining = self.client.get("/logs", headers=self.auth(self.admin_token)).json()
        self.assertEqual(remaining["total"], 1)
        self.assertEqual(remaining["items"][0]["action"], "归档操作日志")

    def test_staff_cannot_archive_logs(self):
        response = self.client.post(
            "/logs/archive",
            headers=self.auth(self.staff_token),
            json={"before": "2026-01-01"},
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_log_date_is_422(self):
        response = self.client.get(
            "/logs?start=not-a-date", headers=self.auth(self.admin_token)
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_log_pagination(self):
        for index in range(3):
            created = self.client.post(
                "/materials",
                headers=self.auth(self.admin_token),
                json=material_payload(f"LOG-10{index}"),
            )
            self.assertEqual(created.status_code, 201)

        totals = self.client.get("/logs?limit=1", headers=self.auth(self.admin_token)).json()
        self.assertGreaterEqual(totals["total"], 3)
        self.assertEqual(len(totals["items"]), 1)

        first = self.client.get("/logs?limit=2&offset=0", headers=self.auth(self.admin_token)).json()
        second = self.client.get("/logs?limit=2&offset=2", headers=self.auth(self.admin_token)).json()
        self.assertEqual(len(first["items"]), 2)
        self.assertEqual(len(second["items"]), 2)
        self.assertNotEqual(
            [item["id"] for item in first["items"]],
            [item["id"] for item in second["items"]],
        )
