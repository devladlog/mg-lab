<#
.SYNOPSIS
  Adds the approval columns to 'Invoices Inbox'. Needs PowerShell 7.4+, PnP.PowerShell and your own Entra app
  registration for PnP (interactive sign-in).
.EXAMPLE
  ./provision/Add-ApprovalColumns.ps1 -SiteUrl https://contoso.sharepoint.com/sites/finance-lab -ClientId <app id> -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $SiteUrl,
    [Parameter(Mandatory)] [string] $ClientId,
    [string] $ContractPath = (Join-Path $PSScriptRoot '..' 'contract' 'approval-columns.json')
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ApprovalColumns.psm1') -Force
Connect-PnPOnline -Url $SiteUrl -ClientId $ClientId -Interactive
$contract = Read-ApprovalContract -Path $ContractPath
Install-ApprovalColumns -Contract $contract -WhatIf:$WhatIfPreference | Format-Table -AutoSize
