<#
.SYNOPSIS
  Creates the 'Invoices Inbox' library and its columns from src/docintel/columns.json.
.EXAMPLE
  ./New-InvoiceInbox.ps1 -SiteUrl https://contoso.sharepoint.com/sites/finance-lab -ClientId 00000000-0000-0000-0000-000000000000 -WhatIf
.NOTES
  Needs PnP.PowerShell (PowerShell 7.4 or later) and your own Entra app registration for -ClientId
  (Register-PnPEntraIDAppForInteractiveLogin creates one).
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [uri] $SiteUrl,
    [Parameter(Mandatory)] [string] $ClientId,
    [string] $ContractPath = (Join-Path $PSScriptRoot '..' 'src' 'docintel' 'columns.json')
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'InvoiceInbox.psm1') -Force
Import-Module PnP.PowerShell

$contract = Read-InvoiceContract -Path $ContractPath
Connect-PnPOnline -Url $SiteUrl -ClientId $ClientId -Interactive
Install-InvoiceInbox -Contract $contract -WhatIf:$WhatIfPreference | Format-Table -AutoSize
