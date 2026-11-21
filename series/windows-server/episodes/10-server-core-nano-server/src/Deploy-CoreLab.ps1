<#
.SYNOPSIS
Brings Server Core servers to the state core-lab.json asks for. Plan first (always printed), then apply. Honors -WhatIf.
  Runs the check live (or from -FromFacts), builds the setup plan, prints it, applies the Run steps.
  Manual steps (a server that does not answer, a server of the wrong install type) are shown and never run.
  A restart is a step of its own and needs -AllowRestart.
.EXAMPLE
./Deploy-CoreLab.ps1 -WhatIf ; ./Deploy-CoreLab.ps1 ; ./Deploy-CoreLab.ps1 -AllowRestart
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'core-lab.json'),
    [string] $FromFacts,
    [string[]] $ComputerName,
    [pscredential] $Credential,
    [switch] $AllowRestart
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'CoreLab/CoreLab.psd1') -Force
$config = Read-CoreLabConfig -Path $ConfigPath
if ($FromFacts) { $hosts = @((Get-Content -Raw -LiteralPath $FromFacts | ConvertFrom-Json).Hosts) }
else {
    if (-not $ComputerName) { $ComputerName = @($config.Targets | ForEach-Object { [string]$_.Name }) }
    $hosts = @(Get-CoreFacts -ComputerName $ComputerName -Credential $Credential)
}
$plan = @(Get-CoreSetupPlan -Hosts $hosts -Config $config)
if (-not $plan.Count) { Write-Output 'Setup plan: nothing to do.'; return }
$plan | Format-Table Target, Id, Kind, NeedsSwitch, Description -Wrap | Out-String -Width 200 | Write-Output
if ($FromFacts -and -not $WhatIfPreference) { Write-Warning 'Saved facts are a snapshot: applying from them is only sensible with -WhatIf.' }
$result = @(Invoke-CoreSetupPlan -Plan $plan -Credential $Credential -AllowRestart:$AllowRestart -WhatIf:$WhatIfPreference)
if ($result.Count) { $result | Format-Table Target, Id, Result, Detail -Wrap | Out-String -Width 200 | Write-Output }
