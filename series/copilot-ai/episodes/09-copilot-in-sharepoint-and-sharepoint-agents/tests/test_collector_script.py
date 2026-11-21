"""Run Get-AgentFileInventory.ps1 under pwsh with stand-ins for the PnP cmdlets (test only), then read its CSV."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agentfiles import inventory

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
SCRIPT = ROOT / "src" / "scripts" / "Get-AgentFileInventory.ps1"
HARNESS = ROOT / "tests" / "collector_harness.ps1"
pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh not installed")

BASE = dict(TenantUrl="https://example.sharepoint.com", ClientId="00000000-0000-0000-0000-000000000000")

ROWS = [
    {"Title": "Vendor Desk", "Path": "https://example.sharepoint.com/sites/contoso-vmo/Policies/Vendor Desk.agent",
     "Author": "Alex Demo", "Created": "2026-03-02T09:00:00Z", "LastModifiedTime": "2026-10-20T14:30:00Z",
     "SPSiteUrl": "https://example.sharepoint.com/sites/contoso-vmo", "SiteTitle": "Contoso VMO",
     "ViewsLifeTime": 214, "ViewsRecent": 31, "ViewsLifeTimeUniqueUsers": 58},
    {"Title": "Old Pilot, v2", "Path": "https://example.sharepoint.com/sites/p/Old Pilot.agent", "Author": "",
     "Created": "", "LastModifiedTime": "", "SPSiteUrl": "", "SiteTitle": "", "ViewsLifeTime": 0, "ViewsRecent": 0,
     "ViewsLifeTimeUniqueUsers": 0},
]


def run(tmp_path, rows, **args):
    log, argfile, rowfile = tmp_path / "calls.json", tmp_path / "args.json", tmp_path / "rows.json"
    argfile.write_text(json.dumps(args), encoding="utf-8")
    rowfile.write_text(json.dumps(rows), encoding="utf-8")
    subprocess.run([PWSH, "-NoProfile", "-File", str(HARNESS), "-Script", str(SCRIPT), "-CallLog", str(log),
                    "-ArgsJson", str(argfile), "-Rows", str(rowfile)], check=True, capture_output=True, text=True, timeout=120)
    return json.loads(log.read_text(encoding="utf-8"))


def test_query_and_columns(tmp_path):
    out = tmp_path / "out.csv"
    r = run(tmp_path, ROWS, OutFile=str(out), **BASE)
    assert r["error"] is None
    connect, search = r["calls"]
    assert connect["Interactive"] is True and connect["ClientId"] == BASE["ClientId"]
    assert search["Query"] == "FileExtension:agent" and search["All"] is True
    assert search["Select"].split(",") == inventory.COLUMNS


def test_site_scope_adds_path_restriction(tmp_path):
    r = run(tmp_path, ROWS, OutFile=str(tmp_path / "o.csv"), SiteUrl="https://example.sharepoint.com/sites/contoso-vmo/", **BASE)
    assert r["calls"][1]["Query"] == 'FileExtension:agent Path:"https://example.sharepoint.com/sites/contoso-vmo"'


def test_csv_is_read_by_the_python_side(tmp_path):
    out = tmp_path / "out.csv"
    run(tmp_path, ROWS, OutFile=str(out), **BASE)
    files, skipped = inventory.read_inventory(out)
    assert skipped == 0 and [f.title for f in files] == ["Vendor Desk", "Old Pilot, v2"]
    assert files[0].views_lifetime == 214 and files[0].owner == "Alex Demo"


def test_no_results_still_writes_a_readable_header(tmp_path):
    out = tmp_path / "empty.csv"
    r = run(tmp_path, [], OutFile=str(out), **BASE)
    assert r["error"] is None
    assert inventory.read_inventory(out) == ([], 0)


def test_rejects_non_sharepoint_url(tmp_path):
    r = run(tmp_path, ROWS, OutFile=str(tmp_path / "o.csv"), TenantUrl="https://evil.example.com", ClientId="x")
    assert r["error"] and "TenantUrl" in r["error"]
