<#
.SYNOPSIS
  Creates the 'Onboarding Requests' and 'Onboarding Tasks' lists on the HR lab site. Needs PowerShell 7.4+,
  PnP.PowerShell and your own Entra app registration for PnP (interactive sign-in). Safe to run twice.
.EXAMPLE
  ./provision/New-OnboardingLists.ps1 -SiteUrl https://contoso.sharepoint.com/sites/hr-lab -ClientId <PnP app id> -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $SiteUrl,
    [Parameter(Mandatory)] [string] $ClientId,
    [string] $ContractPath = (Join-Path $PSScriptRoot '..' 'contract' 'onboarding-lists.json')
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardingLists.psm1') -Force
Connect-PnPOnline -Url $SiteUrl -ClientId $ClientId -Interactive
$contract = Read-OnboardingContract -Path $ContractPath
Install-OnboardingLists -Contract $contract -WhatIf:$WhatIfPreference | Format-Table -AutoSize
