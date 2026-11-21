"""tools/claims.py: decodes for display, never prints the token, and reads a managed identity token from IMDS."""
import base64
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

import claims
from conftest import EP


def jwt(payload: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'RS256', 'typ': 'JWT'})}.{enc(payload)}.c2lnbmF0dXJl"


APP = {"aud": "00000000-0000-0000-0000-000000000001", "idtyp": "app", "roles": ["Orders.ReadWrite.All"],
       "azp": "00000000-0000-0000-0000-000000000002", "ver": "2.0", "nbf": 1, "uti": "drop-me"}
USER = {"aud": "00000000-0000-0000-0000-000000000001", "scp": "Orders.Read", "roles": ["Orders.Reader"],
        "name": "Alex Demo", "ver": "2.0"}


def test_summary_keeps_authorization_claims_only():
    s = claims.summary(claims.payload(jwt(APP)))
    assert s["kind"] == "app-only" and s["roles"] == ["Orders.ReadWrite.All"]
    assert "uti" not in s and "nbf" not in s


def test_user_token_with_roles_is_still_delegated():
    s = claims.summary(claims.payload(jwt(USER)))
    assert s["kind"] == "delegated (user)" and "name" not in s


def test_not_a_jwt():
    with pytest.raises(ValueError):
        claims.payload("abc")


def test_cli_reads_stdin_and_does_not_echo_the_token():
    token = jwt(USER)
    p = subprocess.run([sys.executable, str(EP / "tools" / "claims.py")], input=token, capture_output=True, text=True)
    assert p.returncode == 0 and '"scp": "Orders.Read"' in p.stdout
    assert token not in p.stdout and token.split(".")[1] not in p.stdout


class FakeImds(BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):
        FakeImds.seen.append((urlparse(self.path), self.headers.get("Metadata")))
        body = json.dumps({"access_token": jwt(APP), "token_type": "Bearer"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_imds_mode_against_a_fake_endpoint():
    srv = HTTPServer(("127.0.0.1", 0), FakeImds)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        env = {"IMDS_ENDPOINT": f"http://127.0.0.1:{srv.server_port}", "PATH": "/usr/bin:/bin"}
        p = subprocess.run([sys.executable, str(EP / "tools" / "claims.py"), "--imds",
                            "api://00000000-0000-0000-0000-000000000000/contoso-orders",
                            "00000000-0000-0000-0000-00000000000c"], env=env, capture_output=True, text=True)
    finally:
        srv.shutdown()
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["kind"] == "app-only"
    url, metadata = FakeImds.seen[-1]
    q = parse_qs(url.query)
    assert url.path == "/metadata/identity/oauth2/token" and metadata == "true"
    assert q["resource"] == ["api://00000000-0000-0000-0000-000000000000/contoso-orders"]
    assert q["client_id"] == ["00000000-0000-0000-0000-00000000000c"] and q["api-version"] == ["2018-02-01"]
