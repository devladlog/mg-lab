#Requires -Version 7.2
<#
    M365TenantHealth: a read-only tenant health check built on Microsoft Graph.

    Two layers:
      * Collection  - Invoke-M365GraphGet, Get-M365UsageReport, Get-M365TenantSnapshot
                      (the only functions that talk to Graph, through Invoke-MgGraphRequest)
      * Analysis    - pure functions that turn raw Graph JSON into findings. No network, fully unit tested.

    Everything here is GET-only. Nothing in this module changes the tenant.
#>

Set-StrictMode -Version Latest

$script:GlobalAdminRoleId = '62e90394-69f5-4237-9190-012177145e10'   # Global Administrator role template id

# Delegated scopes, least privileged per API (see README "Permissions").
$script:RequiredScopes = @(
    'ServiceHealth.Read.All'        # healthOverviews, issues
    'ServiceMessage.Read.All'       # message center
    'Reports.Read.All'              # usage reports (CSV)
    'ReportSettings.Read.All'       # concealed names setting
    'LicenseAssignment.Read.All'    # subscribedSkus
    'RoleManagement.Read.Directory' # role assignments
    'SecurityEvents.Read.All'       # security/secureScores
)

function Get-M365RequiredScope { $script:RequiredScopes }

#region Helpers ---------------------------------------------------------------------------------------------------

function ConvertTo-M365Date {
    <# Graph dates arrive as ISO strings, or as DateTime when ConvertFrom-Json already parsed them. #>
    [CmdletBinding()]
    [OutputType([Nullable[datetimeoffset]])]
    param([AllowNull()][object]$Value)

    if ($null -eq $Value -or "$Value" -eq '') { return $null }
    if ($Value -is [datetimeoffset]) { return $Value.ToUniversalTime() }
    if ($Value -is [datetime]) {
        $dt = if ($Value.Kind -eq [DateTimeKind]::Unspecified) { [datetime]::SpecifyKind($Value, 'Utc') } else { $Value }
        return ([datetimeoffset]$dt).ToUniversalTime()
    }
    $styles = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
    return [datetimeoffset]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture, $styles)
}

function New-M365Finding {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Builds an in-memory object only')]
    param(
        [Parameter(Mandatory)][string]$Area,
        [Parameter(Mandatory)][ValidateSet('High', 'Medium', 'Low', 'Info')][string]$Severity,
        [Parameter(Mandatory)][string]$Title,
        [string]$Detail = ''
    )
    [pscustomobject]@{ Area = $Area; Severity = $Severity; Title = $Title; Detail = $Detail }
}

function Get-M365Prop {
    <# Safe property read under StrictMode: Graph omits properties that are null. #>
    param([object]$Object, [string]$Name, [object]$Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { $Default } else { $p.Value }
}

#endregion

#region Collection (talks to Graph) -------------------------------------------------------------------------------

function Invoke-M365GraphGet {
    <#
    .SYNOPSIS  GET a Graph URI and follow @odata.nextLink until the last page.
    .OUTPUTS   The items of every page (collections) or the single object (non-collection responses).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Uri,
        [int]$MaxPages = 100
    )
    $next = $Uri
    $page = 0
    while ($next) {
        if (++$page -gt $MaxPages) { throw "Stopped after $MaxPages pages of $Uri" }
        $resp = Invoke-MgGraphRequest -Method GET -Uri $next -OutputType PSObject -ErrorAction Stop
        if ($null -eq $resp.PSObject.Properties['value']) { return $resp }   # single object, no paging
        foreach ($item in $resp.value) { $item }
        $next = Get-M365Prop $resp '@odata.nextLink'
    }
}

function Get-M365UsageReport {
    <#
    .SYNOPSIS  Download a Microsoft 365 usage report (CSV) and return its rows.
    .NOTES     The API answers 302 with a short-lived download URL; Invoke-MgGraphRequest writes the body to a file.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidatePattern('^get[A-Za-z0-9]+$')][string]$Report,
        [ValidateSet('D7', 'D30', 'D90', 'D180')][string]$Period = 'D30'
    )
    $tmp = [IO.Path]::GetTempFileName()
    try {
        $uri = "/v1.0/reports/{0}(period='{1}')" -f $Report, $Period
        Invoke-MgGraphRequest -Method GET -Uri $uri -OutputFilePath $tmp -ErrorAction Stop
        Import-Csv -LiteralPath $tmp
    }
    finally { Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue }
}

function Get-M365TenantSnapshot {
    <#
    .SYNOPSIS  Collect everything the health check needs. Each section is independent: a 403 on one
               section is recorded in Errors and the rest still runs.
    #>
    [CmdletBinding()]
    param([ValidateSet('D7', 'D30', 'D90', 'D180')][string]$Period = 'D30')

    $sections = [ordered]@{
        healthOverviews = { @(Invoke-M365GraphGet '/v1.0/admin/serviceAnnouncement/healthOverviews') }
        issues          = { @(Invoke-M365GraphGet '/v1.0/admin/serviceAnnouncement/issues?$filter=isResolved eq false') }
        messages        = { @(Invoke-M365GraphGet '/v1.0/admin/serviceAnnouncement/messages?$top=100') }
        subscribedSkus  = { @(Invoke-M365GraphGet '/v1.0/subscribedSkus') }
        globalAdmins    = { @(Invoke-M365GraphGet ('/v1.0/roleManagement/directory/roleAssignments' +
                    "?`$filter=roleDefinitionId eq '$script:GlobalAdminRoleId'&`$expand=principal")) }
        secureScores    = { @(Invoke-M365GraphGet '/v1.0/security/secureScores?$top=7') }
        reportSettings  = { Invoke-M365GraphGet '/v1.0/admin/reportSettings' | Select-Object -First 1 }
        activeUsers     = { @(Get-M365UsageReport -Report 'getOffice365ActiveUserDetail' -Period $Period) }
    }

    $snapshot = [ordered]@{ collectedAt = [datetimeoffset]::UtcNow.ToString('o'); period = $Period; errors = [ordered]@{} }
    foreach ($name in $sections.Keys) {
        try {
            Write-Verbose "Collecting $name"
            $snapshot[$name] = & $sections[$name]
        }
        catch {
            $snapshot[$name] = $null
            $snapshot.errors[$name] = $_.Exception.Message
        }
    }
    [pscustomobject]$snapshot
}

#endregion

#region Analysis (pure) -------------------------------------------------------------------------------------------

$script:HealthState = @{
    serviceoperational          = 'Healthy'
    servicerestored             = 'Healthy'
    falsepositive               = 'Healthy'
    postincidentreviewpublished = 'Healthy'
    restoringservice            = 'Recovering'
    verifyingservice            = 'Recovering'
    extendedrecovery            = 'Recovering'
    investigating               = 'Degraded'
    servicedegradation          = 'Degraded'
    investigationsuspended      = 'Degraded'
    serviceinterruption         = 'Down'
}

function Get-M365HealthState {
    <# Maps a serviceHealthStatus to Healthy / Recovering / Degraded / Down / Unknown. Case-insensitive on purpose:
       the docs list camelCase values, the sample responses show PascalCase. #>
    param([AllowNull()][string]$Status)
    if (-not $Status) { return 'Unknown' }
    $state = $script:HealthState[$Status.ToLowerInvariant()]
    if ($state) { $state } else { 'Unknown' }
}

function Get-M365ServiceHealthSummary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$HealthOverviews,
        [AllowEmptyCollection()][object[]]$Issues = @()
    )
    $open = @($Issues | Where-Object { -not (Get-M365Prop $_ 'isResolved' $false) })
    foreach ($svc in $HealthOverviews) {
        $name = Get-M365Prop $svc 'service'
        $mine = @($open | Where-Object { (Get-M365Prop $_ 'service') -eq $name })
        [pscustomobject]@{
            Service    = $name
            Status     = Get-M365Prop $svc 'status'
            State      = Get-M365HealthState (Get-M365Prop $svc 'status')
            Incidents  = @($mine | Where-Object { (Get-M365Prop $_ 'classification') -eq 'incident' }).Count
            Advisories = @($mine | Where-Object { (Get-M365Prop $_ 'classification') -eq 'advisory' }).Count
            IssueIds   = @($mine | ForEach-Object { Get-M365Prop $_ 'id' })
        }
    }
}

function Get-M365MessageCenterDigest {
    <# Message center posts with an action-required deadline in the window (overdue ones stay visible for 7 days). #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Messages,
        [datetimeoffset]$Now = [datetimeoffset]::UtcNow,
        [int]$WithinDays = 30
    )
    $digest = foreach ($m in $Messages) {
        $deadline = ConvertTo-M365Date (Get-M365Prop $m 'actionRequiredByDateTime')
        if ($null -eq $deadline) { continue }
        $daysLeft = [math]::Floor(($deadline - $Now).TotalDays)
        if ($daysLeft -lt -7 -or $daysLeft -gt $WithinDays) { continue }
        [pscustomobject]@{
            Id       = Get-M365Prop $m 'id'
            Title    = Get-M365Prop $m 'title'
            Services = (@(Get-M365Prop $m 'services' @()) -join ', ')
            Category = Get-M365Prop $m 'category'
            Major    = [bool](Get-M365Prop $m 'isMajorChange' $false)
            Deadline = $deadline
            DaysLeft = [int]$daysLeft
        }
    }
    @($digest) | Sort-Object DaysLeft
}

function Get-M365LicenseSummary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Skus,
        [double]$NearlyFullRatio = 0.9,
        # Free, self-service SKUs report huge "enabled" counts and are never worth flagging as unused.
        [string[]]$IgnoreSkuPartNumber = @('FLOW_FREE', 'POWER_BI_STANDARD')
    )
    foreach ($sku in $Skus) {
        $part = Get-M365Prop $sku 'skuPartNumber'
        if ($part -in $IgnoreSkuPartNumber) { continue }
        $units    = Get-M365Prop $sku 'prepaidUnits'
        $enabled  = [int](Get-M365Prop $units 'enabled' 0)
        $warning  = [int](Get-M365Prop $units 'warning' 0)
        $consumed = [int](Get-M365Prop $sku 'consumedUnits' 0)
        $status   = Get-M365Prop $sku 'capabilityStatus' 'Enabled'
        $flags = @()
        if ($status -ne 'Enabled')                                  { $flags += "Status:$status" }
        if ($warning -gt 0)                                         { $flags += 'InGracePeriod' }
        if ($enabled -gt 0 -and $consumed -gt $enabled)             { $flags += 'OverAssigned' }
        elseif ($enabled -gt 0 -and $consumed -eq $enabled)         { $flags += 'Exhausted' }
        elseif ($enabled -gt 0 -and $consumed / $enabled -ge $NearlyFullRatio) { $flags += 'NearlyFull' }
        if ($enabled -gt 0 -and $consumed -eq 0)                    { $flags += 'Unused' }
        [pscustomobject]@{
            Sku         = $part
            Enabled     = $enabled
            Consumed    = $consumed
            Warning     = $warning
            Available   = $enabled - $consumed
            Utilization = if ($enabled -gt 0) { [math]::Round(100 * $consumed / $enabled, 1) } else { $null }
            Flags       = $flags
        }
    }
}

function Test-M365ConcealedReport {
    <# True when the usage report hides identities (default since 1 Sept 2021): UPNs become hashes without an @. #>
    param([AllowEmptyCollection()][object[]]$Rows)
    $withUpn = @($Rows | Where-Object { Get-M365Prop $_ 'User Principal Name' })
    if ($withUpn.Count -eq 0) { return $false }
    @($withUpn | Where-Object { (Get-M365Prop $_ 'User Principal Name') -notlike '*@*' }).Count -eq $withUpn.Count
}

function Get-M365InactiveUser {
    <#
    .SYNOPSIS  Licensed users with no activity in any workload for -InactiveDays, measured from the report's own
               refresh date (usage data lags a few days behind "today").
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Rows,
        [int]$InactiveDays = 30
    )
    if ($Rows.Count -eq 0) { return }
    if (Test-M365ConcealedReport $Rows) {
        throw [System.InvalidOperationException]::new('The usage report is concealed (user names are hashed). See admin/reportSettings.')
    }
    $licenseCols  = 'Has Exchange License', 'Has OneDrive License', 'Has SharePoint License', 'Has Teams License', 'Has Yammer License', 'Has Skype For Business License'
    $activityCols = 'Exchange Last Activity Date', 'OneDrive Last Activity Date', 'SharePoint Last Activity Date', 'Teams Last Activity Date', 'Yammer Last Activity Date', 'Skype For Business Last Activity Date'

    foreach ($r in $Rows) {
        if ((Get-M365Prop $r 'Is Deleted') -eq 'True') { continue }
        $licensed = @($licenseCols | Where-Object { (Get-M365Prop $r $_) -eq 'True' })
        if ($licensed.Count -eq 0) { continue }
        $asOf = ConvertTo-M365Date (Get-M365Prop $r 'Report Refresh Date')
        $dates = @($activityCols | ForEach-Object { ConvertTo-M365Date (Get-M365Prop $r $_) } | Where-Object { $_ })
        $last = if ($dates.Count) { ($dates | Sort-Object -Descending)[0] } else { $null }
        $idle = if ($last) { [int][math]::Floor(($asOf - $last).TotalDays) } else { $null }
        if ($null -eq $last -or $idle -ge $InactiveDays) {
            [pscustomobject]@{
                UserPrincipalName = Get-M365Prop $r 'User Principal Name'
                DisplayName       = Get-M365Prop $r 'Display Name'
                LastActivity      = $last
                DaysInactive      = $idle
                Products          = Get-M365Prop $r 'Assigned Products'
            }
        }
    }
}

function Get-M365GlobalAdminReport {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Assignments)
    $principals = foreach ($a in $Assignments) {
        $p = Get-M365Prop $a 'principal'
        [pscustomobject]@{
            DisplayName = Get-M365Prop $p 'displayName' (Get-M365Prop $a 'principalId')
            Type        = ((Get-M365Prop $p '@odata.type' '#microsoft.graph.unknown') -replace '^#microsoft\.graph\.', '')
            UserType    = Get-M365Prop $p 'userType'
            Enabled     = Get-M365Prop $p 'accountEnabled'
        }
    }
    [pscustomobject]@{
        Count      = @($principals).Count
        Principals = @($principals)
        Guests     = @($principals | Where-Object UserType -eq 'Guest')
        Disabled   = @($principals | Where-Object { $_.Enabled -eq $false })
        Groups     = @($principals | Where-Object Type -eq 'group')
    }
}

function Get-M365SecureScoreSummary {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Scores)
    $sorted = @($Scores | Sort-Object { ConvertTo-M365Date (Get-M365Prop $_ 'createdDateTime') } -Descending)
    if ($sorted.Count -eq 0) { return $null }
    $latest = $sorted[0]
    $pct = { param($s) $max = [double](Get-M365Prop $s 'maxScore' 0); if ($max -gt 0) { [math]::Round(100 * [double](Get-M365Prop $s 'currentScore' 0) / $max, 1) } else { 0 } }
    [pscustomobject]@{
        Date         = ConvertTo-M365Date (Get-M365Prop $latest 'createdDateTime')
        CurrentScore = [double](Get-M365Prop $latest 'currentScore' 0)
        MaxScore     = [double](Get-M365Prop $latest 'maxScore' 0)
        Percent      = & $pct $latest
        Change       = if ($sorted.Count -gt 1) { [math]::Round((& $pct $latest) - (& $pct $sorted[-1]), 1) } else { $null }
        Days         = $sorted.Count
    }
}

function Get-M365TenantFinding {
    <# Turns a snapshot (live or loaded from JSON) into a single list of findings, worst first. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Snapshot,
        [datetimeoffset]$Now = [datetimeoffset]::UtcNow,
        [int]$InactiveDays = 30
    )
    $findings = [System.Collections.Generic.List[object]]::new()
    $errors = Get-M365Prop $Snapshot 'errors' @{}
    $errorNames = if ($errors -is [System.Collections.IDictionary]) { @($errors.Keys) } else { @($errors.PSObject.Properties | ForEach-Object Name) }
    foreach ($e in $errorNames) {
        $msg = if ($errors -is [System.Collections.IDictionary]) { $errors[$e] } else { $errors.$e }
        $findings.Add((New-M365Finding 'Collection' 'Medium' "Could not collect $e" $msg))
    }

    $health = Get-M365Prop $Snapshot 'healthOverviews'
    if ($null -ne $health) {
        foreach ($s in Get-M365ServiceHealthSummary -HealthOverviews @($health) -Issues @(Get-M365Prop $Snapshot 'issues' @())) {
            $sev = @{ Down = 'High'; Degraded = 'Medium'; Recovering = 'Low'; Unknown = 'Low' }[$s.State]
            if ($sev) { $findings.Add((New-M365Finding 'Service health' $sev "$($s.Service): $($s.Status)" (($s.IssueIds) -join ', '))) }
        }
    }

    $messages = Get-M365Prop $Snapshot 'messages'
    if ($null -ne $messages) {
        foreach ($m in Get-M365MessageCenterDigest -Messages @($messages) -Now $Now) {
            $sev = if ($m.DaysLeft -le 7) { 'High' } elseif ($m.DaysLeft -le 14) { 'Medium' } else { 'Low' }
            $when = if ($m.DaysLeft -lt 0) { "overdue by $(-$m.DaysLeft) days" } else { "action in $($m.DaysLeft) days" }
            $findings.Add((New-M365Finding 'Message center' $sev "$($m.Id) $when" "$($m.Title) [$($m.Services)]"))
        }
    }

    $skus = Get-M365Prop $Snapshot 'subscribedSkus'
    if ($null -ne $skus) {
        foreach ($l in Get-M365LicenseSummary -Skus @($skus) | Where-Object { $_.Flags.Count }) {
            $sev = if ($l.Flags -match 'OverAssigned|Status:|InGracePeriod') { 'High' } elseif ($l.Flags -contains 'Exhausted') { 'Medium' } else { 'Low' }
            $detail = "$($l.Consumed) assigned of $($l.Enabled) enabled"
            if ($l.Warning -gt 0) { $detail += ", $($l.Warning) in grace period (warning)" }
            $findings.Add((New-M365Finding 'Licensing' $sev "$($l.Sku): $($l.Flags -join ', ')" $detail))
        }
    }

    $ga = Get-M365Prop $Snapshot 'globalAdmins'
    if ($null -ne $ga) {
        $r = Get-M365GlobalAdminReport -Assignments @($ga)
        $add = { param($sev, $title, $detail = '') $findings.Add((New-M365Finding 'Privileged access' $sev $title $detail)) }
        if ($r.Count -ge 5) { & $add 'High' "$($r.Count) active Global Administrator assignments" 'Microsoft recommends fewer than five.' }
        if ($r.Count -lt 2) { & $add 'Medium' "Only $($r.Count) Global Administrator" 'Microsoft recommends two cloud-only emergency access accounts.' }
        foreach ($g in $r.Guests)   { & $add 'High' "Guest holds Global Administrator: $($g.DisplayName)" }
        foreach ($d in $r.Disabled) { & $add 'Low' "Disabled account still holds Global Administrator: $($d.DisplayName)" }
    }

    $scores = Get-M365Prop $Snapshot 'secureScores'
    if ($null -ne $scores) {
        $s = Get-M365SecureScoreSummary -Scores @($scores)
        if ($s -and $null -ne $s.Change -and $s.Change -lt 0) {
            $findings.Add((New-M365Finding 'Secure Score' 'Medium' "Secure Score dropped $([math]::Abs($s.Change)) percentage points in $($s.Days) days" "Now $($s.Percent) percent"))
        }
    }

    $settings = Get-M365Prop $Snapshot 'reportSettings'
    $rows = Get-M365Prop $Snapshot 'activeUsers'
    if ($null -ne $rows) {
        if (Test-M365ConcealedReport @($rows)) {
            $flag = if ($settings) { " (displayConcealedNames = $((Get-M365Prop $settings 'displayConcealedNames')))" } else { '' }
            $findings.Add((New-M365Finding 'Usage' 'Info' 'Usage reports are concealed; inactive users cannot be named' "Org settings > Reports$flag"))
        }
        else {
            $idle = @(Get-M365InactiveUser -Rows @($rows) -InactiveDays $InactiveDays)
            if ($idle.Count) {
                $findings.Add((New-M365Finding 'Usage' 'Low' "$($idle.Count) licensed users inactive for $InactiveDays+ days" (($idle.UserPrincipalName) -join ', ')))
            }
        }
    }

    $rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
    $findings | Sort-Object { $rank[$_.Severity] }, Area
}

function ConvertTo-M365HealthMarkdown {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Snapshot,
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings,
        [string]$TenantLabel = 'contoso'
    )
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine("# Tenant health: $TenantLabel")
    $collected = ConvertTo-M365Date (Get-M365Prop $Snapshot 'collectedAt')
    $stamp = if ($collected) { $collected.ToString('yyyy-MM-dd HH:mm', [Globalization.CultureInfo]::InvariantCulture) + ' UTC' } else { 'unknown' }
    $null = $sb.AppendLine("Collected $stamp (usage period $(Get-M365Prop $Snapshot 'period'))")
    $null = $sb.AppendLine()
    $counts = foreach ($sev in 'High', 'Medium', 'Low', 'Info') {
        $n = @($Findings | Where-Object Severity -eq $sev).Count
        if ($n) { "$n $sev" }
    }
    $null = $sb.AppendLine("**Findings:** $(if ($counts) { $counts -join ' / ' } else { 'none' })")
    $null = $sb.AppendLine()
    $null = $sb.AppendLine('| Severity | Area | Finding | Detail |')
    $null = $sb.AppendLine('|---|---|---|---|')
    foreach ($f in $Findings) { $null = $sb.AppendLine("| $($f.Severity) | $($f.Area) | $($f.Title) | $(($f.Detail -replace '\|', '/')) |") }

    $health = Get-M365Prop $Snapshot 'healthOverviews'
    if ($health) {
        $null = $sb.AppendLine(); $null = $sb.AppendLine('## Service health'); $null = $sb.AppendLine()
        $null = $sb.AppendLine('| Service | State | Incidents | Advisories |'); $null = $sb.AppendLine('|---|---|---|---|')
        foreach ($s in Get-M365ServiceHealthSummary -HealthOverviews @($health) -Issues @(Get-M365Prop $Snapshot 'issues' @())) {
            $null = $sb.AppendLine("| $($s.Service) | $($s.State) | $($s.Incidents) | $($s.Advisories) |")
        }
    }
    $skus = Get-M365Prop $Snapshot 'subscribedSkus'
    if ($skus) {
        $null = $sb.AppendLine(); $null = $sb.AppendLine('## Licences'); $null = $sb.AppendLine()
        $null = $sb.AppendLine('| SKU | Assigned | Purchased | Use % |'); $null = $sb.AppendLine('|---|---|---|---|')
        foreach ($l in Get-M365LicenseSummary -Skus @($skus)) { $null = $sb.AppendLine("| $($l.Sku) | $($l.Consumed) | $($l.Enabled) | $($l.Utilization) |") }
    }
    $scores = Get-M365Prop $Snapshot 'secureScores'
    if ($scores) {
        $s = Get-M365SecureScoreSummary -Scores @($scores)
        $null = $sb.AppendLine(); $null = $sb.AppendLine("## Secure Score"); $null = $sb.AppendLine()
        $null = $sb.AppendLine("$($s.CurrentScore) of $($s.MaxScore) ($($s.Percent) percent), change over $($s.Days) days: $($s.Change)")
    }
    $sb.ToString()
}

#endregion

Export-ModuleMember -Function @(
    'Get-M365RequiredScope', 'ConvertTo-M365Date',
    'Invoke-M365GraphGet', 'Get-M365UsageReport', 'Get-M365TenantSnapshot',
    'Get-M365HealthState', 'Get-M365ServiceHealthSummary', 'Get-M365MessageCenterDigest', 'Get-M365LicenseSummary',
    'Test-M365ConcealedReport', 'Get-M365InactiveUser', 'Get-M365GlobalAdminReport', 'Get-M365SecureScoreSummary',
    'Get-M365TenantFinding', 'ConvertTo-M365HealthMarkdown'
)
