<#
.SYNOPSIS
  Prepares the Microsoft Entra External ID external tenant for the Power Pages customer portal and prints the values
  for the Power Pages identity provider wizard. Run as an admin of the EXTERNAL tenant with Microsoft Graph
  PowerShell (Microsoft.Graph.Authentication). Safe to run twice; -WhatIf shows what would change.
.EXAMPLE
  ./external-id/Initialize-ExternalId.ps1 -TenantId <external tenant ID> -ReplyUrl https://contoso-support.powerappsportals.com/signin-openid_1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $TenantId,
    [Parameter(Mandatory)] [string] $ReplyUrl,
    [string] $AppName = 'Contoso support portal',
    [string] $FlowName = 'Contoso support sign-up and sign-in'
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ExternalIdSetup.psm1') -Force

# Application.ReadWrite.All: app + service principal; DelegatedPermissionGrant.ReadWrite.All: admin consent;
# EventListener.ReadWrite.All: user flows; Organization.Read.All: tenant ID and initial domain.
Connect-MgGraph -TenantId $TenantId -NoWelcome -Scopes 'Application.ReadWrite.All', 'DelegatedPermissionGrant.ReadWrite.All',
    'EventListener.ReadWrite.All', 'Organization.Read.All'

$result = Initialize-ExtPortalIdentity -ReplyUrl $ReplyUrl -AppName $AppName -FlowName $FlowName -WhatIf:$WhatIfPreference
$result.Steps | Format-Table -AutoSize
if ($result.Settings) {
    Write-Host 'Power Pages > Security > Identity providers > Microsoft Entra External ID:'
    $result.Settings | Format-Table -AutoSize
}
