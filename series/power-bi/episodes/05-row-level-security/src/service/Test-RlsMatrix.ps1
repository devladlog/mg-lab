#Requires -Version 7.2
<#
.SYNOPSIS
    RLS regression test against the published semantic model: one impersonated DAX query per user.

.EXAMPLE
    Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser      # once
    Connect-PowerBIServiceAccount                               # sign in as the workspace admin (interactive)
    ./Test-RlsMatrix.ps1 -WorkspaceId <guid> -DatasetId <guid> -UpnDomain <your tenant domain>

    Exit code 0 when every user matches reference/expected/rls_matrix.csv, 1 otherwise.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][guid] $WorkspaceId,
    [Parameter(Mandatory)][guid] $DatasetId,
    [Parameter(Mandatory)][string] $UpnDomain,
    [string] $ExpectedPath = (Join-Path $PSScriptRoot '..' 'reference' 'expected' 'rls_matrix.csv')
)

if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
    throw 'MicrosoftPowerBIMgmt is not installed: Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser'
}
Import-Module (Join-Path $PSScriptRoot 'RlsMatrix.psm1') -Force

$results = @(Test-RlsMatrix -WorkspaceId $WorkspaceId -DatasetId $DatasetId -UpnDomain $UpnDomain -ExpectedPath $ExpectedPath)
$results | Format-Table User, Roles, Stores, Customers, Sales, Result, Details -AutoSize | Out-Host
$failed = @($results | Where-Object Result -ne 'PASS').Count
Write-Host ("{0} user(s), {1} passed, {2} failed" -f $results.Count, ($results.Count - $failed), $failed)
exit ([int]($failed -gt 0))
