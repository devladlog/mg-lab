"""Run New-VendorKnowledgeSite.ps1 under pwsh with stand-ins for the PnP cmdlets (test only) and check the calls."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kbpack import docbuild  # noqa: E402

PWSH = shutil.which("pwsh")
SCRIPT = ROOT / "src" / "scripts" / "New-VendorKnowledgeSite.ps1"
HARNESS = ROOT / "tests" / "site_script_harness.ps1"
pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh not installed")


def run(tmp_path, **args):
    log = tmp_path / "calls.json"
    argfile = tmp_path / "args.json"
    argfile.write_text(json.dumps(args), encoding="utf-8")
    subprocess.run([PWSH, "-NoProfile", "-File", str(HARNESS), "-Script", str(SCRIPT),
                    "-CallLog", str(log), "-ArgsJson", str(argfile)],
                   check=True, capture_output=True, text=True, timeout=120)
    return json.loads(log.read_text(encoding="utf-8"))


@pytest.fixture()
def docs(tmp_path):
    out = tmp_path / "docs"
    docbuild.build_all(ROOT / "src" / "knowledge", out)
    return out


BASE = dict(TenantUrl="https://example.sharepoint.com", ClientId="00000000-0000-0000-0000-000000000000",
            OwnerUpn="owner@example.onmicrosoft.com", RestrictedUserUpn="vmo@example.onmicrosoft.com")


def test_script_parses():
    r = subprocess.run([PWSH, "-NoProfile", "-Command",
                        "$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
                        f"'{SCRIPT}',[ref]$t,[ref]$e); $e.Count"],
                       capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "0"


def test_creates_site_libraries_permissions_and_uploads(tmp_path, docs):
    res = run(tmp_path, DocsPath=str(docs), **BASE)
    assert res["error"] is None
    calls = res["calls"]
    names = [c["cmd"] for c in calls]
    # tenant admin connection first, then the site connection
    assert calls[0]["cmd"] == "Connect-PnPOnline" and calls[0]["Url"] == "https://example-admin.sharepoint.com"
    site = next(c for c in calls if c["cmd"] == "New-PnPSite")
    assert site["Url"] == "https://example.sharepoint.com/sites/contoso-vmo" and site["Type"] == "CommunicationSite"
    assert [c["Title"] for c in calls if c["cmd"] == "New-PnPList"] == ["Policies", "Restricted"]
    assert all(c["Template"] == "DocumentLibrary" for c in calls if c["cmd"] == "New-PnPList")
    # inheritance is broken on Restricted only, and the assignments are NOT copied
    brk = [c for c in calls if c["cmd"] == "Set-PnPList"]
    assert len(brk) == 1 and brk[0]["Identity"] == "Restricted" and brk[0]["CopyRoleAssignments"] == "False"
    perm = [c for c in calls if c["cmd"] == "Set-PnPListPermission"]
    assert perm[0]["User"] == "vmo@example.onmicrosoft.com" and perm[0]["AddRole"] == "Read"
    # permissions are set before any file is uploaded into Restricted
    assert names.index("Set-PnPListPermission") < max(i for i, n in enumerate(names) if n == "Add-PnPFile")
    uploads = [(c["Folder"], c["File"]) for c in calls if c["cmd"] == "Add-PnPFile"]
    assert ("Restricted", "vendor-negotiation-playbook-restricted.docx") in uploads
    assert sum(1 for f, _ in uploads if f == "Policies") == 4


def test_readers_are_added_to_the_visitors_group(tmp_path, docs):
    res = run(tmp_path, DocsPath=str(docs), ReaderUpns=["sam@example.onmicrosoft.com", "alex@example.onmicrosoft.com"],
              **BASE)
    adds = [c for c in res["calls"] if c["cmd"] == "Add-PnPGroupMember"]
    assert [a["LoginName"] for a in adds] == ["sam@example.onmicrosoft.com", "alex@example.onmicrosoft.com"]
    assert all(a["Group"] == "Visitors-stand-in" for a in adds)


def test_no_restricted_user_means_no_permission_calls(tmp_path, docs):
    args = {k: v for k, v in BASE.items() if k != "RestrictedUserUpn"}
    res = run(tmp_path, DocsPath=str(docs), **args)
    assert not [c for c in res["calls"] if c["cmd"] in ("Set-PnPList", "Set-PnPListPermission")]


def test_missing_docs_folder_is_an_error(tmp_path):
    res = run(tmp_path, DocsPath=str(tmp_path / "nope"), **BASE)
    assert "kbpack build" in res["error"]
    assert not [c for c in res["calls"] if c["cmd"] == "New-PnPSite"]


def test_remove_deletes_the_site_and_nothing_else(tmp_path):
    res = run(tmp_path, Remove=True, **BASE)
    cmds = [c["cmd"] for c in res["calls"]]
    assert cmds == ["Connect-PnPOnline", "Remove-PnPTenantSite"]
    assert res["calls"][1]["Url"].endswith("/sites/contoso-vmo") and res["calls"][1]["SkipRecycleBin"] == "True"


def test_tenant_url_must_be_sharepoint_com(tmp_path):
    bad = dict(BASE, TenantUrl="https://example.com")
    res = run(tmp_path, **bad)
    assert res["error"] and "TenantUrl" in res["error"]
