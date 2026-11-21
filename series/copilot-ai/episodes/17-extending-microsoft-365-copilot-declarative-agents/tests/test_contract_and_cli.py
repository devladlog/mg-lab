import os
import subprocess
import sys
from datetime import date

from dakit.cli import main
from dakit.contract import run_contract
from vendor_api.app import create_app
from conftest import PACKAGE, SRC

SPEC = PACKAGE / "openapi.yaml"
TODAY = date(2026, 11, 21)


def test_api_matches_its_openapi_description():
    assert run_contract(SPEC, create_app("k", today=lambda: TODAY)) == []


def test_contract_catches_an_api_that_drifted():
    """An API that returns a number as text must be reported, so the plugin description can never silently lie."""
    good = create_app("k", today=lambda: TODAY)

    def drifted(environ, start_response):
        import json
        captured = {}
        body = json.loads(b"".join(good(environ, lambda s, h: captured.update(s=s, h=h))))
        for r in body.get("renewals", []):
            r["annualCostEur"] = str(r["annualCostEur"])
        data = json.dumps(body).encode()
        start_response(captured["s"], [("Content-Length", str(len(data)))])
        return [data]

    findings = run_contract(SPEC, drifted)
    assert any("does not match its schema" in f.message for f in findings)


def test_contract_catches_an_undocumented_status():
    def teapot(environ, start_response):
        start_response("200 OK", [])
        return [b'{"x": 1}']
    findings = run_contract(SPEC, teapot)
    assert any("expected HTTP" in f.message for f in findings)


def test_cli_commands_in_process(capsys):
    assert main(["validate", str(PACKAGE)]) == 0
    assert main(["validate", str(PACKAGE), "--strict"]) == 1
    assert main(["lint-openapi", str(SPEC)]) == 0
    assert main(["contract", str(SPEC)]) == 0
    out = capsys.readouterr().out
    assert "0 error(s), 0 warning(s)" in out


def test_module_entry_points_run_in_a_subprocess():
    r = subprocess.run([sys.executable, "-m", "dakit", "licence", str(PACKAGE / "declarativeAgent.json")],
                       cwd=SRC, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(SRC)})
    assert r.returncode == 0 and "Required: all" in r.stdout
    r = subprocess.run([sys.executable, "-m", "vendor_api", "--help"], cwd=SRC, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(SRC)})
    assert r.returncode == 0 and "--today" in r.stdout
