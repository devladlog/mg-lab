<#
.SYNOPSIS
  Read-only health check of the Contoso intranet against contract/intranet.json. Exit code 1 when any check fails.
.EXAMPLE
  ./Test-Intranet.ps1 -TenantName mytenant -ClientId <your PnP app client id>
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $TenantName,
    [Parameter(Mandatory)] [guid] $ClientId,
    [string] $ContractPath = (Join-Path $PSScriptRoot '..' 'contract' 'intranet.json')
)
$ErrorActionPreference = 'Stop'
Import-Module PnP.PowerShell -ErrorAction Stop
Import-Module (Join-Path $PSScriptRoot 'Intranet.psm1') -Force

$contract = Read-IntranetContract -Path $ContractPath
$admin = Connect-PnPOnline -Url "https://$TenantName-admin.sharepoint.com" -Interactive -ClientId $ClientId.ToString() -ReturnConnection
$connectHub = { param($url) Connect-PnPOnline -Url $url -Interactive -ClientId $ClientId.ToString() -ReturnConnection }.GetNewClosure()

$rows = Test-IntranetHealth -Contract $contract -TenantName $TenantName -AdminConnection $admin -ConnectHub $connectHub
$rows | Format-Table Status, Check, Target, Detail -AutoSize
if ($rows | Where-Object Status -eq 'Fail') { exit 1 }
