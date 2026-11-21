<#
.SYNOPSIS
  Saves the data policies of the tenant as JSON, in the shape `python -m dlpkit` reads.

.DESCRIPTION
  Needs Windows PowerShell 5.1, Microsoft.PowerApps.Administration.PowerShell and Add-PowerAppsAccount
  (see Apply-DlpPolicy.ps1). Get-DlpPolicy returns {value: [...]}; dlpkit reads that, plus a `scope`
  object it doesn't get from the service: say where the policy applies with -ScopeMode and
  -ScopeEnvironments (names that you then pass to `dlpkit check --environment`).

.EXAMPLE
  .\Export-DlpPolicy.ps1 -OutFile ..\policy\exported.json -DisplayName 'MG Lab IT DEV' -ScopeMode only -ScopeEnvironments dev
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$OutFile,
    [string]$DisplayName,
    [ValidateSet('all', 'only', 'except')] [string]$ScopeMode = 'all',
    [string[]]$ScopeEnvironments = @()
)
Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
if (-not (Get-Command Get-DlpPolicy -ErrorAction SilentlyContinue)) {
    throw "Get-DlpPolicy not found. Use Windows PowerShell 5.1, run Install-Module Microsoft.PowerApps.Administration.PowerShell, then Add-PowerAppsAccount."
}
$items = @((Get-DlpPolicy).value)
if ($DisplayName) { $items = @($items | Where-Object { $_.displayName -eq $DisplayName }) }
if ($items.Count -eq 0) { throw "No data policy found$(if ($DisplayName) { " named '$DisplayName'" })." }
foreach ($item in $items) {
    $scope = [pscustomobject]@{ mode = $ScopeMode; environments = @($ScopeEnvironments) }
    $item | Add-Member -NotePropertyName scope -NotePropertyValue $scope -Force
}
$json = ConvertTo-Json -InputObject ([pscustomobject]@{ value = $items }) -Depth 20
Set-Content -LiteralPath $OutFile -Value $json -Encoding UTF8
Write-Output ("Wrote {0} policy(ies) to {1}" -f $items.Count, $OutFile)
