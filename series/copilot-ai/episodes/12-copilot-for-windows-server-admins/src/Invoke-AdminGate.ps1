<#
.SYNOPSIS
Runs the AdminGate review on one or more scripts. Exit code: 0 clean, 1 warnings, 2 blocked.
.EXAMPLE
pwsh ./Invoke-AdminGate.ps1 -Path ./scripts/Get-ServerHealth.ps1 -Mode ReadOnly
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)] [string[]] $Path,
    [ValidateSet('ReadOnly', 'Change')] [string] $Mode = 'ReadOnly',
    [switch] $Json,
    [switch] $SkipResolution
)
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'AdminGate' 'AdminGate.psm1') -Force
$worst = 0
$report = foreach ($p in $Path) {
    $r = Test-AdminScript -Path $p -Mode $Mode -SkipResolution:$SkipResolution
    if ($r.ExitCode -gt $worst) { $worst = $r.ExitCode }
    [pscustomobject]@{ File = $p; Verdict = $r.Verdict; ExitCode = $r.ExitCode; Findings = $r.Findings }
}
if ($Json) {
    $report | ConvertTo-Json -Depth 5
}
else {
    foreach ($r in $report) {
        Write-Output "$($r.File): $($r.Verdict)"
        foreach ($f in $r.Findings) {
            Write-Output ("  {0,-5} {1}  line {2,-3} {3}" -f $f.Severity.ToUpper(), $f.Rule, $f.Line, $f.Message)
        }
    }
}
exit $worst
