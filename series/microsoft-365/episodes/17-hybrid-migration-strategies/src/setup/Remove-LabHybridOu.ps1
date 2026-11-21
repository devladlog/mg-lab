#Requires -Version 7.2
#Requires -Modules ActiveDirectory
<# Removes the OU created by New-LabHybridOu.ps1 and the accounts in it. Refuses any OU that holds an account whose sAMAccountName does not start with "hy.". #>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param([string]$Server, [string]$OuName = 'MG Lab Hybrid')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$srv = @{}; if ($Server) { $srv.Server = $Server }
$ouDn = "OU=$OuName,$((Get-ADDomain @srv).DistinguishedName)"
$members = @(Get-ADObject -SearchBase $ouDn -SearchScope Subtree -Filter * -Properties sAMAccountName @srv | Where-Object { $_.DistinguishedName -ne $ouDn })
$foreign = @($members | Where-Object { $_.ObjectClass -ne 'user' -or ([string]$_.sAMAccountName) -notlike 'hy.*' })
if ($foreign.Count) { throw "Refusing: $($foreign.Count) object(s) in $ouDn are not lab accounts (hy.*): $($foreign.DistinguishedName -join '; ')" }
if ($PSCmdlet.ShouldProcess($ouDn, "Remove the OU and $($members.Count) account(s)")) {
    Remove-ADOrganizationalUnit -Identity $ouDn -Recursive -Confirm:$false @srv
    Write-Host "Removed $ouDn"
}
