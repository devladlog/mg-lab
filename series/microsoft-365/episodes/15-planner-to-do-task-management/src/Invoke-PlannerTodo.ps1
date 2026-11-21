#Requires -Version 7.2
<#
.SYNOPSIS
    A Planner plan from one file (plan.json), an audit of it, and a Microsoft To Do focus list.

.EXAMPLE
    ./Invoke-PlannerTodo.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -Now 2026-11-20T09:30:00Z -OutFile ../sample/planner-audit.md   # offline
.EXAMPLE
    ./Invoke-PlannerTodo.ps1 -FocusList -InventoryFile ../tests/fixtures/inventory.json -ForUser sam.demo@contoso.com -Now 2026-11-20T09:30:00Z       # offline preview
.EXAMPLE
    ./Invoke-PlannerTodo.ps1 -ApplyPlan -WhatIf
.EXAMPLE
    ./Invoke-PlannerTodo.ps1 -ApplyPlan
.EXAMPLE
    ./Invoke-PlannerTodo.ps1 -Audit -OutFile ./planner-audit.md -SaveInventory ./inventory.json
.EXAMPLE
    ./Invoke-PlannerTodo.ps1 -FocusList -WhatIf
#>
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'ApplyPlan', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Audit', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'FocusList', Justification = 'Selects the parameter set')]
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Audit')]
param(
    [Parameter(ParameterSetName = 'Plan', Mandatory)][switch]$ApplyPlan,

    [Parameter(ParameterSetName = 'Audit', Mandatory)][switch]$Audit,
    [Parameter(ParameterSetName = 'Audit')][string]$InventoryFile,
    [Parameter(ParameterSetName = 'Audit')][string]$SaveInventory,
    [Parameter(ParameterSetName = 'Audit')][string]$OutFile,
    [Parameter(ParameterSetName = 'Audit')][switch]$FailOnHigh,

    [Parameter(ParameterSetName = 'Focus', Mandatory)][switch]$FocusList,
    [Parameter(ParameterSetName = 'Focus')][string]$ForUser,   # offline preview: whose tasks to read from -FocusInventoryFile

    [Parameter(ParameterSetName = 'Focus')][string]$FocusInventoryFile,
    [string]$PlanFile = (Join-Path $PSScriptRoot 'plan.json'),
    [datetimeoffset]$Now = [datetimeoffset]::UtcNow
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'PlannerTodo/PlannerTodo.psd1') -Force
$config = Get-PlannerPlanConfig -Path $PlanFile

function Connect-PlannerGraph([string[]]$Scopes) {
    Import-Module Microsoft.Graph.Authentication
    if (-not (Get-MgContext)) { Connect-MgGraph -Scopes $Scopes -NoWelcome }
}

switch ($PSCmdlet.ParameterSetName) {
    'Plan' {
        Connect-PlannerGraph 'Tasks.ReadWrite', 'User.ReadBasic.All'
        Set-PlannerPlan -Config $config -Today $Now -WhatIf:$WhatIfPreference | Format-Table -AutoSize | Out-String -Width 200 | Out-Host
    }
    'Audit' {
        if ($InventoryFile) { $inventory = Get-Content -LiteralPath $InventoryFile -Raw | ConvertFrom-Json }
        else {
            Connect-PlannerGraph 'Tasks.Read', 'User.ReadBasic.All'
            $inventory = Get-PlannerInventory -GroupId $config.plan.groupId -PlanTitle $config.plan.title
            if (-not $inventory) { throw "No plan titled '$($config.plan.title)' in group $($config.plan.groupId). Run -ApplyPlan first." }
            if ($SaveInventory) { $inventory | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SaveInventory -Encoding utf8 }
        }
        $findings = @(Get-PlannerFinding -Inventory $inventory -Config $config -Now $Now)
        $findings | Format-Table Severity, Target, Rule, Detail -AutoSize -Wrap | Out-String -Width 220 | Out-Host
        if ($OutFile) { ConvertTo-PlannerMarkdown -Inventory $inventory -Finding $findings -Now $Now | Set-Content -LiteralPath $OutFile -Encoding utf8; Write-Output "Report: $OutFile" }
        if ($FailOnHigh -and ($findings | Where-Object Severity -eq 'High')) { exit 2 }
    }
    'Focus' {
        if ($FocusInventoryFile -or $ForUser) {
            # Offline preview: which tasks of this user would land in the To Do list?
            if (-not $FocusInventoryFile) { throw 'Give -FocusInventoryFile with -ForUser.' }
            $inv = Get-Content -LiteralPath $FocusInventoryFile -Raw | ConvertFrom-Json
            $uid = $inv.users.PSObject.Properties | Where-Object { $_.Value.upn -eq $ForUser } | ForEach-Object { $_.Name } | Select-Object -First 1
            if (-not $uid) { throw "$ForUser is not an assignee in the inventory." }
            $mine = @($inv.tasks | Where-Object { $uid -in @($_.assignees) })
            Get-PlannerFocusTask -Task $mine -PlanId $inv.plan.id -Now $Now -DueWithinDays $config.focus.dueWithinDays |
                ForEach-Object { [pscustomobject]@{ Title = $_.title; Due = $_.dueDateTime; Importance = ConvertTo-TodoImportance ([int]$_.priority) } } |
                Format-Table -AutoSize | Out-String -Width 200 | Out-Host
        }
        else {
            # Delegated sign-in as the user whose To Do list it is: To Do tasks do not support application permissions.
            Connect-PlannerGraph 'Tasks.ReadWrite'
            $plans = @(Invoke-PLGraphGet "/v1.0/groups/$($config.plan.groupId)/planner/plans" | Where-Object { $_.title -eq $config.plan.title })
            if ($plans.Count -ne 1) { throw "Expected one plan titled '$($config.plan.title)' (found $($plans.Count)). Run -ApplyPlan first." }
            Sync-PlannerFocusToTodo -PlanId $plans[0].id -PlanTitle $config.plan.title -ListName $config.focus.listName `
                -DueWithinDays $config.focus.dueWithinDays -Now $Now -WhatIf:$WhatIfPreference | Format-Table -AutoSize | Out-String -Width 200 | Out-Host
        }
    }
}
