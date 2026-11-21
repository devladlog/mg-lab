#Requires -Version 5.1
<#
.SYNOPSIS
Creates the identities for episode 5 in lab.contoso.com: the two JEA groups and the gMSA the scheduled task runs as.
Run on CON-DC01 (or any machine with the ActiveDirectory module) as a lab domain admin.

.DESCRIPTION
- GG-AppOps-Readers   -> role AppOpsReader (helpdesk: health only)
- GG-AppOps-Operators -> roles AppOpsReader + AppOpsOperator (the runbook)
- gMSA gmsa-opsjob: only CON-SRV02 may retrieve its password; AES only; member of GG-AppOps-Operators
- A KDS root key is required for gMSAs. -CreateLabKdsRootKey creates one that is usable immediately
  (EffectiveTime 10 hours in the past): Learn documents that ONLY for test environments with a single DC.

.EXAMPLE
.\New-OpsJobIdentity.ps1 -HelpdeskUser alex.demo -WhatIf
.\New-OpsJobIdentity.ps1 -HelpdeskUser alex.demo -CreateLabKdsRootKey
.\New-OpsJobIdentity.ps1 -HelpdeskUser alex.demo -Remove
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $GmsaName = 'gmsa-opsjob',
    [string] $JobHost = 'CON-SRV02',
    [string] $ReadersGroup = 'GG-AppOps-Readers',
    [string] $OperatorsGroup = 'GG-AppOps-Operators',
    [string] $HelpdeskUser,
    [switch] $CreateLabKdsRootKey,
    [switch] $Remove
)
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory
$domain = Get-ADDomain

function Get-Quiet([scriptblock] $Lookup) { try { & $Lookup } catch { $null } }

if ($Remove) {
    $g = Get-Quiet { Get-ADServiceAccount -Identity $GmsaName }
    if ($g -and $PSCmdlet.ShouldProcess($GmsaName, 'Remove gMSA')) { Remove-ADServiceAccount -Identity $GmsaName -Confirm:$false }
    foreach ($name in $OperatorsGroup, $ReadersGroup) {
        $grp = Get-Quiet { Get-ADGroup -Identity $name }
        if ($grp -and $PSCmdlet.ShouldProcess($name, 'Remove group')) { Remove-ADGroup -Identity $name -Confirm:$false }
    }
    # The KDS root key is left in place on purpose: deleting and re-creating one causes caching issues (Learn).
    return
}

# 1. KDS root key
if (-not (Get-KdsRootKey)) {
    if (-not $CreateLabKdsRootKey) {
        throw 'No KDS root key in the forest. Create one (production: Add-KdsRootKey -EffectiveImmediately, then wait up to 10 hours), or rerun with -CreateLabKdsRootKey in a single-DC lab.'
    }
    if ($PSCmdlet.ShouldProcess($domain.Forest, 'Add-KdsRootKey -EffectiveTime (now - 10h)  [single-DC lab only]')) {
        Add-KdsRootKey -EffectiveTime ((Get-Date).AddHours(-10)) | Out-Null
    }
}

# 2. Groups
foreach ($name in $ReadersGroup, $OperatorsGroup) {
    if (-not (Get-Quiet { Get-ADGroup -Identity $name })) {
        if ($PSCmdlet.ShouldProcess($name, 'New-ADGroup (Global, Security)')) {
            New-ADGroup -Name $name -GroupScope Global -GroupCategory Security -Description 'JEA endpoint Contoso.AppOps (episode 5)'
        }
    }
}
if ($HelpdeskUser -and $PSCmdlet.ShouldProcess($ReadersGroup, "Add member $HelpdeskUser")) {
    Add-ADGroupMember -Identity $ReadersGroup -Members $HelpdeskUser
}

# 3. gMSA (only the job host retrieves the password; AES, as Learn recommends for MSAs)
$hostAccount = Get-ADComputer -Identity $JobHost
if (-not (Get-Quiet { Get-ADServiceAccount -Identity $GmsaName })) {
    if ($PSCmdlet.ShouldProcess($GmsaName, "New-ADServiceAccount (password retrievable by $JobHost)")) {
        New-ADServiceAccount -Name $GmsaName -DNSHostName "$GmsaName.$($domain.DNSRoot)" `
            -PrincipalsAllowedToRetrieveManagedPassword $hostAccount -KerberosEncryptionType AES128, AES256 `
            -Description 'Runs the Contoso OpsJob scheduled task on CON-SRV02 (episode 5)'
    }
}
if ($PSCmdlet.ShouldProcess($OperatorsGroup, "Add member $GmsaName`$")) {
    $gmsa = Get-Quiet { Get-ADServiceAccount -Identity $GmsaName }
    if ($gmsa) { Add-ADGroupMember -Identity $OperatorsGroup -Members $gmsa }
}

Get-ADServiceAccount -Identity $GmsaName -Properties PrincipalsAllowedToRetrieveManagedPassword, KerberosEncryptionType, MemberOf -ErrorAction SilentlyContinue |
    Select-Object Name, SamAccountName, KerberosEncryptionType, PrincipalsAllowedToRetrieveManagedPassword, MemberOf
