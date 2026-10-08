"""Phase 7.1 backend tests: root endpoint + health endpoint.

Run from the project root:
    python -m unittest discover -s backend/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the project root importable regardless of how the tests are launched.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


class RootEndpointTests(unittest.TestCase):
    """GET / must return API information."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_root_status_200(self) -> None:
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_root_body(self) -> None:
        body = self.client.get("/").json()
        self.assertEqual(body["service"], "PAIMANA AI Backend")
        self.assertIn("version", body)
        self.assertIn("description", body)
        self.assertIsInstance(body["endpoints"], list)
        self.assertIn("/health", body["endpoints"])

    def test_root_content_type_json(self) -> None:
        resp = self.client.get("/")
        self.assertTrue(resp.headers["content-type"].startswith("application/json"))


class HealthEndpointTests(unittest.TestCase):
    """GET /health must report ok."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health_status_200(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_health_body(self) -> None:
        body = self.client.get("/health").json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "PAIMANA AI Backend")
        self.assertIn("version", body)


class CorsAndConfigTests(unittest.TestCase):
    """CORS must be restricted to the React dev origins (not unrestricted)."""

    def test_cors_origins_restricted(self) -> None:
        from backend.app.config import get_settings
        origins = get_settings().cors_origins
        self.assertIn("http://localhost:5173", origins)
        self.assertNotIn("*", origins)

    def test_cors_preflight_from_react_origin(self) -> None:
        resp = self.client_options()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"),
                         "http://localhost:5173")

    def client_options(self):
        return TestClient(app).options(
            "/health",
            headers={"Origin": "http://localhost:5173",
                     "Access-Control-Request-Method": "GET"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
