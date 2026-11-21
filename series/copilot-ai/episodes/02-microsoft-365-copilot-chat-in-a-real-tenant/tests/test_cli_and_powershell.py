import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot_chat_audit.cli import main  # noqa: E402
from copilot_chat_audit.parse import load_records  # noqa: E402

SAMPLE = ROOT / "src" / "samples" / "copilot-interactions-sample.csv"
SCRIPT = ROOT / "src" / "scripts" / "Export-CopilotInteractions.ps1"


def test_cli_text(capsys):
    assert main([str(SAMPLE), "--licensed", str(ROOT / "src/samples/licensed-users.txt")]) == 0
    out = capsys.readouterr().out
    assert "Copilot interactions: 8 by 5 user(s)" in out
    assert "Web search used: 3 (38%)" in out
    assert "Vendor FAQ Agent" in out
    assert "Licence split: 1 licensed, 7 unlicensed" in out
    assert "Skipped: 1 other operation(s), 1 unreadable row(s)" in out


def test_cli_json_and_since(capsys):
    assert main([str(SAMPLE), "--json", "--since", "2026-11-21"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["interactions"] == 3 and data["skipped"]["unreadable"] == 1


def test_cli_exit_code_when_nothing_found(tmp_path, capsys):
    p = tmp_path / "none.csv"
    p.write_text("UserIds,AuditData\n", encoding="utf-8")
    assert main([str(p)]) == 3


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 not installed")
def test_powershell_export_pages_until_empty_and_roundtrips_to_python(tmp_path):
    """Run the real script with a stand-in Search-UnifiedAuditLog (test only), then parse its CSV with the Python tool."""
    audit = lambda n: json.dumps({  # noqa: E731
        "Operation": "CopilotInteraction", "Id": f"id{n}", "UserId": "alex.demo@contoso.example",
        "CreationTime": "2026-11-21T10:00:00",
        "CopilotEventData": {"AppHost": "BizChat", "AISystemPlugin": [{"Id": "BingWebSearch"}]},
    })
    out_csv = tmp_path / "out.csv"
    harness = tmp_path / "harness.ps1"
    harness.write_text(
        f"""
$script:calls = @()
$script:pages = @(
  @([pscustomobject]@{{CreationDate='2026-11-21';UserIds='alex.demo@contoso.example';Operations='CopilotInteraction';RecordType='CopilotInteraction';AuditData='{audit(1).replace("'", "''")}'}},
    [pscustomobject]@{{CreationDate='2026-11-21';UserIds='alex.demo@contoso.example';Operations='CopilotInteraction';RecordType='CopilotInteraction';AuditData='{audit(2).replace("'", "''")}'}}),
  @()
)
function Search-UnifiedAuditLog {{
  param($StartDate,$EndDate,$Operations,$SessionId,$SessionCommand,$ResultSize,$UserIds)
  $script:calls += [pscustomobject]@{{Operations=$Operations;SessionCommand=$SessionCommand;ResultSize=$ResultSize;SessionId=$SessionId}}
  $i = $script:calls.Count - 1
  if ($i -lt $script:pages.Count) {{ return $script:pages[$i] }} else {{ return @() }}
}}
. '{SCRIPT}'
$r = Get-CopilotInteractionRecords -StartDate (Get-Date).AddDays(-1) -EndDate (Get-Date) -PageSize 2
if ($r.Count -ne 2) {{ throw "expected 2 records, got $($r.Count)" }}
if ($script:calls.Count -ne 2) {{ throw "expected 2 calls, got $($script:calls.Count)" }}
if (($script:calls | Where-Object {{ $_.Operations -ne 'CopilotInteraction' -or $_.SessionCommand -ne 'ReturnLargeSet' -or $_.ResultSize -ne 2 }}).Count) {{ throw 'wrong query' }}
if (@($script:calls.SessionId | Select-Object -Unique).Count -ne 1) {{ throw 'session id changed between pages' }}
$r | Select-Object CreationDate, UserIds, Operations, RecordType, AuditData | Export-Csv -LiteralPath '{out_csv}' -NoTypeInformation -Encoding utf8
""",
        encoding="utf-8",
    )
    proc = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(harness)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    result = load_records(out_csv)
    assert len(result.interactions) == 2 and all(i.web_search for i in result.interactions)


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 not installed")
def test_powershell_script_main_path_writes_csv_and_fails_without_connection(tmp_path):
    out_csv = tmp_path / "main.csv"
    audit = json.dumps({"Operation": "CopilotInteraction", "UserId": "sam.demo@contoso.example",
                        "CopilotEventData": {"AppHost": "Teams"}})
    harness = tmp_path / "main.ps1"
    harness.write_text(
        f"""
$script:n = 0
function Search-UnifiedAuditLog {{
  param($StartDate,$EndDate,$Operations,$SessionId,$SessionCommand,$ResultSize,$UserIds)
  $script:n++
  if ($script:n -eq 1) {{ [pscustomobject]@{{CreationDate='2026-11-21';UserIds='sam.demo@contoso.example';Operations='CopilotInteraction';RecordType='CopilotInteraction';AuditData='{audit.replace("'", "''")}'}} }}
}}
& '{SCRIPT}' -OutFile '{out_csv}' -StartDate (Get-Date).AddDays(-1)
""",
        encoding="utf-8",
    )
    proc = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(harness)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "1 CopilotInteraction record(s) written" in proc.stdout
    assert len(load_records(out_csv).interactions) == 1

    # Without a connection the script must stop with a clear message instead of doing nothing.
    bare = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(SCRIPT), "-OutFile", str(tmp_path / "x.csv")],
                          capture_output=True, text=True, timeout=120)
    assert bare.returncode != 0 and "Connect-ExchangeOnline" in (bare.stderr + bare.stdout)
