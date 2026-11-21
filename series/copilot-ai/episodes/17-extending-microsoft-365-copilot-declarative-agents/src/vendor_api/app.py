"""WSGI application and a tiny server for the Vendor Renewals API. Standard library only."""
from __future__ import annotations

import hmac
import json
import re
from datetime import date
from typing import Callable
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIRequestHandler, make_server

from .register import Register, RegisterError

MAX_BODY = 16 * 1024
_VENDOR = re.compile(r"^/vendors/([A-Za-z0-9_-]+)$")
_REMINDERS = re.compile(r"^/vendors/([A-Za-z0-9_-]+)/reminders$")


def create_app(api_key: str, register: Register | None = None, today: Callable[[], date] = date.today):
    """Return a WSGI app. `api_key` is required: the API never runs unauthenticated."""
    if not api_key:
        raise ValueError("api_key must not be empty")
    reg = register or Register.load()

    def respond(start_response, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        phrase = {200: "OK", 201: "Created", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found",
                  405: "Method Not Allowed"}[status]
        start_response(f"{status} {phrase}", [("Content-Type", "application/json; charset=utf-8"),
                                             ("Content-Length", str(len(body)))])
        return [body]

    def app(environ, start_response):
        method, path = environ["REQUEST_METHOD"], environ.get("PATH_INFO", "/")
        auth = environ.get("HTTP_AUTHORIZATION", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(token.encode(), api_key.encode()):
            return respond(start_response, 401, {"error": {"code": "unauthorized", "message": "Missing or invalid bearer token."}})
        try:
            day = today()
            if path == "/renewals":
                if method != "GET":
                    return respond(start_response, 405, {"error": {"code": "method_not_allowed", "message": "Use GET."}})
                q = parse_qs(environ.get("QUERY_STRING", ""))
                within = q.get("withinDays", [None])[0]
                try:
                    within_days = int(within) if within is not None else None
                except ValueError:
                    raise RegisterError(400, "invalid_request", "withinDays must be a whole number from 1 to 730.") from None
                rows = reg.list_renewals(day, within_days, q.get("owner", [None])[0])
                return respond(start_response, 200, {"today": day.isoformat(), "renewals": rows})
            m = _REMINDERS.match(path)
            if m:
                if method != "POST":
                    return respond(start_response, 405, {"error": {"code": "method_not_allowed", "message": "Use POST."}})
                length = int(environ.get("CONTENT_LENGTH") or 0)
                if length > MAX_BODY:
                    raise RegisterError(400, "invalid_request", "The body is too large.")
                raw = environ["wsgi.input"].read(length) if length else b""
                try:
                    body = json.loads(raw or b"null")
                except ValueError:
                    raise RegisterError(400, "invalid_request", "The body is not valid JSON.") from None
                return respond(start_response, 201, reg.create_reminder(m.group(1), body, day))
            m = _VENDOR.match(path)
            if m:
                if method != "GET":
                    return respond(start_response, 405, {"error": {"code": "method_not_allowed", "message": "Use GET."}})
                return respond(start_response, 200, reg.get_vendor(m.group(1), day))
            raise RegisterError(404, "not_found", "No such route.")
        except RegisterError as e:
            return respond(start_response, e.status, {"error": {"code": e.code, "message": e.message}})

    return app


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - keep the console readable; no client data in logs
        pass


def serve(api_key: str, host: str = "127.0.0.1", port: int = 8080, today: Callable[[], date] = date.today):
    """Create the server (not started). Call `.serve_forever()` on the result."""
    return make_server(host, port, create_app(api_key, today=today), handler_class=_QuietHandler)
