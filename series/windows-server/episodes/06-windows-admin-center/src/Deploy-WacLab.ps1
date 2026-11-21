<#
.SYNOPSIS
Sets up Windows Admin Center on the gateway (CON-SRV02) step by step. Run elevated on the gateway, in Windows
PowerShell 5.1, as a lab domain admin. Every step supports -WhatIf.
.PARAMETER Step
Install      silent install in Administration Mode (needs -InstallerPath)
Sso          resource-based constrained delegation from the gateway to each node with KerberosSso (needs RSAT-AD-PowerShell)
Connections  writes, validates and imports the shared connections (needs the access key from Settings > Advanced)
Rbac         after role-based access control was applied to a node in the UI: adds the configured members and checks
.EXAMPLE
.\Deploy-WacLab.ps1 -Step Install -InstallerPath C:\lab\WindowsAdminCenter.exe
.\Deploy-WacLab.ps1 -Step Sso -WhatIf
.\Deploy-WacLab.ps1 -Step Connections -AccessKey (Read-Host -AsSecureString 'Access key') -Credential (Get-Credential)
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [ValidateSet('Install', 'Sso', 'Connections', 'Rbac')] [string] $Step,
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'wac-lab.json'),
    [string] $InstallerPath,
    [securestring] $AccessKey,
    [pscredential] $Credential,
    [switch] $Remove
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'WacLab/WacLab.psd1') -Force
$config = Read-WacLabConfig -Path $ConfigPath

switch ($Step) {
    'Install' {
        if (-not $InstallerPath) { throw '-InstallerPath is required for -Step Install.' }
        Install-WacGateway -Config $config -InstallerPath $InstallerPath -Confirm:$false -WhatIf:$WhatIfPreference
    }
    'Sso' {
        Set-WacKerberosDelegation -Config $config -Remove:$Remove -WhatIf:$WhatIfPreference |
            Format-Table Node, Action, Result, @{ n = 'Kept'; e = { @($_.Kept).Count } } -AutoSize
    }
    'Connections' {
        if (-not $AccessKey) { throw '-AccessKey is required for -Step Connections (Settings > Advanced).' }
        Import-WacLabConnection -Config $config -AccessKey $AccessKey -Credential $Credential -WhatIf:$WhatIfPreference
    }
    'Rbac' {
        Add-WacRbacMember -Config $config -Credential $Credential -WhatIf:$WhatIfPreference
        $f = @(Test-WacRbac -Status @(Get-WacRbacStatus -Config $config -Credential $Credential) -Config $config)
        if ($f.Count) { $f | Format-Table Severity, Target, Check, Message -Wrap } else { 'RBAC matches wac-lab.json.' }
    }
}
