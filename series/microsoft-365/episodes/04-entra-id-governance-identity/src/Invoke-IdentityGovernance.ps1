#Requires -Version 7.2
<#
.SYNOPSIS
    Microsoft Entra ID Governance from one file (governance.json): audit privileged access, guest reviews and
    leaver workflows; make admins eligible instead of permanent; create the guest review and the leaver workflow;
    run the leaver workflow for one user after a pre-flight.

.EXAMPLE
    ./Invoke-IdentityGovernance.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -Now 2026-11-20T09:30:00Z -OutFile ../sample/governance-audit.md   # offline
.EXAMPLE
    ./Invoke-IdentityGovernance.ps1 -Audit -OutFile ./governance-audit.md -SaveInventory ./inventory.json
.EXAMPLE
    ./Invoke-IdentityGovernance.ps1 -Preview -Now 2026-11-20T09:30:00Z     # offline: print the three request bodies and the guest-billing check
.EXAMPLE
    ./Invoke-IdentityGovernance.ps1 -AssignEligible -WhatIf
.EXAMPLE
    ./Invoke-IdentityGovernance.ps1 -CreateGuestReview -StartDate 2026-12-01 -WhatIf
.EXAMPLE
    ./Invoke-IdentityGovernance.ps1 -CreateLeaverWorkflow -WhatIf
.EXAMPLE
    ./Invoke-IdentityGovernance.ps1 -RunLeaver -WorkflowId <id> -UserId <id> -WhatIf
#>
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Audit', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Preview', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'AssignEligible', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'CreateGuestReview', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'CreateLeaverWorkflow', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'RunLeaver', Justification = 'Selects the parameter set')]
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Audit')]
param(
    [Parameter(ParameterSetName = 'Audit', Mandatory)][switch]$Audit,
    [Parameter(ParameterSetName = 'Audit')][string]$InventoryFile,
    [Parameter(ParameterSetName = 'Audit')][string]$SaveInventory,
    [Parameter(ParameterSetName = 'Audit')][string]$OutFile,
    [Parameter(ParameterSetName = 'Audit')][switch]$FailOnHigh,

    [Parameter(ParameterSetName = 'Preview', Mandatory)][switch]$Preview,
    [Parameter(ParameterSetName = 'Eligible', Mandatory)][switch]$AssignEligible,
    [Parameter(ParameterSetName = 'Review', Mandatory)][switch]$CreateGuestReview,
    [Parameter(ParameterSetName = 'Review')][Parameter(ParameterSetName = 'Preview')][datetime]$StartDate = [datetime]::UtcNow.Date.AddDays(1),
    [Parameter(ParameterSetName = 'Workflow', Mandatory)][switch]$CreateLeaverWorkflow,

    [Parameter(ParameterSetName = 'Run', Mandatory)][switch]$RunLeaver,
    [Parameter(ParameterSetName = 'Run', Mandatory)][string]$WorkflowId,
    [Parameter(ParameterSetName = 'Run', Mandatory)][string]$UserId,
    [Parameter(ParameterSetName = 'Run')][switch]$Force,

    [string]$PolicyFile = (Join-Path $PSScriptRoot 'governance.json'),
    [datetimeoffset]$Now = [datetimeoffset]::UtcNow
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'IdentityGovernance/IdentityGovernance.psd1') -Force
$config = Get-IdentityGovernanceConfig -Path $PolicyFile

function Connect-IdentityGovernanceGraph([string[]]$Scopes) {
    Import-Module Microsoft.Graph.Authentication
    if (-not (Get-MgContext)) { Connect-MgGraph -Scopes $Scopes -NoWelcome }
}
function Show-Table($InputObject, [string[]]$Property) { $InputObject | Format-Table $Property -AutoSize -Wrap | Out-String -Width 200 | Out-Host }

switch ($PSCmdlet.ParameterSetName) {
    'Audit' {
        if ($InventoryFile) { $inventory = Get-Content -LiteralPath $InventoryFile -Raw | ConvertFrom-Json }
        else {
            Connect-IdentityGovernanceGraph 'RoleAssignmentSchedule.Read.Directory', 'RoleEligibilitySchedule.Read.Directory', 'AccessReview.Read.All', 'LifecycleWorkflows-Workflow.ReadBasic.All'
            $inventory = Get-IdentityGovernanceInventory
            if ($SaveInventory) { $inventory | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $SaveInventory -Encoding utf8 }
        }
        $findings = @(Get-IdentityGovernanceFinding -Inventory $inventory -Config $config -Now $Now)
        $rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
        Show-Table ($findings | Sort-Object { $rank[$_.Severity] }, Target, Rule) Severity, Target, Rule, Detail
        $high = @($findings | Where-Object Severity -EQ 'High').Count
        Write-Information "$($findings.Count) findings ($high High)." -InformationAction Continue
        if ($OutFile) {
            ConvertTo-IdentityGovernanceMarkdown -Inventory $inventory -Findings $findings -Now $Now | Set-Content -LiteralPath $OutFile -Encoding utf8
            Write-Information "Audit written to $OutFile" -InformationAction Continue
        }
        if ($FailOnHigh -and $high) { exit 1 }
    }
    'Preview' {
        foreach ($a in @($config.eligibleAssignments)) { "# PIM eligibility: $($a.principalName) / $($a.role)"; New-PimEligibilityRequest -Assignment $a -Config $config -Now $Now | ConvertTo-Json -Depth 6 }
        $review = New-GuestAccessReviewDefinition -Config $config -StartDate $StartDate
        '# Guest access review'; $review | ConvertTo-Json -Depth 8
        $wf = New-LeaverWorkflowDefinition -Config $config
        '# Leaver workflow'; $wf | ConvertTo-Json -Depth 8
        $b = @(Get-GuestBillingTrigger -Body $review -Kind AccessReview) + @(Get-GuestBillingTrigger -Body $wf -Kind Workflow)
        "# Guest governance add-on needed: $(if ($b.Count) { $b -join '; ' } else { 'no' })"
    }
    'Eligible' {
        Connect-IdentityGovernanceGraph 'RoleEligibilitySchedule.ReadWrite.Directory'
        Show-Table (New-PimEligibleAssignment -Config $config -Now $Now) Principal, Role, Result
    }
    'Review' {
        Connect-IdentityGovernanceGraph 'AccessReview.ReadWrite.All'
        Show-Table (New-GuestAccessReview -Config $config -StartDate $StartDate) Name, Result, Id
    }
    'Workflow' {
        Connect-IdentityGovernanceGraph 'LifecycleWorkflows-Workflow.ReadWrite.All'
        Show-Table (New-LeaverWorkflow -Config $config) Name, Result, Id
    }
    'Run' {
        Connect-IdentityGovernanceGraph 'User.Read.All', 'RoleAssignmentSchedule.Read.Directory', 'RoleEligibilitySchedule.Read.Directory', 'GroupMember.Read.All', 'LifecycleWorkflows-Workflow.Read.All', 'LifecycleWorkflows-Workflow.Activate'
        $r = Invoke-LeaverWorkflow -WorkflowId $WorkflowId -UserId $UserId -Config $config -Force:$Force
        Write-Information "$($r.User): $($r.Status)" -InformationAction Continue
        if ($r.Checks) { Show-Table $r.Checks Level, Check, Detail }
    }
}
