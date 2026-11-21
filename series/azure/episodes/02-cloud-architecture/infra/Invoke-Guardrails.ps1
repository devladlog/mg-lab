#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Runs PSRule for Azure (Well-Architected rules) against every environment's Bicep parameter file.
  No Azure sign-in needed: the Bicep CLI expands the templates locally.
.EXAMPLE
  pwsh infra/Invoke-Guardrails.ps1            # exit code 1 if any rule fails
#>
[CmdletBinding()]
param(
    [string[]] $Environment = @('lab', 'prod')
)
$ErrorActionPreference = 'Stop'
Import-Module PSRule.Rules.Azure -ErrorAction Stop

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $failed = 0
    foreach ($env in $Environment) {
        $results = Invoke-PSRule -InputPath "infra/env/$env.bicepparam" -Option ./ps-rule.yaml `
            -Format File -Outcome Pass, Fail, Error -WarningAction SilentlyContinue
        $pass = @($results | Where-Object Outcome -eq 'Pass').Count
        $bad = @($results | Where-Object Outcome -in 'Fail', 'Error')
        $suppressed = @(Invoke-PSRule -InputPath "infra/env/$env.bicepparam" -Option ./ps-rule.yaml -Format File `
                -Outcome All -WarningAction SilentlyContinue | Where-Object OutcomeReason -eq 'Suppressed')
        "{0,-5} pass {1,4}   fail {2,3}   suppressed {3,3}" -f $env, $pass, $bad.Count, $suppressed.Count
        foreach ($s in $suppressed) { "        suppressed  {0}  {1}" -f $s.RuleName, $s.TargetName }
        foreach ($b in $bad) { "        FAIL        {0}  {1}" -f $b.RuleName, $b.TargetName }
        $failed += $bad.Count
    }
    if ($failed -gt 0) { Write-Error "$failed rule(s) failed." }
}
finally {
    Pop-Location
}
