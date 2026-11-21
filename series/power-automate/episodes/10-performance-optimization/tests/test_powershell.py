import subprocess

from conftest import ROOT, needs_pwsh


@needs_pwsh
def test_pester_seed_script():
    r = subprocess.run(["pwsh", "-NoProfile", "-Command",
                        "$c=New-PesterConfiguration;$c.Run.Path='tests/Seed-ITRequests.Tests.ps1';$c.Run.PassThru=$true;$c.Output.Verbosity='None';"
                        "$r=Invoke-Pester -Configuration $c;if($r.FailedCount -gt 0 -or $r.PassedCount -lt 5){exit 1}"],
                       cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
