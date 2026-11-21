#Requires -Version 7.2
<#
.SYNOPSIS
    Audits shared semantic models across workspaces. Exit code 1 when there's an error (none of the rules is one yet:
    they are warnings and info, the point is the list).

.EXAMPLE
    Connect-PowerBIServiceAccount                         # interactive sign-in first
    ./Invoke-SharedModelCheck.ps1 -DataWorkspaceId $dataWs -ReportWorkspaceId $salesWs
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][guid] $DataWorkspaceId,
    [Parameter(Mandatory)][guid] $ReportWorkspaceId,
    [string] $DataWorkspaceName = 'Contoso Data (Lab)',
    [string] $ReportWorkspaceName = 'Contoso Sales (Lab)'
)

Import-Module (Join-Path $PSScriptRoot 'PbiShared' 'PbiShared.psd1') -Force
if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
    throw 'MicrosoftPowerBIMgmt is not installed: Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser'
}

$inventory = Get-PbiSharedModelInventory -Workspace ([ordered]@{ $DataWorkspaceName = $DataWorkspaceId; $ReportWorkspaceName = $ReportWorkspaceId })
foreach ($ws in $inventory.Workspaces) {
    Write-Host ("{0}: {1} semantic model(s), {2} report(s), {3} dataflow(s)" -f $ws.Name, $ws.Datasets.Count, $ws.Reports.Count, $ws.Dataflows.Count)
}
$findings = @($inventory | Test-PbiSharedModel -DataWorkspace $DataWorkspaceName)
$findings | Format-Table Rule, Severity, Message -Wrap | Out-String -Width 160 | Write-Host
$errors = @($findings | Where-Object Severity -eq 'Error').Count
$warnings = @($findings | Where-Object Severity -eq 'Warning').Count
Write-Host "$errors error(s), $warnings warning(s)"
exit ([int]($errors -gt 0))
