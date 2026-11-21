#Requires -RunAsAdministrator
#  Written for Windows PowerShell 5.1 (powershell.exe, built into Windows Server); a Pester test keeps it 5.1-safe.
<#
.SYNOPSIS
  DEVLADLOG Windows Server #2 - promote a Windows Server 2025 VM to the first DC of a new lab forest.

.DESCRIPTION
  Run on the VM that becomes CON-DC01 (Windows Server 2025, static IP, isolated lab network).
  1. Installs the AD DS role and its management tools.
  2. Runs Test-ADDSForestInstallation (real prerequisite checks, unlike -WhatIf).
  3. Promotes the server with Install-ADDSForest. The DNS Server role is installed by default with a new forest.
  The server restarts at the end unless -NoReboot is given.

  New forests need at least the Windows Server 2016 functional level. Learn's install guide uses -ForestMode Win2025;
  the Install-ADDSForest reference page still lists values only up to WinThreshold. The script reads the values
  your server actually accepts and stops with a clear message if the one you asked for isn't there.

.EXAMPLE
  ./New-LabForest.ps1 -DomainName lab.contoso.com -NetbiosName CONTOSOLAB -WhatIf
  ./New-LabForest.ps1 -DomainName lab.contoso.com -NetbiosName CONTOSOLAB
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9-]+(\.[a-z0-9-]+)+$')][string] $DomainName,
    [Parameter(Mandatory)][ValidateLength(1, 15)][string] $NetbiosName,
    [string] $FunctionalLevel = 'Win2025',
    [securestring] $SafeModePassword,
    [switch] $NoReboot
)
$ErrorActionPreference = 'Stop'

$os = Get-CimInstance -ClassName Win32_OperatingSystem
if ($os.ProductType -eq 1) { throw 'This is a client OS. Run it on Windows Server.' }
if ((Get-CimInstance -ClassName Win32_ComputerSystem).DomainRole -ge 4) { throw 'This server is already a domain controller.' }

$dhcp = Get-NetIPInterface -AddressFamily IPv4 -ConnectionState Connected | Where-Object { $_.Dhcp -eq 'Enabled' -and $_.InterfaceAlias -notlike 'Loopback*' }
if ($dhcp) { Write-Warning "Interface(s) $($dhcp.InterfaceAlias -join ', ') use DHCP. Give a domain controller a static IP before promoting it." }

# 1. Role + tools (idempotent: Install-WindowsFeature skips what is already installed)
if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, 'Install-WindowsFeature AD-Domain-Services -IncludeManagementTools')) {
    $r = Install-WindowsFeature -Name AD-Domain-Services -IncludeManagementTools
    if (-not $r.Success) { throw "Install-WindowsFeature failed: $($r.ExitCode)" }
}
if (-not (Get-Module -ListAvailable -Name ADDSDeployment)) {
    Write-Host 'ADDSDeployment is not installed yet (a -WhatIf run skips the role install). Stopping here.'
    return
}
Import-Module ADDSDeployment

# 2. Which functional levels does THIS server accept?
$accepted = (Get-Command Install-ADDSForest).Parameters['ForestMode'].ParameterType.GetEnumNames()
Write-Host "ForestMode values accepted here: $($accepted -join ', ')"
if ($accepted -notcontains $FunctionalLevel) {
    throw "Functional level '$FunctionalLevel' isn't accepted on this server. Pick one of: $($accepted -join ', ') (Windows Server 2016 or later for a new forest)."
}

if (-not $SafeModePassword) { $SafeModePassword = Read-Host -AsSecureString 'Directory Services Restore Mode (DSRM) password' }

$forest = @{
    DomainName                    = $DomainName
    DomainNetbiosName             = $NetbiosName
    DomainMode                    = $FunctionalLevel
    ForestMode                    = $FunctionalLevel
    InstallDns                    = $true
    SafeModeAdministratorPassword = $SafeModePassword
    DatabasePath                  = 'C:\Windows\NTDS'
    LogPath                       = 'C:\Windows\NTDS'
    SysvolPath                    = 'C:\Windows\SYSVOL'
}

# 3. Prerequisite checks, then the promotion
$test = Test-ADDSForestInstallation @forest -WarningAction SilentlyContinue
$test | Format-List Status, Message | Out-String -Width 200 | Write-Host
if ($test.Status -ne 'Success') { throw 'Prerequisite checks failed (see above).' }

if ($PSCmdlet.ShouldProcess($DomainName, 'Install-ADDSForest (the server restarts afterwards)')) {
    Install-ADDSForest @forest -NoRebootOnCompletion:$NoReboot -Force
}
