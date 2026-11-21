<#
.SYNOPSIS
Creates the AD group that the session collection allows (CONTOSO\RDS Demo Users) and adds the lab demo users. Idempotent. Needs the ActiveDirectory module (RSAT) and Domain Admin rights; run on CON-SRV02 or CON-DC01.
.EXAMPLE
./New-RdsDemoGroup.ps1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $GroupName = 'RDS Demo Users',
    [string[]] $Members = @('alex.demo', 'sam.demo'),
    [string] $Path
)
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory
if (-not $Path) { $Path = "CN=Users,$((Get-ADDomain).DistinguishedName)" }
if (-not (Get-ADGroup -Filter "Name -eq '$GroupName'" -ErrorAction SilentlyContinue)) {
    if ($PSCmdlet.ShouldProcess($GroupName, "Create global security group in $Path")) {
        New-ADGroup -Name $GroupName -GroupScope Global -GroupCategory Security -Path $Path -Description 'Allowed to use the lab RDS collection (episode 11)'
    }
}
foreach ($m in $Members) {
    if ($PSCmdlet.ShouldProcess($m, "Add to $GroupName")) { Add-ADGroupMember -Identity $GroupName -Members $m }
}
