#Requires -Version 7.2
<#
.SYNOPSIS
    Governance checks over the Power BI / Fabric admin APIs.

.DESCRIPTION
    Get-PbiActivityEvent        the activity log of one UTC day (Get Activity Events), following the continuation token
    Get-PbiActivitySummary      counts per activity, most viewed reports, failures, and the operations worth a second look
    Get-PbiOrphanedWorkspace    workspaces without an Admin (Get Groups as Admin, the OData filter from Learn's orphaned-workspace example)
    Get-PbiModifiedWorkspace    workspace ids for the metadata scanner (full list, or modified in the last 30 days)
    Invoke-PbiWorkspaceScan     scanner API: getInfo in chunks of 100 workspaces, poll scanStatus, read scanResult
    Test-PbiGovernance          nine rules (GV001-GV009) over a scan result
    Get-PbiTenantSetting        List Tenant Settings (Fabric admin API, own token) with paging and a retry on 429
    Export-PbiTenantBaseline    saves the settings that matter (name, enabled, group names) as the baseline
    Compare-PbiTenantSetting    drift between a baseline and now
    New-PbiGovernanceReport     Markdown for the Monday meeting

    The Power BI admin calls use Invoke-PowerBIRestMethod (module MicrosoftPowerBIMgmt, after Connect-PowerBIServiceAccount as a Fabric
    administrator). The tenant settings call is on api.fabric.microsoft.com and needs its own token: pass -FabricToken (SecureString, for
    example Get-AzAccessToken -ResourceUrl 'https://api.fabric.microsoft.com' -AsSecureString).
    Output uses names and user aliases, never e-mail domains or ids.
#>

Set-StrictMode -Version Latest

$script:FabricBase = 'https://api.fabric.microsoft.com'

$script:Rules = [ordered]@{
    GV001 = @{ Severity = 'warning'; Text = 'an item (semantic model, report, dashboard, dataflow) has no sensitivity label' }
    GV002 = @{ Severity = 'info';    Text = 'a semantic model is neither promoted nor certified' }
    GV003 = @{ Severity = 'error';   Text = 'an item uses a data source the scanner reports as misconfigured' }
    GV004 = @{ Severity = 'warning'; Text = 'the scanner could not read a semantic model schema (a blind spot for every other rule)' }
    GV005 = @{ Severity = 'error';   Text = 'a workspace has no Admin (orphaned)' }
    GV006 = @{ Severity = 'warning'; Text = 'an item is shared with the whole organization (principal type None)' }
    GV007 = @{ Severity = 'info';    Text = 'a workspace is not in the Active state' }
    GV008 = @{ Severity = 'warning'; Text = 'a row-level security role has no members' }
    GV009 = @{ Severity = 'info';    Text = 'a personal workspace (My workspace) holds items' }
}

# Operations from Learn's operation list (Fabric > Admin > Operation list) that a governance review reads first.
$script:RiskyOperations = @('ExportReport', 'ExportArtifact', 'ShareReport', 'ShareDashboard', 'PublishToWebReport',
    'UpdatedAdminFeatureSwitch', 'AddWorkspaceRoleViaAdminApi', 'DeleteReport', 'SensitivityLabelRemoved')

function Get-PbiGovernanceRule { $script:Rules.GetEnumerator() | ForEach-Object { [pscustomobject]@{ Rule = $_.Key; Severity = $_.Value.Severity; Text = $_.Value.Text } } }

function Get-Prop($Object, [string[]] $Name) {
    if ($null -eq $Object) { return $null }
    foreach ($n in $Name) { if ($Object.PSObject.Properties[$n]) { return $Object.$n } }
    $null
}

function Get-Alias([string] $UserId) { if ([string]::IsNullOrEmpty($UserId)) { '' } else { ($UserId -split '@')[0] } }

function Invoke-PbiAdminApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Get', 'Post')][string] $Method,
        [Parameter(Mandatory)][string] $Url,
        [hashtable] $Body
    )
    $params = @{ Method = $Method; Url = $Url }
    if ($Body) { $params.Body = $Body | ConvertTo-Json -Depth 6 -Compress }
    $json = Invoke-PowerBIRestMethod @params
    if ([string]::IsNullOrWhiteSpace($json)) { return $null }
    $json | ConvertFrom-Json -Depth 32
}

# ---- activity log ---------------------------------------------------------------------------------------------------------------

function Get-PbiActivityEvent {
    <#
    .SYNOPSIS  All activity events of one UTC day. Learn: start and end must be in the same UTC day, within the last 28 days; max 200 requests per hour.
    .PARAMETER Activity  Only this operation, for example ViewReport (OData filter, 'eq' only).
    .PARAMETER MaxRequests  Safety stop. A day with many events needs many requests (each returns a few thousand at most).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][datetime] $Date,
        [ValidatePattern('^[A-Za-z0-9]+$')][string] $Activity,
        [ValidatePattern("^[^'\s]+$")][string] $UserId,
        [ValidateRange(1, 200)][int] $MaxRequests = 50
    )
    $day = [datetime]::SpecifyKind($Date.Date, [DateTimeKind]::Utc)
    $today = [datetime]::UtcNow.Date
    if ($day -gt $today) { throw "The activity log has no events for a future day ($($day.ToString('yyyy-MM-dd')))." }
    if ($day -lt $today.AddDays(-28)) { throw "Learn: events must be within the last 28 days; $($day.ToString('yyyy-MM-dd')) is older." }

    $start = $day.ToString("yyyy-MM-dd'T'00:00:00.000'Z'")
    $end = $day.ToString("yyyy-MM-dd'T'23:59:59.999'Z'")
    $filter = @()
    if ($Activity) { $filter += "Activity eq '$Activity'" }
    if ($UserId) { $filter += "UserId eq '$UserId'" }
    $filterPart = if ($filter) { '&$filter=' + [uri]::EscapeDataString($filter -join ' and ') } else { '' }

    $url = "admin/activityevents?startDateTime='$start'&endDateTime='$end'$filterPart"
    $requests = 0
    do {
        if (++$requests -gt $MaxRequests) { throw "Stopped after $MaxRequests requests (Learn: 200 per hour). Raise -MaxRequests or narrow the day with -Activity." }
        $r = Invoke-PbiAdminApi -Method Get -Url $url
        foreach ($e in @(Get-Prop $r @('activityEventEntities'))) { if ($e) { $e } }
        # A response can carry a continuation token and no events; keep going until there is no token.
        $token = Get-Prop $r @('continuationToken')
        $url = "admin/activityevents?continuationToken='$token'$filterPart"
    } while ($token)
}

function Get-PbiActivitySummary {
    <#
    .SYNOPSIS  Summary of activity events: totals, per activity, most viewed reports (with distinct users), failed events, risky operations.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]] $Event)

    $events = @($Event | Where-Object { $_ })
    $byActivity = $events | Group-Object { Get-Prop $_ @('Activity', 'Operation') } | Sort-Object Count -Descending |
        ForEach-Object { [pscustomobject]@{ Activity = $_.Name; Count = $_.Count } }

    $views = $events | Where-Object { (Get-Prop $_ @('Activity')) -eq 'ViewReport' } |
        Group-Object { Get-Prop $_ @('ReportName', 'ItemName') } | Sort-Object Count -Descending |
        ForEach-Object {
            [pscustomobject]@{
                Report = $_.Name
                Views  = $_.Count
                Users  = @($_.Group | ForEach-Object { Get-Alias (Get-Prop $_ @('UserId')) } | Sort-Object -Unique).Count
            }
        }

    $failed = @($events | Where-Object { (Get-Prop $_ @('IsSuccess')) -eq $false })
    $risky = @($events | Where-Object { $script:RiskyOperations -contains (Get-Prop $_ @('Activity')) } | ForEach-Object {
            [pscustomobject]@{
                Time     = Get-Prop $_ @('CreationTime')
                Activity = Get-Prop $_ @('Activity')
                User     = Get-Alias (Get-Prop $_ @('UserId'))
                Item     = Get-Prop $_ @('ItemName', 'ReportName', 'ArtifactName')
            }
        } | Sort-Object Time)

    [pscustomobject]@{
        Total      = $events.Count
        ByActivity = @($byActivity)
        TopReports = @($views)
        Failed     = $failed.Count
        Risky      = $risky
    }
}

# ---- workspaces ------------------------------------------------------------------------------------------------------------------

function Get-PbiOrphanedWorkspace {
    <#
    .SYNOPSIS  Workspaces with no users, or none with the Admin right (Get Groups as Admin; filter copied from Learn's "orphaned workspaces" example).
    .NOTES     Learn: max 50 requests per hour, 15 per minute; $top 1-5000. Learn also says the users property of this API will be removed in a
               future release while its own orphaned example still uses $expand=users: check the result on your tenant.
    #>
    [CmdletBinding()]
    param([ValidateRange(1, 5000)][int] $Top = 100)
    $filter = "(not users/any()) or (not users/any(u: u/groupUserAccessRight eq Microsoft.PowerBI.ServiceContracts.Api.GroupUserAccessRight'Admin'))"
    $url = 'admin/groups?$expand=users&$filter=' + [uri]::EscapeDataString($filter) + '&$top=' + $Top
    $r = Invoke-PbiAdminApi -Method Get -Url $url
    foreach ($g in @(Get-Prop $r @('value'))) {
        if ($g) { [pscustomobject]@{ Name = $g.name; Type = Get-Prop $g @('type'); State = Get-Prop $g @('state'); OnCapacity = Get-Prop $g @('isOnDedicatedCapacity') } }
    }
}

function Get-PbiModifiedWorkspace {
    <#
    .SYNOPSIS  Workspace ids for the scanner. Without -ModifiedSince: all workspaces. Learn: modifiedSince must be between 30 minutes and 30 days ago; max 30 requests per hour.
    #>
    [CmdletBinding()]
    param([datetime] $ModifiedSince, [switch] $ExcludePersonal, [switch] $ExcludeInactive)
    $q = @()
    if ($PSBoundParameters.ContainsKey('ModifiedSince')) {
        $utc = $ModifiedSince.ToUniversalTime()
        $age = [datetime]::UtcNow - $utc
        if ($age -gt [timespan]::FromDays(30)) { throw 'Learn: modifiedSince must be within the last 30 days. Do a full scan (no -ModifiedSince) instead.' }
        if ($age -lt [timespan]::FromMinutes(30)) { throw 'Learn: modifiedSince must be at least 30 minutes ago (workspace changes need time to take effect).' }
        $q += 'modifiedSince=' + $utc.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'")
    }
    if ($ExcludePersonal) { $q += 'excludePersonalWorkspaces=True' }
    if ($ExcludeInactive) { $q += 'excludeInActiveWorkspaces=True' }
    $url = 'admin/workspaces/modified' + $(if ($q) { '?' + ($q -join '&') } else { '' })
    $r = Invoke-PbiAdminApi -Method Get -Url $url
    @($r | Where-Object { $_ } | ForEach-Object { $_.id })
}

function Invoke-PbiWorkspaceScan {
    <#
    .SYNOPSIS  Metadata scanning: getInfo (up to 100 workspaces per call) > poll scanStatus > scanResult. One chunk at a time, so Learn's limit of 16 simultaneous calls is never reached.
    .PARAMETER PollSeconds  Learn recommends 30-60 seconds.
    .NOTES     Learn: 500 getInfo requests per hour; the scan result stays available for 24 hours. DatasetSchema and DatasetExpressions only return data when the two
               "Enhance admin APIs responses ..." tenant settings are on. The terminal status for success is "Succeeded"; a status "Failed" or an error object stops the scan.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string[]] $WorkspaceId,
        [switch] $Lineage, [switch] $DatasourceDetails, [switch] $DatasetSchema, [switch] $DatasetExpressions, [switch] $GetArtifactUsers,
        [ValidateRange(0, 600)][int] $PollSeconds = 30,
        [ValidateRange(1, 7200)][int] $TimeoutSeconds = 1800
    )
    $q = @()
    if ($Lineage) { $q += 'lineage=True' }
    if ($DatasourceDetails) { $q += 'datasourceDetails=True' }
    if ($DatasetSchema) { $q += 'datasetSchema=True' }
    if ($DatasetExpressions) { $q += 'datasetExpressions=True' }
    if ($GetArtifactUsers) { $q += 'getArtifactUsers=True' }
    $getInfo = 'admin/workspaces/getInfo' + $(if ($q) { '?' + ($q -join '&') } else { '' })

    $ids = @($WorkspaceId | Where-Object { $_ } | Select-Object -Unique)
    if (-not $ids) { throw 'No workspace ids to scan.' }
    $workspaces = @(); $sources = @(); $bad = @()
    for ($i = 0; $i -lt $ids.Count; $i += 100) {
        $chunk = @($ids[$i..([Math]::Min($i + 99, $ids.Count - 1))])
        $scan = Invoke-PbiAdminApi -Method Post -Url $getInfo -Body @{ workspaces = $chunk }
        $scanId = $scan.id
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        while ($true) {
            $st = Invoke-PbiAdminApi -Method Get -Url "admin/workspaces/scanStatus/$scanId"
            $status = [string] (Get-Prop $st @('status'))
            if ($status -eq 'Succeeded') { break }
            if ($status -eq 'Failed' -or (Get-Prop $st @('error'))) { throw "Scan $scanId failed (status '$status')." }
            if ($watch.Elapsed.TotalSeconds -gt $TimeoutSeconds) { throw "Scan $scanId did not finish in $TimeoutSeconds seconds (last status '$status')." }
            Start-Sleep -Seconds $PollSeconds
        }
        $res = Invoke-PbiAdminApi -Method Get -Url "admin/workspaces/scanResult/$scanId"
        $workspaces += @(Get-Prop $res @('workspaces') | Where-Object { $_ })
        $sources += @(Get-Prop $res @('datasourceInstances') | Where-Object { $_ })
        $bad += @(Get-Prop $res @('misconfiguredDatasourceInstances') | Where-Object { $_ })
    }
    [pscustomobject]@{ workspaces = $workspaces; datasourceInstances = $sources; misconfiguredDatasourceInstances = $bad }
}

# ---- rules over a scan result ---------------------------------------------------------------------------------------------------

function New-Finding([string] $Rule, [string] $Workspace, [string] $ItemType, [string] $Item, [string] $Message) {
    [pscustomobject]@{ Rule = $Rule; Severity = $script:Rules[$Rule].Severity; Workspace = $Workspace; ItemType = $ItemType; ItemName = $Item; Message = $Message }
}

function Test-PbiGovernance {
    <#
    .SYNOPSIS  Applies GV001-GV009 to a scan result (the object from Invoke-PbiWorkspaceScan, or the JSON of scanResult). Returns findings; nothing is changed in the service.
    .NOTES     GV005 and GV006 read user lists, which the scanner returns only with -GetArtifactUsers; without them the rules stay silent (not "all fine").
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $ScanResult)

    $kinds = @(
        @{ Type = 'semantic model'; Prop = 'datasets'; Name = 'name' },
        @{ Type = 'report'; Prop = 'reports'; Name = 'name' },
        @{ Type = 'dashboard'; Prop = 'dashboards'; Name = 'displayName' },
        @{ Type = 'dataflow'; Prop = 'dataflows'; Name = 'name' })

    foreach ($ws in @(Get-Prop $ScanResult @('workspaces'))) {
        if (-not $ws) { continue }
        $wn = [string] (Get-Prop $ws @('name'))
        $type = [string] (Get-Prop $ws @('type'))
        $state = [string] (Get-Prop $ws @('state'))
        $itemCount = 0

        foreach ($k in $kinds) {
            foreach ($item in @(Get-Prop $ws @($k.Prop))) {
                if (-not $item) { continue }
                $itemCount++
                $in = [string] (Get-Prop $item @($k.Name))
                $label = Get-Prop (Get-Prop $item @('sensitivityLabel')) @('labelId')
                if ([string]::IsNullOrWhiteSpace([string] $label)) {
                    New-Finding GV001 $wn $k.Type $in "no sensitivity label on this $($k.Type)"
                }
                if (@(Get-Prop $item @('misconfiguredDatasourceUsages') | Where-Object { $_ }).Count -gt 0) {
                    New-Finding GV003 $wn $k.Type $in 'the scanner lists a misconfigured data source usage for this item (misconfiguredDatasourceUsages)'
                }
                if ($item.PSObject.Properties['users']) {
                    foreach ($u in @(@($item.users) | Where-Object { $_ -and (Get-Prop $_ @('principalType')) -eq 'None' })) {
                        New-Finding GV006 $wn $k.Type $in 'access granted to the whole organization (principal type None)'
                    }
                }
            }
        }

        foreach ($ds in @(Get-Prop $ws @('datasets') | Where-Object { $_ })) {
            $dn = [string] (Get-Prop $ds @('name'))
            $endorse = [string] (Get-Prop (Get-Prop $ds @('endorsementDetails')) @('endorsement'))
            if ([string]::IsNullOrWhiteSpace($endorse) -or $endorse -eq 'None') {
                New-Finding GV002 $wn 'semantic model' $dn 'not promoted and not certified'
            }
            $err = Get-Prop $ds @('schemaRetrievalError')
            if ($err) { New-Finding GV004 $wn 'semantic model' $dn "schema not readable: $err" }
            foreach ($role in @(Get-Prop $ds @('roles') | Where-Object { $_ })) {
                $members = Get-Prop $role @('members')
                if ($role.PSObject.Properties['members'] -and @($members | Where-Object { $_ }).Count -eq 0) {
                    New-Finding GV008 $wn 'semantic model' $dn "role '$(Get-Prop $role @('name'))' has no members"
                }
            }
        }

        # An empty users array is a real answer (nobody has access), so test that the property exists; Get-Prop would return $null for an empty array.
        if ($type -eq 'Workspace' -and $ws.PSObject.Properties['users'] -and $null -ne $ws.users) {
            $wsUsers = @($ws.users)
            $admins = @($wsUsers | Where-Object { $_ -and (Get-Prop $_ @('groupUserAccessRight')) -eq 'Admin' })
            if ($admins.Count -eq 0) { New-Finding GV005 $wn 'workspace' $wn 'no user, group or app has the Admin right' }
        }
        if ($state -and $state -ne 'Active') { New-Finding GV007 $wn 'workspace' $wn "state is '$state'" }
        if ($type -eq 'PersonalGroup' -and $itemCount -gt 0) { New-Finding GV009 $wn 'workspace' $wn "personal workspace holds $itemCount item(s); they belong to one person, not to a team" }
    }
}

# ---- tenant settings ------------------------------------------------------------------------------------------------------------

function Invoke-FabricGet {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Uri, [Parameter(Mandatory)][securestring] $Token, [int] $MaxRetry = 3)
    $headers = @{ Authorization = 'Bearer ' + (ConvertFrom-SecureString -SecureString $Token -AsPlainText) }
    for ($try = 0; ; $try++) {
        try { return Invoke-RestMethod -Method Get -Uri $Uri -Headers $headers }
        catch [Microsoft.PowerShell.Commands.HttpResponseException] {
            $resp = $_.Exception.Response
            if ([int] $resp.StatusCode -eq 429 -and $try -lt $MaxRetry) {
                # Learn (List Tenant Settings): 25 requests per minute; 429 carries Retry-After in seconds.
                $wait = 5
                $vals = $null
                if ($resp.Headers.TryGetValues('Retry-After', [ref] $vals)) { $wait = [int] ($vals | Select-Object -First 1) }
                Start-Sleep -Seconds $wait
                continue
            }
            throw
        }
    }
}

function Get-PbiTenantSetting {
    <#
    .SYNOPSIS  All tenant settings (GET https://api.fabric.microsoft.com/v1/admin/tenantsettings). Caller: Fabric administrator; token for api.fabric.microsoft.com.
    #>
    [CmdletBinding()]
    param([securestring] $FabricToken)
    if (-not $FabricToken -and $env:PBIGOV_FABRIC_TOKEN) { $FabricToken = ConvertTo-SecureString $env:PBIGOV_FABRIC_TOKEN -AsPlainText -Force }
    if (-not $FabricToken) { throw "Pass -FabricToken, for example: Get-AzAccessToken -ResourceUrl 'https://api.fabric.microsoft.com' -AsSecureString" }
    $uri = "$script:FabricBase/v1/admin/tenantsettings"
    while ($uri) {
        $r = Invoke-FabricGet -Uri $uri -Token $FabricToken
        foreach ($s in @(Get-Prop $r @('value'))) {
            if (-not $s) { continue }
            [pscustomobject]@{
                SettingName = $s.settingName
                Title       = Get-Prop $s @('title')
                Group       = Get-Prop $s @('tenantSettingGroup')
                Enabled     = [bool] (Get-Prop $s @('enabled'))
                Groups      = @(@(Get-Prop $s @('enabledSecurityGroups')) | Where-Object { $_ } | ForEach-Object { $_.name } | Sort-Object)
                Excluded    = @(@(Get-Prop $s @('excludedSecurityGroups')) | Where-Object { $_ } | ForEach-Object { $_.name } | Sort-Object)
            }
        }
        # "If there are no more records, it's removed from the response."
        $uri = Get-Prop $r @('continuationUri')
    }
}

function Export-PbiTenantBaseline {
    <#
    .SYNOPSIS  Writes the baseline: for each setting its name, title, enabled and the names of its security groups. Review it, keep the settings you care about, commit it.
    .PARAMETER Name  Only these setting names (default: all).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object[]] $Setting, [Parameter(Mandatory)][string] $Path, [string[]] $Name)
    $rows = @($Setting | Where-Object { -not $Name -or $Name -contains $_.SettingName } | Sort-Object SettingName | ForEach-Object {
            [ordered]@{ settingName = $_.SettingName; title = $_.Title; enabled = $_.Enabled; enabledSecurityGroups = @($_.Groups); excludedSecurityGroups = @($_.Excluded) }
        })
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    ConvertTo-Json -InputObject $rows -Depth 5 | Set-Content -Path $Path -Encoding utf8
    $rows.Count
}

function Compare-PbiTenantSetting {
    <#
    .SYNOPSIS  Drift between a baseline (file written by Export-PbiTenantBaseline) and the current settings.
               EnabledChanged and GroupsChanged are drift; Missing = in the baseline but not returned now; New = not in the baseline (info).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object[]] $Current, [Parameter(Mandatory)][string] $BaselinePath, [switch] $IgnoreNew)
    $baseline = @(Get-Content -Raw -Path $BaselinePath | ConvertFrom-Json -Depth 5)
    $now = @{}; foreach ($c in $Current) { $now[$c.SettingName] = $c }
    $known = @{}
    foreach ($b in $baseline) {
        $known[$b.settingName] = $true
        $c = $now[$b.settingName]
        if (-not $c) { [pscustomobject]@{ Setting = $b.settingName; Kind = 'Missing'; Was = "enabled=$($b.enabled)"; Now = '(not returned)' }; continue }
        if ([bool] $b.enabled -ne [bool] $c.Enabled) {
            [pscustomobject]@{ Setting = $b.settingName; Kind = 'EnabledChanged'; Was = "enabled=$($b.enabled)"; Now = "enabled=$($c.Enabled)" }
        }
        $was = @(@($b.enabledSecurityGroups) | Where-Object { $_ } | Sort-Object)
        $is = @($c.Groups)
        if (($was -join '|') -ne ($is -join '|')) {
            [pscustomobject]@{ Setting = $b.settingName; Kind = 'GroupsChanged'; Was = ($was -join ', '); Now = ($is -join ', ') }
        }
    }
    if (-not $IgnoreNew) {
        foreach ($c in ($Current | Where-Object { -not $known.ContainsKey($_.SettingName) })) {
            [pscustomobject]@{ Setting = $c.SettingName; Kind = 'New'; Was = '(not in baseline)'; Now = "enabled=$($c.Enabled)" }
        }
    }
}

# ---- report ---------------------------------------------------------------------------------------------------------------------

function New-PbiGovernanceReport {
    <#
    .SYNOPSIS  A short Markdown report. Every section is optional; a missing section says it was not run, it never says "all clear".
    #>
    [CmdletBinding()]
    param([datetime] $Date, $Findings, $Drift, $ActivitySummary, $Orphans, [int] $WorkspacesScanned = -1)
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine('# Power BI governance check' + $(if ($PSBoundParameters.ContainsKey('Date')) { " ($($Date.ToString('yyyy-MM-dd')) UTC)" } else { '' }))
    $null = $sb.AppendLine()

    $null = $sb.AppendLine('## Tenant settings drift')
    if ($null -eq $Drift) { $null = $sb.AppendLine('_Not run._') }
    elseif (@($Drift).Count -eq 0) { $null = $sb.AppendLine('No difference from the baseline.') }
    else { foreach ($d in $Drift) { $null = $sb.AppendLine("- **$($d.Setting)** $($d.Kind): $($d.Was) -> $($d.Now)") } }
    $null = $sb.AppendLine()

    $null = $sb.AppendLine('## Orphaned workspaces')
    if ($null -eq $Orphans) { $null = $sb.AppendLine('_Not run._') }
    elseif (@($Orphans).Count -eq 0) { $null = $sb.AppendLine('None returned.') }
    else { foreach ($o in $Orphans) { $null = $sb.AppendLine("- $($o.Name) ($($o.Type), $($o.State))") } }
    $null = $sb.AppendLine()

    $null = $sb.AppendLine('## Scan findings' + $(if ($WorkspacesScanned -ge 0) { " ($WorkspacesScanned workspaces scanned)" } else { '' }))
    if ($null -eq $Findings) { $null = $sb.AppendLine('_Not run._') }
    elseif (@($Findings).Count -eq 0) { $null = $sb.AppendLine('No findings from rules GV001-GV009.') }
    else {
        $null = $sb.AppendLine('| Rule | Severity | Workspace | Item | Message |')
        $null = $sb.AppendLine('|---|---|---|---|---|')
        $order = @{ error = 0; warning = 1; info = 2 }
        foreach ($f in ($Findings | Sort-Object { $order[$_.Severity] }, Rule, Workspace, ItemName)) {
            $null = $sb.AppendLine("| $($f.Rule) | $($f.Severity) | $($f.Workspace) | $($f.ItemType): $($f.ItemName) | $($f.Message) |")
        }
    }
    $null = $sb.AppendLine()

    $null = $sb.AppendLine('## Activity')
    if ($null -eq $ActivitySummary) { $null = $sb.AppendLine('_Not run._') }
    else {
        $null = $sb.AppendLine("$($ActivitySummary.Total) events, $($ActivitySummary.Failed) with IsSuccess false.")
        foreach ($a in @($ActivitySummary.ByActivity | Select-Object -First 8)) { $null = $sb.AppendLine("- $($a.Activity): $($a.Count)") }
        if (@($ActivitySummary.TopReports).Count) {
            $null = $sb.AppendLine(); $null = $sb.AppendLine('Most viewed reports:')
            foreach ($r in @($ActivitySummary.TopReports | Select-Object -First 5)) { $null = $sb.AppendLine("- $($r.Report): $($r.Views) views, $($r.Users) user(s)") }
        }
        if (@($ActivitySummary.Risky).Count) {
            $null = $sb.AppendLine(); $null = $sb.AppendLine('Worth a second look:')
            foreach ($r in $ActivitySummary.Risky) { $null = $sb.AppendLine("- $($r.Time) $($r.Activity) by $($r.User) on $($r.Item)") }
        }
    }
    $sb.ToString()
}

Export-ModuleMember -Function Get-PbiGovernanceRule, Get-PbiActivityEvent, Get-PbiActivitySummary, Get-PbiOrphanedWorkspace,
    Get-PbiModifiedWorkspace, Invoke-PbiWorkspaceScan, Test-PbiGovernance, Get-PbiTenantSetting, Export-PbiTenantBaseline,
    Compare-PbiTenantSetting, New-PbiGovernanceReport
