"""分页、统一错误格式、CORS 的回归测试。"""

import os
import unittest
from unittest.mock import patch

from helpers import ApiTest
from app.main import _cors_origins


def _material_payload(code, title):
    return {
        "material_code": code,
        "title": title,
        "modality": "CT",
        "body_part": "胸部",
        "material_type": "胶片",
        "storage_location": "一号库 A-01",
    }


class PaginationTests(ApiTest):
    def test_default_returns_all(self):
        response = self.client.get("/materials", headers=self.auth(self.viewer_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_material_pagination(self):
        for index in range(3):
            created = self.client.post(
                "/materials",
                headers=self.auth(self.admin_token),
                json=_material_payload(f"IMG-10{index}", f"测试资料 {index}"),
            )
            self.assertEqual(created.status_code, 201)

        first = self.client.get("/materials?limit=2", headers=self.auth(self.viewer_token)).json()
        second = self.client.get(
            "/materials?limit=2&offset=2", headers=self.auth(self.viewer_token)
        ).json()
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)
        self.assertNotEqual(first[0]["id"], second[0]["id"])
        # 不传分页参数时仍然是全量，保持旧行为
        self.assertEqual(len(self.client.get("/materials", headers=self.auth(self.viewer_token)).json()), 4)

    def test_users_pagination(self):
        first = self.client.get("/users?limit=2", headers=self.auth(self.admin_token)).json()
        second = self.client.get("/users?limit=2&offset=2", headers=self.auth(self.admin_token)).json()
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 1)
        self.assertEqual(len({row["id"] for row in first + second}), 3)

    def test_borrow_history_pagination(self):
        for _ in range(2):
            self.client.post(
                "/borrows",
                headers=self.auth(self.staff_token),
                json={"material_id": self.material["id"]},
            )
            self.client.post(
                f"/borrows/{self.material['id']}/return",
                headers=self.auth(self.staff_token),
            )

        first = self.client.get("/borrows/history?limit=1", headers=self.auth(self.viewer_token)).json()
        second = self.client.get(
            "/borrows/history?limit=1&offset=1", headers=self.auth(self.viewer_token)
        ).json()
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0]["id"], second[0]["id"])

    def test_invalid_pagination_params(self):
        for url in ("/materials?limit=0", "/materials?limit=501", "/materials?offset=-1"):
            response = self.client.get(url, headers=self.auth(self.viewer_token))
            self.assertEqual(response.status_code, 422, url)
            self.assertEqual(response.json()["code"], "validation_error")

    def test_offset_without_limit(self):
        for index in range(3):
            created = self.client.post(
                "/materials",
                headers=self.auth(self.admin_token),
                json=_material_payload(f"IMG-20{index}", f"offset 测试 {index}"),
            )
            self.assertEqual(created.status_code, 201)

        all_rows = self.client.get("/materials", headers=self.auth(self.viewer_token)).json()
        offset_rows = self.client.get(
            "/materials?offset=2", headers=self.auth(self.viewer_token)
        ).json()
        self.assertEqual([row["id"] for row in offset_rows], [row["id"] for row in all_rows[2:]])


class ErrorFormatTests(ApiTest):
    def test_unknown_route_uses_unified_format(self):
        response = self.client.get("/not-exist")
        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["code"], "not_found")
        self.assertIn("message", body)

    def test_method_not_allowed_uses_unified_format(self):
        response = self.client.post("/health")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], "method_not_allowed")


class CorsTests(ApiTest):
    def test_allowed_local_origin(self):
        response = self.client.get("/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5173")

    def test_unknown_origin_is_not_allowed(self):
        response = self.client.get("/health", headers={"Origin": "http://evil.example"})
        self.assertIsNone(response.headers.get("access-control-allow-origin"))

    def test_login_accepts_different_username_case(self):
        response = self.client.post(
            "/auth/login", json={"username": "ADMIN", "password": "admin123"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "admin")


class CorsConfigTests(unittest.TestCase):
    def test_default_origins_do_not_include_wildcard(self):
        self.assertNotIn("*", _cors_origins())

    def test_environment_override(self):
        with patch.dict(
            os.environ,
            {"YY_CORS_ORIGINS": "https://a.example, https://b.example"},
            clear=False,
        ):
            self.assertEqual(_cors_origins(), ["https://a.example", "https://b.example"])
