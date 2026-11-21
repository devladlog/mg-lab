#Requires -Version 7.2
<#
.SYNOPSIS
    OneDrive for Business administration (DEVLADLOG Microsoft 365 #12).
      * Tenant side (read-only, Microsoft Graph): OneDrive settings against a baseline, and an account audit from the OneDrive usage report.
      * PC side (writes the Windows registry): the sync-app policies silent sign-in, Files On-Demand and Known Folder Move, with a rollback file.
    The analysis is pure functions, so it runs offline on saved data (and in the tests).

    Graph v1.0 used (Microsoft Learn), with the delegated scope each call needs:
      GET /admin/sharepoint/settings                          SharePointTenantSettings.Read.All + SharePoint Administrator or Global Reader
      GET /reports/getOneDriveUsageAccountDetail(period=)     Reports.Read.All + a role such as Reports Reader
      GET /admin/reportSettings                               ReportSettings.Read.All (is the report concealed?)
    Nothing on the tenant side is written. The only writes are registry values under HKLM\SOFTWARE\Policies\Microsoft\OneDrive on the PC.
#>
Set-StrictMode -Version Latest

$script:Graph = '/v1.0'
$script:PolicyRoot = 'HKLM:\SOFTWARE\Policies\Microsoft\OneDrive'
$script:SeverityOrder = @{ High = 3; Medium = 2; Low = 1; Info = 0 }
# OneDrive-related properties of sharepointSettings (Learn), the type this tool checks and how serious a drift is.
$script:SettingSpec = @{
    personalSiteDefaultStorageLimitInMB          = @{ Type = 'int'; Severity = 'Medium' }
    deletedUserPersonalSiteRetentionPeriodInDays = @{ Type = 'int'; Severity = 'Medium'; Min = 30; Max = 3650 }   # Learn (Set the OneDrive retention): 30 through 3650
    isUnmanagedSyncAppForTenantRestricted        = @{ Type = 'bool'; Severity = 'High' }
    allowedDomainGuidsForSyncApp                 = @{ Type = 'guidlist'; Severity = 'High' }
    excludedFileExtensionsForSyncApp             = @{ Type = 'list'; Severity = 'Low' }
    isSyncButtonHiddenOnPersonalSite             = @{ Type = 'bool'; Severity = 'Low' }
    isMacSyncAppEnabled                          = @{ Type = 'bool'; Severity = 'Low' }
    isFileActivityNotificationEnabled            = @{ Type = 'bool'; Severity = 'Low' }
}

function Test-ODAGuid([string]$Value) { $g = [guid]::Empty; [guid]::TryParse($Value, [ref]$g) }

function Get-ODAProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($p -and $null -ne $p.Value) { $p.Value } else { $Default }
}

# ---------------------------------------------------------------- baseline file
function Get-ODABaseline {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Path)
    $b = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($s in 'settings', 'accounts') { if ($null -eq (Get-ODAProp $b $s)) { throw "Baseline: section '$s' is missing." } }
    if (@($b.settings.PSObject.Properties).Count -eq 0) { throw 'Baseline: settings is empty: nothing to check.' }
    foreach ($p in $b.settings.PSObject.Properties) {
        $spec = $script:SettingSpec[$p.Name]
        if (-not $spec) { throw "Baseline: '$($p.Name)' is not a OneDrive setting this tool can check ($($script:SettingSpec.Keys | Sort-Object | Join-String -Separator ', '))." }
        $v = $p.Value
        switch ($spec.Type) {
            'bool' { if ($v -isnot [bool]) { throw "Baseline: $($p.Name) must be true or false." } }
            'int' {
                $min = Get-ODAProp $spec 'Min' 0; $max = Get-ODAProp $spec 'Max' ([long]::MaxValue)
                if (($v -isnot [int] -and $v -isnot [long]) -or $v -lt $min -or $v -gt $max) { throw "Baseline: $($p.Name) must be a whole number from $min to $max." }
            }
            'list' { if ($null -ne $v -and (@($v) | Where-Object { $_ -isnot [string] })) { throw "Baseline: $($p.Name) must be a list of strings." } }
            'guidlist' { if ($null -ne $v -and (@($v) | Where-Object { $_ -isnot [string] -or -not (Test-ODAGuid $_) })) { throw "Baseline: $($p.Name) must be a list of GUIDs." } }
        }
    }
    foreach ($n in 'inactiveDays', 'topConsumers') { $v = Get-ODAProp $b.accounts $n 0; if (($v -isnot [int] -and $v -isnot [long]) -or $v -lt 1 -or $v -gt 3650) { throw "Baseline: accounts.$n must be a whole number from 1 to 3650." } }
    $q = Get-ODAProp $b.accounts 'nearFullPercent' 0
    if (($q -isnot [int] -and $q -isnot [long] -and $q -isnot [double]) -or $q -lt 1 -or $q -gt 100) { throw 'Baseline: accounts.nearFullPercent must be a number from 1 to 100.' }
    $b
}

# ---------------------------------------------------------------- collection (Graph, GET only)
function Get-ODATenantSetting {
    [CmdletBinding()] param()
    try { Invoke-MgGraphRequest -Method GET -Uri "$script:Graph/admin/sharepoint/settings" -OutputType PSObject -ErrorAction Stop }
    catch {
        $details = if ($_.ErrorDetails) { $_.ErrorDetails.Message } else { '' }
        if ("$($_.Exception.Message) $details" -match 'Forbidden|403|Authorization') {
            throw "Microsoft Graph refused the tenant settings. It needs SharePointTenantSettings.Read.All and the SharePoint Administrator or Global Reader role. Original error: $($_.Exception.Message)"
        }
        throw
    }
}

function Get-ODAUsageReport {
    <# GET /reports/getOneDriveUsageAccountDetail(period=): 302 to a short-lived download URL; the CSV is written to a file. #>
    [CmdletBinding()] param([ValidateSet('D7', 'D30', 'D90', 'D180')][string]$Period = 'D180')
    $tmp = [IO.Path]::GetTempFileName()
    try {
        Invoke-MgGraphRequest -Method GET -Uri "$script:Graph/reports/getOneDriveUsageAccountDetail(period='$Period')" -OutputFilePath $tmp -ErrorAction Stop
        @(Import-Csv -LiteralPath $tmp)
    }
    finally { Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue }
}

function Get-ODAReportPrivacy {
    [CmdletBinding()] param()
    try { [bool](Get-ODAProp (Invoke-MgGraphRequest -Method GET -Uri "$script:Graph/admin/reportSettings" -OutputType PSObject -ErrorAction Stop) 'displayConcealedNames' $null) }
    catch { $null }
}

# ---------------------------------------------------------------- analysis (pure)
function Get-ODAFindingRecord($Severity, $Rule, $Target, $Detail, $Setting = '', $Current = $null, $Expected = $null) {
    [pscustomobject]@{ Severity = $Severity; Rule = $Rule; Target = $Target; Setting = $Setting; Current = $Current; Expected = $Expected; Detail = $Detail }
}

function Format-ODAValue($Value) {
    if ($null -eq $Value) { return '(not set)' }
    if ($Value -is [bool]) { return $Value.ToString().ToLowerInvariant() }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) { $a = @($Value); if ($a.Count -eq 0) { return '(empty list)' }; return ($a -join ', ') }
    [string]$Value
}

function Test-ODAValueEqual($Actual, $Expected) {
    if ($null -eq $Expected -or ($Expected -is [System.Collections.IEnumerable] -and $Expected -isnot [string])) {
        $a = @($Actual | Where-Object { $null -ne $_ } | ForEach-Object { "$_".ToLowerInvariant() } | Sort-Object -Unique)
        $e = @($Expected | Where-Object { $null -ne $_ } | ForEach-Object { "$_".ToLowerInvariant() } | Sort-Object -Unique)
        return (($a -join '|') -eq ($e -join '|'))
    }
    if ($Expected -is [bool]) { return ($Actual -is [bool] -and $Actual -eq $Expected) }
    if ($Expected -is [string]) { return ([string]$Actual -ceq $Expected) }
    return ($Actual -eq $Expected)
}

function Get-ODASettingFinding {
    [CmdletBinding()] param([Parameter(Mandatory)]$Settings, [Parameter(Mandatory)]$Baseline)
    foreach ($p in $Baseline.settings.PSObject.Properties) {
        $name = $p.Name; $expected = $p.Value; $spec = $script:SettingSpec[$name]
        if ($null -eq $Settings.PSObject.Properties[$name]) { Get-ODAFindingRecord 'Info' 'SettingNotReturned' $name "The tenant did not return '$name': it cannot be compared." $name $null $expected; continue }
        $actual = $Settings.$name
        if (Test-ODAValueEqual $actual $expected) { continue }
        $detail = "is $(Format-ODAValue $actual), the baseline says $(Format-ODAValue $expected)."
        if ($name -eq 'isUnmanagedSyncAppForTenantRestricted' -and $expected -eq $true) { $detail += ' Without it, users can sync on any PC, not only on PCs joined to specific domains.' }
        Get-ODAFindingRecord $spec.Severity 'SettingDrift' $name $detail $name $actual $expected
    }
}

function Test-ODAConcealedReport {
    <# True when the usage report hides identities: owner principal names become hashes without an @. #>
    param([AllowEmptyCollection()][object[]]$Rows)
    $upns = @($Rows | ForEach-Object { Get-ODAProp $_ 'Owner Principal Name' } | Where-Object { $_ })
    if ($upns.Count -eq 0) { return $false }
    @($upns | Where-Object { $_ -notlike '*@*' }).Count -eq $upns.Count
}

function ConvertTo-ODADate($Value) {
    if ($null -eq $Value -or "$Value".Trim() -eq '') { return $null }
    $d = [datetime]::MinValue
    if ([datetime]::TryParseExact("$Value".Trim(), 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal, [ref]$d)) { return $d.Date }
    $null
}

function ConvertTo-ODALong($Value) {
    $n = 0L
    if ([long]::TryParse("$Value".Trim(), [Globalization.NumberStyles]::Integer, [Globalization.CultureInfo]::InvariantCulture, [ref]$n)) { $n } else { 0L }
}

function Get-ODAAccountRow {
    <# The report rows as plain objects with numbers and dates parsed. The report only lists users with a valid OneDrive licence (Learn). #>
    [CmdletBinding()] param([Parameter(Mandatory)][AllowEmptyCollection()]$Rows)
    if (Test-ODAConcealedReport @($Rows)) {
        throw [System.InvalidOperationException]::new('The OneDrive usage report is concealed (owner names are hashed). Ask a Global Administrator to clear "Conceal user, group, and site names in all reports" (Microsoft 365 admin center > Settings > Org settings > Services > Reports).')
    }
    foreach ($r in @($Rows)) {
        $used = ConvertTo-ODALong (Get-ODAProp $r 'Storage Used (Byte)'); $alloc = ConvertTo-ODALong (Get-ODAProp $r 'Storage Allocated (Byte)')
        [pscustomobject]@{
            Owner = [string](Get-ODAProp $r 'Owner Principal Name' ''); OwnerName = [string](Get-ODAProp $r 'Owner Display Name' '')
            Deleted = [bool]((Get-ODAProp $r 'Is Deleted' 'False') -match '^(?i:true)$')
            LastActivity = ConvertTo-ODADate (Get-ODAProp $r 'Last Activity Date'); Files = ConvertTo-ODALong (Get-ODAProp $r 'File Count')
            UsedBytes = $used; AllocatedBytes = $alloc
            UsedPercent = $(if ($alloc -gt 0) { [Math]::Round(100.0 * $used / $alloc, 1) } else { $null })
        }
    }
}

function Get-ODAAccountFinding {
    <# Rules on the account report: NearFull, InactiveOneDrive, NeverUsed, NoActivityRecorded, CustomQuota (only when -DefaultQuotaMB is given), DeletedRetained. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()]$Rows, [Parameter(Mandatory)]$Baseline, [datetimeoffset]$Now = [datetimeoffset]::UtcNow, [long]$DefaultQuotaMB = 0)
    $inactive = [int]$Baseline.accounts.inactiveDays; $near = [double]$Baseline.accounts.nearFullPercent; $today = $Now.UtcDateTime.Date
    foreach ($a in @(Get-ODAAccountRow -Rows $Rows)) {
        $who = if ($a.Owner) { $a.Owner } else { '(no owner name in the report)' }
        if ($a.Deleted) { Get-ODAFindingRecord 'Info' 'DeletedRetained' $who 'The owner was deleted: this OneDrive is in the retention period (the tenant setting), then 93 days in the site collection recycle bin.'; continue }
        if ($null -eq $a.LastActivity) {
            if ($a.Files -eq 0) { Get-ODAFindingRecord 'Low' 'NeverUsed' $who 'No files and no activity recorded: the OneDrive was provisioned but never used.' }
            else { Get-ODAFindingRecord 'Medium' 'NoActivityRecorded' $who "Has $($a.Files) file(s) but no activity date in the report." }
        }
        else {
            $age = [int]($today - $a.LastActivity).TotalDays
            if ($age -ge $inactive) { Get-ODAFindingRecord 'Medium' 'InactiveOneDrive' $who "Last activity $($a.LastActivity.ToString('yyyy-MM-dd')), $age days ago (limit $inactive)." }
        }
        if ($null -ne $a.UsedPercent -and $a.UsedPercent -ge $near) { Get-ODAFindingRecord 'High' 'NearFull' $who "Uses $($a.UsedPercent) percent of its storage limit (limit $near percent)." }
        if ($DefaultQuotaMB -gt 0 -and $a.AllocatedBytes -gt 0 -and $a.AllocatedBytes -ne ($DefaultQuotaMB * 1MB)) {
            Get-ODAFindingRecord 'Info' 'CustomQuota' $who "Storage limit is $([Math]::Round($a.AllocatedBytes / 1GB, 1)) GB, not the tenant default of $([Math]::Round($DefaultQuotaMB / 1024, 1)) GB (a licence can also cap the default)."
        }
    }
}

function Get-ODAStorageSummary {
    [CmdletBinding()] param([Parameter(Mandatory)][AllowEmptyCollection()]$Rows, [Parameter(Mandatory)]$Baseline)
    $acc = @(Get-ODAAccountRow -Rows $Rows | Where-Object { -not $_.Deleted })
    $used = 0L; foreach ($a in $acc) { $used += $a.UsedBytes }
    [pscustomobject]@{
        Accounts = $acc.Count; UsedGB = [Math]::Round($used / 1GB, 3); DeletedAccounts = @(Get-ODAAccountRow -Rows $Rows | Where-Object Deleted).Count
        Top      = @($acc | Sort-Object UsedBytes -Descending | Select-Object -First ([int]$Baseline.accounts.topConsumers) | ForEach-Object { [pscustomobject]@{ Owner = $_.Owner; UsedGB = [Math]::Round($_.UsedBytes / 1GB, 3); UsedPercent = $_.UsedPercent } })
    }
}

# ---------------------------------------------------------------- the PC side: sync-app policies (registry)
function Get-ODASyncPolicyPlan {
    <# The registry values for: silent sign-in (SilentAccountConfig), Files On-Demand (FilesOnDemandEnabled) and silent Known Folder Move
       (KFMSilentOptIn = tenant id, plus the folders and the notification), optionally KFMBlockOptOut. Names and values: Learn, "Use OneDrive policies
       to control sync settings". Pure: it writes nothing. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$TenantId,
        [ValidateSet('Desktop', 'Documents', 'Pictures')][string[]]$KnownFolders = @('Desktop', 'Documents', 'Pictures'),
        [switch]$Notify, [switch]$BlockOptOut
    )
    if (-not (Test-ODAGuid $TenantId)) { throw "TenantId '$TenantId' is not a GUID (Microsoft Entra tenant ID)." }
    $folders = @($KnownFolders | Select-Object -Unique)
    if ($folders.Count -eq 0) { throw 'KnownFolders is empty: name at least one of Desktop, Documents, Pictures.' }
    $plan = [System.Collections.Generic.List[object]]::new()
    $add = { param($n, $t, $v) $plan.Add([pscustomobject]@{ Name = $n; Type = $t; Value = $v }) }
    & $add 'SilentAccountConfig' 'DWord' 1
    & $add 'FilesOnDemandEnabled' 'DWord' 1
    & $add 'KFMSilentOptIn' 'String' $TenantId.ToLowerInvariant()
    & $add 'KFMSilentOptInWithNotification' 'DWord' $(if ($Notify) { 1 } else { 0 })
    foreach ($f in $folders) { & $add "KFMSilentOptIn$f" 'DWord' 1 }
    if ($BlockOptOut) { & $add 'KFMBlockOptOut' 'DWord' 1 }
    $plan.ToArray()
}

function Get-ODACurrentValue([string]$Root, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Root)) { return [pscustomobject]@{ Exists = $false; Value = $null } }
    $p = Get-ItemProperty -LiteralPath $Root -Name $Name -ErrorAction SilentlyContinue
    if ($null -ne $p -and $null -ne $p.PSObject.Properties[$Name]) { [pscustomobject]@{ Exists = $true; Value = $p.$Name } } else { [pscustomobject]@{ Exists = $false; Value = $null } }
}

function Get-ODASyncPolicyState {
    <# Reads the PC and says, per planned value, Compliant, Different or Missing. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Plan, [string]$Root = $script:PolicyRoot)
    foreach ($p in @($Plan)) {
        $c = Get-ODACurrentValue $Root $p.Name
        $status = if (-not $c.Exists) { 'Missing' } elseif ("$($c.Value)" -ieq "$($p.Value)") { 'Compliant' } else { 'Different' }
        [pscustomobject]@{ Name = $p.Name; Expected = $p.Value; Actual = $c.Value; Status = $status }
    }
}

function Set-ODASyncPolicy {
    <# Writes the planned values under the policy key. Before it writes anything it records what is there now (or that it was absent) in a rollback
       file and refuses to overwrite an old one. -WhatIf writes nothing and creates no file. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)][string]$RollbackFile, [string]$Root = $script:PolicyRoot)
    $plan = @($Plan)
    if (-not $WhatIfPreference -and [IO.File]::Exists($RollbackFile)) { throw "Rollback file '$RollbackFile' already exists: use a new name so a previous rollback is never overwritten." }
    $before = foreach ($p in $plan) { $c = Get-ODACurrentValue $Root $p.Name; [pscustomobject]@{ name = $p.Name; existed = $c.Exists; previous = $c.Value; previousType = $(if ($c.Value -is [int] -or $c.Value -is [uint32]) { 'DWord' } else { 'String' }) } }
    if ($PSCmdlet.ShouldProcess($Root, "Write $($plan.Count) OneDrive policy value(s)")) {
        ConvertTo-Json -InputObject ([pscustomobject]@{ root = $Root; writtenAt = [datetimeoffset]::UtcNow.ToString('o'); items = @($before) }) -Depth 6 | Set-Content -LiteralPath $RollbackFile -Encoding utf8
        if (-not (Test-Path -LiteralPath $Root)) { New-Item -Path $Root -Force | Out-Null }
        foreach ($p in $plan) {
            # New-ItemProperty -Force creates the value or overwrites it; -PropertyType is a regular parameter (Set-ItemProperty -Type exists only with the registry provider loaded)
            New-ItemProperty -LiteralPath $Root -Name $p.Name -Value $p.Value -PropertyType $p.Type -Force -ErrorAction Stop | Out-Null
            [pscustomobject]@{ Name = $p.Name; Status = 'Written'; Value = $p.Value }
        }
    }
    else { foreach ($p in $plan) { [pscustomobject]@{ Name = $p.Name; Status = 'WhatIf'; Value = $p.Value } } }
}

function Restore-ODASyncPolicy {
    <# Puts every value back as the rollback file says: the old value, or removed when it did not exist. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
    param([Parameter(Mandatory)][string]$RollbackFile)
    $rb = Get-Content -LiteralPath $RollbackFile -Raw | ConvertFrom-Json
    foreach ($i in @($rb.items)) {
        $r = [pscustomobject]@{ Name = $i.name; Status = ''; Message = '' }
        if ($PSCmdlet.ShouldProcess("$($rb.root)\$($i.name)", $(if ($i.existed) { "Put back $($i.previous)" } else { 'Remove (it did not exist before)' }))) {
            try {
                if ($i.existed) { New-ItemProperty -LiteralPath $rb.root -Name $i.name -Value $i.previous -PropertyType $i.previousType -Force -ErrorAction Stop | Out-Null }
                else { Remove-ItemProperty -LiteralPath $rb.root -Name $i.name -ErrorAction SilentlyContinue }
                $r.Status = 'Restored'
            }
            catch { $r.Status = 'Failed'; $r.Message = $_.Exception.Message }
        }
        else { $r.Status = 'WhatIf' }
        $r
    }
}

# ---------------------------------------------------------------- report
function ConvertTo-ODAMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Findings, $Storage, [string]$GeneratedOn = '', [string]$Period = '')
    $f = @($Findings | Sort-Object @{ Expression = { $script:SeverityOrder[$_.Severity] }; Descending = $true }, Rule, Target)
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine('# OneDrive for Business report').AppendLine()
    if ($GeneratedOn) { $null = $sb.AppendLine("Generated: $GeneratedOn").AppendLine() }
    $null = $sb.AppendLine("$($f.Count) finding(s): " + ((@('High', 'Medium', 'Low', 'Info') | ForEach-Object { "$_ $(@($f | Where-Object Severity -eq $_).Count)" }) -join ', ') + '.').AppendLine()
    $drift = @($f | Where-Object { $_.Rule -in 'SettingDrift', 'SettingNotReturned' })
    $null = $sb.AppendLine('## Tenant OneDrive settings against the baseline').AppendLine()
    if ($drift.Count -eq 0) { $null = $sb.AppendLine('Every baseline setting matches.') }
    else { $null = $sb.AppendLine('| Severity | Setting | Detail |').AppendLine('|---|---|---|'); foreach ($x in $drift) { $null = $sb.AppendLine("| $($x.Severity) | $($x.Target) | $($x.Detail) |") } }
    $acc = @($f | Where-Object { $_.Rule -notin 'SettingDrift', 'SettingNotReturned' })
    $null = $sb.AppendLine().AppendLine('## Accounts' + $(if ($Period) { " (usage report, period $Period)" } else { '' })).AppendLine()
    if ($acc.Count -eq 0) { $null = $sb.AppendLine('No findings.') }
    else { $null = $sb.AppendLine('| Severity | Rule | Owner | Detail |').AppendLine('|---|---|---|---|'); foreach ($x in $acc) { $null = $sb.AppendLine("| $($x.Severity) | $($x.Rule) | $($x.Target) | $($x.Detail) |") } }
    if ($Storage) {
        $null = $sb.AppendLine().AppendLine("## Storage: $($Storage.Accounts) account(s), $($Storage.UsedGB) GB used, $($Storage.DeletedAccounts) deleted").AppendLine()
        if (@($Storage.Top).Count) {
            $null = $sb.AppendLine('| Owner | Used GB | Used of limit |').AppendLine('|---|---|---|')
            foreach ($t in $Storage.Top) { $null = $sb.AppendLine("| $($t.Owner) | $($t.UsedGB) | $(if ($null -ne $t.UsedPercent) { "$($t.UsedPercent) %" } else { 'n/a' }) |") }
        }
    }
    $null = $sb.AppendLine().AppendLine('_The report only lists users with a valid OneDrive licence, and a deleted owner shows up only after at least seven days (Microsoft Learn). Nothing here changed the tenant._')
    $sb.ToString()
}
Export-ModuleMember -Function Get-ODABaseline, Get-ODATenantSetting, Get-ODAUsageReport, Get-ODAReportPrivacy, Get-ODASettingFinding, Test-ODAConcealedReport, Get-ODAAccountRow, Get-ODAAccountFinding, Get-ODAStorageSummary, Get-ODASyncPolicyPlan, Get-ODASyncPolicyState, Set-ODASyncPolicy, Restore-ODASyncPolicy, ConvertTo-ODAMarkdown
