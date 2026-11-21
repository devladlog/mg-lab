#Requires -Version 7.2
<#
.SYNOPSIS
    PC side of DEVLADLOG Microsoft 365 #12 (OneDrive for Business): writes the OneDrive sync-app policies (silent sign-in, Files On-Demand,
    silent Known Folder Move) under HKLM\SOFTWARE\Policies\Microsoft\OneDrive, checks them, or puts them back. Windows only; writing needs an
    elevated PowerShell. It does not talk to Microsoft 365: the tenant id is a parameter (Entra admin center > Overview, or
    (Get-MgOrganization).Id).
.EXAMPLE
    ./Set-OneDriveSyncPolicy.ps1 -TenantId <tenant guid> -WhatIf                                 # show the plan, write nothing
    ./Set-OneDriveSyncPolicy.ps1 -TenantId <tenant guid> -RollbackFile .\onedrive-policy.rollback.json
    ./Set-OneDriveSyncPolicy.ps1 -TenantId <tenant guid> -Check                                   # Compliant / Different / Missing
    ./Set-OneDriveSyncPolicy.ps1 -Restore .\onedrive-policy.rollback.json
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Apply')]
param(
    [Parameter(ParameterSetName = 'Apply', Mandatory)][Parameter(ParameterSetName = 'Check', Mandatory)][string]$TenantId,
    [Parameter(ParameterSetName = 'Apply')][Parameter(ParameterSetName = 'Check')][ValidateSet('Desktop', 'Documents', 'Pictures')][string[]]$KnownFolders = @('Desktop', 'Documents', 'Pictures'),
    [Parameter(ParameterSetName = 'Apply')][Parameter(ParameterSetName = 'Check')][switch]$Notify,
    [Parameter(ParameterSetName = 'Apply')][Parameter(ParameterSetName = 'Check')][switch]$BlockOptOut,
    [Parameter(ParameterSetName = 'Apply')][string]$RollbackFile,
    [Parameter(ParameterSetName = 'Check', Mandatory)][switch]$Check,
    [Parameter(ParameterSetName = 'Restore', Mandatory)][string]$Restore
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'The OneDrive sync-app policies live in the Windows registry: run this on the Windows PC.' }
Import-Module (Join-Path $PSScriptRoot 'OneDriveAdmin/OneDriveAdmin.psd1') -Force
function Show-Table($Data) { ($Data | Format-Table -AutoSize | Out-String -Width 160).TrimEnd() | Write-Output }
function Assert-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not ([Security.Principal.WindowsPrincipal]::new($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Writing under HKLM needs an elevated (Run as administrator) PowerShell.' }
}

if ($PSCmdlet.ParameterSetName -eq 'Restore') { Assert-Elevated; Show-Table @(Restore-ODASyncPolicy -RollbackFile $Restore -WhatIf:$WhatIfPreference); return }
$plan = @(Get-ODASyncPolicyPlan -TenantId $TenantId -KnownFolders $KnownFolders -Notify:$Notify -BlockOptOut:$BlockOptOut)
if ($Check) { Show-Table @(Get-ODASyncPolicyState -Plan $plan); return }
if (-not $RollbackFile) { throw '-RollbackFile is required (a new file name): it records what was there before.' }
if (-not $WhatIfPreference) { Assert-Elevated }
Show-Table @(Set-ODASyncPolicy -Plan $plan -RollbackFile $RollbackFile -WhatIf:$WhatIfPreference)
Write-Output 'Next: start (or restart) OneDrive on this PC, sign in as the user, then run this script again with -Check.'
