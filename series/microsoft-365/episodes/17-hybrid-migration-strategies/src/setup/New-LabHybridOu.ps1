#Requires -Version 7.2
#Requires -Modules ActiveDirectory
<#
.SYNOPSIS
    Seeds the lab domain with one OU of six DISABLED, fictional accounts that contain the problems the directory check looks for.
.DESCRIPTION
    Run on a lab domain member (CON-SRV02) as a lab Domain Admin. Only the OU named by -OuName is touched; it must not exist yet.
    The accounts are created disabled, so no password is needed or stored. Remove everything with Remove-LabHybridOu.ps1.
    What AD itself refuses and therefore cannot be seeded: a duplicate userPrincipalName, a sAMAccountName over 20 characters.
.EXAMPLE
    ./New-LabHybridOu.ps1 -Server 10.50.0.10 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param([string]$Server, [string]$OuName = 'MG Lab Hybrid')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$srv = @{}; if ($Server) { $srv.Server = $Server }
$domain = Get-ADDomain @srv
$ouDn = "OU=$OuName,$($domain.DistinguishedName)"
if (Get-ADOrganizationalUnit -Filter "distinguishedName -eq '$ouDn'" @srv) { throw "OU '$ouDn' already exists: remove it first or choose another -OuName." }
$suffix = $domain.DNSRoot   # lab.contoso.com: not a verified domain in the tenant, which is the first real finding

# Sam, display name, UPN local part, mail, proxyAddresses
$users = @(
    @{ Sam = 'hy.alex';   Given = 'Alex';   Upn = "hy.alex@$suffix";   Mail = 'hy.alex@contoso.com';  Proxy = @('SMTP:hy.alex@contoso.com') }
    @{ Sam = 'hy.sam';    Given = 'Sam';    Upn = "hy.sam@$suffix";    Mail = 'hy.sam@contoso.com';   Proxy = @('SMTP:hy.sam@contoso.com') }
    @{ Sam = 'hy.jordan'; Given = 'Jordan'; Upn = "hy.jordan@$suffix"; Mail = 'hy.jordan@contoso.com'; Proxy = @('SMTP:hy.jordan@contoso.com', 'smtp:hy jordan.old@contoso.com') }   # a space
    @{ Sam = 'hy.riley';  Given = 'Riley';  Upn = "hy.riley@$suffix";  Mail = 'hy.shared@contoso.com'; Proxy = @('SMTP:hy.riley@contoso.com', 'smtp:hy.shared@contoso.com') }       # same mail as taylor
    @{ Sam = 'hy.taylor'; Given = 'Taylor'; Upn = "hy.taylor@$suffix"; Mail = 'hy.shared@contoso.com'; Proxy = @('SMTP:hy.taylor@contoso.com', 'smtp:hy.shared@contoso.com') }
    @{ Sam = 'hy.josee';  Given = 'Josee';  Upn = "hy.jos$([char]0xE9)e@$suffix"; Mail = 'hy.josee@contoso.com'; Proxy = @('SMTP:hy.josee@contoso.com') }                              # an accent
)
if ($PSCmdlet.ShouldProcess($ouDn, 'Create OU')) { New-ADOrganizationalUnit -Name $OuName -Path $domain.DistinguishedName -ProtectedFromAccidentalDeletion $false @srv }
foreach ($u in $users) {
    if ($PSCmdlet.ShouldProcess("CN=$($u.Sam),$ouDn", "Create disabled user $($u.Upn)")) {
        New-ADUser -Name $u.Sam -SamAccountName $u.Sam -GivenName $u.Given -Surname 'Demo' -DisplayName "$($u.Given) Demo (hybrid lab)" `
            -UserPrincipalName $u.Upn -EmailAddress $u.Mail -Path $ouDn -Enabled $false `
            -OtherAttributes @{ proxyAddresses = [string[]]$u.Proxy; mailNickname = $u.Sam } @srv
    }
}
Write-Host "Seeded $($users.Count) disabled accounts in $ouDn"
