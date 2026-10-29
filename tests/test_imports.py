"""资料批量导入测试：成功、部分失败、重复编号、权限。"""

from helpers import ApiTest


def row(code, title="导入资料"):
    return {
        "material_code": code,
        "title": title,
        "modality": "CT",
        "body_part": "胸部",
        "material_type": "胶片",
        "storage_location": "导入库 I-01",
    }


class MaterialImportTests(ApiTest):
    def test_admin_can_import_multiple_rows(self):
        response = self.client.post(
            "/materials/import",
            headers=self.auth(self.admin_token),
            json={"rows": [row("IMP-001"), row("IMP-002", "第二条")]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["success_count"], 2)
        self.assertEqual(body["failed_count"], 0)
        self.assertEqual(len(body["created"]), 2)

        materials = self.client.get("/materials", headers=self.auth(self.admin_token)).json()
        codes = {item["material_code"] for item in materials}
        self.assertIn("IMP-001", codes)
        self.assertIn("IMP-002", codes)

        logs = self.client.get("/logs", headers=self.auth(self.admin_token)).json()
        self.assertIn("批量导入资料", [item["action"] for item in logs["items"]])

    def test_partial_import_reports_each_bad_row(self):
        response = self.client.post(
            "/materials/import",
            headers=self.auth(self.admin_token),
            json={"rows": [
                row("IMP-010"),
                row(""),                      # 空编号
                row("IMP-010"),               # 同批次重复
                {**row("IMG-001"), "title": "与已有资料重复"},  # 数据库已有
            ]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["success_count"], 1)
        self.assertEqual(body["failed_count"], 3)
        messages = [item["message"] for item in body["errors"]]
        self.assertTrue(any("资料编号不能为空" in text for text in messages))
        self.assertTrue(any("资料编号已存在" in text for text in messages))

    def test_staff_cannot_import(self):
        response = self.client.post(
            "/materials/import",
            headers=self.auth(self.staff_token),
            json={"rows": [row("IMP-100")]},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "permission_denied")

    def test_empty_rows_is_422(self):
        response = self.client.post(
            "/materials/import",
            headers=self.auth(self.admin_token),
            json={"rows": []},
        )
        self.assertEqual(response.status_code, 422)

    def test_too_many_rows_is_422(self):
        response = self.client.post(
            "/materials/import",
            headers=self.auth(self.admin_token),
            json={"rows": [row(f"IMP-{index:03d}") for index in range(501)]},
        )
        self.assertEqual(response.status_code, 422)
