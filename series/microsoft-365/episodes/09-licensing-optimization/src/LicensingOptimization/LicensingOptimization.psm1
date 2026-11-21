#Requires -Version 7.2
<#
.SYNOPSIS
    Microsoft 365 licence optimization (DEVLADLOG Microsoft 365 #9). Collection and the reclaim talk to Microsoft Graph;
    the analysis is pure functions, so it runs offline on a saved snapshot (and in the tests, without a tenant).

    Graph v1.0 used (Microsoft Learn), with the delegated scope each call needs:
      GET  /subscribedSkus                                  LicenseAssignment.Read.All (or Organization.Read.All)
      GET  /users?$select=...,signInActivity                User.Read.All + AuditLog.Read.All, a role such as Reports Reader,
                                                            and a Microsoft Entra ID P1 or P2 licence in the tenant (for signInActivity)
      GET  /directoryRoles, /directoryRoles/{id}/members    RoleManagement.Read.Directory
      POST /users/{id}/assignLicense                        LicenseAssignment.ReadWrite.All + a role (License Administrator,
                                                            User Administrator or Directory Writers). ONLY the reclaim and restore use it.
#>
Set-StrictMode -Version Latest

$script:Graph = '/v1.0'
$script:SeverityOrder = @{ High = 3; Medium = 2; Low = 1; Info = 0 }
$script:ReclaimRules = @('DisabledAccountLicensed', 'InactiveLicensed', 'NeverSignedIn', 'RedundantLicence', 'DuplicateDirectAndGroup')
$script:SavingRules = @('DisabledAccountLicensed', 'InactiveLicensed', 'NeverSignedIn', 'RedundantLicence')
$script:ErrorHint = @{
    CountViolation                     = 'Not enough licences: buy more, or free seats held by users who do not use them.'
    MutuallyExclusiveViolation         = 'Conflicting service plans: disable one of the plans or remove the redundant licence.'
    DependencyViolation                = 'Another assigned product depends on this licence: fix the dependent one first.'
    ProhibitedInUsageLocationViolation = 'The usage location is missing or not allowed for this service: set the right one.'
    UniquenessViolation                = 'A value that must be unique (often a proxy address) is duplicated.'
    Other                              = 'See Errors & issues on the product page of the Microsoft 365 admin center.'
}

function Get-LOProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($p -and $null -ne $p.Value) { $p.Value } else { $Default }
}

function ConvertTo-LODate($Value) {
    if ($null -eq $Value -or "$Value" -eq '') { return $null }
    if ($Value -is [datetimeoffset]) { return $Value }
    if ($Value -is [datetime]) { return [datetimeoffset]::new($Value.ToUniversalTime()) }
    [datetimeoffset]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal)
}

function Invoke-LOGraphPaged([string]$Uri) {
    $items = [System.Collections.Generic.List[object]]::new()
    $next = $Uri
    while ($next) {
        $page = Invoke-MgGraphRequest -Method GET -Uri $next -OutputType PSObject -ErrorAction Stop
        foreach ($v in @(Get-LOProp $page 'value' @())) { $items.Add($v) }
        $next = Get-LOProp $page '@odata.nextLink'
    }
    $items.ToArray()
}

# ---------------------------------------------------------------- config
function Get-LOConfig {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Path)
    $c = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($s in 'inactivity', 'overlap', 'prices', 'reclaim') { if ($null -eq (Get-LOProp $c $s)) { throw "Config: section '$s' is missing." } }
    $i = $c.inactivity
    $d = Get-LOProp $i 'inactiveDays' 0
    if ($d -isnot [int] -and $d -isnot [long] -or $d -lt 1 -or $d -gt 3650) { throw 'Config: inactivity.inactiveDays must be a whole number from 1 to 3650.' }
    $g = Get-LOProp $i 'neverSignedInGraceDays' -1
    if ($g -isnot [int] -and $g -isnot [long] -or $g -lt 0) { throw 'Config: inactivity.neverSignedInGraceDays must be a whole number, 0 or more.' }
    foreach ($u in @(Get-LOProp $c 'protectedUsers' @())) { if ($u -isnot [string] -or [string]::IsNullOrWhiteSpace($u)) { throw 'Config: protectedUsers must be a list of user principal names (wildcards allowed).' } }
    if ((Get-LOProp $c 'protectAdminRoleMembers') -isnot [bool]) { throw 'Config: protectAdminRoleMembers must be true or false.' }
    $m = Get-LOProp $c.overlap 'minSharedPlans' 0
    if ($m -isnot [int] -and $m -isnot [long] -or $m -lt 1) { throw 'Config: overlap.minSharedPlans must be a whole number of at least 1.' }
    foreach ($p in @((Get-LOProp $c 'supersededBy' ([pscustomobject]@{})).PSObject.Properties)) {
        if (@($p.Value).Count -eq 0 -or (@($p.Value) | Where-Object { $_ -isnot [string] })) { throw "Config: supersededBy.$($p.Name) must be a non-empty list of SKU part numbers." }
    }
    if ((Get-LOProp $c.prices 'currency' '') -notmatch '^[A-Z]{3}$') { throw 'Config: prices.currency must be a three-letter currency code.' }
    foreach ($p in @((Get-LOProp $c.prices 'perUserPerMonth' ([pscustomobject]@{})).PSObject.Properties)) {
        if ($p.Value -isnot [int] -and $p.Value -isnot [long] -and $p.Value -isnot [double] -and $p.Value -isnot [decimal] -or $p.Value -lt 0) { throw "Config: prices.perUserPerMonth.$($p.Name) must be a number, 0 or more." }
    }
    foreach ($r in @(Get-LOProp $c.reclaim 'rules' @())) { if ($r -notin $script:ReclaimRules) { throw "Config: reclaim.rules has '$r', which is not a reclaim rule ($($script:ReclaimRules -join ', '))." } }
    foreach ($s in @(Get-LOProp $c.reclaim 'allowedSkuPartNumbers' @())) { if ($s -isnot [string] -or [string]::IsNullOrWhiteSpace($s)) { throw 'Config: reclaim.allowedSkuPartNumbers must be a list of SKU part numbers.' } }
    $c
}

# ---------------------------------------------------------------- collection (Graph)
function Get-LOSku {
    <# Tenant subscriptions: GET /subscribedSkus. #>
    [CmdletBinding()] param()
    @(Invoke-LOGraphPaged "$script:Graph/subscribedSkus")
}

function Get-LOUser {
    <# Users with their licences, how each was assigned, and their sign-in activity. The page size is 500: the documented
       maximum when signInActivity is selected. #>
    [CmdletBinding()] param([int]$Top = 500)
    $select = 'id,displayName,userPrincipalName,accountEnabled,userType,createdDateTime,usageLocation,assignedLicenses,licenseAssignmentStates,signInActivity'
    try { @(Invoke-LOGraphPaged "$script:Graph/users?`$select=$select&`$top=$([Math]::Min(500, $Top))") }
    catch {
        $details = if ($_.ErrorDetails) { $_.ErrorDetails.Message } else { '' }
        if ("$($_.Exception.Message) $details" -match 'Forbidden|403|premium|AuditLog') {
            throw "Microsoft Graph refused the sign-in activity (signInActivity). It needs a Microsoft Entra ID P1 or P2 licence in the tenant, the AuditLog.Read.All permission and a role such as Reports Reader. Original error: $($_.Exception.Message)"
        }
        throw
    }
}

function Get-LOProtectedUserId {
    <# Ids of users who hold an activated Microsoft Entra directory role (direct members only: the directoryRole API does
       not list group-assigned or PIM-eligible members). #>
    [CmdletBinding()] param()
    $ids = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($role in @(Invoke-LOGraphPaged "$script:Graph/directoryRoles?`$select=id,displayName")) {
        foreach ($m in @(Invoke-LOGraphPaged "$script:Graph/directoryRoles/$($role.id)/members?`$select=id")) {
            if ((Get-LOProp $m '@odata.type' '#microsoft.graph.user') -eq '#microsoft.graph.user') { [void]$ids.Add([string]$m.id) }
        }
    }
    @($ids)
}

# ---------------------------------------------------------------- analysis (pure)
function Get-LOFindingRecord($Severity, $Rule, $User, $Sku, $Detail, [bool]$Reclaimable = $false, $Source = '', $DaysInactive = $null, $DisabledPlans = @(), $UserId = '', $SkuId = '', $Price = $null) {
    [pscustomobject]@{
        Severity      = $Severity; Rule = $Rule; User = $User; UserId = $UserId; Sku = $Sku; SkuId = $SkuId; Source = $Source
        Detail        = $Detail; Reclaimable = $Reclaimable; DaysInactive = $DaysInactive; DisabledPlans = @($DisabledPlans)
        MonthlySaving = $(if ($Rule -in $script:SavingRules -and $Reclaimable) { $Price } else { $null })
    }
}

function Get-LOLastActivity($User) {
    $s = Get-LOProp $User 'signInActivity'
    if ($null -eq $s) { return $null }
    # lastSuccessfulSignInDateTime is not backfilled before Dec 2023; fall back to the other two (Learn: signInActivity).
    $ok = ConvertTo-LODate (Get-LOProp $s 'lastSuccessfulSignInDateTime')
    if ($ok) { return $ok }
    $dates = @((Get-LOProp $s 'lastSignInDateTime'), (Get-LOProp $s 'lastNonInteractiveSignInDateTime') | ForEach-Object { ConvertTo-LODate $_ } | Where-Object { $_ })
    if ($dates.Count -eq 0) { return $null }
    ($dates | Sort-Object -Descending | Select-Object -First 1)
}

function Get-LOLicenceFinding {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Skus, [Parameter(Mandatory)]$Users, [string[]]$ProtectedUserId = @(), [Parameter(Mandatory)]$Config, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    $skuInfo = @{}
    foreach ($s in @($Skus)) {
        $plans = @(Get-LOProp $s 'servicePlans' @())
        $skuInfo[([string]$s.skuId).ToLowerInvariant()] = @{ Part = [string]$s.skuPartNumber; PlanIds = @($plans | ForEach-Object { ([string]$_.servicePlanId).ToLowerInvariant() }) }
    }
    $prices = Get-LOProp $Config.prices 'perUserPerMonth'
    $superseded = Get-LOProp $Config 'supersededBy'
    $findings = [System.Collections.Generic.List[object]]::new()
    $users = @($Users)
    $haveSignIn = @($users | Where-Object { $null -ne (Get-LOProp $_ 'signInActivity') }).Count -gt 0
    if ($users.Count -gt 0 -and -not $haveSignIn) {
        $findings.Add((Get-LOFindingRecord 'Info' 'NoSignInData' '(tenant)' '' 'No user came back with signInActivity: the inactivity rules were skipped. It needs a Microsoft Entra ID P1 or P2 licence and AuditLog.Read.All.'))
    }
    foreach ($u in $users) {
        $licences = @(Get-LOProp $u 'assignedLicenses' @())
        if ($licences.Count -eq 0) { continue }
        $upn = [string](Get-LOProp $u 'userPrincipalName' $u.id); $uid = [string]$u.id
        $states = @(Get-LOProp $u 'licenseAssignmentStates' @())
        $isProtected = $false; $why = ''
        if ($Config.protectAdminRoleMembers -and $uid -in $ProtectedUserId) { $isProtected = $true; $why = 'holds an Entra admin role' }
        foreach ($pat in @(Get-LOProp $Config 'protectedUsers' @())) { if ($upn -like $pat) { $isProtected = $true; $why = 'is in protectedUsers' } }
        $held = @{}   # lower sku id -> part number, of licences that are really active
        foreach ($l in $licences) { $held[([string]$l.skuId).ToLowerInvariant()] = $l }
        $enabled = (Get-LOProp $u 'accountEnabled' $true) -ne $false
        $last = Get-LOLastActivity $u
        $created = ConvertTo-LODate (Get-LOProp $u 'createdDateTime')
        $parts = @($licences | ForEach-Object { $k = ([string]$_.skuId).ToLowerInvariant(); if ($skuInfo.ContainsKey($k)) { $skuInfo[$k].Part } else { [string]$_.skuId } })

        foreach ($l in $licences) {
            $key = ([string]$l.skuId).ToLowerInvariant()
            $part = if ($skuInfo.ContainsKey($key)) { $skuInfo[$key].Part } else { [string]$l.skuId }
            $mine = @($states | Where-Object { ([string](Get-LOProp $_ 'skuId' '')).ToLowerInvariant() -eq $key })
            $direct = @($mine | Where-Object { $null -eq (Get-LOProp $_ 'assignedByGroup') }).Count -gt 0
            $viaGroup = @($mine | Where-Object { $null -ne (Get-LOProp $_ 'assignedByGroup') }).Count -gt 0
            $source = if ($mine.Count -eq 0) { 'Unknown' } elseif ($direct -and $viaGroup) { 'Both' } elseif ($direct) { 'Direct' } else { 'Group' }
            $price = if ($prices -and $null -ne (Get-LOProp $prices $part)) { [double](Get-LOProp $prices $part) } else { $null }
            $dis = @(Get-LOProp $l 'disabledPlans' @())
            $note = if ($isProtected) { " Not reclaimable: the user $why." } elseif ($source -eq 'Group') { ' Assigned through a group: remove the user from the group instead.' } elseif ($source -eq 'Both') { ' Also assigned through a group: the direct assignment is not what keeps the seat.' } elseif ($source -eq 'Unknown') { ' Assignment state not returned: not reclaimable.' } else { '' }
            $canReclaim = (-not $isProtected) -and $source -eq 'Direct'
            $add = { param($sev, $rule, $detail, $reclaim, $days) $findings.Add((Get-LOFindingRecord $sev $rule $upn $part $detail $reclaim $source $days $dis $uid ([string]$l.skuId) $price)) }

            if (-not $enabled) { & $add 'Medium' 'DisabledAccountLicensed' "Account is disabled but still holds $part.$note" $canReclaim $null }
            elseif ($haveSignIn) {
                if ($null -eq $last) {
                    if ($created -and ($Now - $created).TotalDays -ge $Config.inactivity.neverSignedInGraceDays) {
                        & $add 'Medium' 'NeverSignedIn' ("Never signed in, created {0:0} days ago.{1}" -f ($Now - $created).TotalDays, $note) $canReclaim $null
                    }
                }
                else {
                    $idle = [int][Math]::Floor(($Now - $last).TotalDays)
                    if ($idle -ge $Config.inactivity.inactiveDays) { & $add 'Medium' 'InactiveLicensed' "No successful sign-in for $idle days (limit $($Config.inactivity.inactiveDays)).$note" $canReclaim $idle }
                }
            }
            # Redundant: a licence the config says another held licence supersedes.
            $by = @(Get-LOProp $superseded $part @())
            $cover = @($parts | Where-Object { $_ -in $by })
            if ($cover.Count -gt 0) { & $add 'High' 'RedundantLicence' "$part is covered by $($cover -join ', ') on the same user.$note" $canReclaim $null }
            if ($source -eq 'Both') { & $add 'Low' 'DuplicateDirectAndGroup' "$part is assigned directly and through a group: removing the user from the group would not free the seat." (-not $isProtected) $null }
        }
        # Overlapping plans between two licences, when no supersede rule explains it.
        $keys = @($held.Keys)
        for ($a = 0; $a -lt $keys.Count; $a++) {
            for ($b = $a + 1; $b -lt $keys.Count; $b++) {
                if (-not $skuInfo.ContainsKey($keys[$a]) -or -not $skuInfo.ContainsKey($keys[$b])) { continue }
                $pa = $skuInfo[$keys[$a]].Part; $pb = $skuInfo[$keys[$b]].Part
                if ($pb -in @(Get-LOProp $superseded $pa @()) -or $pa -in @(Get-LOProp $superseded $pb @())) { continue }
                $da = @(Get-LOProp $held[$keys[$a]] 'disabledPlans' @()) | ForEach-Object { "$_".ToLowerInvariant() }
                $db = @(Get-LOProp $held[$keys[$b]] 'disabledPlans' @()) | ForEach-Object { "$_".ToLowerInvariant() }
                $shared = @($skuInfo[$keys[$a]].PlanIds | Where-Object { $_ -notin $da -and $_ -in $skuInfo[$keys[$b]].PlanIds -and $_ -notin $db })
                if ($shared.Count -ge $Config.overlap.minSharedPlans) {
                    $findings.Add((Get-LOFindingRecord 'Low' 'OverlappingPlans' $upn "$pa + $pb" "$($shared.Count) service plans are enabled in both licences. Review which one the user needs." $false 'Mixed'))
                }
            }
        }
        foreach ($st in $states) {
            $state = [string](Get-LOProp $st 'state' ''); $err = Get-LOProp $st 'error'
            if ($state -in 'Error', 'ActiveWithError' -or $err) {
                $k = ([string](Get-LOProp $st 'skuId' '')).ToLowerInvariant()
                $hint = if ($err -and $script:ErrorHint.ContainsKey([string]$err)) { $script:ErrorHint[[string]$err] } else { $script:ErrorHint.Other }
                $findings.Add((Get-LOFindingRecord 'High' 'AssignmentError' $upn $(if ($skuInfo.ContainsKey($k)) { $skuInfo[$k].Part } else { $k }) "State $state, error $(if ($err) { $err } else { 'none given' }). $hint" $false $(if ($null -ne (Get-LOProp $st 'assignedByGroup')) { 'Group' } else { 'Direct' })))
            }
        }
    }
    @($findings | Sort-Object @{ Expression = { -$script:SeverityOrder[$_.Severity] } }, Rule, User, Sku)
}

function Get-LOSeatSummary {
    <# Seats paid for but not assigned, with what they cost per month. Exhausted and nearly full SKUs are episode 1's job. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Skus, [Parameter(Mandatory)]$Config)
    $prices = Get-LOProp $Config.prices 'perUserPerMonth'
    foreach ($s in @($Skus)) {
        if ((Get-LOProp $s 'appliesTo' 'User') -ne 'User' -or (Get-LOProp $s 'capabilityStatus' 'Enabled') -ne 'Enabled') { continue }
        $enabledUnits = [int](Get-LOProp (Get-LOProp $s 'prepaidUnits') 'enabled' 0)
        $unassigned = [Math]::Max(0, $enabledUnits - [int](Get-LOProp $s 'consumedUnits' 0))
        if ($unassigned -eq 0) { continue }
        $price = if ($prices -and $null -ne (Get-LOProp $prices $s.skuPartNumber)) { [double](Get-LOProp $prices $s.skuPartNumber) } else { $null }
        [pscustomobject]@{ Sku = $s.skuPartNumber; Seats = $enabledUnits; Assigned = [int](Get-LOProp $s 'consumedUnits' 0); Unassigned = $unassigned; MonthlyIdleCost = $(if ($null -ne $price) { [Math]::Round($unassigned * $price, 2) } else { $null }) }
    }
}

function Get-LOSavingSummary {
    <# What the reclaimable findings are worth: one seat per user and SKU, however many rules hit it. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Findings, [Parameter(Mandatory)]$Config)
    $seats = @($Findings | Where-Object { $_.Rule -in $script:SavingRules -and $_.Reclaimable } | Group-Object UserId, SkuId | ForEach-Object { $_.Group[0] })
    $priced = @($seats | Where-Object { $null -ne $_.MonthlySaving })
    $monthly = 0.0; foreach ($x in $priced) { $monthly += [double]$x.MonthlySaving }
    [pscustomobject]@{
        Currency     = $Config.prices.currency; Seats = $seats.Count; PricedSeats = $priced.Count; UnpricedSeats = $seats.Count - $priced.Count
        MonthlyTotal = [Math]::Round($monthly, 2); AnnualTotal = [Math]::Round($monthly * 12, 2)
        BySku        = @($seats | Group-Object Sku | ForEach-Object { [pscustomobject]@{ Sku = $_.Name; Seats = $_.Count } })
    }
}

# ---------------------------------------------------------------- reclaim (the only writes)
function Get-LOReclaimPlan {
    <# Turns findings into removals. Nothing is planned for a SKU that is not in reclaim.allowedSkuPartNumbers (empty = nothing),
       a rule that is not in reclaim.rules, a protected user, or a licence that is not a direct assignment. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Findings, [Parameter(Mandatory)]$Config)
    $allowed = @(Get-LOProp $Config.reclaim 'allowedSkuPartNumbers' @())
    $rules = @(Get-LOProp $Config.reclaim 'rules' @())
    $cand = @($Findings | Where-Object { $_.Reclaimable -and $_.Rule -in $rules -and $_.Sku -in $allowed -and $_.UserId -and $_.SkuId })
    @($cand | Group-Object UserId, SkuId | ForEach-Object {
            $f = $_.Group[0]
            [pscustomobject]@{ UserId = $f.UserId; UserPrincipalName = $f.User; SkuId = $f.SkuId; SkuPartNumber = $f.Sku; DisabledPlans = @($f.DisabledPlans); Rules = @($_.Group.Rule | Select-Object -Unique); MonthlySaving = $f.MonthlySaving }
        })
}

function Invoke-LOReclaim {
    <# Removes the planned licences (POST /users/{id}/assignLicense with removeLicenses) and records each removal in a rollback
       file BEFORE moving on. Re-reads every user first and skips a licence that is no longer a direct assignment. -WhatIf sends nothing. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)][string]$RollbackFile)
    $plan = @($Plan)
    if ($plan.Count -eq 0) { return @() }
    if (-not $WhatIfPreference -and (Test-Path -LiteralPath $RollbackFile)) { throw "Rollback file '$RollbackFile' already exists: use a new name so a previous rollback is never overwritten." }
    $rollback = [System.Collections.Generic.List[object]]::new()
    foreach ($p in $plan) {
        $result = [pscustomobject]@{ User = $p.UserPrincipalName; Sku = $p.SkuPartNumber; Status = ''; Message = '' }
        if ($PSCmdlet.ShouldProcess($p.UserPrincipalName, "Remove licence $($p.SkuPartNumber)")) {
            try {
                $now = Invoke-MgGraphRequest -Method GET -Uri "$script:Graph/users/$($p.UserId)?`$select=id,assignedLicenses,licenseAssignmentStates" -OutputType PSObject -ErrorAction Stop
                $stillDirect = @(@(Get-LOProp $now 'licenseAssignmentStates' @()) | Where-Object { ([string]$_.skuId) -eq $p.SkuId -and $null -eq (Get-LOProp $_ 'assignedByGroup') }).Count -gt 0
                if (-not $stillDirect) { $result.Status = 'Skipped'; $result.Message = 'No longer a direct assignment.'; $result; continue }
                $body = @{ addLicenses = @(); removeLicenses = @($p.SkuId) } | ConvertTo-Json -Depth 5 -Compress
                Invoke-MgGraphRequest -Method POST -Uri "$script:Graph/users/$($p.UserId)/assignLicense" -Body $body -ContentType 'application/json' -ErrorAction Stop | Out-Null
                $rollback.Add([pscustomobject]@{ userId = $p.UserId; userPrincipalName = $p.UserPrincipalName; skuId = $p.SkuId; skuPartNumber = $p.SkuPartNumber; disabledPlans = @($p.DisabledPlans); removedAt = [datetimeoffset]::UtcNow.ToString('o') })
                ConvertTo-Json -InputObject @($rollback.ToArray()) -Depth 6 | Set-Content -LiteralPath $RollbackFile -Encoding utf8
                $result.Status = 'Removed'
            }
            catch { $result.Status = 'Failed'; $result.Message = $_.Exception.Message }
        }
        else { $result.Status = 'WhatIf' }
        $result
    }
}

function Restore-LOReclaim {
    <# Puts the licences in a rollback file back (same SKU, same disabled plans). Checks that a seat is free first. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
    param([Parameter(Mandatory)][string]$RollbackFile)
    $items = @(Get-Content -LiteralPath $RollbackFile -Raw | ConvertFrom-Json)
    $skus = @(Get-LOSku)
    foreach ($i in $items) {
        $result = [pscustomobject]@{ User = $i.userPrincipalName; Sku = $i.skuPartNumber; Status = ''; Message = '' }
        $sku = $skus | Where-Object { ([string]$_.skuId) -eq $i.skuId } | Select-Object -First 1
        if (-not $sku) { $result.Status = 'Failed'; $result.Message = 'The tenant no longer has this SKU.'; $result; continue }
        if ([int]$sku.consumedUnits -ge [int]$sku.prepaidUnits.enabled) { $result.Status = 'Failed'; $result.Message = 'No free seat: buy one or free another first.'; $result; continue }
        if ($PSCmdlet.ShouldProcess($i.userPrincipalName, "Restore licence $($i.skuPartNumber)")) {
            try {
                $body = @{ addLicenses = @(@{ skuId = $i.skuId; disabledPlans = @($i.disabledPlans) }); removeLicenses = @() } | ConvertTo-Json -Depth 6 -Compress
                Invoke-MgGraphRequest -Method POST -Uri "$script:Graph/users/$($i.userId)/assignLicense" -Body $body -ContentType 'application/json' -ErrorAction Stop | Out-Null
                $sku.consumedUnits = [int]$sku.consumedUnits + 1
                $result.Status = 'Restored'
            }
            catch { $result.Status = 'Failed'; $result.Message = $_.Exception.Message }
        }
        else { $result.Status = 'WhatIf' }
        $result
    }
}

# ---------------------------------------------------------------- report
function ConvertTo-LOMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Findings, $Seats = @(), $Savings, $Plan = @(), [int]$UsersScanned = 0, [string]$GeneratedOn = '', [string]$Currency = '')
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine('# Microsoft 365 licence optimization report').AppendLine()
    if ($GeneratedOn) { $null = $sb.AppendLine("Generated: $GeneratedOn").AppendLine() }
    $f = @($Findings)
    $null = $sb.AppendLine("$UsersScanned users scanned, $($f.Count) finding(s): " + ((@('High', 'Medium', 'Low', 'Info') | ForEach-Object { "$_ $(@($f | Where-Object Severity -eq $_).Count)" }) -join ', ') + '.').AppendLine()
    if ($Savings) {
        if ($Savings.PricedSeats -gt 0) { $null = $sb.AppendLine("**Reclaimable seats: $($Savings.Seats)** ($($Savings.PricedSeats) priced). Potential saving $($Savings.MonthlyTotal) $($Savings.Currency) per month, $($Savings.AnnualTotal) $($Savings.Currency) per year, only if the subscription is reduced at renewal.").AppendLine() }
        else { $null = $sb.AppendLine("**Reclaimable seats: $($Savings.Seats).** No prices configured (prices.perUserPerMonth), so no money is shown.").AppendLine() }
    }
    $null = $sb.AppendLine('## Findings').AppendLine()
    if ($f.Count -eq 0) { $null = $sb.AppendLine('No findings.') }
    else {
        $null = $sb.AppendLine('| Severity | Rule | User | Licence | How assigned | Reclaimable | Detail |').AppendLine('|---|---|---|---|---|---|---|')
        foreach ($x in $f) { $null = $sb.AppendLine("| $($x.Severity) | $($x.Rule) | $($x.User) | $($x.Sku) | $($x.Source) | $(if ($x.Reclaimable) {'yes'} else {'no'}) | $($x.Detail) |") }
    }
    $null = $sb.AppendLine().AppendLine('## Seats paid for but not assigned').AppendLine()
    if (@($Seats).Count -eq 0) { $null = $sb.AppendLine('None.') }
    else {
        $null = $sb.AppendLine('| Licence | Seats | Assigned | Unassigned | Monthly cost of idle seats |').AppendLine('|---|---|---|---|---|')
        foreach ($s in $Seats) { $null = $sb.AppendLine("| $($s.Sku) | $($s.Seats) | $($s.Assigned) | $($s.Unassigned) | $(if ($null -ne $s.MonthlyIdleCost) { "$($s.MonthlyIdleCost) $Currency" } else { 'no price' }) |") }
    }
    if (@($Plan).Count -gt 0) {
        $null = $sb.AppendLine().AppendLine('## Reclaim plan (nothing removed yet)').AppendLine().AppendLine('| User | Licence | Why |').AppendLine('|---|---|---|')
        foreach ($p in $Plan) { $null = $sb.AppendLine("| $($p.UserPrincipalName) | $($p.SkuPartNumber) | $($p.Rules -join ', ') |") }
    }
    $null = $sb.AppendLine().AppendLine('_Removing a licence is not free of consequences: Exchange Online data is held for 30 days and then deleted, and an unlicensed OneDrive is archived after 93 days (Microsoft Learn). Money is saved only when the subscription is reduced; an annual commitment cannot be reduced mid-term._')
    $sb.ToString()
}
Export-ModuleMember -Function Get-LOConfig, Get-LOSku, Get-LOUser, Get-LOProtectedUserId, Get-LOLicenceFinding, Get-LOSeatSummary, Get-LOSavingSummary, Get-LOReclaimPlan, Invoke-LOReclaim, Restore-LOReclaim, ConvertTo-LOMarkdown
