#Requires -Version 7.2
<#
.SYNOPSIS
    Teams governance from one policy file: audit every team, create teams that follow the rules, and push the
    naming policy and creation restriction to the tenant.

.EXAMPLE
    ./Invoke-TeamsGovernance.ps1 -Audit -OutFile ./teams-audit.md -SaveInventory ./inventory.json
.EXAMPLE
    ./Invoke-TeamsGovernance.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -OutFile ../sample/teams-audit.md   # offline
.EXAMPLE
    ./Invoke-TeamsGovernance.ps1 -NewTeam 'Project Falcon' -Department Finance -OwnerIds <id1>,<id2> -WhatIf
.EXAMPLE
    ./Invoke-TeamsGovernance.ps1 -ApplyTenantPolicy -WhatIf
#>
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Audit', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'ApplyTenantPolicy', Justification = 'Selects the parameter set')]
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Audit')]
param(
    [Parameter(ParameterSetName = 'Audit', Mandatory)][switch]$Audit,
    [Parameter(ParameterSetName = 'Audit')][string]$InventoryFile,
    [Parameter(ParameterSetName = 'Audit')][string]$SaveInventory,
    [Parameter(ParameterSetName = 'Audit')][string]$OutFile,

    [Parameter(ParameterSetName = 'NewTeam', Mandatory)][string]$NewTeam,
    [Parameter(ParameterSetName = 'NewTeam', Mandatory)][string]$Department,
    [Parameter(ParameterSetName = 'NewTeam', Mandatory)][string[]]$OwnerIds,
    [Parameter(ParameterSetName = 'NewTeam')][string]$Description = '',
    [Parameter(ParameterSetName = 'NewTeam')][ValidateSet('private', 'public')][string]$Visibility,

    [Parameter(ParameterSetName = 'Tenant', Mandatory)][switch]$ApplyTenantPolicy,

    [string]$PolicyFile = (Join-Path $PSScriptRoot 'governance.json')
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'TeamsGovernance/TeamsGovernance.psd1') -Force
$policy = Get-TeamsGovernancePolicy -Path $PolicyFile

function Connect-TeamsGovernanceGraph([string[]]$Scopes) {
    Import-Module Microsoft.Graph.Authentication
    if (-not (Get-MgContext)) { Connect-MgGraph -Scopes $Scopes -NoWelcome }
}

switch ($PSCmdlet.ParameterSetName) {
    'Audit' {
        if ($InventoryFile) {
            $inventory = @(Get-Content -LiteralPath $InventoryFile -Raw | ConvertFrom-Json)
        }
        else {
            Connect-TeamsGovernanceGraph 'Team.ReadBasic.All', 'TeamMember.Read.All', 'Reports.Read.All'
            $inventory = @(Get-TeamsInventory -Period $policy.lifecycle.reportPeriod)
            if ($SaveInventory) { $inventory | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $SaveInventory -Encoding utf8 }
        }
        $findings = @(Get-TeamsGovernanceFinding -Inventory $inventory -Policy $policy)
        $rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
        $findings = @($findings | Sort-Object { $rank[$_.Severity] }, Team)
        $findings | Format-Table Severity, Team, Rule, Detail -AutoSize | Out-String -Width 180 | Out-Host

        if ($OutFile) {
            $md = [System.Collections.Generic.List[string]]::new()
            $md.Add('# Teams governance audit'); $md.Add('')
            $md.Add("$($inventory.Count) teams, $($findings.Count) findings. Policy: ``$($policy.naming.prefixSuffix)``, minimum $($policy.owners.minimum) owners, inactive after $($policy.lifecycle.inactiveDays) days."); $md.Add('')
            $md.Add('| Severity | Team | Rule | Detail |'); $md.Add('|---|---|---|---|')
            foreach ($f in $findings) { $md.Add("| $($f.Severity) | $($f.Team) | $($f.Rule) | $($f.Detail) |") }
            $md.Add(''); $md.Add('| Team | Visibility | Owners | Members | Guests | Days inactive |'); $md.Add('|---|---|---|---|---|---|')
            foreach ($t in $inventory) { $md.Add("| $($t.DisplayName) | $($t.Visibility) | $($t.Owners) | $($t.Members) | $($t.Guests) | $($t.DaysInactive) |") }
            $md | Set-Content -LiteralPath $OutFile -Encoding utf8
            Write-Information "Audit written to $OutFile" -InformationAction Continue
        }
    }
    'NewTeam' {
        # "pwsh -File" passes "a,b" as one string; accept both forms.
        $OwnerIds = @($OwnerIds | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        if (-not $WhatIfPreference) { Connect-TeamsGovernanceGraph 'Team.Create' }
        $splat = @{ RequestedName = $NewTeam; Creator = @{ Department = $Department }; OwnerIds = $OwnerIds; Policy = $policy; Description = $Description }
        if ($Visibility) { $splat.Visibility = $Visibility }
        $result = New-GovernedTeam @splat
        Write-Information "$($result.DisplayName): $($result.Status) $($result.TeamId)" -InformationAction Continue
        if ($result.Status -eq 'WhatIf') { $result.Body | ConvertTo-Json -Depth 6 | Out-Host }
    }
    'Tenant' {
        Connect-TeamsGovernanceGraph 'GroupSettings.ReadWrite.All'
        Set-TeamsDirectoryPolicy -Policy $policy | Format-Table name, value -AutoSize | Out-Host
    }
}
