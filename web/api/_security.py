"""Request guards for the Jambox web UI.

The server binds 127.0.0.1, but any web page the user visits can still make
requests to it. These guards close the two practical holes:

* DNS rebinding: a hostile domain re-pointed at 127.0.0.1 can read responses.
  Every request must carry a loopback ``Host`` header (or one listed in
  ``WEB_ALLOWED_HOSTS``).
* CSRF: multipart and body-less POSTs are CORS "simple" requests, so a foreign
  page can fire them without a preflight. State-changing ``/api/*`` requests
  must carry ``X-Jambox-Client: 1`` (a custom header forces a preflight that
  this app never approves), and any ``Origin`` they send must be our own.
"""
from urllib.parse import urlsplit

from flask import Response, jsonify, request

DEFAULT_PORT = 5404
DEFAULT_MAX_CONTENT_LENGTH = 256 * 1024 * 1024
CLIENT_HEADER = "X-Jambox-Client"
CLIENT_HEADER_VALUE = "1"

_LOOPBACK_NAMES = ("localhost", "127.0.0.1", "[::1]")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _split_hosts(value):
    """Normalise WEB_ALLOWED_HOSTS (comma-separated string or list) to a list."""
    if not value:
        return []
    items = value.split(",") if isinstance(value, str) else list(value)
    return [str(item).strip().lower() for item in items if str(item).strip()]


def allowed_hosts(app):
    """Return the set of acceptable ``Host`` header values for *app*."""
    port = app.config.get("WEB_PORT") or DEFAULT_PORT
    hosts = set()
    for name in _LOOPBACK_NAMES:
        hosts.add(name)
        hosts.add(f"{name}:{port}")
    hosts.update(_split_hosts(app.config.get("WEB_ALLOWED_HOSTS")))
    return hosts


def _origin_allowed(origin, hosts):
    try:
        parts = urlsplit(origin.strip())
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        return False
    return parts.netloc.lower() in hosts


def _reject(status, message, is_api):
    if is_api:
        return jsonify({"ok": False, "error": message}), status
    return Response(message, status=status, mimetype="text/plain")


def install_guards(app):
    """Register the Host / CSRF / Origin guard and a request-size cap on *app*."""
    if not app.config.get("MAX_CONTENT_LENGTH"):
        app.config["MAX_CONTENT_LENGTH"] = DEFAULT_MAX_CONTENT_LENGTH

    @app.before_request
    def _jambox_request_guard():
        is_api = request.path.startswith("/api/") or request.path == "/api"
        hosts = allowed_hosts(app)

        host = (request.host or "").strip().lower()
        if host not in hosts:
            return _reject(400, "Host not allowed", is_api)

        if not is_api or request.method in _SAFE_METHODS:
            return None

        if request.headers.get(CLIENT_HEADER, "").strip() != CLIENT_HEADER_VALUE:
            return _reject(403, f"Missing {CLIENT_HEADER} header", True)

        origin = request.headers.get("Origin")
        if origin is not None and not _origin_allowed(origin, hosts):
            return _reject(403, "Origin not allowed", True)

        return None

    return app
