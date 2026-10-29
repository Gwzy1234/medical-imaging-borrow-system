"""前端静态资源与后端集成的回归测试。"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app


class FrontendServingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Path(self._tmp.name) / "frontend.db"))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self._tmp.cleanup()

    def test_index_page_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("医学影像资料借阅管理系统", response.text)
        self.assertIn("/js/app.js", response.text)

    def test_static_assets_served_with_correct_types(self):
        css = self.client.get("/css/style.css")
        self.assertEqual(css.status_code, 200)
        self.assertIn("text/css", css.headers["content-type"])

        app_js = self.client.get("/js/app.js")
        self.assertEqual(app_js.status_code, 200)
        self.assertIn("javascript", app_js.headers["content-type"])

        api_js = self.client.get("/js/api.js")
        self.assertEqual(api_js.status_code, 200)
        self.assertIn("javascript", api_js.headers["content-type"])

    def test_api_routes_not_shadowed_by_static_mount(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/docs").status_code, 200)

        unauthorized = self.client.get("/materials")
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized.json()["code"], "authentication_error")

    def test_unknown_path_returns_404(self):
        response = self.client.get("/no-such-page")
        self.assertEqual(response.status_code, 404)

    def test_health_reports_app_version(self):
        body = self.client.get("/health").json()
        self.assertEqual(body["version"], __version__)

    def test_frontend_assets_are_not_cached(self):
        response = self.client.get("/js/app.js")
        self.assertIn("no-cache", response.headers.get("cache-control", ""))
        self.assertEqual(response.headers.get("x-app-version"), __version__)
