import http.server
import json
import threading
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from copilot_landscape import licence_audit as la  # noqa: E402
from copilot_landscape.cli import main  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[1] / "src" / "samples" / "subscribed-skus-contoso.json"


def addon_sku(enabled=3, consumed=2, status="Enabled"):
    return {
        "skuPartNumber": "Microsoft_365_Copilot",
        "capabilityStatus": status,
        "consumedUnits": consumed,
        "prepaidUnits": {"enabled": enabled},
        "servicePlans": [{"servicePlanName": n} for n in la.COPILOT_ADDON_PLANS],
    }


def test_sample_tenant_has_no_addon_but_eligible_base():
    report = la.audit(la.load_skus(SAMPLE))
    assert report["skuCount"] == 3
    assert report["copilotAddon"] == []
    assert {b["skuPartNumber"] for b in report["eligibleBase"]} == {"SPE_E5", "O365_BUSINESS_PREMIUM"}
    assert report["copilotStudioTrial"][0]["consumed"] == 2
    assert "No Microsoft 365 Copilot add-on SKU" in report["verdict"]
    assert "Microsoft 365 E5" in report["verdict"]


def test_addon_detected_by_part_number_and_by_service_plans():
    report = la.audit(la.parse_skus({"value": [addon_sku()]}))
    assert report["copilotAddon"][0]["enabled"] == 3
    assert report["copilotAddon"][0]["unassigned"] == 1
    assert len(report["copilotAddon"][0]["copilotServicePlans"]) == 8
    assert "3 enabled seat(s), 2 assigned" in report["verdict"]

    renamed = {"skuPartNumber": "SOME_FUTURE_NAME", "capabilityStatus": "Enabled", "prepaidUnits": {"enabled": 1},
               "consumedUnits": 0, "servicePlans": [{"servicePlanName": "M365_COPILOT_APPS"}]}
    assert la.audit(la.parse_skus([renamed]))["copilotAddon"][0]["skuPartNumber"] == "SOME_FUTURE_NAME"


def test_suspended_addon_is_not_reported_as_usable():
    report = la.audit(la.parse_skus([addon_sku(enabled=0, status="Suspended")]))
    assert "not Enabled or has no seats" in report["verdict"]


def test_powershell_pascal_case_shape_is_accepted():
    pascal = {
        "SkuPartNumber": "SPE_E3", "CapabilityStatus": "Enabled", "ConsumedUnits": 4,
        "PrepaidUnits": {"Enabled": 10, "Suspended": 0},
        "ServicePlans": [{"ServicePlanName": "Bing_Chat_Enterprise"}],
    }
    report = la.audit(la.parse_skus([pascal]))
    assert report["eligibleBase"][0]["product"] == "Microsoft 365 E3"
    assert report["eligibleBase"][0]["unassigned"] == 6


def test_bom_file_from_windows_powershell(tmp_path):
    p = tmp_path / "skus.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps([addon_sku()]).encode())
    assert la.audit(la.load_skus(p))["copilotAddon"]


def test_unknown_tenant_gets_a_cautious_verdict():
    assert "check the SKU list by hand" in la.audit([])["verdict"]


def test_bad_payload():
    with pytest.raises(ValueError):
        la.parse_skus("nope")


def test_cli_audit_text_and_json(capsys):
    assert main(["audit", "--skus", str(SAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "Microsoft 365 Copilot add-on: none" in out and "Verdict:" in out
    assert main(["audit", "--skus", str(SAMPLE), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["skuCount"] == 3


def test_cli_catalog_validate_and_free(capsys):
    assert main(["catalog", "--validate"]) == 0
    assert "0 problem(s)" in capsys.readouterr().out
    assert main(["catalog", "--free"]) == 0
    assert "Copilot Chat (Basic)" in capsys.readouterr().out


class _Handler(http.server.BaseHTTPRequestHandler):
    seen = {}

    def do_GET(self):  # noqa: N802
        _Handler.seen = {"path": self.path, "auth": self.headers.get("Authorization")}
        body = json.dumps({"value": [addon_sku()]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        pass


def test_live_fetch_sends_bearer_token_to_subscribed_skus(monkeypatch, capsys):
    # Local HTTP server stands in for Graph in this unit test only; the recording uses the real service.
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/v1.0"
        monkeypatch.setenv("GRAPH_TOKEN_TEST", "fake-token")
        assert main(["audit", "--graph-token-env", "GRAPH_TOKEN_TEST", "--graph-base", base, "--json"]) == 0
    finally:
        server.shutdown()
    assert _Handler.seen == {"path": "/v1.0/subscribedSkus", "auth": "Bearer fake-token"}
    assert json.loads(capsys.readouterr().out)["copilotAddon"][0]["enabled"] == 3


def test_missing_token_env_is_an_error(monkeypatch, capsys):
    monkeypatch.delenv("NOPE_TOKEN", raising=False)
    assert main(["audit", "--graph-token-env", "NOPE_TOKEN"]) == 2
