#Requires -Version 7.2
<#
.SYNOPSIS
    SharePoint Online administration (DEVLADLOG Microsoft 365 #11): a tenant-settings baseline and a site hygiene audit, on Microsoft Graph.
    Collection and the one write talk to Graph; the analysis is pure functions, so it runs offline on saved data (and in the tests).

    Graph v1.0 used (Microsoft Learn), with the delegated scope each call needs:
      GET   /admin/sharepoint/settings                      SharePointTenantSettings.Read.All + SharePoint Administrator or Global Reader
      PATCH /admin/sharepoint/settings                      SharePointTenantSettings.ReadWrite.All + SharePoint Administrator (ONLY the remediation uses it)
      GET   /reports/getSharePointSiteUsageDetail(period=)  Reports.Read.All + a role such as Reports Reader
      GET   /admin/reportSettings                           ReportSettings.Read.All (is the report concealed?)
    Not used: GET /sites/getAllSites (application permissions only, Learn).
#>
Set-StrictMode -Version Latest

$script:Graph = '/v1.0'
$script:SharingOrder = @('disabled', 'existingExternalUserSharingOnly', 'externalUserSharingOnly', 'externalUserAndGuestSharing')   # least to most permissive

# The properties Learn lists as updatable on sharepointSettings (PATCH), with the type this tool checks and how serious a drift is.
# idleSessionSignOut is an object and is not supported here; availableManagedPathsForSiteCreation is read-only.
$script:SettingSpec = @{
    sharingCapability                               = @{ Type = 'enum'; Values = @('disabled', 'externalUserSharingOnly', 'externalUserAndGuestSharing', 'existingExternalUserSharingOnly'); Severity = 'High' }
    isLegacyAuthProtocolsEnabled                    = @{ Type = 'bool'; Severity = 'High' }
    isResharingByExternalUsersEnabled               = @{ Type = 'bool'; Severity = 'Medium' }
    isRequireAcceptingUserToMatchInvitedUserEnabled = @{ Type = 'bool'; Severity = 'Medium' }
    sharingDomainRestrictionMode                    = @{ Type = 'enum'; Values = @('none', 'allowList', 'blockList'); Severity = 'Medium' }
    sharingAllowedDomainList                        = @{ Type = 'list'; Severity = 'Medium' }
    sharingBlockedDomainList                        = @{ Type = 'list'; Severity = 'Medium' }
    isSiteCreationEnabled                           = @{ Type = 'bool'; Severity = 'Low' }
    isSiteCreationUIEnabled                         = @{ Type = 'bool'; Severity = 'Low' }
    isSitePagesCreationEnabled                      = @{ Type = 'bool'; Severity = 'Low' }
    isSitesStorageLimitAutomatic                    = @{ Type = 'bool'; Severity = 'Low' }
    siteCreationDefaultManagedPath                  = @{ Type = 'string'; Severity = 'Low' }
    siteCreationDefaultStorageLimitInMB             = @{ Type = 'int'; Severity = 'Low' }
    tenantDefaultTimezone                           = @{ Type = 'string'; Severity = 'Low' }
    isCommentingOnSitePagesEnabled                  = @{ Type = 'bool'; Severity = 'Low' }
    isSharePointNewsfeedEnabled                     = @{ Type = 'bool'; Severity = 'Low' }
    isSharePointMobileNotificationEnabled           = @{ Type = 'bool'; Severity = 'Low' }
    isLoopEnabled                                   = @{ Type = 'bool'; Severity = 'Low' }
    imageTaggingOption                              = @{ Type = 'enum'; Values = @('disabled', 'basic', 'enhanced'); Severity = 'Low' }
}
$script:SeverityOrder = @{ High = 3; Medium = 2; Low = 1; Info = 0 }

function Get-SPAProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($p -and $null -ne $p.Value) { $p.Value } else { $Default }
}

# ---------------------------------------------------------------- baseline file
function Get-SPABaseline {
    <# Reads and validates the baseline file. Unknown or read-only property names are errors (a typo must not silently check nothing). #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Path)
    $b = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($s in 'settings', 'sites', 'remediate') { if ($null -eq (Get-SPAProp $b $s)) { throw "Baseline: section '$s' is missing." } }
    $names = @($b.settings.PSObject.Properties | ForEach-Object Name)
    if ($names.Count -eq 0) { throw 'Baseline: settings is empty: nothing to check.' }
    foreach ($p in $b.settings.PSObject.Properties) {
        $spec = $script:SettingSpec[$p.Name]
        if (-not $spec) {
            if ($p.Name -eq 'idleSessionSignOut') { throw "Baseline: '$($p.Name)' is an object and is not supported by this tool." }
            throw "Baseline: '$($p.Name)' is not a tenant setting this tool can check ($($script:SettingSpec.Keys | Sort-Object | Join-String -Separator ', '))."
        }
        $v = $p.Value
        switch ($spec.Type) {
            'bool' { if ($v -isnot [bool]) { throw "Baseline: $($p.Name) must be true or false." } }
            'enum' { if ($v -isnot [string] -or $v -notin $spec.Values) { throw "Baseline: $($p.Name) must be one of $($spec.Values -join ', ')." } }
            'int' { if (($v -isnot [int] -and $v -isnot [long]) -or $v -lt 0) { throw "Baseline: $($p.Name) must be a whole number, 0 or more." } }
            'string' { if ($v -isnot [string] -or [string]::IsNullOrWhiteSpace($v)) { throw "Baseline: $($p.Name) must be a non-empty string." } }
            'list' { if ($null -ne $v -and (@($v) | Where-Object { $_ -isnot [string] })) { throw "Baseline: $($p.Name) must be a list of strings." } }
        }
    }
    $s = $b.sites
    foreach ($n in 'inactiveDays', 'topConsumers') { $v = Get-SPAProp $s $n 0; if (($v -isnot [int] -and $v -isnot [long]) -or $v -lt 1 -or $v -gt 3650) { throw "Baseline: sites.$n must be a whole number from 1 to 3650." } }
    $q = Get-SPAProp $s 'nearQuotaPercent' 0
    if (($q -isnot [int] -and $q -isnot [long] -and $q -isnot [double]) -or $q -lt 1 -or $q -gt 100) { throw 'Baseline: sites.nearQuotaPercent must be a number from 1 to 100.' }
    foreach ($a in @(Get-SPAProp $b.remediate 'allowedSettings' @())) {
        if ($a -isnot [string] -or $a -notin $names) { throw "Baseline: remediate.allowedSettings has '$a', which is not a setting in the baseline." }
    }
    $b
}

# ---------------------------------------------------------------- collection (Graph)
function Get-SPATenantSetting {
    <# GET /admin/sharepoint/settings: one object with the tenant-level settings for SharePoint and OneDrive. #>
    [CmdletBinding()] param()
    try { Invoke-MgGraphRequest -Method GET -Uri "$script:Graph/admin/sharepoint/settings" -OutputType PSObject -ErrorAction Stop }
    catch {
        $details = if ($_.ErrorDetails) { $_.ErrorDetails.Message } else { '' }
        if ("$($_.Exception.Message) $details" -match 'Forbidden|403|Authorization') {
            throw "Microsoft Graph refused the SharePoint settings. It needs SharePointTenantSettings.Read.All and the SharePoint Administrator or Global Reader role. Original error: $($_.Exception.Message)"
        }
        throw
    }
}

function Get-SPASiteUsageReport {
    <# GET /reports/getSharePointSiteUsageDetail(period=): the API answers 302 with a short-lived download URL; the CSV is written to a file. #>
    [CmdletBinding()] param([ValidateSet('D7', 'D30', 'D90', 'D180')][string]$Period = 'D180')
    $tmp = [IO.Path]::GetTempFileName()
    try {
        Invoke-MgGraphRequest -Method GET -Uri "$script:Graph/reports/getSharePointSiteUsageDetail(period='$Period')" -OutputFilePath $tmp -ErrorAction Stop
        @(Import-Csv -LiteralPath $tmp)
    }
    finally { Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue }
}

function Get-SPAReportPrivacy {
    <# True when usage reports conceal user, group and site names. $null when the tenant did not tell us (permission or API). #>
    [CmdletBinding()] param()
    try { [bool](Get-SPAProp (Invoke-MgGraphRequest -Method GET -Uri "$script:Graph/admin/reportSettings" -OutputType PSObject -ErrorAction Stop) 'displayConcealedNames' $null) }
    catch { $null }
}

# ---------------------------------------------------------------- analysis (pure)
function Get-SPAFindingRecord($Severity, $Rule, $Target, $Detail, $Setting = '', $Current = $null, $Expected = $null) {
    [pscustomobject]@{ Severity = $Severity; Rule = $Rule; Target = $Target; Setting = $Setting; Current = $Current; Expected = $Expected; Detail = $Detail }
}

function Format-SPAValue($Value) {
    if ($null -eq $Value) { return '(not set)' }
    if ($Value -is [bool]) { return $Value.ToString().ToLowerInvariant() }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) { $a = @($Value); if ($a.Count -eq 0) { return '(empty list)' }; return ($a -join ', ') }
    [string]$Value
}

function Test-SPAValueEqual($Actual, $Expected) {
    if ($Expected -is [System.Collections.IEnumerable] -and $Expected -isnot [string] -or ($null -eq $Expected)) {
        $a = @($Actual | Where-Object { $null -ne $_ } | ForEach-Object { "$_".ToLowerInvariant() } | Sort-Object -Unique)
        $e = @($Expected | Where-Object { $null -ne $_ } | ForEach-Object { "$_".ToLowerInvariant() } | Sort-Object -Unique)
        return (($a -join '|') -eq ($e -join '|'))
    }
    if ($Expected -is [bool]) { return ($Actual -is [bool] -and $Actual -eq $Expected) }
    if ($Expected -is [string]) { return ([string]$Actual -ceq $Expected) }
    return ($Actual -eq $Expected)
}

function Get-SPASettingFinding {
    <# Compares the tenant settings with the baseline. A setting the tenant did not return is reported as Info (never as drift). #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Settings, [Parameter(Mandatory)]$Baseline)
    foreach ($p in $Baseline.settings.PSObject.Properties) {
        $name = $p.Name; $expected = $p.Value; $spec = $script:SettingSpec[$name]
        $has = $null -ne $Settings.PSObject.Properties[$name]
        if (-not $has) { Get-SPAFindingRecord 'Info' 'SettingNotReturned' $name "The tenant did not return '$name': it cannot be compared." $name $null $expected; continue }
        $actual = $Settings.$name
        if (Test-SPAValueEqual $actual $expected) { continue }
        $sev = $spec.Severity; $detail = "is $(Format-SPAValue $actual), the baseline says $(Format-SPAValue $expected)."
        if ($name -eq 'sharingCapability') {
            $ra = $script:SharingOrder.IndexOf([string]$actual); $re = $script:SharingOrder.IndexOf([string]$expected)
            if ($ra -ge 0 -and $re -ge 0) {
                if ($ra -gt $re) { $detail = "is $actual, more permissive than the baseline ($expected)." }
                else { $sev = 'Low'; $detail = "is $actual, stricter than the baseline ($expected)." }
            }
        }
        Get-SPAFindingRecord $sev 'SettingDrift' $name $detail $name $actual $expected
    }
}

function Test-SPAConcealedReport {
    <# True when the site usage report hides site URLs (concealed names are hashes, not URLs). #>
    param([AllowEmptyCollection()][object[]]$Rows)
    $urls = @($Rows | ForEach-Object { Get-SPAProp $_ 'Site URL' } | Where-Object { $_ })
    if ($urls.Count -eq 0) { return $false }
    @($urls | Where-Object { $_ -notmatch '^https?://' }).Count -eq $urls.Count
}

function ConvertTo-SPADate($Value) {
    if ($null -eq $Value -or "$Value".Trim() -eq '') { return $null }
    $d = [datetime]::MinValue
    if ([datetime]::TryParseExact("$Value".Trim(), 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal, [ref]$d)) { return $d.Date }
    $null
}

function ConvertTo-SPALong($Value) {
    $n = 0L
    if ([long]::TryParse("$Value".Trim(), [Globalization.NumberStyles]::Integer, [Globalization.CultureInfo]::InvariantCulture, [ref]$n)) { $n } else { 0L }
}

function Get-SPASiteRow {
    <# The report rows as plain objects (deleted sites and ignored URL patterns left out), with numbers and dates parsed. #>
    [CmdletBinding()] param([Parameter(Mandatory)][AllowEmptyCollection()]$Rows, [Parameter(Mandatory)]$Baseline)
    if (Test-SPAConcealedReport @($Rows)) {
        throw [System.InvalidOperationException]::new('The site usage report is concealed (site URLs are hashed). Ask a Global Administrator to clear "Conceal user, group, and site names in all reports" (Microsoft 365 admin center > Settings > Org settings > Services > Reports).')
    }
    $ignore = @(Get-SPAProp $Baseline.sites 'ignoreSiteUrlPatterns' @())
    foreach ($r in @($Rows)) {
        $url = [string](Get-SPAProp $r 'Site URL' '')
        if ((Get-SPAProp $r 'Is Deleted' 'False') -match '^(?i:true)$') { continue }
        if ($ignore | Where-Object { $url -like $_ }) { continue }
        $used = ConvertTo-SPALong (Get-SPAProp $r 'Storage Used (Byte)'); $alloc = ConvertTo-SPALong (Get-SPAProp $r 'Storage Allocated (Byte)')
        [pscustomobject]@{
            Url = $url; Owner = [string](Get-SPAProp $r 'Owner Principal Name' ''); OwnerName = [string](Get-SPAProp $r 'Owner Display Name' '')
            LastActivity = ConvertTo-SPADate (Get-SPAProp $r 'Last Activity Date'); Files = ConvertTo-SPALong (Get-SPAProp $r 'File Count'); ActiveFiles = ConvertTo-SPALong (Get-SPAProp $r 'Active File Count')
            UsedBytes = $used; AllocatedBytes = $alloc; Template = [string](Get-SPAProp $r 'Root Web Template' '')
            UsedPercent = $(if ($alloc -gt 0) { [Math]::Round(100.0 * $used / $alloc, 1) } else { $null })
        }
    }
}

function Get-SPASiteFinding {
    <# Site hygiene rules on the usage report: NoActivityRecorded, InactiveSite, NearQuota, NoOwner, EmptySite. Pure. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()]$Rows, [Parameter(Mandatory)]$Baseline, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    $inactive = [int]$Baseline.sites.inactiveDays; $near = [double]$Baseline.sites.nearQuotaPercent
    $today = $Now.UtcDateTime.Date
    foreach ($s in @(Get-SPASiteRow -Rows $Rows -Baseline $Baseline)) {
        if ($null -eq $s.LastActivity) { Get-SPAFindingRecord 'Medium' 'NoActivityRecorded' $s.Url 'The report has no activity date for this site (new sites look the same: the report has no creation date).' }
        else {
            $age = [int]($today - $s.LastActivity).TotalDays
            if ($age -ge $inactive) { Get-SPAFindingRecord 'Medium' 'InactiveSite' $s.Url "Last activity $($s.LastActivity.ToString('yyyy-MM-dd')), $age days ago (limit $inactive)." }
        }
        if ($null -ne $s.UsedPercent -and $s.UsedPercent -ge $near) { Get-SPAFindingRecord 'High' 'NearQuota' $s.Url "Uses $($s.UsedPercent) percent of its allocated storage (limit $near percent)." }
        if ([string]::IsNullOrWhiteSpace($s.Owner)) { Get-SPAFindingRecord 'Medium' 'NoOwner' $s.Url 'The report shows no owner principal name for this site.' }
        if ($s.Files -eq 0) { Get-SPAFindingRecord 'Info' 'EmptySite' $s.Url 'The site has no files.' }
    }
}

function Get-SPAStorageSummary {
    [CmdletBinding()] param([Parameter(Mandatory)][AllowEmptyCollection()]$Rows, [Parameter(Mandatory)]$Baseline)
    $sites = @(Get-SPASiteRow -Rows $Rows -Baseline $Baseline)
    $used = 0L; foreach ($s in $sites) { $used += $s.UsedBytes }
    [pscustomobject]@{
        Sites = $sites.Count; UsedGB = [Math]::Round($used / 1GB, 3)
        Top   = @($sites | Sort-Object UsedBytes -Descending | Select-Object -First ([int]$Baseline.sites.topConsumers) | ForEach-Object { [pscustomobject]@{ Url = $_.Url; UsedGB = [Math]::Round($_.UsedBytes / 1GB, 3); UsedPercent = $_.UsedPercent; Owner = $_.Owner } })
    }
}

# ---------------------------------------------------------------- remediation (the only writes)
function Get-SPARemediationPlan {
    <# Only drifted settings that are ALSO named in remediate.allowedSettings (empty = nothing). #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Findings, [Parameter(Mandatory)]$Baseline)
    $allowed = @(Get-SPAProp $Baseline.remediate 'allowedSettings' @())
    @($Findings | Where-Object { $_.Rule -eq 'SettingDrift' -and $_.Setting -in $allowed } | ForEach-Object {
            [pscustomobject]@{ Setting = $_.Setting; Current = $_.Current; Expected = $_.Expected }
        })
}

function Invoke-SPARemediation {
    <# One PATCH /admin/sharepoint/settings per setting, body = only that property. Re-reads the tenant first and skips a setting that no
       longer drifts; records the previous value in a rollback file after every success; stops at the first failure. -WhatIf sends nothing. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)][string]$RollbackFile)
    $plan = @($Plan)
    if ($plan.Count -eq 0) { return @() }
    if (-not $WhatIfPreference -and (Test-Path -LiteralPath $RollbackFile)) { throw "Rollback file '$RollbackFile' already exists: use a new name so a previous rollback is never overwritten." }
    $rollback = [System.Collections.Generic.List[object]]::new()
    $stop = $false
    foreach ($p in $plan) {
        $r = [pscustomobject]@{ Setting = $p.Setting; Status = ''; Message = '' }
        if ($stop) { $r.Status = 'NotRun'; $r.Message = 'An earlier change failed.'; $r; continue }
        if ($PSCmdlet.ShouldProcess($p.Setting, "Set to $(Format-SPAValue $p.Expected) (now $(Format-SPAValue $p.Current))")) {
            try {
                $now = Get-SPATenantSetting
                $before = $now.PSObject.Properties[$p.Setting]
                if ($before -and (Test-SPAValueEqual $before.Value $p.Expected)) { $r.Status = 'Skipped'; $r.Message = 'Already matches the baseline.'; $r; continue }
                $body = ConvertTo-Json -InputObject @{ $p.Setting = $p.Expected } -Depth 5 -Compress
                Invoke-MgGraphRequest -Method PATCH -Uri "$script:Graph/admin/sharepoint/settings" -Body $body -ContentType 'application/json' -ErrorAction Stop | Out-Null
                $rollback.Add([pscustomobject]@{ setting = $p.Setting; previous = $(if ($before) { $before.Value } else { $null }); applied = $p.Expected; changedAt = [datetimeoffset]::UtcNow.ToString('o') })
                ConvertTo-Json -InputObject @($rollback.ToArray()) -Depth 6 | Set-Content -LiteralPath $RollbackFile -Encoding utf8
                $r.Status = 'Changed'
            }
            catch { $r.Status = 'Failed'; $r.Message = $_.Exception.Message; $stop = $true }
        }
        else { $r.Status = 'WhatIf' }
        $r
    }
}

function Restore-SPARemediation {
    <# Puts the previous values from a rollback file back, newest change first, but only for a setting that still has the value we applied
       (someone changed it since: skipped, not overwritten). #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
    param([Parameter(Mandatory)][string]$RollbackFile)
    $items = @(Get-Content -LiteralPath $RollbackFile -Raw | ConvertFrom-Json)
    [array]::Reverse($items)
    foreach ($i in $items) {
        $r = [pscustomobject]@{ Setting = $i.setting; Status = ''; Message = '' }
        $now = Get-SPATenantSetting
        $cur = $now.PSObject.Properties[$i.setting]
        if (-not $cur -or -not (Test-SPAValueEqual $cur.Value $i.applied)) { $r.Status = 'Skipped'; $r.Message = 'The setting no longer has the value this tool applied: left alone.'; $r; continue }
        if ($PSCmdlet.ShouldProcess($i.setting, "Put back $(Format-SPAValue $i.previous)")) {
            try {
                $body = ConvertTo-Json -InputObject @{ $i.setting = $i.previous } -Depth 5 -Compress
                Invoke-MgGraphRequest -Method PATCH -Uri "$script:Graph/admin/sharepoint/settings" -Body $body -ContentType 'application/json' -ErrorAction Stop | Out-Null
                $r.Status = 'Restored'
            }
            catch { $r.Status = 'Failed'; $r.Message = $_.Exception.Message }
        }
        else { $r.Status = 'WhatIf' }
        $r
    }
}

# ---------------------------------------------------------------- report
function ConvertTo-SPAMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Findings, $Storage, $Plan = @(), [string]$GeneratedOn = '', [string]$Period = '')
    $f = @($Findings | Sort-Object @{ Expression = { $script:SeverityOrder[$_.Severity] }; Descending = $true }, Rule, Target)
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine('# SharePoint Online administration report').AppendLine()
    if ($GeneratedOn) { $null = $sb.AppendLine("Generated: $GeneratedOn").AppendLine() }
    $null = $sb.AppendLine("$($f.Count) finding(s): " + ((@('High', 'Medium', 'Low', 'Info') | ForEach-Object { "$_ $(@($f | Where-Object Severity -eq $_).Count)" }) -join ', ') + '.').AppendLine()
    $drift = @($f | Where-Object { $_.Rule -in 'SettingDrift', 'SettingNotReturned' })
    $null = $sb.AppendLine('## Tenant settings against the baseline').AppendLine()
    if ($drift.Count -eq 0) { $null = $sb.AppendLine('Every baseline setting matches.') }
    else {
        $null = $sb.AppendLine('| Severity | Setting | Detail |').AppendLine('|---|---|---|')
        foreach ($x in $drift) { $null = $sb.AppendLine("| $($x.Severity) | $($x.Target) | $($x.Detail) |") }
    }
    $sites = @($f | Where-Object { $_.Rule -notin 'SettingDrift', 'SettingNotReturned' })
    $null = $sb.AppendLine().AppendLine('## Site hygiene' + $(if ($Period) { " (usage report, period $Period)" } else { '' })).AppendLine()
    if ($sites.Count -eq 0) { $null = $sb.AppendLine('No findings.') }
    else {
        $null = $sb.AppendLine('| Severity | Rule | Site | Detail |').AppendLine('|---|---|---|---|')
        foreach ($x in $sites) { $null = $sb.AppendLine("| $($x.Severity) | $($x.Rule) | $($x.Target) | $($x.Detail) |") }
    }
    if ($Storage) {
        $null = $sb.AppendLine().AppendLine("## Storage: $($Storage.Sites) site(s), $($Storage.UsedGB) GB used").AppendLine()
        if (@($Storage.Top).Count) {
            $null = $sb.AppendLine('| Site | Used GB | Used of allocated | Owner |').AppendLine('|---|---|---|---|')
            foreach ($t in $Storage.Top) { $null = $sb.AppendLine("| $($t.Url) | $($t.UsedGB) | $(if ($null -ne $t.UsedPercent) { "$($t.UsedPercent) %" } else { 'n/a' }) | $($t.Owner) |") }
        }
    }
    if (@($Plan).Count -gt 0) {
        $null = $sb.AppendLine().AppendLine('## Remediation plan (nothing changed yet)').AppendLine().AppendLine('| Setting | Now | Becomes |').AppendLine('|---|---|---|')
        foreach ($p in $Plan) { $null = $sb.AppendLine("| $($p.Setting) | $(Format-SPAValue $p.Current) | $(Format-SPAValue $p.Expected) |") }
    }
    $null = $sb.AppendLine().AppendLine('_The usage report has a refresh date (the Report Refresh Date column), is not live, and has no creation date, so a new site can look idle. Site-level sharing and sensitivity labels are not in the Graph report (see the README)._')
    $sb.ToString()
}
Export-ModuleMember -Function Get-SPABaseline, Get-SPATenantSetting, Get-SPASiteUsageReport, Get-SPAReportPrivacy, Get-SPASettingFinding, Test-SPAConcealedReport, Get-SPASiteRow, Get-SPASiteFinding, Get-SPAStorageSummary, Get-SPARemediationPlan, Invoke-SPARemediation, Restore-SPARemediation, ConvertTo-SPAMarkdown
