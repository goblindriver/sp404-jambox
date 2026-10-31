import os
import sys
import unittest

from flask import Flask, jsonify, request


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(REPO_ROOT, "web")
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from api._security import DEFAULT_MAX_CONTENT_LENGTH, install_guards


CLIENT = {"X-Jambox-Client": "1"}


def _build_app(**config):
    app = Flask(__name__)
    app.config.update(config)

    @app.route("/api/thing", methods=["GET", "POST"])
    def thing():
        body = request.get_data()
        return jsonify({"ok": True, "method": request.method, "bytes": len(body)})

    @app.route("/page")
    def page():
        return "page"

    install_guards(app)
    return app


class RequestGuardTests(unittest.TestCase):
    def setUp(self):
        self.app = _build_app()
        self.client = self.app.test_client()

    # ── CSRF header / Origin ──

    def test_cross_origin_post_is_rejected(self):
        resp = self.client.post(
            "/api/thing",
            headers={**CLIENT, "Origin": "https://evil.example"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["ok"], False)

    def test_post_without_client_header_is_rejected(self):
        resp = self.client.post("/api/thing", data={"a": "b"})
        self.assertEqual(resp.status_code, 403)
        payload = resp.get_json()
        self.assertFalse(payload["ok"])
        self.assertIn("X-Jambox-Client", payload["error"])

    def test_post_with_wrong_client_header_value_is_rejected(self):
        resp = self.client.post("/api/thing", headers={"X-Jambox-Client": "yes"})
        self.assertEqual(resp.status_code, 403)

    def test_post_with_header_and_no_origin_is_allowed(self):
        resp = self.client.post("/api/thing", headers=CLIENT, json={"x": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])

    def test_post_with_header_and_same_origin_is_allowed(self):
        resp = self.client.post(
            "/api/thing",
            headers={**CLIENT, "Origin": "http://localhost:5404"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_post_with_header_and_null_origin_is_rejected(self):
        resp = self.client.post("/api/thing", headers={**CLIENT, "Origin": "null"})
        self.assertEqual(resp.status_code, 403)

    def test_post_with_lookalike_origin_is_rejected(self):
        for origin in (
            "http://localhost:5404.evil.example",
            "http://localhost.evil.example:5404",
            "file://localhost:5404",
        ):
            with self.subTest(origin=origin):
                resp = self.client.post("/api/thing", headers={**CLIENT, "Origin": origin})
                self.assertEqual(resp.status_code, 403)

    def test_get_without_client_header_is_allowed(self):
        resp = self.client.get("/api/thing")
        self.assertEqual(resp.status_code, 200)

    def test_non_api_page_is_served_on_loopback_host(self):
        resp = self.client.get("/page")
        self.assertEqual(resp.status_code, 200)

    # ── Host allowlist ──

    def test_bad_host_header_is_rejected_for_api(self):
        resp = self.client.get("/api/thing", headers={"Host": "evil.example:5404"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json(), {"ok": False, "error": "Host not allowed"})

    def test_bad_host_via_base_url_is_rejected(self):
        resp = self.client.post(
            "/api/thing", base_url="http://evil.example:5404", headers=CLIENT,
        )
        self.assertEqual(resp.status_code, 400)

    def test_bad_host_on_page_returns_plain_400(self):
        resp = self.client.get("/page", headers={"Host": "rebind.evil.example"})
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(resp.get_json(silent=True))

    def test_loopback_hosts_are_allowed(self):
        for host in ("localhost", "localhost:5404", "127.0.0.1:5404", "[::1]:5404"):
            with self.subTest(host=host):
                resp = self.client.get("/api/thing", headers={"Host": host})
                self.assertEqual(resp.status_code, 200)

    def test_wrong_port_is_rejected(self):
        resp = self.client.get("/api/thing", headers={"Host": "localhost:8080"})
        self.assertEqual(resp.status_code, 400)

    def test_extra_allowed_hosts_from_config(self):
        for extra in ("jambox.local:5404, other.test", ["jambox.local:5404", "other.test"]):
            with self.subTest(extra=extra):
                app = _build_app(WEB_ALLOWED_HOSTS=extra)
                client = app.test_client()
                resp = client.post(
                    "/api/thing",
                    headers={**CLIENT, "Host": "jambox.local:5404",
                             "Origin": "http://jambox.local:5404"},
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(
                    client.get("/api/thing", headers={"Host": "other.test"}).status_code, 200,
                )

    # ── Body size ──

    def test_default_max_content_length_is_set(self):
        self.assertEqual(self.app.config["MAX_CONTENT_LENGTH"], DEFAULT_MAX_CONTENT_LENGTH)

    def test_existing_max_content_length_is_kept(self):
        app = _build_app(MAX_CONTENT_LENGTH=1024)
        self.assertEqual(app.config["MAX_CONTENT_LENGTH"], 1024)

    def test_oversize_body_is_rejected(self):
        app = _build_app(MAX_CONTENT_LENGTH=1024)
        client = app.test_client()
        resp = client.post(
            "/api/thing",
            headers={**CLIENT, "Content-Type": "application/octet-stream"},
            data=b"x" * 4096,
        )
        self.assertEqual(resp.status_code, 413)


if __name__ == "__main__":
    unittest.main()
