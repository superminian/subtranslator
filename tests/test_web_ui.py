import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web_ui


class WebUiTests(unittest.TestCase):
    def setUp(self):
        self.client = web_ui.app.test_client()
        web_ui.state.set_health_checker(None)

    def tearDown(self):
        web_ui.state.set_health_checker(None)

    def test_health_reflects_monitor_state(self):
        self.assertEqual(self.client.get("/health").status_code, 503)
        web_ui.state.set_health_checker(lambda: True)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_sensitive_api_requires_token_when_configured(self):
        with patch.object(web_ui, "ADMIN_TOKEN", "secret"):
            self.assertEqual(self.client.get("/api/logs").status_code, 401)
            response = self.client.get(
                "/api/logs",
                headers={"X-Admin-Token": "secret"},
            )
            self.assertEqual(response.status_code, 200)

    def test_configuration_write_requires_admin_token(self):
        with patch.object(web_ui, "ADMIN_TOKEN", ""):
            response = self.client.post("/api/config", json={})
            self.assertEqual(response.status_code, 503)

    def test_configuration_is_saved_and_secret_is_not_rendered(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "settings.json"
            environment = {
                "CONFIG_FILE": str(config_path),
                "API_KEY": "environment-key",
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch.object(web_ui, "ADMIN_TOKEN", "secret"),
            ):
                response = self.client.post(
                    "/api/config",
                    headers={"X-Admin-Token": "secret"},
                    json={"MODEL": "saved-model"},
                )
                self.assertEqual(response.status_code, 200)

                page = self.client.get("/")
                self.assertNotIn(b"secret", page.data)
                self.assertIn(b"static/dashboard.js", page.data)
                self.assertIn(b"static/style.css", page.data)

                dashboard_script = self.client.get("/static/dashboard.js")
                try:
                    self.assertEqual(dashboard_script.status_code, 200)
                    self.assertIn(b"escapeHtml", dashboard_script.data)
                finally:
                    dashboard_script.close()

    def test_dashboard_has_modern_accessible_controls(self):
        page = self.client.get("/")

        self.assertEqual(page.status_code, 200)
        self.assertIn(b'id="theme-toggle"', page.data)
        self.assertIn(b'role="dialog"', page.data)
        self.assertIn(b'aria-live="polite"', page.data)
        self.assertNotIn(b'class="glass"', page.data)

    def test_cors_is_not_open_by_default(self):
        response = self.client.get(
            "/api/stats",
            headers={"Origin": "https://attacker.example"},
        )
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)


if __name__ == "__main__":
    unittest.main()
