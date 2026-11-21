<#
.SYNOPSIS
  DEVLADLOG Windows Server #4 - install and finish the DHCP Server role (run on CON-SRV01 and CON-SRV02, elevated).
.DESCRIPTION
  The steps from Learn's "Deploy DHCP using Windows PowerShell": install the role, create the DHCP Administrators
  and DHCP Users local groups, restart the service so they take effect, and tell Server Manager the post-install
  configuration is done. Authorization in AD, bindings, scopes and failover are done by Invoke-NetLabDhcpDeployment.
#>
[CmdletBinding(SupportsShouldProcess)]
param()
$ErrorActionPreference = 'Stop'
if (-not (Get-WindowsFeature -Name DHCP).Installed) {
    if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, 'Install-WindowsFeature DHCP -IncludeManagementTools')) {
        Install-WindowsFeature -Name DHCP -IncludeManagementTools | Out-Null
    }
}
if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, 'netsh dhcp add securitygroups; Restart-Service dhcpserver')) {
    netsh dhcp add securitygroups | Out-Null
    Restart-Service -Name dhcpserver
}
if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, 'Server Manager: DHCP post-install configuration complete')) {
    Set-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\ServerManager\Roles\12' -Name ConfigurationState -Value 2
}
