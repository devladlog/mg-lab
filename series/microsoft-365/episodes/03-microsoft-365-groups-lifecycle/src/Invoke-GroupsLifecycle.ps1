#Requires -Version 7.2
<#
.SYNOPSIS
    Microsoft 365 groups lifecycle from one file (lifecycle.json): audit, apply the expiration policy, renew,
    restore a deleted group, archive a team.

.EXAMPLE
    ./Invoke-GroupsLifecycle.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -Now 2026-11-20T09:30:00Z -OutFile ../sample/lifecycle-audit.md   # offline
.EXAMPLE
    ./Invoke-GroupsLifecycle.ps1 -Audit -OutFile ./lifecycle-audit.md -SaveInventory ./inventory.json
.EXAMPLE
    ./Invoke-GroupsLifecycle.ps1 -ApplyExpirationPolicy -WhatIf
.EXAMPLE
    ./Invoke-GroupsLifecycle.ps1 -Renew <group id>
.EXAMPLE
    ./Invoke-GroupsLifecycle.ps1 -Restore <deleted group id>
.EXAMPLE
    ./Invoke-GroupsLifecycle.ps1 -Archive <team id> -WhatIf
#>
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Audit', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'ApplyExpirationPolicy', Justification = 'Selects the parameter set')]
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Audit')]
param(
    [Parameter(ParameterSetName = 'Audit', Mandatory)][switch]$Audit,
    [Parameter(ParameterSetName = 'Audit')][string]$InventoryFile,
    [Parameter(ParameterSetName = 'Audit')][string]$SaveInventory,
    [Parameter(ParameterSetName = 'Audit')][string]$OutFile,
    [Parameter(ParameterSetName = 'Audit')][switch]$FailOnHigh,

    [Parameter(ParameterSetName = 'Policy', Mandatory)][switch]$ApplyExpirationPolicy,
    [Parameter(ParameterSetName = 'Policy')][string]$ImpactInventoryFile,

    [Parameter(ParameterSetName = 'Renew', Mandatory)][string]$Renew,
    [Parameter(ParameterSetName = 'Restore', Mandatory)][string]$Restore,
    [Parameter(ParameterSetName = 'Archive', Mandatory)][string]$Archive,

    [string]$PolicyFile = (Join-Path $PSScriptRoot 'lifecycle.json'),
    [datetimeoffset]$Now = [datetimeoffset]::UtcNow
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'GroupsLifecycle/GroupsLifecycle.psd1') -Force
$config = Get-GroupsLifecycleConfig -Path $PolicyFile

function Connect-GroupsLifecycleGraph([string[]]$Scopes) {
    Import-Module Microsoft.Graph.Authentication
    if (-not (Get-MgContext)) { Connect-MgGraph -Scopes $Scopes -NoWelcome }
}

switch ($PSCmdlet.ParameterSetName) {
    'Audit' {
        if ($InventoryFile) { $inventory = Get-Content -LiteralPath $InventoryFile -Raw | ConvertFrom-Json }
        else {
            Connect-GroupsLifecycleGraph 'Directory.Read.All', 'Group.Read.All', 'GroupMember.Read.All'
            $inventory = Get-GroupsLifecycleInventory
            if ($SaveInventory) { $inventory | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $SaveInventory -Encoding utf8 }
        }
        $findings = @(Get-GroupsLifecycleFinding -Inventory $inventory -Config $config -Now $Now)
        $rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
        $findings | Sort-Object { $rank[$_.Severity] }, Target, Rule | Format-Table Severity, Target, Rule, Detail -AutoSize -Wrap |
            Out-String -Width 200 | Out-Host
        $high = @($findings | Where-Object Severity -EQ 'High').Count
        Write-Information "$($findings.Count) findings ($high High)." -InformationAction Continue
        if ($OutFile) {
            ConvertTo-GroupsLifecycleMarkdown -Inventory $inventory -Findings $findings -Now $Now | Set-Content -LiteralPath $OutFile -Encoding utf8
            Write-Information "Audit written to $OutFile" -InformationAction Continue
        }
        if ($FailOnHigh -and $high) { exit 1 }
    }
    'Policy' {
        # Impact preview first: which groups would start with 35 days? From a saved inventory (offline) or live.
        if ($ImpactInventoryFile) { $inv = Get-Content -LiteralPath $ImpactInventoryFile -Raw | ConvertFrom-Json }
        else {
            Connect-GroupsLifecycleGraph 'Directory.ReadWrite.All', 'Group.Read.All', 'GroupMember.Read.All'
            $inv = Get-GroupsLifecycleInventory
        }
        $only = if ($config.expiration.managedGroupTypes -eq 'Selected') { @($config.expiration.selectedGroupIds) } else { $null }
        $impact = @(Get-ExpirationRolloutImpact -Groups @($inv.groups) -LifetimeDays $config.expiration.groupLifetimeInDays -Now $Now -OnlyGroupIds $only)
        $impact | Format-Table Group, AgeDays, Outcome, ExpiresAround -AutoSize | Out-String -Width 200 | Out-Host
        if ($ImpactInventoryFile -and $WhatIfPreference) { return }   # offline preview: nothing to connect to
        Connect-GroupsLifecycleGraph 'Directory.ReadWrite.All'
        Set-GroupsExpirationPolicy -Config $config | Format-Table Step, Target, Result -AutoSize | Out-String -Width 200 | Out-Host
    }
    'Renew' {
        if (-not $WhatIfPreference) { Connect-GroupsLifecycleGraph 'Group.ReadWrite.All' }
        Invoke-GroupRenewal -GroupId $Renew | Format-List | Out-String -Width 200 | Out-Host
    }
    'Restore' {
        Connect-GroupsLifecycleGraph 'Group.ReadWrite.All'
        Restore-DeletedM365Group -GroupId $Restore -Now $Now | Format-List | Out-String -Width 200 | Out-Host
    }
    'Archive' {
        Connect-GroupsLifecycleGraph 'TeamSettings.ReadWrite.All', 'GroupMember.Read.All'
        Invoke-TeamArchive -TeamId $Archive -SetSpoSiteReadOnlyForMembers:([bool]$config.endOfLife.setSpoSiteReadOnlyForMembers) | Format-List | Out-String -Width 200 | Out-Host
    }
}
