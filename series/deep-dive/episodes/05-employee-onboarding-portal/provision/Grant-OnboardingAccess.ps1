<#
.SYNOPSIS
  Grants the onboarding function's managed identity its Graph app roles and 'write' on the two onboarding lists,
  then prints the IDs for the function's app settings. Run as an admin with Microsoft Graph PowerShell
  (Microsoft.Graph.Authentication). Safe to run twice; -WhatIf shows what would change.
.EXAMPLE
  ./provision/Grant-OnboardingAccess.ps1 -IdentityClientId <identityClientId output> -HostName contoso.sharepoint.com -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $IdentityClientId,
    [Parameter(Mandatory)] [string] $HostName,
    [string] $SitePath = '/sites/hr-lab',
    [string] $IdentityDisplayName = 'id-onboarding (function)'
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardingAccess.psm1') -Force

# AppRoleAssignment.ReadWrite.All + Application.Read.All for the app roles; Sites.FullControl.All to grant on lists.
Connect-MgGraph -Scopes 'Application.Read.All', 'AppRoleAssignment.ReadWrite.All', 'Sites.FullControl.All' -NoWelcome

$results = @(Grant-OnbGraphAppRoles -IdentityClientId $IdentityClientId -WhatIf:$WhatIfPreference)
$ids = Resolve-OnbListIds -HostName $HostName -SitePath $SitePath -ListTitles 'Onboarding Requests', 'Onboarding Tasks'
foreach ($title in 'Onboarding Requests', 'Onboarding Tasks') {
    $results += Grant-OnbListAccess -SiteId $ids.SiteId -ListId $ids[$title] -IdentityClientId $IdentityClientId -DisplayName $IdentityDisplayName -WhatIf:$WhatIfPreference
}
$results | Format-Table -AutoSize

Write-Host 'App settings for the function (az functionapp config appsettings set ...):'
[ordered]@{
    Onboarding__SiteId         = $ids.SiteId
    Onboarding__RequestsListId = $ids['Onboarding Requests']
    Onboarding__TasksListId    = $ids['Onboarding Tasks']
} | Format-Table -AutoSize
