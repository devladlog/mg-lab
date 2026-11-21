"""Every script parses and passes PSScriptAnalyzer (errors and warnings)."""
import json
import subprocess

from conftest import SCRIPTS

COMMAND = r"""
$ErrorActionPreference = 'Stop'
$result = @()
foreach ($f in Get-ChildItem -LiteralPath '{dir}' -Filter *.ps1) {
    $tokens = $null; $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$errors)
    foreach ($e in $errors) { $result += [pscustomobject]@{ File = $f.Name; Rule = 'ParseError'; Message = $e.Message } }
    foreach ($d in Invoke-ScriptAnalyzer -Path $f.FullName -Severity Error, Warning) {
        $result += [pscustomobject]@{ File = $f.Name; Rule = $d.RuleName; Message = $d.Message }
    }
}
ConvertTo-Json -InputObject @($result) -Compress
"""


def test_scripts_parse_and_pass_psscriptanalyzer():
    out = subprocess.run(["pwsh", "-NoProfile", "-Command", COMMAND.replace("{dir}", str(SCRIPTS))], capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == []


def test_there_are_scripts_to_check():
    assert len(list(SCRIPTS.glob("*.ps1"))) == 6
