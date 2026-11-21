<#
.SYNOPSIS
  Builds the Contoso intranet in a Microsoft 365 tenant: site design, hub, department sites, hub navigation, home site.
.DESCRIPTION
  Reads contract/intranet.json. Idempotent: run it again and every step reports Exists. Honours -WhatIf.
  Needs PnP.PowerShell and a Microsoft Entra app registration you control (see the PnP authentication article):
  pass its client ID. Sign in as a SharePoint administrator; the browser opens once per connection. Nothing is stored.
.EXAMPLE
  ./Initialize-Intranet.ps1 -TenantName mytenant -ClientId <your PnP app client id> -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $TenantName,
    [Parameter(Mandatory)] [guid] $ClientId,
    [string] $ContractPath = (Join-Path $PSScriptRoot '..' 'contract' 'intranet.json')
)
$ErrorActionPreference = 'Stop'
Import-Module PnP.PowerShell -ErrorAction Stop
Import-Module (Join-Path $PSScriptRoot 'Intranet.psm1') -Force

$contract = Read-IntranetContract -Path $ContractPath
$scriptPath = Join-Path (Split-Path $ContractPath -Parent) '..' $contract.siteDesign.scriptFile

$admin = Connect-PnPOnline -Url "https://$TenantName-admin.sharepoint.com" -Interactive -ClientId $ClientId.ToString() -ReturnConnection
$connectHub = { param($url) Connect-PnPOnline -Url $url -Interactive -ClientId $ClientId.ToString() -ReturnConnection }.GetNewClosure()

Invoke-IntranetProvisioning -Contract $contract -TenantName $TenantName -ScriptPath $scriptPath -AdminConnection $admin -ConnectHub $connectHub -WhatIf:$WhatIfPreference |
    Format-Table Step, Target, Action -AutoSize
