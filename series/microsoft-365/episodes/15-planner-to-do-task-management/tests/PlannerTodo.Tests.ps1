BeforeAll {
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        function global:Invoke-MgGraphRequest { param($Method, $Uri, $Body, $Headers, $OutputFilePath, $OutputType, $ContentType, $ErrorAction) throw 'stub' }
    }
    Import-Module "$PSScriptRoot/../src/PlannerTodo/PlannerTodo.psd1" -Force
    $script:cfgPath = "$PSScriptRoot/../src/plan.json"
    $script:config = Get-PlannerPlanConfig -Path $cfgPath
    $script:inventory = Get-Content "$PSScriptRoot/fixtures/inventory.json" -Raw | ConvertFrom-Json
    $script:now = [datetimeoffset]'2026-11-20T09:30:00Z'
    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json
        & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 8 | Set-Content $p; $p
    }
}

Describe 'Config file' {
    It 'loads the sample plan' {
        $config.plan.title | Should -Be 'Project Falcon - Launch Readiness'
        @($config.tasks).Count | Should -Be 8
    }
    It 'rejects a missing group id' {
        { Get-PlannerPlanConfig -Path (New-Config { param($c) $c.plan.groupId = 'not-a-guid' }) } | Should -Throw '*object id*'
    }
    It 'rejects a task in an unknown bucket' {
        { Get-PlannerPlanConfig -Path (New-Config { param($c) $c.tasks[0].bucket = 'Nowhere' }) } | Should -Throw "*not in the bucket list*"
    }
    It 'rejects duplicate task titles (the title is the idempotency key)' {
        { Get-PlannerPlanConfig -Path (New-Config { param($c) $c.tasks[1].title = $c.tasks[0].title }) } | Should -Throw '*Duplicate task title*'
    }
    It 'rejects an unknown priority' {
        { Get-PlannerPlanConfig -Path (New-Config { param($c) $c.tasks[0].priority = 'asap' }) } | Should -Throw '*urgent, important, medium or low*'
    }
    It 'rejects more than 20 checklist items' {
        { Get-PlannerPlanConfig -Path (New-Config { param($c) $c.tasks[0].checklist = @(1..21 | ForEach-Object { "step $_" }) }) } | Should -Throw '*20 checklist items*'
    }
    It 'accepts exactly 20 checklist items' {
        (Get-PlannerPlanConfig -Path (New-Config { param($c) $c.tasks[0].checklist = @(1..20 | ForEach-Object { "step $_" }) })).tasks[0].checklist.Count | Should -Be 20
    }
    It 'rejects more than 20 assignees' {
        { Get-PlannerPlanConfig -Path (New-Config { param($c) $c.tasks[0].assignees = @(1..21 | ForEach-Object { "u$_@contoso.com" }) }) } | Should -Throw '*20 assignees*'
    }
    It 'rejects more than 6 labels on a task' {
        $p = New-Config { param($c) $c.plan.labels = @(1..8 | ForEach-Object { "L$_" }); $c.tasks[0].labels = @(1..7 | ForEach-Object { "L$_" }) }
        { Get-PlannerPlanConfig -Path $p } | Should -Throw '*6 labels*'
    }
    It 'rejects a label that the plan does not define' {
        { Get-PlannerPlanConfig -Path (New-Config { param($c) $c.tasks[0].labels = @('Mystery') }) } | Should -Throw '*not defined in plan.labels*'
    }
    It 'rejects a start date after the due date' {
        { Get-PlannerPlanConfig -Path (New-Config { param($c) $c.tasks[0].startInDays = 5; $c.tasks[0].dueInDays = 2 }) } | Should -Throw '*start date is after the due date*'
    }
    It 'rejects a reference that is not http(s)' {
        { Get-PlannerPlanConfig -Path (New-Config { param($c) $c.tasks[1].references[0].url = 'ftp://x' }) } | Should -Throw '*http or https*'
    }
    It 'rejects more than 200 buckets' {
        { Get-PlannerPlanConfig -Path (New-Config { param($c) $c.buckets = @(1..201 | ForEach-Object { "B$_" }) }) } | Should -Throw '*200 buckets*'
    }
}

Describe 'Request bodies' {
    BeforeAll {
        $script:users = @{ 'alex.demo@contoso.com' = '00000000-0000-0000-0000-0000000000a1'; 'sam.demo@contoso.com' = '00000000-0000-0000-0000-0000000000a2' }
        $script:today = [datetimeoffset]'2026-11-20T09:30:00Z'
        $script:t1 = $config.tasks[0]; $script:t2 = $config.tasks[1]
    }
    It 'builds the task: planId, bucketId, priority number, UTC dates' {
        $b = ConvertTo-PlannerTaskBody -Task $t1 -Config $config -PlanId 'P' -BucketId 'B' -UserIds $users -Today $today
        $b.planId | Should -Be 'P'; $b.bucketId | Should -Be 'B'
        $b.priority | Should -Be 1
        $b.dueDateTime | Should -Be '2026-11-22T17:00:00Z'
        $b.startDateTime | Should -Be '2026-11-20T08:00:00Z'
    }
    It 'maps the four priority names to 1, 3, 5, 9' {
        $vals = foreach ($p in 'urgent', 'important', 'medium', 'low') {
            $t = [pscustomobject]@{ title = 'x'; priority = $p }
            (ConvertTo-PlannerTaskBody -Task $t -Config $config -PlanId 'P' -BucketId 'B' -Today $today).priority
        }
        $vals | Should -Be @(1, 3, 5, 9)
    }
    It 'assignments: user id is the property name, with @odata.type and orderHint' {
        $b = ConvertTo-PlannerTaskBody -Task $t1 -Config $config -PlanId 'P' -BucketId 'B' -UserIds $users -Today $today
        $a = $b.assignments['00000000-0000-0000-0000-0000000000a1']
        $a['@odata.type'] | Should -Be '#microsoft.graph.plannerAssignment'
        $a.orderHint | Should -Be ' !'
    }
    It 'throws when an assignee has no user id' {
        { ConvertTo-PlannerTaskBody -Task $t1 -Config $config -PlanId 'P' -BucketId 'B' -UserIds @{} -Today $today } | Should -Throw '*No user id*'
    }
    It 'applies labels as categoryN = true using the position in plan.labels' {
        $b = ConvertTo-PlannerTaskBody -Task $t2 -Config $config -PlanId 'P' -BucketId 'B' -UserIds $users -Today $today
        $b.appliedCategories.Keys | Sort-Object | Should -Be @('category1', 'category2')
        $b.appliedCategories.category1 | Should -BeTrue
    }
    It 'a task without a due date has no dueDateTime' {
        $t = [pscustomobject]@{ title = 'x' }
        (ConvertTo-PlannerTaskBody -Task $t -Config $config -PlanId 'P' -BucketId 'B' -Today $today).Keys | Should -Not -Contain 'dueDateTime'
    }
    It 'details: checklist items keyed by a GUID, unchecked, with @odata.type, previewType checklist' {
        $d = ConvertTo-PlannerDetailsBody -Task $t1
        $d.description | Should -Match 'go-live date'
        $d.previewType | Should -Be 'checklist'
        $d.checklist.Count | Should -Be 3
        foreach ($k in $d.checklist.Keys) { { [guid]$k } | Should -Not -Throw; $d.checklist[$k].isChecked | Should -BeFalse; $d.checklist[$k]['@odata.type'] | Should -Be 'microsoft.graph.plannerChecklistItem' }
    }
    It 'checklist keys are stable between runs' {
        @((ConvertTo-PlannerDetailsBody -Task $t1).checklist.Keys | Sort-Object) | Should -Be @((ConvertTo-PlannerDetailsBody -Task $t1).checklist.Keys | Sort-Object)
    }
    It 'encodes reference URLs the way Learn describes (. : % @ # are not allowed in property names)' {
        ConvertTo-PLReferenceKey 'https://contoso.sharepoint.com/teams/agile/AnnualReport.pptx' | Should -Be 'https%3A//contoso%2Esharepoint%2Ecom/teams/agile/AnnualReport%2Epptx'
        ConvertTo-PLReferenceKey 'https://x.com/a%20b#c' | Should -Be 'https%3A//x%2Ecom/a%2520b%23c'
    }
    It 'details: reference carries alias, type and @odata.type' {
        $d = ConvertTo-PlannerDetailsBody -Task $t2
        $r = $d.references['https%3A//contoso%2Eexample%2Ecom/falcon/announcement-draft']
        $r.alias | Should -Be 'Announcement draft'; $r.type | Should -Be 'Word'
    }
    It 'returns nothing when a task has no description, checklist or references' {
        ConvertTo-PlannerDetailsBody -Task ([pscustomobject]@{ title = 'x' }) | Should -BeNullOrEmpty
    }
}

Describe 'Plan diff (create what is missing, never touch what exists)' {
    It 'a plan that does not exist: create plan, labels, 3 buckets, 8 tasks' {
        $d = @(Get-PlannerPlanDiff -Config $config -Existing $null)
        $g = @{}; $d | Group-Object Action | ForEach-Object { $g[$_.Name] = $_.Count }
        $g.CreatePlan | Should -Be 1; $g.SetLabels | Should -Be 1; $g.CreateBucket | Should -Be 3; $g.CreateTask | Should -Be 8
        $d[0].Action | Should -Be 'CreatePlan'
    }
    It 'an identical plan: no actions' {
        $ex = @{ Plan = @{ id = 'p' }; CategoryDescriptions = @{ category1 = 'Customer facing'; category2 = 'Needs legal review'; category3 = 'Blocked' }
            Buckets = @($config.buckets | ForEach-Object { @{ name = $_ } }); Tasks = @($config.tasks | ForEach-Object { @{ title = $_.title } }) }
        @(Get-PlannerPlanDiff -Config $config -Existing $ex).Count | Should -Be 0
    }
    It 'only the missing label slot is set: a label somebody renamed stays' {
        $ex = @{ Plan = @{ id = 'p' }; CategoryDescriptions = @{ category1 = 'Customer facing'; category3 = 'Blocked (renamed by hand)' }
            Buckets = @($config.buckets | ForEach-Object { @{ name = $_ } }); Tasks = @($config.tasks | ForEach-Object { @{ title = $_.title } }) }
        $d = @(Get-PlannerPlanDiff -Config $config -Existing $ex)
        $d.Count | Should -Be 1
        $d[0].Action | Should -Be 'SetLabels'; $d[0].Detail | Should -Be 'Needs legal review'
    }
    It 'matches buckets and tasks case-insensitively and ignores extra ones in the plan' {
        $ex = @{ Plan = @{ id = 'p' }; CategoryDescriptions = @{ category1 = 'a'; category2 = 'b'; category3 = 'c' }
            Buckets = @(@{ name = 'PLAN' }, @{ name = 'build' }, @{ name = 'Archive' }); Tasks = @(@{ title = 'CONFIRM LAUNCH DATE WITH SPONSORS ' }) }
        $d = @(Get-PlannerPlanDiff -Config $config -Existing $ex)
        ($d | Where-Object Action -eq 'CreateBucket').Target | Should -Be 'Launch'
        @($d | Where-Object Action -eq 'CreateTask').Count | Should -Be 7
    }
}

Describe 'Audit findings' {
    BeforeAll {
        $script:findings = @(Get-PlannerFinding -Inventory $inventory -Config $config -Now $now)
        function script:Find($Rule, $Target) { @($findings | Where-Object { $_.Rule -eq $Rule -and $_.Target -eq $Target }) }
    }
    It 'overdue urgent task is High and names the assignee' {
        $f = Find 'Overdue' 'Confirm launch date with sponsors'
        $f.Count | Should -Be 1
        $f[0].Severity | Should -Be 'High'
        $f[0].Detail | Should -Match 'Alex Demo'
        $f[0].Detail | Should -Match '4 day'
    }
    It 'overdue non-urgent task is Medium' { (Find 'Overdue' 'Draft customer announcement')[0].Severity | Should -Be 'Medium' }
    It 'a completed task is never overdue' { (Find 'Overdue' 'Freeze the release branch').Count | Should -Be 0 }
    It 'task due within 7 days is DueSoon (Info)' {
        (Find 'DueSoon' 'Fix the three open blocker bugs')[0].Severity | Should -Be 'Info'
        (Find 'DueSoon' 'Brief the support team').Count | Should -Be 0   # due Dec 4: 14 days away
    }
    It 'unassigned active task' { (Find 'Unassigned' 'Retire the old landing page')[0].Severity | Should -Be 'Medium' }
    It 'no due date' { (Find 'NoDueDate' 'Retire the old landing page').Count | Should -Be 1 }
    It 'not started for 21+ days' { (Find 'NotStartedStale' 'Retire the old landing page')[0].Detail | Should -Match '50 days' }
    It 'complete with open checklist' { (Find 'CompletedWithOpenChecklist' 'Freeze the release branch')[0].Detail | Should -Match '1 unchecked' }
    It 'overloaded assignee (limit 5 in the sample config; Riley has 4 active)' {
        @($findings | Where-Object Rule -eq 'Overloaded').Count | Should -Be 0
        $c2 = Get-Content $cfgPath -Raw | ConvertFrom-Json; $c2.audit.maxActivePerPerson = 2
        $f = @(Get-PlannerFinding -Inventory $inventory -Config $c2 -Now $now | Where-Object Rule -eq 'Overloaded')
        $f.Count | Should -Be 1
        $f[0].Target | Should -Match 'Riley Demo'
    }
    It 'empty bucket is Info' { (Find 'EmptyBucket' 'Archive')[0].Severity | Should -Be 'Info' }
    It 'warns at 80 percent of the documented limits (200 buckets per plan)' {
        $big = [pscustomobject]@{ plan = $inventory.plan; users = @{}; tasks = @()
            buckets = @(1..160 | ForEach-Object { [pscustomobject]@{ id = "b$_"; name = "Bucket $_" } }) }
        $f = @(Get-PlannerFinding -Inventory $big -Config $config -Now $now | Where-Object Rule -eq 'ApproachingLimit')
        $f.Count | Should -Be 1
        $f[0].Detail | Should -Match '160 buckets of 200'
        @(Get-PlannerFinding -Inventory $inventory -Config $config -Now $now | Where-Object Rule -eq 'ApproachingLimit').Count | Should -Be 0
    }
    It 'is sorted High first' { $findings[0].Severity | Should -Be 'High' }
    It 'markdown report has the findings table' {
        $md = ConvertTo-PlannerMarkdown -Inventory $inventory -Finding $findings -Now $now
        $md | Should -Match '# Planner audit: Project Falcon - Launch Readiness'
        $md | Should -Match '\| High \| Confirm launch date with sponsors \| Overdue \|'
    }
}

Describe 'Etags: Invoke-PlannerPatch' {
    BeforeAll {
        $script:err412 = { $e = [System.Exception]::new('Response status code does not indicate success: 412 (Precondition Failed).'); $e }
    }
    It 'sends If-Match with the etag it just read, and asks for the representation back' {
        Mock -ModuleName PlannerTodo Invoke-MgGraphRequest { if ($Method -eq 'GET') { [pscustomobject]@{ '@odata.etag' = 'W/"abc"' } } else { [pscustomobject]@{ id = 'ok' } } }
        $r = Invoke-PlannerPatch -Uri '/v1.0/planner/tasks/T/details' -Body @{ description = 'x' }
        $r.id | Should -Be 'ok'
        Should -Invoke -ModuleName PlannerTodo Invoke-MgGraphRequest -Times 1 -ParameterFilter { $Method -eq 'PATCH' -and $Headers['If-Match'] -eq 'W/"abc"' -and $Headers['Prefer'] -eq 'return=representation' }
    }
    It 'on 412 reads the new etag and retries once' {
        $script:n = 0
        Mock -ModuleName PlannerTodo Invoke-MgGraphRequest {
            if ($Method -eq 'GET') { $script:n++; return [pscustomobject]@{ '@odata.etag' = "W/`"v$script:n`"" } }
            if ($Headers['If-Match'] -eq 'W/"v1"') { throw [System.Exception]::new('412 Precondition Failed') }
            [pscustomobject]@{ id = 'ok' }
        }
        (Invoke-PlannerPatch -Uri '/v1.0/planner/tasks/T' -Body @{ title = 'x' }).id | Should -Be 'ok'
        Should -Invoke -ModuleName PlannerTodo Invoke-MgGraphRequest -Times 2 -ParameterFilter { $Method -eq 'PATCH' }
        Should -Invoke -ModuleName PlannerTodo Invoke-MgGraphRequest -Times 1 -ParameterFilter { $Method -eq 'PATCH' -and $Headers['If-Match'] -eq 'W/"v2"' }
    }
    It 'gives up after the retries and rethrows' {
        Mock -ModuleName PlannerTodo Invoke-MgGraphRequest { if ($Method -eq 'GET') { [pscustomobject]@{ '@odata.etag' = 'W/"e"' } } else { throw [System.Exception]::new('409 Conflict') } }
        { Invoke-PlannerPatch -Uri '/v1.0/planner/tasks/T' -Body @{ title = 'x' } -MaxRetries 1 } | Should -Throw '*409*'
        Should -Invoke -ModuleName PlannerTodo Invoke-MgGraphRequest -Times 2 -ParameterFilter { $Method -eq 'PATCH' }
    }
    It 'does not retry other errors (403)' {
        Mock -ModuleName PlannerTodo Invoke-MgGraphRequest { if ($Method -eq 'GET') { [pscustomobject]@{ '@odata.etag' = 'W/"e"' } } else { throw [System.Exception]::new('403 Forbidden') } }
        { Invoke-PlannerPatch -Uri '/v1.0/planner/tasks/T' -Body @{ title = 'x' } } | Should -Throw '*403*'
        Should -Invoke -ModuleName PlannerTodo Invoke-MgGraphRequest -Times 1 -ParameterFilter { $Method -eq 'PATCH' }
    }
    It 'refuses to patch when the resource has no etag' {
        Mock -ModuleName PlannerTodo Invoke-MgGraphRequest { [pscustomobject]@{ id = 'x' } }
        { Invoke-PlannerPatch -Uri '/v1.0/planner/tasks/T' -Body @{ title = 'x' } } | Should -Throw '*etag*'
    }
}

Describe 'Set-PlannerPlan (mocked Graph)' {
    It 'new plan: creates plan, labels, buckets in order, tasks with details; -WhatIf creates nothing' {
        $script:calls = [System.Collections.Generic.List[string]]::new()
        Mock -ModuleName PlannerTodo Invoke-MgGraphRequest {
            $script:calls.Add("$Method $Uri")
            switch -Regex ("$Method $Uri") {
                '^GET /v1.0/groups/.*/planner/plans' { return [pscustomobject]@{ value = @() } }
                '^POST /v1.0/planner/plans$' { return [pscustomobject]@{ id = 'PLAN1' } }
                '^GET /v1.0/planner/plans/PLAN1/details' { return [pscustomobject]@{ '@odata.etag' = 'W/"d"'; categoryDescriptions = [pscustomobject]@{} } }
                '^POST /v1.0/planner/buckets' { $n = ($script:calls | Where-Object { $_ -like 'POST /v1.0/planner/buckets' }).Count; return [pscustomobject]@{ id = "B$n"; orderHint = "H$n" } }
                '^GET /v1.0/users/' { $raw = (($Uri -split '/users/')[1] -replace '\?.*$', ''); $u = [uri]::UnescapeDataString($raw); return [pscustomobject]@{ id = "id-$u" } }
                '^POST /v1.0/planner/tasks$' { return [pscustomobject]@{ id = 'T' + ($script:calls | Where-Object { $_ -like 'POST /v1.0/planner/tasks' }).Count } }
                '^GET .*(details|/planner/tasks/T)' { return [pscustomobject]@{ '@odata.etag' = 'W/"e"' } }
                '^PATCH' { return [pscustomobject]@{} }
            }
        }
        $rows = @(Set-PlannerPlan -Config $config -Today $now -WhatIf)
        @($script:calls | Where-Object { $_ -like 'POST *' -or $_ -like 'PATCH *' }).Count | Should -Be 0
        ($rows | Where-Object Result -like 'WhatIf*').Count | Should -Be 13

        $script:calls.Clear()
        $rows = @(Set-PlannerPlan -Config $config -Today $now -Confirm:$false)
        ($rows | Where-Object Result -eq 'Created').Count | Should -Be 12   # plan + 3 buckets + 8 tasks
        @($script:calls | Where-Object { $_ -eq 'POST /v1.0/planner/tasks' }).Count | Should -Be 8
        Should -Invoke -ModuleName PlannerTodo Invoke-MgGraphRequest -ParameterFilter { $Method -eq 'POST' -and $Uri -eq '/v1.0/planner/plans' -and ($Body | ConvertFrom-Json).container.type -eq 'group' }
        # buckets are chained: the 2nd bucket's orderHint is "<hint of the 1st> !"
        Should -Invoke -ModuleName PlannerTodo Invoke-MgGraphRequest -ParameterFilter { $Uri -eq '/v1.0/planner/buckets' -and ($Body | ConvertFrom-Json).orderHint -eq 'H1 !' }
        # the first task body has the assignment keyed by the resolved user id
        Should -Invoke -ModuleName PlannerTodo Invoke-MgGraphRequest -ParameterFilter { $Uri -eq '/v1.0/planner/tasks' -and $Body -like '*id-alex.demo@contoso.com*' }
        # details for tasks with a description: PATCH .../details with If-Match
        Should -Invoke -ModuleName PlannerTodo Invoke-MgGraphRequest -ParameterFilter { $Method -eq 'PATCH' -and $Uri -like '*/details' -and $Headers['If-Match'] -eq 'W/"e"' }
    }
    It 'an existing complete plan: nothing is created' {
        Mock -ModuleName PlannerTodo Get-PlannerInventory {
            [ordered]@{ plan = @{ id = 'P'; title = $Config.plan.title }; categoryDescriptions = [pscustomobject]@{ category1 = 'a'; category2 = 'b'; category3 = 'c' }
                buckets = @($Config.buckets | ForEach-Object { @{ id = "b-$_"; name = $_ } }); tasks = @($Config.tasks | ForEach-Object { @{ title = $_.title } }) }
        }
        Mock -ModuleName PlannerTodo Invoke-MgGraphRequest { throw 'must not be called' }
        $rows = @(Set-PlannerPlan -Config $config -Today $now -Confirm:$false)
        $rows.Count | Should -Be 1
        $rows[0].Result | Should -Match 'Nothing to do'
    }
}

Describe 'To Do focus list' {
    BeforeAll {
        $script:mine = @(
            [pscustomobject]@{ id = 'p1'; planId = 'PL'; title = 'Overdue one'; priority = 3; percentComplete = 0; dueDateTime = '2026-11-15T17:00:00Z' }
            [pscustomobject]@{ id = 'p2'; planId = 'PL'; title = 'Due in 3 days'; priority = 5; percentComplete = 40; dueDateTime = '2026-11-23T17:00:00Z' }
            [pscustomobject]@{ id = 'p3'; planId = 'PL'; title = 'Due in 30 days'; priority = 5; percentComplete = 0; dueDateTime = '2026-12-20T17:00:00Z' }
            [pscustomobject]@{ id = 'p4'; planId = 'PL'; title = 'Urgent, no date'; priority = 1; percentComplete = 0 }
            [pscustomobject]@{ id = 'p5'; planId = 'PL'; title = 'Already done'; priority = 1; percentComplete = 100; dueDateTime = '2026-11-10T17:00:00Z' }
            [pscustomobject]@{ id = 'p6'; planId = 'OTHER'; title = 'Other plan'; priority = 1; percentComplete = 0; dueDateTime = '2026-11-10T17:00:00Z' }
        )
    }
    It 'picks overdue, due within 7 days and urgent; skips complete and other plans; most pressing first' {
        $f = @(Get-PlannerFocusTask -Task $mine -PlanId 'PL' -Now $now -DueWithinDays 7)
        ($f.title -join '|') | Should -Be 'Overdue one|Due in 3 days|Urgent, no date'
    }
    It 'importance: 1-4 high, 5-7 normal, 8+ low (Learn: priority 1 urgent, 3 important, 5 medium, 9 low)' {
        (1, 3, 5, 9 | ForEach-Object { ConvertTo-TodoImportance $_ }) | Should -Be @('high', 'high', 'normal', 'low')
    }
    It 'To Do task body: due date in UTC, linkedResource with the Planner task id as externalId' {
        $b = ConvertTo-TodoTaskBody -PlannerTask $mine[0] -PlanTitle 'Plan X' -BucketName 'Build'
        $b.dueDateTime.dateTime | Should -Be '2026-11-15T17:00:00.0000000'; $b.dueDateTime.timeZone | Should -Be 'UTC'
        $b.linkedResources[0].externalId | Should -Be 'p1'
        $b.linkedResources[0].applicationName | Should -Be 'Microsoft Planner'
        $b.importance | Should -Be 'high'
        $b.body.content | Should -Match "plan 'Plan X', bucket 'Build'"
    }
    Context 'Sync-PlannerFocusToTodo (mocked Graph)' {
        BeforeEach {
            $script:posts = [System.Collections.Generic.List[object]]::new()
            Mock -ModuleName PlannerTodo Invoke-PLGraphGet {
                switch -Wildcard ($Uri) {
                    '/v1.0/me/planner/tasks' { $mine }
                    '/v1.0/me/todo/lists' { @([pscustomobject]@{ id = 'L1'; displayName = 'Falcon focus' }) }
                    '/v1.0/me/todo/lists/L1/tasks' {
                        @([pscustomobject]@{ id = 'td1'; title = 'Overdue one'; status = 'notStarted'; linkedResources = @([pscustomobject]@{ applicationName = 'Microsoft Planner'; externalId = 'p1' }) },
                            [pscustomobject]@{ id = 'td5'; title = 'Already done'; status = 'notStarted'; linkedResources = @([pscustomobject]@{ applicationName = 'Microsoft Planner'; externalId = 'p5' }) })
                    }
                }
            } -ParameterFilter { $true }
            Mock -ModuleName PlannerTodo Invoke-MgGraphRequest { $script:posts.Add([pscustomobject]@{ Method = $Method; Uri = $Uri; Body = $Body }); [pscustomobject]@{ id = 'new' } }
        }
        It 'creates only the missing focus tasks, and completes the To Do task of a finished Planner task' {
            $rows = @(Sync-PlannerFocusToTodo -PlanId 'PL' -PlanTitle 'Plan X' -ListName 'Falcon focus' -Now $now -Confirm:$false)
            ($rows | Where-Object Step -eq 'Keep').Target | Should -Be 'Overdue one'
            ($rows | Where-Object Step -eq 'CreateTodoTask').Target | Should -Be @('Due in 3 days', 'Urgent, no date')
            ($rows | Where-Object Step -eq 'CompleteTodoTask').Target | Should -Be 'Already done'
            $p = @($script:posts | Where-Object Method -eq 'POST'); $p.Count | Should -Be 2
            ($p[0].Body | ConvertFrom-Json).linkedResources[0].externalId | Should -Be 'p2'
            $c = @($script:posts | Where-Object Method -eq 'PATCH'); $c.Count | Should -Be 1
            $c[0].Uri | Should -Be '/v1.0/me/todo/lists/L1/tasks/td5'
            ($c[0].Body | ConvertFrom-Json).status | Should -Be 'completed'
        }
        It '-WhatIf writes nothing' {
            $rows = @(Sync-PlannerFocusToTodo -PlanId 'PL' -PlanTitle 'Plan X' -ListName 'Falcon focus' -Now $now -WhatIf)
            $script:posts.Count | Should -Be 0
            ($rows | Where-Object Result -like 'WhatIf*').Count | Should -Be 3
        }
    }
}

Describe 'Calls match the real Microsoft Graph PowerShell module' -Tag 'RealModule' {
    It 'Invoke-MgGraphRequest has every parameter we pass (-Headers, -OutputType, -ContentType, -Body)' -Skip:(-not (Get-Module Microsoft.Graph.Authentication -ListAvailable)) {
        $keys = (Get-Command Invoke-MgGraphRequest -Module Microsoft.Graph.Authentication).Parameters.Keys
        foreach ($p in 'Method', 'Uri', 'Body', 'Headers', 'OutputType', 'ContentType') { $keys | Should -Contain $p }
    }
    It 'the Planner cmdlets take the same bodies and an If-Match value (New-MgPlannerTask, Update-MgPlannerTaskDetail)' -Skip:(-not (Get-Module Microsoft.Graph.Planner -ListAvailable)) {
        (Get-Command New-MgPlannerTask -Module Microsoft.Graph.Planner).Parameters.Keys | Should -Contain 'BodyParameter'
        (Get-Command Update-MgPlannerTaskDetail -Module Microsoft.Graph.Planner).Parameters.Keys | Should -Contain 'IfMatch'
    }
}
