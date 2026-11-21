"""The tenant scripts, run here against a fake `az`, a fake API and a fake IMDS endpoint."""
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from conftest import EP
from test_claims_tool import APP, USER, FakeImds, jwt

INFRA = EP / "infra"
FAKES = EP / "tests" / "python" / "fakes"
OUTPUTS = {
    "tenantId": "00000000-0000-0000-0000-000000000000",
    "apiClientId": "00000000-0000-0000-0000-000000000001",
    "apiAppIdUri": "api://00000000-0000-0000-0000-000000000000/contoso-orders",
    "readScope": "api://00000000-0000-0000-0000-000000000000/contoso-orders/Orders.Read",
    "processorClientId": "00000000-0000-0000-0000-00000000000c",
    "processorPrincipalId": "00000000-0000-0000-0000-0000000000b2",
    "processorResourceId": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/"
                           "Microsoft.ManagedIdentity/userAssignedIdentities/id-contoso-order-processor",
}


@pytest.fixture
def env(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "outputs.json").write_text(json.dumps(OUTPUTS))
    token = tmp_path / "token"
    token.write_text(jwt(USER))
    return dict(os.environ, PATH=f"{FAKES}:{os.environ['PATH']}", OUT=str(out), FAKE_LOG=str(tmp_path / "az.log"),
                FAKE_TOKEN_FILE=str(token))


class FakeApi(BaseHTTPRequestHandler):
    def _reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        ok = self.headers.get("Authorization", "").startswith("Bearer ")
        self._reply(200 if ok else 401, [] if self.path == "/orders" else {"kind": "delegated"})

    def do_POST(self):
        self._reply(403, {})

    def log_message(self, *a):
        pass


def serve(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_call_as_user_shows_claims_and_codes_but_not_the_token(env):
    srv = serve(FakeApi)
    try:
        p = subprocess.run(["bash", str(INFRA / "call-as-user.sh"), f"http://127.0.0.1:{srv.server_port}"],
                           env=env, capture_output=True, text=True)
    finally:
        srv.shutdown()
    assert p.returncode == 0, p.stderr
    assert "== GET /orders -> 200" in p.stdout and "== POST /orders -> 403" in p.stdout
    assert '"kind": "delegated (user)"' in p.stdout
    token = open(env["FAKE_TOKEN_FILE"]).read()
    assert token not in p.stdout
    log = open(env["FAKE_LOG"]).read()
    assert f"--scope {OUTPUTS['readScope']}" in log


def test_preauthorize_merges_into_the_existing_api_block(env, tmp_path):
    api = {"requestedAccessTokenVersion": 2, "oauth2PermissionScopes": [
        {"id": "00000000-0000-0000-0000-00000000e001", "value": "Orders.Read", "type": "User"}],
        "preAuthorizedApplications": [{"appId": "00000000-0000-0000-0000-00000000f001",
                                       "delegatedPermissionIds": ["00000000-0000-0000-0000-00000000e001"]}]}
    (tmp_path / "api.json").write_text(json.dumps(api))
    env["FAKE_API_JSON"] = str(tmp_path / "api.json")
    p = subprocess.run(["bash", str(INFRA / "lab-preauthorize-cli.sh")], env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    log = open(env["FAKE_LOG"]).read()
    assert "rest --method PATCH --uri https://graph.microsoft.com/v1.0/applications/00000000-0000-0000-0000-0000000000d1" in log
    body = json.loads(open(env["FAKE_LOG"] + ".body").read())["api"]
    assert body["requestedAccessTokenVersion"] == 2 and body["oauth2PermissionScopes"] == api["oauth2PermissionScopes"]
    assert {"appId": "04b07795-8ddb-461a-bbee-02f9e1bf7b46",
            "delegatedPermissionIds": ["00000000-0000-0000-0000-00000000e001"]} in body["preAuthorizedApplications"]
    assert len(body["preAuthorizedApplications"]) == 2          # the other client is kept


def test_aci_command_line_runs_claims_py_from_base64(tmp_path):
    """Run the exact --command-line from prove-app-token.sh, split the way the Azure CLI splits it."""
    script = (INFRA / "prove-app-token.sh").read_text()
    raw = re.search(r'--command-line "(.*)" \\\n', script).group(1).replace('\\"', '"')
    argv = shlex.split(raw)
    assert argv[:2] == ["python3", "-c"]
    srv = serve(FakeImds)
    try:
        env = {"PATH": os.environ["PATH"], "IMDS_ENDPOINT": f"http://127.0.0.1:{srv.server_port}",
               "CODE": base64.b64encode((EP / "tools" / "claims.py").read_bytes()).decode(),
               "RES": OUTPUTS["apiAppIdUri"], "CID": OUTPUTS["processorClientId"]}
        p = subprocess.run([sys.executable, *argv[1:]], env=env, capture_output=True, text=True)
    finally:
        srv.shutdown()
    assert p.returncode == 0, p.stderr
    claims = json.loads(p.stdout)
    assert claims["kind"] == "app-only" and claims["roles"] == APP["roles"]


def test_scripts_parse():
    for s in INFRA.glob("*.sh"):
        subprocess.run(["bash", "-n", str(s)], check=True)
