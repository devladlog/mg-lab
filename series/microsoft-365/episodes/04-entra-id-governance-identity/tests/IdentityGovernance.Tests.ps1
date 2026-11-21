BeforeAll {
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        function global:Invoke-MgGraphRequest { param($Method, $Uri, $Body, $Headers, $OutputFilePath, $OutputType, $ContentType, $ErrorAction) throw 'stub' }
    }
    Import-Module "$PSScriptRoot/../src/IdentityGovernance/IdentityGovernance.psd1" -Force
    $script:cfgPath = "$PSScriptRoot/../src/governance.json"
    $script:config = Get-IdentityGovernanceConfig -Path $cfgPath
    $script:inventory = Get-Content "$PSScriptRoot/fixtures/inventory.json" -Raw | ConvertFrom-Json
    $script:now = [datetimeoffset]'2026-11-20T09:30:00Z'
    $script:GA = '62e90394-69f5-4237-9190-012177145e10'
    $script:GroupsAdmin = 'fdd7a751-b60b-444a-984c-02652fe8fa1c'
    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json; & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 6 | Set-Content $p; $p
    }
    function script:Copy-Inventory { $inventory | ConvertTo-Json -Depth 6 | ConvertFrom-Json }
    function script:Find($Rule, $Target) { @($findings | Where-Object { $_.Rule -eq $Rule -and $_.Target -eq $Target }) }
}

Describe 'Config file' {
    It 'loads the sample config' { $config.eligibleAssignments[0].role | Should -Be 'Groups Administrator' }
    It 'rejects an eligible assignment to a role outside privilegedRoles' {
        { Get-IdentityGovernanceConfig -Path (New-Config { param($c) $c.eligibleAssignments[0].role = 'Exchange Administrator' }) } | Should -Throw '*not in privilegedRoles*'
    }
    It 'refuses permanent eligibility (durationDays 0)' {
        { Get-IdentityGovernanceConfig -Path (New-Config { param($c) $c.eligibleAssignments[0].durationDays = 0 }) } | Should -Throw '*1 or more*'
    }
    It 'requires a justification' {
        { Get-IdentityGovernanceConfig -Path (New-Config { param($c) $c.eligibleAssignments[0].justification = ' ' }) } | Should -Throw '*justification*'
    }
    It 'rejects an unknown leaver task' {
        { Get-IdentityGovernanceConfig -Path (New-Config { param($c) $c.leaverWorkflow.tasks = @('Wipe laptop') }) } | Should -Throw "*unknown task 'Wipe laptop'*"
    }
}

Describe 'PIM eligibility request' {
    BeforeAll { $script:body = New-PimEligibilityRequest -Assignment $config.eligibleAssignments[0] -Config $config -Now $now }
    It 'is an adminAssign for the role template, tenant-wide' {
        $body.action | Should -Be 'adminAssign'
        $body.roleDefinitionId | Should -Be $GroupsAdmin
        $body.directoryScopeId | Should -Be '/'
        $body.principalId | Should -Be '00000000-0000-0000-0000-000000000101'
    }
    It 'is time-bound: afterDateTime, start + durationDays' {
        $body.scheduleInfo.expiration.type | Should -Be 'afterDateTime'
        $body.scheduleInfo.startDateTime | Should -Be '2026-11-20T09:30:00Z'
        $body.scheduleInfo.expiration.endDateTime | Should -Be '2027-05-19T09:30:00Z'
    }
    It 'carries the justification' { $body.justification | Should -BeLike '*groups lifecycle*' }
}

Describe 'Guest access review definition' {
    BeforeAll { $script:review = New-GuestAccessReviewDefinition -Config $config -StartDate ([datetime]'2026-12-01') }
    It 'reviews guests, one instance per Microsoft 365 group' {
        $review.scope.query | Should -Be "./members/microsoft.graph.user/?`$count=true&`$filter=(userType eq 'Guest')"
        $review.instanceEnumerationScope.query | Should -BeLike "*groupTypes/any(c:c+eq+'Unified')*"
    }
    It 'asks the group owners, with a fallback reviewer' {
        $review.reviewers[0].query | Should -Be './owners'
        $review.fallbackReviewers[0].query | Should -Be '/users/00000000-0000-0000-0000-000000000101'
    }
    It 'denies by default and removes denied guests automatically' {
        $review.settings.defaultDecision | Should -Be 'Deny'
        $review.settings.autoApplyDecisionsEnabled | Should -BeTrue
        $review.settings.applyActions[0].'@odata.type' | Should -Be '#microsoft.graph.removeAccessApplyAction'
    }
    It 'recurs every 3 months for a year' {
        $review.settings.recurrence.pattern.type | Should -Be 'absoluteMonthly'
        $review.settings.recurrence.pattern.interval | Should -Be 3
        $review.settings.recurrence.range.endDate | Should -Be '2027-12-01'
    }
    It 'serialises to the JSON the API expects (no PowerShell artefacts)' {
        $json = $review | ConvertTo-Json -Depth 8
        $json | Should -Match '"@odata.type": "#microsoft.graph.accessReviewQueryScope"'
        ($json | ConvertFrom-Json).settings.instanceDurationInDays | Should -Be 14
    }
}

Describe 'Leaver workflow definition' {
    BeforeAll { $script:wf = New-LeaverWorkflowDefinition -Config $config }
    It 'is a leaver workflow on employeeLeaveDateTime, scoped by rule' {
        $wf.category | Should -Be 'leaver'
        $wf.executionConditions.trigger.timeBasedAttribute | Should -Be 'employeeLeaveDateTime'
        $wf.executionConditions.trigger.offsetInDays | Should -Be 0
        $wf.executionConditions.scope.rule | Should -Be "(department eq 'Sales')"
    }
    It 'starts with scheduling off (validate on demand first, like the Learn tutorial)' { $wf.isSchedulingEnabled | Should -BeFalse }
    It 'maps task names to the built-in taskDefinitionIds, in order' {
        $wf.tasks.taskDefinitionId | Should -Be @('509589a4-0466-4471-829e-49c5e502bdee', '81f7b200-2816-4b3b-8c5d-dc556f07b024', 'b3a31406-2a15-4c9a-b25b-a658fa5f07fc', '1dfdfcc7-52fa-4c2e-bf3a-e3919cc12950')
    }
    It 'keeps going on membership removal errors, stops on the others' {
        ($wf.tasks | Where-Object displayName -EQ 'Remove users from all groups').continueOnError | Should -BeTrue
        ($wf.tasks | Where-Object displayName -EQ 'Disable user account').continueOnError | Should -BeFalse
    }
}

Describe 'Guest billing guard' {
    It 'accepts the sample review and workflow (P2-level features only)' {
        Get-GuestBillingTrigger -Body (New-GuestAccessReviewDefinition -Config $config -StartDate ([datetime]'2026-12-01')) -Kind AccessReview | Should -BeNullOrEmpty
        Get-GuestBillingTrigger -Body (New-LeaverWorkflowDefinition -Config $config) -Kind Workflow | Should -BeNullOrEmpty
    }
    It 'flags an inactive-guest review' {
        $b = New-GuestAccessReviewDefinition -Config $config -StartDate ([datetime]'2026-12-01')
        $b.scope.'@odata.type' = '#microsoft.graph.accessReviewInactiveUsersQueryScope'
        Get-GuestBillingTrigger -Body $b -Kind AccessReview | Should -BeLike '*inactive*'
    }
    It 'flags the user-to-group affiliation helper on a guest review' {
        $b = New-GuestAccessReviewDefinition -Config $config -StartDate ([datetime]'2026-12-01')
        $b.settings.recommendationInsightSettings = @(@{ '@odata.type' = '#microsoft.graph.groupPeerOutlierRecommendationInsightSettings' })
        Get-GuestBillingTrigger -Body $b -Kind AccessReview | Should -BeLike '*affiliation*'
    }
    It 'flags a workflow whose rule targets guests' {
        $b = New-LeaverWorkflowDefinition -Config $config
        $b.executionConditions.scope.rule = "(userType eq 'Guest')"
        Get-GuestBillingTrigger -Body $b -Kind Workflow | Should -Not -BeNullOrEmpty
    }
}

Describe 'Governance findings' {
    BeforeAll { $script:findings = @(Get-IdentityGovernanceFinding -Inventory $inventory -Config $config -Now $now) }
    It 'finds 6 issues on the fictional tenant (3 High, 1 Medium, 2 Info)' {
        $findings.Count | Should -Be 6
        @($findings | Where-Object Severity -EQ 'High').Count | Should -Be 3
    }
    It 'flags <Rule> on <Target> as <Severity>' -ForEach @(
        @{ Rule = 'PermanentActivePrivileged'; Target = 'Legacy Admin'; Severity = 'High' }
        @{ Rule = 'PermanentActivePrivileged'; Target = 'Ops Admin'; Severity = 'High' }
        @{ Rule = 'LicenceEnding'; Target = 'Tenant'; Severity = 'High' }
        @{ Rule = 'NoGuestReview'; Target = 'Tenant'; Severity = 'Medium' }
        @{ Rule = 'ActivatedNow'; Target = 'Alex Demo'; Severity = 'Info' }
        @{ Rule = 'LeaverNotScheduled'; Target = 'Leaver - Sales members on their last day'; Severity = 'Info' }
    ) { (Find $Rule $Target).Severity | Should -Be $Severity }
    It 'does not flag the emergency access accounts or time-bound assignments' {
        $findings.Target | Should -Not -Contain 'Emergency Access 1'
        $findings.Target | Should -Not -Contain 'Megan Sample'
    }
    It 'spells out what the licence end does to PIM' {
        (Find 'LicenceEnding' 'Tenant').Detail | Should -BeLike '*2 eligible assignment(s) will be removed and 1 time-bound active assignment(s) become permanent*'
    }
    It 'is quiet about the licence when the end date is far away' {
        $c = Get-IdentityGovernanceConfig -Path (New-Config { param($c) $c.licensing.governanceLicenceEndsOn = '2027-12-20' })
        (Get-IdentityGovernanceFinding -Inventory $inventory -Config $c -Now $now).Rule | Should -Not -Contain 'LicenceEnding'
    }
    It 'flags an emergency access account that is only eligible' {
        $inv = Copy-Inventory
        $inv.activeAssignments = @($inv.activeAssignments | Where-Object principalId -NE '00000000-0000-0000-0000-000000000902')
        (Get-IdentityGovernanceFinding -Inventory $inv -Config $config -Now $now | Where-Object Rule -EQ 'EmergencyAccessNotPermanent').Target | Should -Be 'Emergency Access 2'
    }
    It 'counts active and eligible Global Administrators together: 5 is too many' {
        $inv = Copy-Inventory
        $inv.eligibleAssignments += [pscustomobject]@{ principalId = '00000000-0000-0000-0000-000000000102'; roleDefinitionId = $GA; assignmentType = $null; startDateTime = $null; endDateTime = $null }
        (Get-IdentityGovernanceFinding -Inventory $inv -Config $config -Now $now).Rule | Should -Contain 'TooManyGlobalAdmins'
        $findings.Rule | Should -Not -Contain 'TooManyGlobalAdmins'   # 4 in the fixture
    }
    It 'recognises a guest review by its scope query' {
        $inv = Copy-Inventory
        $inv.accessReviews += [pscustomobject]@{ id = 'r2'; displayName = 'Guests'; status = 'NotStarted'; scope = [pscustomobject]@{ query = "./members/microsoft.graph.user/?`$count=true&`$filter=(userType eq 'Guest')" } }
        (Get-IdentityGovernanceFinding -Inventory $inv -Config $config -Now $now).Rule | Should -Not -Contain 'NoGuestReview'
    }
    It 'reports a missing leaver workflow' {
        $inv = Copy-Inventory; $inv.workflows = @()
        (Get-IdentityGovernanceFinding -Inventory $inv -Config $config -Now $now).Rule | Should -Contain 'NoLeaverWorkflow'
    }
    It 'renders a Markdown report' {
        $md = ConvertTo-IdentityGovernanceMarkdown -Inventory $inventory -Findings $findings -Now $now
        ($md | Where-Object { $_ -like '| High |*' }).Count | Should -Be 3
    }
}

Describe 'Leaver pre-flight' {
    BeforeAll {
        $script:sam = [pscustomobject]@{ id = 'u9'; displayName = 'Sam Leaver'; userType = 'Member' }
        $script:allTasks = @($config.leaverWorkflow.tasks)
    }
    It 'blocks Disable user account for someone holding an active Entra role' {
        $r = @(Get-LeaverPreflight -User $sam -ActiveAssignments @([pscustomobject]@{ roleDefinitionId = $GroupsAdmin }) -Config $config -Tasks $allTasks)
        $r[0].Level | Should -Be 'Blocker'
        $r[0].Detail | Should -BeLike '*Groups Administrator*Disable user account*'
    }
    It 'does not block when the workflow has no disable task' {
        @(Get-LeaverPreflight -User $sam -ActiveAssignments @([pscustomobject]@{ roleDefinitionId = $GroupsAdmin }) -Config $config -Tasks @('Remove users from all groups')).Count | Should -Be 0
    }
    It 'blocks a guest (on-demand runs ignore the scope rule, and guest runs are billable)' {
        (Get-LeaverPreflight -User ([pscustomobject]@{ displayName = 'Partner Guest'; userType = 'Guest' }) -Config $config -Tasks $allTasks).Check | Should -Contain 'GuestSubject'
    }
    It 'warns about eligible roles and sole-owner groups' {
        $r = @(Get-LeaverPreflight -User $sam -EligibleAssignments @([pscustomobject]@{ roleDefinitionId = $GA }) `
                -OwnedGroups @([pscustomobject]@{ displayName = 'Sales Pipeline Review'; ownerCount = 1 }, [pscustomobject]@{ displayName = 'TEAM_Sales_Partner Portal'; ownerCount = 2 }) -Config $config -Tasks $allTasks)
        $r.Level | Should -Be @('Warning', 'Warning')
        $r[1].Detail | Should -BeLike "*only owner of 'Sales Pipeline Review'*"
    }
}

Describe 'Inventory (mocked Graph)' {
    BeforeAll {
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -like '*/roleAssignmentScheduleInstances*' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ principalId = 'p1'; roleDefinitionId = '62e90394-69f5-4237-9190-012177145e10'; assignmentType = 'Assigned'; startDateTime = $null; endDateTime = $null; principal = [pscustomobject]@{ id = 'p1'; displayName = 'Legacy Admin'; userType = 'Member' } }) }
        }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -like '*/roleEligibilityScheduleInstances*' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ principalId = 'p2'; roleDefinitionId = 'fdd7a751-b60b-444a-984c-02652fe8fa1c'; startDateTime = $null; endDateTime = '2027-05-19T09:30:00Z'; principal = [pscustomobject]@{ id = 'p2'; displayName = 'Alex Demo'; userType = 'Member' } }) }
        }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -eq '/v1.0/identityGovernance/accessReviews/definitions' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ id = 'r1'; displayName = 'Admins'; status = 'InProgress'; scope = [pscustomobject]@{ query = '/roleManagement' } }); '@odata.nextLink' = 'https://graph.microsoft.com/v1.0/identityGovernance/accessReviews/definitions?$skiptoken=2' }
        }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -like '*accessReviews/definitions?$skiptoken=2' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ id = 'r2'; displayName = 'Guests'; status = 'NotStarted'; scope = [pscustomobject]@{ query = "./members/microsoft.graph.user/?`$filter=(userType eq 'Guest')" } }) }
        }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -eq '/v1.0/identityGovernance/lifecycleWorkflows/workflows' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ id = 'w1'; displayName = 'Leaver'; category = 'leaver'; isEnabled = $true; isSchedulingEnabled = $true }) }
        }
        $script:inv = Get-IdentityGovernanceInventory
    }
    It 'reads active and eligible schedule instances with their principals' {
        $inv.activeAssignments[0].assignmentType | Should -Be 'Assigned'
        $inv.eligibleAssignments[0].principalId | Should -Be 'p2'
        ($inv.principals | Sort-Object id).displayName | Should -Be @('Legacy Admin', 'Alex Demo')
    }
    It 'expands the principal instead of one lookup per assignment' {
        Should -Invoke Invoke-MgGraphRequest -ModuleName IdentityGovernance -Scope Describe -Times 1 -Exactly -ParameterFilter { $Uri -eq "/v1.0/roleManagement/directory/roleAssignmentScheduleInstances?`$expand=principal" }
    }
    It 'follows nextLink for access reviews' { $inv.accessReviews.displayName | Should -Be @('Admins', 'Guests') }
    It 'feeds the findings end to end' {
        $f = @(Get-IdentityGovernanceFinding -Inventory $inv -Config $config -Now $now)
        $f.Rule | Should -Contain 'PermanentActivePrivileged'
        $f.Rule | Should -Not -Contain 'NoGuestReview'
    }
}

Describe 'Write operations (mocked Graph)' {
    It 'creates the eligible assignment when it does not exist yet' {
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Method -eq 'GET' } { [pscustomobject]@{ value = @() } }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Method -eq 'POST' } { $script:pimBody = $Body | ConvertFrom-Json; [pscustomobject]@{ status = 'Provisioned' } }
        $r = @(New-PimEligibleAssignment -Config $config -Now $now -Confirm:$false)
        $r[0].Result | Should -Be 'Provisioned'
        $pimBody.scheduleInfo.expiration.type | Should -Be 'afterDateTime'
        Should -Invoke Invoke-MgGraphRequest -ModuleName IdentityGovernance -Times 1 -Exactly -ParameterFilter { $Method -eq 'GET' -and $Uri -like '*roleEligibilityScheduleInstances?$filter=principalId%20eq*' }
    }
    It 'skips an assignment that already exists' {
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Method -eq 'GET' } { [pscustomobject]@{ value = @([pscustomobject]@{ id = 'x' }) } }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Method -eq 'POST' } { throw 'should not be called' }
        (New-PimEligibleAssignment -Config $config -Now $now -Confirm:$false).Result | Should -Be 'AlreadyEligible'
    }
    It 'creates the guest review once, and only with -Confirm, not -WhatIf' {
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Method -eq 'GET' } { [pscustomobject]@{ value = @() } }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Method -eq 'POST' } { [pscustomobject]@{ id = 'r9'; status = 'NotStarted' } }
        (New-GuestAccessReview -Config $config -StartDate ([datetime]'2026-12-01') -WhatIf).Result | Should -Be 'WhatIf'
        Should -Invoke Invoke-MgGraphRequest -ModuleName IdentityGovernance -Times 0 -ParameterFilter { $Method -eq 'POST' }
        (New-GuestAccessReview -Config $config -StartDate ([datetime]'2026-12-01') -Confirm:$false).Result | Should -Be 'Created (NotStarted)'
    }
    It 'refuses a billable guest review without -AllowGuestBilling' {
        $c = Get-IdentityGovernanceConfig -Path $cfgPath
        Mock New-GuestAccessReviewDefinition -ModuleName IdentityGovernance {
            [ordered]@{ displayName = 'x'; scope = [ordered]@{ '@odata.type' = '#microsoft.graph.accessReviewInactiveUsersQueryScope'; query = "./members/microsoft.graph.user/?`$filter=(userType eq 'Guest')" }; settings = [ordered]@{} }
        }
        { New-GuestAccessReview -Config $c -StartDate ([datetime]'2026-12-01') -Confirm:$false } | Should -Throw '*guest governance add-on*'
    }
    It 'does not duplicate an existing leaver workflow' {
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Method -eq 'GET' } { [pscustomobject]@{ value = @([pscustomobject]@{ id = 'w1'; displayName = 'Leaver - Sales members on their last day' }) } }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Method -eq 'POST' } { throw 'should not be called' }
        (New-LeaverWorkflow -Config $config -Confirm:$false).Result | Should -Be 'Exists'
    }
}

Describe 'Invoke-LeaverWorkflow (mocked Graph)' {
    BeforeEach {
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -like '/v1.0/users/u9?*' } { [pscustomobject]@{ id = 'u9'; displayName = 'Sam Leaver'; userType = 'Member' } }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -like '*roleEligibilityScheduleInstances*' } { [pscustomobject]@{ value = @() } }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -eq '/v1.0/users/u9/ownedObjects' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ '@odata.type' = '#microsoft.graph.group'; id = 'g1'; displayName = 'Sales Pipeline Review' }, [pscustomobject]@{ '@odata.type' = '#microsoft.graph.application'; id = 'a1'; displayName = 'App' }) }
        }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -eq '/v1.0/groups/g1/owners' } { [pscustomobject]@{ value = @([pscustomobject]@{ id = 'u9' }) } }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -eq '/v1.0/identityGovernance/lifecycleWorkflows/workflows/w1' } { [pscustomobject]@{ id = 'w1'; displayName = 'Leaver - Sales members on their last day' } }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -eq '/v1.0/identityGovernance/lifecycleWorkflows/workflows/w1/tasks' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ taskDefinitionId = 'b3a31406-2a15-4c9a-b25b-a658fa5f07fc' }, [pscustomobject]@{ taskDefinitionId = '1dfdfcc7-52fa-4c2e-bf3a-e3919cc12950' }) }
        }
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -like '*/activate' } { $script:activateBody = $Body | ConvertFrom-Json }
    }
    It 'stops before activate when the user still holds an Entra role' {
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -like '*roleAssignmentScheduleInstances*' } { [pscustomobject]@{ value = @([pscustomobject]@{ roleDefinitionId = 'fdd7a751-b60b-444a-984c-02652fe8fa1c' }) } }
        $r = Invoke-LeaverWorkflow -WorkflowId 'w1' -UserId 'u9' -Config $config -Confirm:$false
        $r.Status | Should -Be 'Blocked'
        $r.Checks.Check | Should -Contain 'HoldsEntraRole'
        $r.Checks.Check | Should -Contain 'SoleOwner'
        Should -Invoke Invoke-MgGraphRequest -ModuleName IdentityGovernance -Times 0 -ParameterFilter { $Uri -like '*/activate' }
    }
    It 'activates with the user as the only subject when the pre-flight passes' {
        Mock Invoke-MgGraphRequest -ModuleName IdentityGovernance -ParameterFilter { $Uri -like '*roleAssignmentScheduleInstances*' } { [pscustomobject]@{ value = @() } }
        $r = Invoke-LeaverWorkflow -WorkflowId 'w1' -UserId 'u9' -Config $config -Confirm:$false
        $r.Status | Should -Be 'Started'
        $activateBody.subjects[0].id | Should -Be 'u9'
        @($activateBody.subjects).Count | Should -Be 1
    }
}

Describe 'Real Microsoft Graph PowerShell parameters' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
    It 'Invoke-MgGraphRequest has every parameter and output type the module uses' {
        $cmd = Get-Command Invoke-MgGraphRequest
        foreach ($name in 'Method', 'Uri', 'Body', 'ContentType', 'OutputType') { $cmd.Parameters.Keys | Should -Contain $name }
        [enum]::GetNames($cmd.Parameters['OutputType'].ParameterType) | Should -Contain 'PSObject'
    }
    It 'Get-MgContext exists (used to skip a second sign-in)' { Get-Command Get-MgContext | Should -Not -BeNullOrEmpty }
}
