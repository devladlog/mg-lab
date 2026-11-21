#Requires -Version 7.2
<#
.SYNOPSIS
    Publishing checks, before (a PBIP folder) or after (a workspace) publishing. Exit code 1 when there's an error.

.EXAMPLE
    ./Invoke-PublishingCheck.ps1 -ProjectPath ../../05-row-level-security/src          # offline, before Publish

.EXAMPLE
    Connect-PowerBIServiceAccount                                                       # interactive sign-in first
    ./Invoke-PublishingCheck.ps1 -WorkspaceId <workspace id>                            # after Publish
#>
[CmdletBinding(DefaultParameterSetName = 'Project')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Project')][string] $ProjectPath,
    [Parameter(Mandatory, ParameterSetName = 'Workspace')][guid] $WorkspaceId,
    [Parameter(ParameterSetName = 'Workspace')][int] $MaxTiles = 12
)

Import-Module (Join-Path $PSScriptRoot 'PbiPublishing' 'PbiPublishing.psd1') -Force

if ($PSCmdlet.ParameterSetName -eq 'Project') {
    $findings = @(Test-PbipPublishReadiness -Path $ProjectPath)
}
else {
    if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
        throw 'MicrosoftPowerBIMgmt is not installed: Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser'
    }
    $inventory = Get-PbiWorkspaceInventory -WorkspaceId $WorkspaceId
    Write-Host ("{0} report(s), {1} semantic model(s), {2} dashboard(s), {3} tile(s)" -f $inventory.Reports.Count,
        $inventory.Datasets.Count, $inventory.Dashboards.Count, ($inventory.Dashboards | ForEach-Object { $_.Tiles.Count } | Measure-Object -Sum).Sum)
    $findings = @($inventory | Test-PbiWorkspacePublishing -MaxTiles $MaxTiles)
}

$findings | Format-Table Rule, Severity, Message -Wrap | Out-String -Width 140 | Write-Host
$errors = @($findings | Where-Object Severity -eq 'Error').Count
$warnings = @($findings | Where-Object Severity -eq 'Warning').Count
Write-Host "$errors error(s), $warnings warning(s)"
exit ([int]($errors -gt 0))
