#Requires -Version 7.2
<#
    IdentityGovernance: Microsoft Entra ID Governance as code, driven by governance.json.

      * PIM       - New-PimEligibilityRequest / New-PimEligibleAssignment: time-bound eligible role assignments
                    instead of permanent active ones (roleEligibilityScheduleRequests, action adminAssign).
      * Reviews   - New-GuestAccessReviewDefinition / New-GuestAccessReview: a recurring review of guests in every
                    Microsoft 365 group, decided by the group owners, denied by default, applied automatically.
      * Workflows - New-LeaverWorkflowDefinition / New-LeaverWorkflow / Invoke-LeaverWorkflow: a leaver
                    lifecycle workflow on employeeLeaveDateTime, plus a pre-flight before any on-demand run.
      * Guard     - Get-GuestBillingTrigger: refuses definitions that would need the guest governance add-on
                    (inactive-guest reviews, user-to-group affiliation, workflows scoped to guests).
      * Audit     - Get-IdentityGovernanceInventory + Get-IdentityGovernanceFinding: permanent active privileged
                    roles, emergency access accounts, Global Administrator count, guest review coverage, leaver
                    workflow, and what the end of the governance licence does to PIM.

    Only Invoke-IGGraphGet and the New-*/Invoke-*/Get-*Inventory functions that say so call Microsoft Graph.
#>

Set-StrictMode -Version Latest

# Built-in Lifecycle Workflows task definitions (taskDefinitionId), from "Lifecycle Workflow built-in tasks".
$script:LeaverTasks = [ordered]@{
    'Revoke all refresh tokens for user'      = '509589a4-0466-4471-829e-49c5e502bdee'
    'Remove user from all teams'              = '81f7b200-2816-4b3b-8c5d-dc556f07b024'
    'Remove users from all groups'            = 'b3a31406-2a15-4c9a-b25b-a658fa5f07fc'
    'Disable user account'                    = '1dfdfcc7-52fa-4c2e-bf3a-e3919cc12950'
    'Remove all license assignments from user' = '8fa97d28-3e52-4985-b3a9-a1126f9b8b4e'
    "Send email on user's last day"           = '9c0a1eaf-5bda-4392-9d9e-6e155bb57411'
    'Delete user'                             = '8d18588d-9ad3-4c0f-99d0-ec215f0e3dff'
}
# Membership removals keep going on error (as in the docs' examples); everything else stops the workflow.
$script:ContinueOnError = @('Remove user from all teams', 'Remove users from all groups')
$script:GlobalAdminTemplateId = '62e90394-69f5-4237-9190-012177145e10'
$script:MaxGlobalAdmins = 4   # Microsoft: assign Global Administrator to fewer than five people

#region Helpers ---------------------------------------------------------------------------------------------------

function Get-IGProp {
    param([object]$Object, [string]$Name, [object]$Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { $Default } else { $p.Value }
}

function ConvertTo-IGDate {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value -or "$Value" -eq '') { return $null }
    if ($Value -is [datetimeoffset]) { return $Value.ToUniversalTime() }
    if ($Value -is [datetime]) { return ([datetimeoffset][datetime]::SpecifyKind($Value, 'Utc')) }
    $styles = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
    [datetimeoffset]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture, $styles)
}

function ConvertTo-IGFinding([string]$Severity, [string]$Target, [string]$Rule, [string]$Detail) {
    [pscustomobject]@{ Severity = $Severity; Target = $Target; Rule = $Rule; Detail = $Detail }
}

function Get-IGRoleName {
    param([object]$Config, [string]$TemplateId)
    $r = @($Config.privilegedRoles | Where-Object { $_.templateId -eq $TemplateId }) | Select-Object -First 1
    if ($r) { $r.name } else { $TemplateId }
}

#endregion

#region Config and request bodies (pure) --------------------------------------------------------------------------

function Get-IdentityGovernanceConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $c = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $roles = @($c.privilegedRoles.name)
    foreach ($a in @($c.eligibleAssignments)) {
        if ($a.role -notin $roles) { throw "eligibleAssignments: role '$($a.role)' is not in privilegedRoles." }
        if ([int]$a.durationDays -lt 1) { throw "eligibleAssignments: durationDays must be 1 or more for '$($a.principalName)' (no permanent eligibility from this file)." }
        if ([string]::IsNullOrWhiteSpace($a.justification)) { throw "eligibleAssignments: a justification is required for '$($a.principalName)'." }
    }
    if ([int]$c.guestReview.intervalMonths -lt 1) { throw 'guestReview.intervalMonths must be 1 or more.' }
    if ([int]$c.guestReview.instanceDurationInDays -lt 1) { throw 'guestReview.instanceDurationInDays must be 1 or more.' }
    if ($c.guestReview.defaultDecision -cnotin 'Approve', 'Deny', 'Recommendation') { throw 'guestReview.defaultDecision must be Approve, Deny or Recommendation.' }
    foreach ($t in @($c.leaverWorkflow.tasks)) {
        if (-not $script:LeaverTasks.Contains($t)) { throw "leaverWorkflow: unknown task '$t'. Known: $($script:LeaverTasks.Keys -join '; ')." }
    }
    $c
}

function New-PimEligibilityRequest {
    <# Body for POST /roleManagement/directory/roleEligibilityScheduleRequests (time-bound, tenant-wide scope). #>
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Pure: builds a request body')]
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Assignment, [Parameter(Mandatory)][object]$Config, [Parameter(Mandatory)][datetimeoffset]$Now)
    $role = @($Config.privilegedRoles | Where-Object { $_.name -eq $Assignment.role })[0]
    [ordered]@{
        action           = 'adminAssign'
        justification    = $Assignment.justification
        roleDefinitionId = $role.templateId
        directoryScopeId = '/'
        principalId      = $Assignment.principalId
        scheduleInfo     = [ordered]@{
            startDateTime = $Now.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
            expiration    = [ordered]@{ type = 'afterDateTime'; endDateTime = $Now.AddDays([int]$Assignment.durationDays).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'") }
        }
    }
}

function New-GuestAccessReviewDefinition {
    <#
    .SYNOPSIS  Body for POST /identityGovernance/accessReviews/definitions: guests in every Microsoft 365 group,
               one instance per group, owners decide (fallback reviewer when a group has none), recurring,
               default decision + auto-apply removes denied guests from the group.
    #>
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Pure: builds a request body')]
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Config, [Parameter(Mandatory)][datetime]$StartDate)
    $r = $Config.guestReview
    [ordered]@{
        displayName              = $r.displayName
        scope                    = [ordered]@{
            '@odata.type' = '#microsoft.graph.accessReviewQueryScope'
            query         = "./members/microsoft.graph.user/?`$count=true&`$filter=(userType eq 'Guest')"
            queryType     = 'MicrosoftGraph'
        }
        instanceEnumerationScope = [ordered]@{
            '@odata.type' = '#microsoft.graph.accessReviewQueryScope'
            query         = "/v1.0/groups?`$filter=(groupTypes/any(c:c+eq+'Unified'))&`$count=true"
            queryType     = 'MicrosoftGraph'
        }
        reviewers                = @([ordered]@{ query = './owners'; queryType = 'MicrosoftGraph' })
        fallbackReviewers        = @([ordered]@{ query = "/users/$($r.fallbackReviewerId)"; queryType = 'MicrosoftGraph' })
        settings                 = [ordered]@{
            mailNotificationsEnabled        = $true
            reminderNotificationsEnabled    = $true
            justificationRequiredOnApproval = $true
            defaultDecisionEnabled          = $true
            defaultDecision                 = $r.defaultDecision
            instanceDurationInDays          = [int]$r.instanceDurationInDays
            autoApplyDecisionsEnabled       = [bool]$r.autoApplyDecisionsEnabled
            recommendationsEnabled          = $true
            recommendationLookBackDuration  = 'P30D'
            recurrence                      = [ordered]@{
                # Same shape as Microsoft's "review guest access to groups" tutorial.
                pattern = [ordered]@{ type = 'absoluteMonthly'; interval = [int]$r.intervalMonths; month = 0; dayOfMonth = 0; daysOfWeek = @(); firstDayOfWeek = 'sunday'; index = 'first' }
                range   = [ordered]@{ type = 'endDate'; numberOfOccurrences = 0; recurrenceTimeZone = $null; startDate = $StartDate.ToString('yyyy-MM-dd'); endDate = $StartDate.AddYears(1).ToString('yyyy-MM-dd') }
            }
            applyActions                    = @([ordered]@{ '@odata.type' = '#microsoft.graph.removeAccessApplyAction' })
        }
    }
}

function New-LeaverWorkflowDefinition {
    <# Body for POST /identityGovernance/lifecycleWorkflows/workflows (category leaver, trigger employeeLeaveDateTime). #>
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Pure: builds a request body')]
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Config)
    $w = $Config.leaverWorkflow
    [ordered]@{
        category            = 'leaver'
        displayName         = $w.displayName
        description         = $w.description
        isEnabled           = $true
        isSchedulingEnabled = [bool]$w.isSchedulingEnabled
        executionConditions = [ordered]@{
            '@odata.type' = '#microsoft.graph.identityGovernance.triggerAndScopeBasedConditions'
            scope         = [ordered]@{ '@odata.type' = '#microsoft.graph.identityGovernance.ruleBasedSubjectSet'; rule = $w.scopeRule }
            trigger       = [ordered]@{
                '@odata.type'      = '#microsoft.graph.identityGovernance.timeBasedAttributeTrigger'
                timeBasedAttribute = 'employeeLeaveDateTime'
                offsetInDays       = [int]$w.offsetInDays
            }
        }
        tasks               = @(foreach ($t in @($w.tasks)) {
                [ordered]@{
                    category         = 'leaver'
                    continueOnError  = $t -in $script:ContinueOnError
                    displayName      = $t
                    isEnabled        = $true
                    taskDefinitionId = $script:LeaverTasks[$t]
                    arguments        = @()
                }
            })
    }
}

function Get-GuestBillingTrigger {
    <#
    .SYNOPSIS  Reasons a definition would need the Microsoft Entra ID Governance for guests add-on (an Azure
               subscription linked for MAU billing). Empty = fine with the employee licences alone.
               Learn: without the add-on you can't create guest-scoped reviews with inactive-user scope or the
               user-to-group affiliation helper, nor workflows whose rule includes userType=Guest.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][System.Collections.IDictionary]$Body, [Parameter(Mandatory)][ValidateSet('AccessReview', 'Workflow')][string]$Kind)
    if ($Kind -eq 'AccessReview') {
        $scope = $Body['scope']
        $guests = "$(Get-IGProp $scope 'query')" -match "userType\s+eq\s+'Guest'"
        if (-not $guests) { return }
        if ((Get-IGProp $scope '@odata.type') -eq '#microsoft.graph.accessReviewInactiveUsersQueryScope') { 'Guest review scoped to inactive users' }
        $insights = @(Get-IGProp $Body['settings'] 'recommendationInsightSettings' @())
        if ($insights | Where-Object { "$(Get-IGProp $_ '@odata.type')" -like '*groupPeerOutlierRecommendationInsightSettings' }) { 'Guest review with the user-to-group affiliation helper' }
    }
    else {
        $rule = "$(Get-IGProp (Get-IGProp $Body['executionConditions'] 'scope') 'rule')"
        if ($rule -match "userType\s+eq\s+'Guest'") { 'Workflow scope rule includes guests (userType eq Guest)' }
    }
}

#endregion

#region Pre-flight and findings (pure) ----------------------------------------------------------------------------

function Get-LeaverPreflight {
    <#
    .SYNOPSIS  Before running a leaver workflow on demand: things that make a task fail or leave a mess.
               On-demand runs ignore the workflow's scope and trigger, so the scope rule doesn't protect you here.
    .OUTPUTS   Level (Blocker/Warning), Check, Detail.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$User,
        [AllowEmptyCollection()][object[]]$ActiveAssignments = @(),
        [AllowEmptyCollection()][object[]]$EligibleAssignments = @(),
        [AllowEmptyCollection()][object[]]$OwnedGroups = @(),
        [Parameter(Mandatory)][object]$Config,
        [string[]]$Tasks = @()
    )
    $name = Get-IGProp $User 'displayName'
    if ((Get-IGProp $User 'userType' 'Member') -ne 'Member') {
        [pscustomobject]@{ Level = 'Blocker'; Check = 'GuestSubject'; Detail = "$name is a guest: a workflow run for a guest is a billable guest governance action (needs the add-on)." }
    }
    if ($ActiveAssignments.Count -and 'Disable user account' -in $Tasks) {
        $roles = ($ActiveAssignments | ForEach-Object { Get-IGRoleName $Config $_.roleDefinitionId }) -join ', '
        [pscustomobject]@{ Level = 'Blocker'; Check = 'HoldsEntraRole'; Detail = "$name holds $roles. The Disable user account task doesn't support users with Microsoft Entra role assignments: remove them first." }
    }
    if ($EligibleAssignments.Count) {
        $roles = ($EligibleAssignments | ForEach-Object { Get-IGRoleName $Config $_.roleDefinitionId }) -join ', '
        [pscustomobject]@{ Level = 'Warning'; Check = 'EligibleRole'; Detail = "$name is eligible for $roles in PIM: remove the eligibility as part of the leaver process." }
    }
    foreach ($g in $OwnedGroups) {
        if ([int](Get-IGProp $g 'ownerCount' 0) -le 1) {
            [pscustomobject]@{ Level = 'Warning'; Check = 'SoleOwner'; Detail = "$name is the only owner of '$($g.displayName)': assign a new owner, or the group ends up ownerless." }
        }
    }
}

function Get-IdentityGovernanceFinding {
    <#
    .SYNOPSIS  Judge an inventory (role assignment and eligibility instances, access reviews, workflows) against
               governance.json. OUTPUTS Severity (High/Medium/Low/Info), Target, Rule, Detail.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Inventory, [Parameter(Mandatory)][object]$Config, [Parameter(Mandatory)][datetimeoffset]$Now)
    $privileged = @($Config.privilegedRoles.templateId)
    $breakGlass = @($Config.emergencyAccessAccountIds)
    $active = @(Get-IGProp $Inventory 'activeAssignments' @())
    $eligible = @(Get-IGProp $Inventory 'eligibleAssignments' @())
    $names = @{}; foreach ($p in @(Get-IGProp $Inventory 'principals' @())) { $names[$p.id] = $p.displayName }
    $who = { param($id) if ($names.ContainsKey($id)) { $names[$id] } else { $id } }

    foreach ($a in $active) {
        $isPermanent = (Get-IGProp $a 'assignmentType') -eq 'Assigned' -and $null -eq (ConvertTo-IGDate (Get-IGProp $a 'endDateTime'))
        $role = Get-IGRoleName $Config $a.roleDefinitionId
        if ($isPermanent -and $a.roleDefinitionId -in $privileged -and $a.principalId -notin $breakGlass) {
            ConvertTo-IGFinding High (& $who $a.principalId) 'PermanentActivePrivileged' "$role is permanently active. Keep zero permanent active assignments except emergency access accounts: make it eligible in PIM."
        }
        if ((Get-IGProp $a 'assignmentType') -eq 'Activated') {
            $until = ConvertTo-IGDate (Get-IGProp $a 'endDateTime')
            ConvertTo-IGFinding Info (& $who $a.principalId) 'ActivatedNow' "$role activated through PIM$(if ($until) { " until $($until.ToString('yyyy-MM-dd HH:mm')) UTC" })."
        }
    }

    if ($breakGlass.Count -lt 2) { ConvertTo-IGFinding Medium 'Tenant' 'EmergencyAccessCount' "$($breakGlass.Count) emergency access account(s) configured; Microsoft recommends two cloud-only accounts." }
    foreach ($id in $breakGlass) {
        $ok = $active | Where-Object { $_.principalId -eq $id -and $_.roleDefinitionId -eq $script:GlobalAdminTemplateId -and $_.assignmentType -eq 'Assigned' -and $null -eq (ConvertTo-IGDate (Get-IGProp $_ 'endDateTime')) }
        if (-not $ok) { ConvertTo-IGFinding Medium (& $who $id) 'EmergencyAccessNotPermanent' 'Emergency access accounts should hold Global Administrator as permanent active, not eligible.' }
    }

    $gaPrincipals = @(@($active) + @($eligible) | Where-Object { $_.roleDefinitionId -eq $script:GlobalAdminTemplateId } | ForEach-Object principalId | Sort-Object -Unique)
    if ($gaPrincipals.Count -gt $script:MaxGlobalAdmins) {
        ConvertTo-IGFinding Medium 'Tenant' 'TooManyGlobalAdmins' "$($gaPrincipals.Count) principals hold or can activate Global Administrator; Microsoft recommends fewer than five."
    }

    $reviews = @(Get-IGProp $Inventory 'accessReviews' @())
    $guestReview = $reviews | Where-Object { "$(Get-IGProp (Get-IGProp $_ 'scope') 'query')" -match "userType\s+eq\s+'Guest'" }
    if (-not $guestReview) { ConvertTo-IGFinding Medium 'Tenant' 'NoGuestReview' 'No access review covers guests: guests stay in Microsoft 365 groups until someone notices.' }

    $leavers = @(Get-IGProp $Inventory 'workflows' @() | Where-Object { $_.category -eq 'leaver' -and $_.isEnabled })
    if (-not $leavers) { ConvertTo-IGFinding Low 'Tenant' 'NoLeaverWorkflow' 'No enabled leaver workflow: offboarding depends on someone remembering.' }
    foreach ($w in $leavers | Where-Object { -not $_.isSchedulingEnabled }) {
        ConvertTo-IGFinding Info $w.displayName 'LeaverNotScheduled' 'Enabled but not scheduled: it only runs on demand.'
    }

    $end = ConvertTo-IGDate (Get-IGProp $Config.licensing 'governanceLicenceEndsOn')
    if ($end) {
        $days = [int][math]::Floor(($end - $Now).TotalDays)
        if ($days -le [int]$Config.licensing.warnDays) {
            $timeBound = @($active | Where-Object { $_.assignmentType -eq 'Assigned' -and $null -ne (ConvertTo-IGDate (Get-IGProp $_ 'endDateTime')) }).Count
            ConvertTo-IGFinding High 'Tenant' 'LicenceEnding' "Governance licence ends $($end.ToString('yyyy-MM-dd')) ($days days): $($eligible.Count) eligible assignment(s) will be removed and $timeBound time-bound active assignment(s) become permanent."
        }
    }
}

function ConvertTo-IdentityGovernanceMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Inventory, [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings, [Parameter(Mandatory)][datetimeoffset]$Now)
    $rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
    $md = [System.Collections.Generic.List[string]]::new()
    $md.Add('# Entra ID governance audit'); $md.Add('')
    $md.Add("As of $($Now.ToString('yyyy-MM-dd HH:mm')) UTC. $(@($Inventory.activeAssignments).Count) active and $(@($Inventory.eligibleAssignments).Count) eligible role assignments, $(@($Inventory.accessReviews).Count) access reviews, $(@($Inventory.workflows).Count) lifecycle workflows, $($Findings.Count) findings."); $md.Add('')
    $md.Add('| Severity | Target | Rule | Detail |'); $md.Add('|---|---|---|---|')
    foreach ($f in @($Findings | Sort-Object { $rank[$_.Severity] }, Target, Rule)) { $md.Add("| $($f.Severity) | $($f.Target) | $($f.Rule) | $($f.Detail) |") }
    $md
}

#endregion

#region Microsoft Graph -------------------------------------------------------------------------------------------

function Invoke-IGGraphGet {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Uri, [int]$MaxPages = 200)
    $next = $Uri; $page = 0
    while ($next) {
        if (++$page -gt $MaxPages) { throw "Stopped after $MaxPages pages of $Uri" }
        $resp = Invoke-MgGraphRequest -Method GET -Uri $next -OutputType PSObject -ErrorAction Stop
        if ($null -eq $resp.PSObject.Properties['value']) { return $resp }
        foreach ($i in $resp.value) { $i }
        $next = Get-IGProp $resp '@odata.nextLink'
    }
}

function Get-IdentityGovernanceInventory {
    <#
    .SYNOPSIS  Read-only snapshot. Scopes: RoleAssignmentSchedule.Read.Directory, RoleEligibilitySchedule.Read.Directory,
               AccessReview.Read.All, LifecycleWorkflows-Workflow.ReadBasic.All.
    #>
    [CmdletBinding()]
    param()
    $principals = @{}
    $map = {
        param($i)
        $p = Get-IGProp $i 'principal'
        if ($p -and -not $principals.ContainsKey($p.id)) { $principals[$p.id] = [pscustomobject]@{ id = $p.id; displayName = Get-IGProp $p 'displayName'; userType = Get-IGProp $p 'userType' } }
        [pscustomobject]@{ principalId = $i.principalId; roleDefinitionId = $i.roleDefinitionId; assignmentType = Get-IGProp $i 'assignmentType'; startDateTime = Get-IGProp $i 'startDateTime'; endDateTime = Get-IGProp $i 'endDateTime' }
    }
    $active = foreach ($i in Invoke-IGGraphGet "/v1.0/roleManagement/directory/roleAssignmentScheduleInstances?`$expand=principal") { & $map $i }
    $eligible = foreach ($i in Invoke-IGGraphGet "/v1.0/roleManagement/directory/roleEligibilityScheduleInstances?`$expand=principal") { & $map $i }
    $reviews = foreach ($r in Invoke-IGGraphGet '/v1.0/identityGovernance/accessReviews/definitions') {
        [pscustomobject]@{ id = $r.id; displayName = $r.displayName; status = Get-IGProp $r 'status'; scope = Get-IGProp $r 'scope' }
    }
    $workflows = foreach ($w in Invoke-IGGraphGet '/v1.0/identityGovernance/lifecycleWorkflows/workflows') {
        [pscustomobject]@{ id = $w.id; displayName = $w.displayName; category = $w.category; isEnabled = [bool](Get-IGProp $w 'isEnabled' $false); isSchedulingEnabled = [bool](Get-IGProp $w 'isSchedulingEnabled' $false) }
    }
    [pscustomobject]@{
        collectedAt         = [datetimeoffset]::UtcNow.ToString('o')
        principals          = @($principals.Values)
        activeAssignments   = @($active)
        eligibleAssignments = @($eligible)
        accessReviews       = @($reviews)
        workflows           = @($workflows)
    }
}

function New-PimEligibleAssignment {
    <# Create each eligible assignment in governance.json unless it already exists. Scope: RoleEligibilitySchedule.ReadWrite.Directory. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][object]$Config, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    foreach ($a in @($Config.eligibleAssignments)) {
        $body = New-PimEligibilityRequest -Assignment $a -Config $Config -Now $Now
        $filter = "principalId eq '$($a.principalId)' and roleDefinitionId eq '$($body.roleDefinitionId)'"
        $existing = @(Invoke-IGGraphGet "/v1.0/roleManagement/directory/roleEligibilityScheduleInstances?`$filter=$([uri]::EscapeDataString($filter))")
        if ($existing.Count) { [pscustomobject]@{ Principal = $a.principalName; Role = $a.role; Result = 'AlreadyEligible'; Body = $body }; continue }
        if (-not $PSCmdlet.ShouldProcess("$($a.principalName) / $($a.role)", "Make eligible for $($a.durationDays) days")) {
            [pscustomobject]@{ Principal = $a.principalName; Role = $a.role; Result = 'WhatIf'; Body = $body }; continue
        }
        $r = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/roleManagement/directory/roleEligibilityScheduleRequests' -Body ($body | ConvertTo-Json -Depth 6) `
            -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop
        [pscustomobject]@{ Principal = $a.principalName; Role = $a.role; Result = "$(Get-IGProp $r 'status' 'Submitted')"; Body = $body }
    }
}

function New-GuestAccessReview {
    <# Create the guest review unless one with the same name exists. Refuses billable settings unless -AllowGuestBilling. Scope: AccessReview.ReadWrite.All. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][object]$Config, [Parameter(Mandatory)][datetime]$StartDate, [switch]$AllowGuestBilling)
    $body = New-GuestAccessReviewDefinition -Config $Config -StartDate $StartDate
    $billing = @(Get-GuestBillingTrigger -Body $body -Kind AccessReview)
    if ($billing.Count -and -not $AllowGuestBilling) { throw "Needs the guest governance add-on: $($billing -join '; '). Use -AllowGuestBilling only if your tenant has it linked." }
    $existing = @(Invoke-IGGraphGet '/v1.0/identityGovernance/accessReviews/definitions' | Where-Object { $_.displayName -eq $body.displayName })
    if ($existing.Count) { return [pscustomobject]@{ Name = $body.displayName; Result = 'Exists'; Id = $existing[0].id; Body = $body } }
    if (-not $PSCmdlet.ShouldProcess($body.displayName, 'Create recurring guest access review')) { return [pscustomobject]@{ Name = $body.displayName; Result = 'WhatIf'; Id = $null; Body = $body } }
    $r = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/identityGovernance/accessReviews/definitions' -Body ($body | ConvertTo-Json -Depth 8) `
        -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop
    [pscustomobject]@{ Name = $body.displayName; Result = "Created ($(Get-IGProp $r 'status' 'unknown'))"; Id = $r.id; Body = $body }
}

function New-LeaverWorkflow {
    <# Create the leaver workflow unless one with the same name exists. Scope: LifecycleWorkflows-Workflow.ReadWrite.All. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][object]$Config, [switch]$AllowGuestBilling)
    $body = New-LeaverWorkflowDefinition -Config $Config
    $billing = @(Get-GuestBillingTrigger -Body $body -Kind Workflow)
    if ($billing.Count -and -not $AllowGuestBilling) { throw "Needs the guest governance add-on: $($billing -join '; ')." }
    $existing = @(Invoke-IGGraphGet '/v1.0/identityGovernance/lifecycleWorkflows/workflows' | Where-Object { $_.displayName -eq $body.displayName })
    if ($existing.Count) { return [pscustomobject]@{ Name = $body.displayName; Result = 'Exists'; Id = $existing[0].id; Body = $body } }
    $what = "Create leaver workflow ($(@($body.tasks).Count) tasks, scheduling $(if ($body.isSchedulingEnabled) { 'on' } else { 'off' }))"
    if (-not $PSCmdlet.ShouldProcess($body.displayName, $what)) { return [pscustomobject]@{ Name = $body.displayName; Result = 'WhatIf'; Id = $null; Body = $body } }
    $r = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/identityGovernance/lifecycleWorkflows/workflows' -Body ($body | ConvertTo-Json -Depth 8) `
        -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop
    [pscustomobject]@{ Name = $body.displayName; Result = 'Created'; Id = $r.id; Body = $body }
}

function Invoke-LeaverWorkflow {
    <#
    .SYNOPSIS  Pre-flight, then run the leaver workflow on demand for one user (204 No Content).
               Scopes: User.Read.All, RoleAssignmentSchedule.Read.Directory, RoleEligibilitySchedule.Read.Directory,
               GroupMember.Read.All, LifecycleWorkflows-Workflow.Read.All, LifecycleWorkflows-Workflow.Activate.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)][string]$WorkflowId, [Parameter(Mandatory)][string]$UserId, [Parameter(Mandatory)][object]$Config, [switch]$Force)
    $user = Invoke-MgGraphRequest -Method GET -Uri "/v1.0/users/$($UserId)?`$select=id,displayName,userType" -OutputType PSObject -ErrorAction Stop
    $f = [uri]::EscapeDataString("principalId eq '$UserId'")
    $active = @(Invoke-IGGraphGet "/v1.0/roleManagement/directory/roleAssignmentScheduleInstances?`$filter=$f")
    $eligible = @(Invoke-IGGraphGet "/v1.0/roleManagement/directory/roleEligibilityScheduleInstances?`$filter=$f")
    $owned = foreach ($o in Invoke-IGGraphGet "/v1.0/users/$UserId/ownedObjects") {
        if ((Get-IGProp $o '@odata.type') -ne '#microsoft.graph.group') { continue }
        [pscustomobject]@{ id = $o.id; displayName = $o.displayName; ownerCount = @(Invoke-IGGraphGet "/v1.0/groups/$($o.id)/owners").Count }
    }
    $wf = Invoke-MgGraphRequest -Method GET -Uri "/v1.0/identityGovernance/lifecycleWorkflows/workflows/$WorkflowId" -OutputType PSObject -ErrorAction Stop
    $tasks = @(foreach ($t in Invoke-IGGraphGet "/v1.0/identityGovernance/lifecycleWorkflows/workflows/$WorkflowId/tasks") {
            $script:LeaverTasks.Keys | Where-Object { $script:LeaverTasks[$_] -eq $t.taskDefinitionId }
        })
    $checks = @(Get-LeaverPreflight -User $user -ActiveAssignments $active -EligibleAssignments $eligible -OwnedGroups @($owned) -Config $Config -Tasks $tasks)
    $blockers = @($checks | Where-Object Level -EQ 'Blocker')
    if ($blockers.Count -and -not $Force) {
        return [pscustomobject]@{ User = $user.displayName; Status = 'Blocked'; Checks = $checks }
    }
    if (-not $PSCmdlet.ShouldProcess($user.displayName, "Run leaver workflow '$($wf.displayName)' now")) {
        return [pscustomobject]@{ User = $user.displayName; Status = 'WhatIf'; Checks = $checks }
    }
    Invoke-MgGraphRequest -Method POST -Uri "/v1.0/identityGovernance/lifecycleWorkflows/workflows/$WorkflowId/activate" `
        -Body (@{ subjects = @(@{ id = $UserId }) } | ConvertTo-Json -Depth 4) -ContentType 'application/json' -ErrorAction Stop | Out-Null
    [pscustomobject]@{ User = $user.displayName; Status = 'Started'; Checks = $checks }
}

#endregion
