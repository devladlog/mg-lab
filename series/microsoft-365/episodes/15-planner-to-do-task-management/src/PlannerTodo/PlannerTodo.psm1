#Requires -Version 7.2
<#
    PlannerTodo: a Planner plan built from one file (plan.json), audited with Graph data, and a personal
    Microsoft To Do focus list fed from the Planner tasks assigned to the signed-in user.

      * Config   - Get-PlannerPlanConfig: validates plan.json against the documented Planner limits.
      * Plan     - Get-PlannerPlanDiff (pure) + Set-PlannerPlan: create the plan, labels, buckets and tasks that are
                   missing. Existing items are never touched (people edit plans by hand).
      * Audit    - Get-PlannerInventory + Get-PlannerFinding + ConvertTo-PlannerMarkdown.
      * To Do    - Get-PlannerFocusTask (pure) + Sync-PlannerFocusToTodo: delegated only, one To Do list.
      * Etags    - Invoke-PlannerPatch: PATCH with If-Match, re-reads and retries once on 409/412.

    Only Invoke-PLGraphGet, Invoke-PlannerPatch, Get-PlannerInventory, Set-PlannerPlan and Sync-PlannerFocusToTodo
    call Microsoft Graph (Invoke-MgGraphRequest).
#>

Set-StrictMode -Version Latest

# Planner limits (Learn: office365/planner/planner-limits)
$script:Limits = @{
    ActiveTasksInPlan = 3000; TasksInPlan = 9000; BucketsInPlan = 200
    AssigneesInTask = 20; ChecklistItemsInTask = 20; ReferencesOnTask = 15; CategoriesOnTask = 6; CategoriesInPlan = 25
}
# Planner interprets priority 1 = urgent, 3 = important, 5 = medium, 9 = low (Learn: plannerTask resource)
$script:PriorityValue = @{ urgent = 1; important = 3; medium = 5; low = 9 }
$script:ZeroGuid = [guid]::Empty.ToString()

#region Helpers ---------------------------------------------------------------------------------------------------

function Get-PLProp {
    param([object]$Object, [string]$Name, [object]$Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { $Default } else { $p.Value }
}

function Get-PLKey {
    <# Property names of an open-type object (assignments, appliedCategories): hashtable or PSCustomObject. #>
    param([AllowNull()][object]$Object, [switch]$TrueOnly)
    if ($null -eq $Object) { return @() }
    if ($Object -is [System.Collections.IDictionary]) {
        return @($Object.Keys | Where-Object { -not $TrueOnly -or $Object[$_] -eq $true })
    }
    @($Object.PSObject.Properties | Where-Object { -not $TrueOnly -or $_.Value -eq $true } | ForEach-Object { $_.Name })
}

function ConvertTo-PLDate {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value -or "$Value" -eq '') { return $null }
    if ($Value -is [datetimeoffset]) { return $Value.ToUniversalTime() }
    if ($Value -is [datetime]) { return ([datetimeoffset][datetime]::SpecifyKind($Value, 'Utc')) }
    $styles = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
    [datetimeoffset]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture, $styles)
}

function ConvertTo-PLReferenceKey {
    <# Open-type property names cannot contain . : % @ # (Learn: plannerExternalReferences), so a URL is encoded. #>
    param([Parameter(Mandatory)][string]$Url)
    if ($Url -notmatch '^https?://') { throw "A Planner reference must be an http or https URL (got '$Url')." }
    $Url.Replace('%', '%25').Replace('.', '%2E').Replace(':', '%3A').Replace('@', '%40').Replace('#', '%23')
}

function Get-PLStableGuid {
    <# Deterministic GUID for checklist keys, so the same task definition always produces the same item ids. #>
    param([Parameter(Mandatory)][string]$Text)
    $md5 = [Security.Cryptography.MD5]::Create()
    try { [guid]::new($md5.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text))).ToString() } finally { $md5.Dispose() }
}

function Get-PLHttpStatus {
    <# Status code of a failed Invoke-MgGraphRequest: from the response if there is one, else from the message. #>
    param([Parameter(Mandatory)][System.Management.Automation.ErrorRecord]$ErrorRecord)
    $e = $ErrorRecord.Exception
    $r = Get-PLProp $e 'Response'
    if ($r -and (Get-PLProp $r 'StatusCode')) { return [int](Get-PLProp $r 'StatusCode') }
    if ($e.Message -match '\b(400|403|404|409|412|429)\b') { return [int]$Matches[1] }
    $null
}

#endregion

#region Config (pure) ---------------------------------------------------------------------------------------------

function Get-PlannerPlanConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $c = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $title = "$(Get-PLProp $c.plan 'title' '')".Trim()
    if (-not $title) { throw 'plan.title is required.' }
    if ("$(Get-PLProp $c.plan 'groupId' '')" -notmatch '^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$') { throw 'plan.groupId must be the object id (GUID) of the Microsoft 365 group that will own the plan.' }
    $labels = @(Get-PLProp $c.plan 'labels' @())
    if ($labels.Count -gt $script:Limits.CategoriesInPlan) { throw "A plan has up to $($script:Limits.CategoriesInPlan) labels (got $($labels.Count))." }
    $buckets = @($c.buckets)
    if ($buckets.Count -eq 0) { throw 'At least one bucket is required.' }
    if ($buckets.Count -gt $script:Limits.BucketsInPlan) { throw "A plan has up to $($script:Limits.BucketsInPlan) buckets (got $($buckets.Count))." }
    if (@($buckets | Sort-Object -Unique).Count -ne $buckets.Count) { throw 'Bucket names must be unique.' }
    $tasks = @($c.tasks)
    if ($tasks.Count -gt $script:Limits.TasksInPlan) { throw "A plan has up to $($script:Limits.TasksInPlan) tasks (got $($tasks.Count))." }
    $seen = @{}
    foreach ($t in $tasks) {
        $name = "$(Get-PLProp $t 'title' '')".Trim()
        if (-not $name) { throw 'Every task needs a title.' }
        if ($seen.ContainsKey($name.ToLowerInvariant())) { throw "Duplicate task title '$name': the title is how the script recognises a task it already created." }
        $seen[$name.ToLowerInvariant()] = $true
        if ($t.bucket -notin $buckets) { throw "Task '$name': bucket '$($t.bucket)' is not in the bucket list." }
        $prio = "$(Get-PLProp $t 'priority' 'medium')"
        if (-not $script:PriorityValue.ContainsKey($prio)) { throw "Task '$name': priority must be urgent, important, medium or low (got '$prio')." }
        $as = @(Get-PLProp $t 'assignees' @())
        if ($as.Count -gt $script:Limits.AssigneesInTask) { throw "Task '$name': up to $($script:Limits.AssigneesInTask) assignees (got $($as.Count))." }
        foreach ($a in $as) { if ($a -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') { throw "Task '$name': '$a' is not a user principal name." } }
        $cl = @(Get-PLProp $t 'checklist' @())
        if ($cl.Count -gt $script:Limits.ChecklistItemsInTask) { throw "Task '$name': up to $($script:Limits.ChecklistItemsInTask) checklist items (got $($cl.Count))." }
        $refs = @(Get-PLProp $t 'references' @())
        if ($refs.Count -gt $script:Limits.ReferencesOnTask) { throw "Task '$name': up to $($script:Limits.ReferencesOnTask) references (got $($refs.Count))." }
        foreach ($r in $refs) { $null = ConvertTo-PLReferenceKey $r.url }
        $tl = @(Get-PLProp $t 'labels' @())
        if ($tl.Count -gt $script:Limits.CategoriesOnTask) { throw "Task '$name': up to $($script:Limits.CategoriesOnTask) labels on a task (got $($tl.Count))." }
        foreach ($l in $tl) { if ($l -notin $labels) { throw "Task '$name': label '$l' is not defined in plan.labels." } }
        $s = Get-PLProp $t 'startInDays'; $d = Get-PLProp $t 'dueInDays'
        if ($null -ne $s -and $null -ne $d -and [int]$s -gt [int]$d) { throw "Task '$name': the start date is after the due date (Planner answers 400 for that)." }
    }
    $c
}

#endregion

#region Plan (pure) -----------------------------------------------------------------------------------------------

function ConvertTo-PlannerTaskBody {
    <# The POST /planner/tasks body for one task of the config. $UserIds maps UPN (lower case) -> user object id. #>
    param(
        [Parameter(Mandatory)][object]$Task, [Parameter(Mandatory)][object]$Config, [Parameter(Mandatory)][string]$PlanId,
        [Parameter(Mandatory)][string]$BucketId, [hashtable]$UserIds = @{}, [datetimeoffset]$Today = [datetimeoffset]::UtcNow
    )
    $body = [ordered]@{ planId = $PlanId; bucketId = $BucketId; title = "$($Task.title)".Trim(); priority = $script:PriorityValue["$(Get-PLProp $Task 'priority' 'medium')"] }
    # Due dates are stored as UTC timestamps; 17:00 UTC is the end of the working day in Portugal.
    $day = $Today.UtcDateTime.Date
    $s = Get-PLProp $Task 'startInDays'; $d = Get-PLProp $Task 'dueInDays'
    if ($null -ne $s) { $body.startDateTime = $day.AddDays([int]$s).AddHours(8).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'") }
    if ($null -ne $d) { $body.dueDateTime = $day.AddDays([int]$d).AddHours(17).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'") }
    $assign = [ordered]@{}
    foreach ($upn in @(Get-PLProp $Task 'assignees' @())) {
        $id = $UserIds[$upn.ToLowerInvariant()]
        if (-not $id) { throw "No user id for '$upn'." }
        # The user id is the property name; @odata.type and orderHint are required (Learn: planner-overview, Tasks).
        $assign[$id] = [ordered]@{ '@odata.type' = '#microsoft.graph.plannerAssignment'; orderHint = ' !' }
    }
    if ($assign.Count) { $body.assignments = $assign }
    $labels = @($Config.plan.labels)
    $applied = [ordered]@{}
    foreach ($l in @(Get-PLProp $Task 'labels' @())) { $applied["category$([array]::IndexOf($labels, $l) + 1)"] = $true }
    if ($applied.Count) { $body.appliedCategories = $applied }
    $body
}

function ConvertTo-PlannerDetailsBody {
    <# The PATCH /planner/tasks/{id}/details body: description, checklist and references. $null when there is nothing. #>
    param([Parameter(Mandatory)][object]$Task)
    $body = [ordered]@{}
    $desc = "$(Get-PLProp $Task 'description' '')"
    if ($desc) { $body.description = $desc }
    $cl = @(Get-PLProp $Task 'checklist' @())
    if ($cl.Count) {
        $items = [ordered]@{}
        $i = 0
        foreach ($text in $cl) {
            $i++
            $items[(Get-PLStableGuid "$($Task.title)|$i|$text")] = [ordered]@{ '@odata.type' = 'microsoft.graph.plannerChecklistItem'; title = $text; isChecked = $false }
        }
        $body.checklist = $items
        $body.previewType = 'checklist'
    }
    $refs = @(Get-PLProp $Task 'references' @())
    if ($refs.Count) {
        $r = [ordered]@{}
        foreach ($ref in $refs) {
            $r[(ConvertTo-PLReferenceKey $ref.url)] = [ordered]@{ '@odata.type' = 'microsoft.graph.plannerExternalReference'; alias = $ref.alias; type = (Get-PLProp $ref 'type' 'Other'); previewPriority = ' !' }
        }
        $body.references = $r
    }
    if ($body.Count) { $body } else { $null }
}

function Get-PlannerPlanDiff {
    <#
        What has to be created so that the tenant matches the config. $Existing is $null when the plan does not exist yet,
        else @{ Plan; Buckets; Tasks; CategoryDescriptions }. Nothing that exists is ever modified.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Config, [AllowNull()][object]$Existing)
    $actions = [System.Collections.Generic.List[object]]::new()
    $add = { param($a, $t, $d) $actions.Add([pscustomobject]@{ Action = $a; Target = $t; Detail = $d }) }
    $labels = @($Config.plan.labels)
    if (-not $Existing) {
        & $add 'CreatePlan' $Config.plan.title "Container: group $($Config.plan.groupId)"
        if ($labels.Count) { & $add 'SetLabels' $Config.plan.title ($labels -join ', ') }
        foreach ($b in @($Config.buckets)) { & $add 'CreateBucket' $b '' }
        foreach ($t in @($Config.tasks)) { & $add 'CreateTask' $t.title "bucket $($t.bucket), $(@(Get-PLProp $t 'assignees' @()).Count) assignee(s)" }
        return $actions.ToArray()
    }
    $desc = Get-PLProp $Existing 'CategoryDescriptions'
    $missingLabels = for ($i = 0; $i -lt $labels.Count; $i++) {
        $cur = Get-PLProp $desc "category$($i + 1)"
        if (-not $cur) { $labels[$i] }   # only fill empty slots: a label somebody renamed stays
    }
    if (@($missingLabels).Count) { & $add 'SetLabels' $Config.plan.title (@($missingLabels) -join ', ') }
    $haveBuckets = @(@($Existing.Buckets) | ForEach-Object { "$($_.name)".ToLowerInvariant() })
    foreach ($b in @($Config.buckets)) { if ($b.ToLowerInvariant() -notin $haveBuckets) { & $add 'CreateBucket' $b '' } }
    $haveTasks = @(@($Existing.Tasks) | ForEach-Object { "$($_.title)".Trim().ToLowerInvariant() })
    foreach ($t in @($Config.tasks)) {
        if ($t.title.Trim().ToLowerInvariant() -notin $haveTasks) { & $add 'CreateTask' $t.title "bucket $($t.bucket), $(@(Get-PLProp $t 'assignees' @()).Count) assignee(s)" }
    }
    $actions.ToArray()
}

#endregion

#region Graph calls ------------------------------------------------------------------------------------------------

function Invoke-PLGraphGet {
    <# GET with @odata.nextLink paging; returns the items. #>
    param([Parameter(Mandatory)][string]$Uri)
    $items = [System.Collections.Generic.List[object]]::new()
    $next = $Uri
    while ($next) {
        $r = Invoke-MgGraphRequest -Method GET -Uri $next -OutputType PSObject -ErrorAction Stop
        # An empty collection is { "value": [] }: test for the property, not for a non-empty value.
        $isCollection = if ($r -is [System.Collections.IDictionary]) { $r.Contains('value') } else { $null -ne $r.PSObject.Properties['value'] }
        if ($isCollection) { foreach ($v in @(Get-PLProp $r 'value')) { $items.Add($v) } } else { $items.Add($r) }
        $next = Get-PLProp $r '@odata.nextLink'
    }
    $items.ToArray()
}

function Invoke-PlannerPatch {
    <#
        PATCH a Planner resource. Planner requires If-Match with the last etag you know; so: read it, patch, and if the
        service answers 412 or 409 (somebody changed the item in between) read the new version and try again.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Uri, [Parameter(Mandatory)][object]$Body, [int]$MaxRetries = 2)
    $attempt = 0
    while ($true) {
        $current = Invoke-MgGraphRequest -Method GET -Uri $Uri -OutputType PSObject -ErrorAction Stop
        $etag = Get-PLProp $current '@odata.etag'
        if (-not $etag) { throw "No @odata.etag on ${Uri}: Planner PATCH needs If-Match." }
        try {
            return Invoke-MgGraphRequest -Method PATCH -Uri $Uri -Body ($Body | ConvertTo-Json -Depth 10) -ContentType 'application/json' `
                -Headers @{ 'If-Match' = $etag; Prefer = 'return=representation' } -OutputType PSObject -ErrorAction Stop
        }
        catch {
            $code = Get-PLHttpStatus $_
            if ($code -in 409, 412 -and $attempt -lt $MaxRetries) { $attempt++; continue }
            throw
        }
    }
}

function Resolve-PLUser {
    param([Parameter(Mandatory)][string]$Upn, [Parameter(Mandatory)][hashtable]$Cache)
    $key = $Upn.ToLowerInvariant()
    if (-not $Cache.ContainsKey($key)) {
        $u = Invoke-MgGraphRequest -Method GET -Uri "/v1.0/users/$([uri]::EscapeDataString($Upn))?`$select=id,displayName,userPrincipalName" -OutputType PSObject -ErrorAction Stop
        $Cache[$key] = $u.id
    }
    $Cache[$key]
}

function Get-PlannerInventory {
    <# Everything the audit needs from one plan, as plain data (save it with ConvertTo-Json to audit offline). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$GroupId, [Parameter(Mandatory)][string]$PlanTitle)
    $plans = @(Invoke-PLGraphGet "/v1.0/groups/$GroupId/planner/plans" | Where-Object { $_.title -eq $PlanTitle })
    if ($plans.Count -eq 0) { return $null }
    if ($plans.Count -gt 1) { throw "Group $GroupId has $($plans.Count) plans titled '$PlanTitle'." }
    $planId = $plans[0].id
    $details = Invoke-MgGraphRequest -Method GET -Uri "/v1.0/planner/plans/$planId/details" -OutputType PSObject -ErrorAction Stop
    $buckets = @(Invoke-PLGraphGet "/v1.0/planner/plans/$planId/buckets")
    $tasks = @(Invoke-PLGraphGet "/v1.0/planner/plans/$planId/tasks")
    $users = [ordered]@{}
    $ids = $tasks | ForEach-Object { Get-PLKey (Get-PLProp $_ 'assignments') } | Sort-Object -Unique
    foreach ($id in $ids) {
        $u = Invoke-MgGraphRequest -Method GET -Uri "/v1.0/users/$id`?`$select=id,displayName,userPrincipalName" -OutputType PSObject -ErrorAction Stop
        $users[$id] = [ordered]@{ upn = $u.userPrincipalName; name = $u.displayName }
    }
    [ordered]@{
        plan                 = [ordered]@{ id = $planId; title = $plans[0].title }
        categoryDescriptions = Get-PLProp $details 'categoryDescriptions'
        buckets              = @($buckets | ForEach-Object { [ordered]@{ id = $_.id; name = $_.name } })
        users                = $users
        tasks                = @($tasks | ForEach-Object {
                [ordered]@{
                    id = $_.id; title = $_.title; bucketId = $_.bucketId; priority = $_.priority; percentComplete = $_.percentComplete
                    createdDateTime = $_.createdDateTime; startDateTime = $_.startDateTime; dueDateTime = $_.dueDateTime
                    completedDateTime = $_.completedDateTime
                    assignees = @(Get-PLKey (Get-PLProp $_ 'assignments'))
                    checklistItemCount = $_.checklistItemCount; activeChecklistItemCount = $_.activeChecklistItemCount
                    referenceCount = $_.referenceCount; appliedCategories = @(Get-PLKey (Get-PLProp $_ 'appliedCategories') -TrueOnly)
                }
            })
    }
}

function Set-PlannerPlan {
    <#
        Creates what Get-PlannerPlanDiff says is missing: plan, labels, buckets, tasks (+ details). Supports -WhatIf.
        Returns Step / Target / Result rows.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
    param([Parameter(Mandatory)][object]$Config, [datetimeoffset]$Today = [datetimeoffset]::UtcNow)
    $gid = $Config.plan.groupId
    $inv = Get-PlannerInventory -GroupId $gid -PlanTitle $Config.plan.title
    $existing = if ($inv) { @{ Plan = $inv.plan; Buckets = $inv.buckets; Tasks = $inv.tasks; CategoryDescriptions = $inv.categoryDescriptions } } else { $null }
    $diff = @(Get-PlannerPlanDiff -Config $Config -Existing $existing)
    $rows = [System.Collections.Generic.List[object]]::new()
    $row = { param($s, $t, $r) $rows.Add([pscustomobject]@{ Step = $s; Target = $t; Result = $r }) }
    if ($diff.Count -eq 0) { return @([pscustomobject]@{ Step = 'Plan'; Target = $Config.plan.title; Result = 'Nothing to do: the plan already has everything in the file' }) }

    $planId = if ($inv) { $inv.plan.id } else { $null }
    $bucketIds = @{}; if ($inv) { foreach ($b in $inv.buckets) { $bucketIds[$b.name.ToLowerInvariant()] = $b.id } }
    $users = @{}
    $lastBucketHint = $null
    foreach ($a in $diff) {
        if (-not $PSCmdlet.ShouldProcess("$($a.Target)", $a.Action)) { & $row $a.Action $a.Target "WhatIf $($a.Detail)".Trim(); continue }
        switch ($a.Action) {
            'CreatePlan' {
                $p = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/planner/plans' -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop `
                    -Body (@{ title = $Config.plan.title; container = @{ containerId = $gid; type = 'group' } } | ConvertTo-Json -Depth 5)
                $planId = $p.id; & $row 'CreatePlan' $a.Target 'Created'
            }
            'SetLabels' {
                $labels = @($Config.plan.labels)
                $cur = Invoke-MgGraphRequest -Method GET -Uri "/v1.0/planner/plans/$planId/details" -OutputType PSObject -ErrorAction Stop
                $desc = [ordered]@{}
                for ($i = 0; $i -lt $labels.Count; $i++) { if (-not (Get-PLProp (Get-PLProp $cur 'categoryDescriptions') "category$($i + 1)")) { $desc["category$($i + 1)"] = $labels[$i] } }
                $null = Invoke-PlannerPatch -Uri "/v1.0/planner/plans/$planId/details" -Body @{ categoryDescriptions = $desc }
                & $row 'SetLabels' $a.Target "Set $($desc.Count) label(s)"
            }
            'CreateBucket' {
                $body = @{ name = $a.Target; planId = $planId }
                if ($lastBucketHint) { $body.orderHint = "$lastBucketHint !" }   # "<previous order hint> !" = after the previous bucket
                $b = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/planner/buckets' -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop -Body ($body | ConvertTo-Json)
                $bucketIds[$a.Target.ToLowerInvariant()] = $b.id; $lastBucketHint = Get-PLProp $b 'orderHint'
                & $row 'CreateBucket' $a.Target 'Created'
            }
            'CreateTask' {
                $t = @($Config.tasks) | Where-Object { $_.title -eq $a.Target } | Select-Object -First 1
                foreach ($upn in @(Get-PLProp $t 'assignees' @())) { $null = Resolve-PLUser -Upn $upn -Cache $users }
                $body = ConvertTo-PlannerTaskBody -Task $t -Config $Config -PlanId $planId -BucketId $bucketIds[$t.bucket.ToLowerInvariant()] -UserIds $users -Today $Today
                $created = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/planner/tasks' -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop -Body ($body | ConvertTo-Json -Depth 10)
                $d = ConvertTo-PlannerDetailsBody -Task $t
                if ($d) { $null = Invoke-PlannerPatch -Uri "/v1.0/planner/tasks/$($created.id)/details" -Body $d }
                & $row 'CreateTask' $a.Target 'Created'
            }
        }
    }
    $rows.ToArray()
}

#endregion

#region Audit (pure) ----------------------------------------------------------------------------------------------

function ConvertTo-PLFinding {
    param([string]$Severity, [string]$Target, [string]$Rule, [string]$Detail)
    [pscustomobject]@{ Severity = $Severity; Target = $Target; Rule = $Rule; Detail = $Detail }
}

function Get-PlannerFinding {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Inventory, [Parameter(Mandatory)][object]$Config, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    $au = Get-PLProp $Config 'audit'
    $soon = [int](Get-PLProp $au 'dueSoonDays' 7); $stale = [int](Get-PLProp $au 'staleNotStartedDays' 21); $maxActive = [int](Get-PLProp $au 'maxActivePerPerson' 8)
    $tasks = @($Inventory.tasks)
    $users = Get-PLProp $Inventory 'users' @{}
    $who = { param($id) $u = Get-PLProp $users $id; if ($u) { "$(Get-PLProp $u 'name') ($(Get-PLProp $u 'upn'))" } else { 'unknown user' } }
    $active = @($tasks | Where-Object { [int](Get-PLProp $_ 'percentComplete' 0) -lt 100 })
    $out = [System.Collections.Generic.List[object]]::new()
    foreach ($t in $active) {
        $due = ConvertTo-PLDate (Get-PLProp $t 'dueDateTime')
        $prio = [int](Get-PLProp $t 'priority' 5)
        $assignees = @(Get-PLProp $t 'assignees' @())
        if ($due -and $due -lt $Now) {
            $days = [int][math]::Floor(($Now - $due).TotalDays)
            $sev = if ($prio -le 1) { 'High' } else { 'Medium' }
            $who2 = if ($assignees.Count) { (@($assignees | ForEach-Object { & $who $_ }) -join ', ') } else { 'nobody' }
            $out.Add((ConvertTo-PLFinding $sev $t.title 'Overdue' "Due $($due.ToString('yyyy-MM-dd')), $days day(s) ago, not complete. Assigned to $who2."))
        }
        elseif ($due -and $due -le $Now.AddDays($soon)) {
            $out.Add((ConvertTo-PLFinding 'Info' $t.title 'DueSoon' "Due $($due.ToString('yyyy-MM-dd')) (within $soon days)."))
        }
        if ($assignees.Count -eq 0) { $out.Add((ConvertTo-PLFinding 'Medium' $t.title 'Unassigned' 'Not assigned to anyone, so it appears in nobody''s My Tasks or To Do.')) }
        if (-not $due) { $out.Add((ConvertTo-PLFinding 'Low' $t.title 'NoDueDate' 'No due date: it can never be overdue, so it never shows up as a risk.')) }
        $created = ConvertTo-PLDate (Get-PLProp $t 'createdDateTime')
        if ($created -and [int](Get-PLProp $t 'percentComplete' 0) -eq 0 -and ($Now - $created).TotalDays -ge $stale) {
            $out.Add((ConvertTo-PLFinding 'Low' $t.title 'NotStartedStale' "Created $([int][math]::Floor(($Now - $created).TotalDays)) days ago and still at 0 percent."))
        }
    }
    foreach ($t in $tasks) {
        if ([int](Get-PLProp $t 'percentComplete' 0) -eq 100 -and [int](Get-PLProp $t 'activeChecklistItemCount' 0) -gt 0) {
            $out.Add((ConvertTo-PLFinding 'Low' $t.title 'CompletedWithOpenChecklist' "Marked complete with $($t.activeChecklistItemCount) unchecked checklist item(s)."))
        }
    }
    # Workload: active tasks per assignee (a task with two assignees counts for both)
    $load = @{}
    foreach ($t in $active) { foreach ($id in @(Get-PLProp $t 'assignees' @())) { $load[$id] = 1 + [int](Get-PLProp $load $id 0) } }
    foreach ($id in $load.Keys) {
        if ($load[$id] -gt $maxActive) { $out.Add((ConvertTo-PLFinding 'Medium' (& $who $id) 'Overloaded' "$($load[$id]) active tasks in this plan (limit used by this audit: $maxActive).")) }
    }
    foreach ($b in @($Inventory.buckets)) {
        if (@($tasks | Where-Object { $_.bucketId -eq $b.id }).Count -eq 0) { $out.Add((ConvertTo-PLFinding 'Info' $b.name 'EmptyBucket' 'The bucket has no tasks.')) }
    }
    # Documented limits: 3,000 active tasks, 9,000 tasks, 200 buckets per plan
    $checks = @(
        @('active tasks', $active.Count, $script:Limits.ActiveTasksInPlan), @('tasks', $tasks.Count, $script:Limits.TasksInPlan), @('buckets', @($Inventory.buckets).Count, $script:Limits.BucketsInPlan)
    )
    foreach ($c in $checks) {
        if ($c[1] -ge 0.8 * $c[2]) { $out.Add((ConvertTo-PLFinding 'Medium' $Inventory.plan.title 'ApproachingLimit' "$($c[1]) $($c[0]) of $($c[2]) allowed in a plan.")) }
    }
    $rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
    @($out | Sort-Object { $rank[$_.Severity] }, Target, Rule)
}

function ConvertTo-PlannerMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Inventory, [AllowEmptyCollection()][object[]]$Finding, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    $tasks = @($Inventory.tasks)
    $done = @($tasks | Where-Object { [int](Get-PLProp $_ 'percentComplete' 0) -eq 100 }).Count
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine("# Planner audit: $($Inventory.plan.title)").AppendLine()
    $null = $sb.AppendLine("Generated $($Now.ToString('yyyy-MM-dd HH:mm')) UTC. $($tasks.Count) tasks ($done complete), $(@($Inventory.buckets).Count) buckets, $(@($Finding).Count) findings.").AppendLine()
    if (@($Finding).Count -eq 0) { $null = $sb.AppendLine('No findings.'); return $sb.ToString() }
    $null = $sb.AppendLine('| Severity | Target | Rule | Detail |').AppendLine('|---|---|---|---|')
    foreach ($f in $Finding) { $null = $sb.AppendLine("| $($f.Severity) | $($f.Target -replace '\|', '/') | $($f.Rule) | $($f.Detail -replace '\|', '/') |") }
    $sb.ToString()
}

#endregion

#region To Do ------------------------------------------------------------------------------------------------------

function Get-PlannerFocusTask {
    <# Active Planner tasks of this plan that are overdue, due within N days, or urgent; most pressing first. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object[]]$Task, [Parameter(Mandatory)][string]$PlanId, [datetimeoffset]$Now = [datetimeoffset]::UtcNow, [int]$DueWithinDays = 7)
    $rows = foreach ($t in $Task) {
        if ((Get-PLProp $t 'planId') -and (Get-PLProp $t 'planId') -ne $PlanId) { continue }
        if ([int](Get-PLProp $t 'percentComplete' 0) -ge 100) { continue }
        $due = ConvertTo-PLDate (Get-PLProp $t 'dueDateTime')
        $urgent = [int](Get-PLProp $t 'priority' 5) -le 1
        if (($due -and $due -le $Now.AddDays($DueWithinDays)) -or $urgent) { [pscustomobject]@{ Task = $t; Due = $due } }
    }
    @($rows | Sort-Object { if ($_.Due) { $_.Due } else { [datetimeoffset]::MaxValue } }, { [int](Get-PLProp $_.Task 'priority' 5) } | ForEach-Object { $_.Task })
}

function ConvertTo-TodoImportance {
    # Learn (plannerTask.priority): 0-1 urgent, 2-4 important, 5-7 medium, 8-10 low. To Do has low, normal, high.
    param([int]$Priority)
    if ($Priority -le 4) { 'high' } elseif ($Priority -le 7) { 'normal' } else { 'low' }
}

function ConvertTo-TodoTaskBody {
    param([Parameter(Mandatory)][object]$PlannerTask, [Parameter(Mandatory)][string]$PlanTitle, [string]$BucketName = '')
    $body = [ordered]@{
        title     = "$($PlannerTask.title)"
        importance = ConvertTo-TodoImportance ([int](Get-PLProp $PlannerTask 'priority' 5))
        body      = [ordered]@{ contentType = 'text'; content = ("From the Planner plan '$PlanTitle'" + $(if ($BucketName) { ", bucket '$BucketName'." } else { '.' })) }
        # linkedResource ties the To Do task to its source; externalId is how we recognise it on the next run.
        linkedResources = @([ordered]@{ applicationName = 'Microsoft Planner'; displayName = $PlanTitle; externalId = "$($PlannerTask.id)"; webUrl = 'https://planner.cloud.microsoft/' })
    }
    $due = ConvertTo-PLDate (Get-PLProp $PlannerTask 'dueDateTime')
    if ($due) { $body.dueDateTime = [ordered]@{ dateTime = $due.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.0000000"); timeZone = 'UTC' } }
    $body
}

function Sync-PlannerFocusToTodo {
    <#
        Delegated only (To Do tasks do not support application permissions). Reads the signed-in user's Planner tasks,
        keeps the focus ones in one To Do list, creates what is missing, and completes the To Do task when the Planner
        task is complete. Returns Step / Target / Result rows.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
    param(
        [Parameter(Mandatory)][string]$PlanId, [Parameter(Mandatory)][string]$PlanTitle,
        [string]$ListName = 'Planner focus', [int]$DueWithinDays = 7, [datetimeoffset]$Now = [datetimeoffset]::UtcNow
    )
    $rows = [System.Collections.Generic.List[object]]::new()
    $row = { param($s, $t, $r) $rows.Add([pscustomobject]@{ Step = $s; Target = $t; Result = $r }) }
    $mine = @(Invoke-PLGraphGet '/v1.0/me/planner/tasks' | Where-Object { $_.planId -eq $PlanId })
    $focus = @(Get-PlannerFocusTask -Task $mine -PlanId $PlanId -Now $Now -DueWithinDays $DueWithinDays)

    $list = @(Invoke-PLGraphGet '/v1.0/me/todo/lists' | Where-Object { $_.displayName -eq $ListName }) | Select-Object -First 1
    if (-not $list) {
        if (-not $PSCmdlet.ShouldProcess($ListName, 'Create To Do list')) {
            foreach ($t in $focus) { & $row 'CreateTodoTask' $t.title 'WhatIf (the list does not exist yet)' }
            return $rows.ToArray()
        }
        $list = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/me/todo/lists' -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop -Body (@{ displayName = $ListName } | ConvertTo-Json)
        & $row 'CreateList' $ListName 'Created'
    }
    $listUri = "/v1.0/me/todo/lists/$($list.id)/tasks"
    $have = @{}   # Planner task id -> To Do task
    foreach ($tt in @(Invoke-PLGraphGet $listUri)) {
        $res = Get-PLProp $tt 'linkedResources'
        if ($null -eq $res) { $res = @(Invoke-PLGraphGet "$listUri/$($tt.id)/linkedResources") }
        foreach ($r in @($res)) { if ($r.applicationName -eq 'Microsoft Planner' -and $r.externalId) { $have[$r.externalId] = $tt } }
    }
    foreach ($t in $focus) {
        if ($have.ContainsKey($t.id)) { & $row 'Keep' $t.title 'Already in the list'; continue }
        if (-not $PSCmdlet.ShouldProcess($t.title, 'Create To Do task')) { & $row 'CreateTodoTask' $t.title 'WhatIf'; continue }
        $bodyJson = ConvertTo-TodoTaskBody -PlannerTask $t -PlanTitle $PlanTitle | ConvertTo-Json -Depth 6
        $null = Invoke-MgGraphRequest -Method POST -Uri $listUri -ContentType 'application/json' -Body $bodyJson -OutputType PSObject -ErrorAction Stop
        & $row 'CreateTodoTask' $t.title 'Created'
    }
    # Close the loop: Planner task finished -> To Do task completed
    foreach ($t in $mine) {
        if ([int](Get-PLProp $t 'percentComplete' 0) -lt 100 -or -not $have.ContainsKey($t.id)) { continue }
        $tt = $have[$t.id]
        if ($tt.status -eq 'completed') { continue }
        if (-not $PSCmdlet.ShouldProcess($tt.title, 'Complete To Do task')) { & $row 'CompleteTodoTask' $tt.title 'WhatIf'; continue }
        $null = Invoke-MgGraphRequest -Method PATCH -Uri "$listUri/$($tt.id)" -ContentType 'application/json' -Body (@{ status = 'completed' } | ConvertTo-Json) -OutputType PSObject -ErrorAction Stop
        & $row 'CompleteTodoTask' $tt.title 'Completed'
    }
    if ($rows.Count -eq 0) { & $row 'Focus' $ListName 'Nothing overdue, due soon or urgent' }
    $rows.ToArray()
}

#endregion
