#Requires -Version 7.2
<#
.SYNOPSIS
    Microsoft 365 Copilot readiness (DEVLADLOG Microsoft 365 #8). Everything here is READ-ONLY and works WITHOUT a
    Copilot licence: it collects licences, labels and sharing through Microsoft Graph, then analyses the snapshot
    with pure functions (so the analysis runs offline on a saved snapshot).

    Graph v1.0 used (Microsoft Learn), with the delegated scope each call needs:
      GET /subscribedSkus                                         LicenseAssignment.Read.All
      GET /users, GET /users/{id}/licenseDetails                  User.Read.All, LicenseAssignment.Read.All (+ a role such as Directory Readers)
      GET /security/dataSecurityAndGovernance/sensitivityLabels   SensitivityLabel.Read (or SensitivityLabels.Read.All)
      GET /sites?search={q}, GET /sites/{id}/drive                Sites.Read.All
      GET /drives/{id}/items/{id}/children, .../permissions       Files.Read.All
      GET /copilot/reports/getMicrosoft365CopilotUsageUserDetail  Reports.Read.All + a report-reader admin role
                                                                  (NEEDS a Copilot licence to return anything)
#>
Set-StrictMode -Version Latest

$script:Graph = '/v1.0'
$script:Severity = @{ High = 3; Medium = 2; Low = 1; Info = 0 }

function Get-CRProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($p -and $null -ne $p.Value) { $p.Value } else { $Default }
}

function Invoke-CRGraphPaged([string]$Uri) {
    $items = [System.Collections.Generic.List[object]]::new()
    $next = $Uri
    while ($next) {
        $page = Invoke-MgGraphRequest -Method GET -Uri $next -OutputType PSObject -ErrorAction Stop
        foreach ($v in @(Get-CRProp $page 'value' @())) { $items.Add($v) }
        $next = Get-CRProp $page '@odata.nextLink'
    }
    $items.ToArray()
}

# ---------------------------------------------------------------- config
function Get-CopilotConfig {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Path)
    $c = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($s in 'readiness', 'sharing', 'labels') { if (-not (Get-CRProp $c $s)) { throw "Config: section '$s' is missing." } }
    $r = $c.readiness
    foreach ($k in 'copilotSkuPartNumbers', 'copilotAppPlans', 'copilotAllPlans', 'chatEntitlementPlans', 'mailboxPlans', 'officeAppsPlans') {
        $v = @(Get-CRProp $r $k @())
        if ($v.Count -eq 0 -or ($v | Where-Object { $_ -isnot [string] -or [string]::IsNullOrWhiteSpace($_) })) { throw "Config: readiness.$k must be a non-empty list of names." }
    }
    $mu = Get-CRProp $r 'maxUsers' 0
    if ($mu -isnot [int] -and $mu -isnot [long] -or $mu -lt 1 -or $mu -gt 1000) { throw 'Config: readiness.maxUsers must be a whole number from 1 to 1000.' }
    $s = $c.sharing
    foreach ($k in 'maxItemsPerDrive', 'maxDepth') {
        $v = Get-CRProp $s $k 0
        if ($v -isnot [int] -and $v -isnot [long] -or $v -lt 1) { throw "Config: sharing.$k must be a whole number of at least 1." }
    }
    if ([int]$s.maxDepth -gt 10) { throw 'Config: sharing.maxDepth must be 10 or less.' }
    foreach ($k in 'flagOrganizationLinks', 'flagEveryoneExceptExternalUsers') {
        if ((Get-CRProp $s $k) -isnot [bool]) { throw "Config: sharing.$k must be true or false." }
    }
    foreach ($k in 'requireFileLabel', 'requireContainerLabel') {
        if ((Get-CRProp $c.labels $k) -isnot [bool]) { throw "Config: labels.$k must be true or false." }
    }
    $c
}

# ---------------------------------------------------------------- collection (Graph, read-only)
function Get-CopilotSku {
    <# Tenant subscriptions: GET /subscribedSkus. #>
    [CmdletBinding()] param()
    @(Invoke-CRGraphPaged "$script:Graph/subscribedSkus")
}

function Get-CopilotUserLicence {
    <# Enabled users and the service plans of their licences: GET /users + /users/{id}/licenseDetails. #>
    [CmdletBinding()] param([int]$Top = 50)
    $users = @(Invoke-CRGraphPaged "$script:Graph/users?`$select=id,displayName,userPrincipalName,accountEnabled&`$top=100") | Select-Object -First $Top
    foreach ($u in $users) {
        $details = @(Invoke-CRGraphPaged "$script:Graph/users/$($u.id)/licenseDetails")
        [pscustomobject]@{
            id                = $u.id
            displayName       = $u.displayName
            userPrincipalName = $u.userPrincipalName
            accountEnabled    = [bool](Get-CRProp $u 'accountEnabled' $true)
            licences          = @($details | ForEach-Object { Get-CRProp $_ 'skuPartNumber' })
            servicePlans      = @($details | ForEach-Object { @(Get-CRProp $_ 'servicePlans' @()) } | ForEach-Object {
                    [pscustomobject]@{ servicePlanName = $_.servicePlanName; provisioningStatus = $_.provisioningStatus } })
        }
    }
}

function Get-CopilotLabel {
    <# Sensitivity labels of the tenant: GET /security/dataSecurityAndGovernance/sensitivityLabels. #>
    [CmdletBinding()] param()
    @(Invoke-CRGraphPaged "$script:Graph/security/dataSecurityAndGovernance/sensitivityLabels")
}

function Get-CopilotDrive {
    <# Default document library of each site that matches a search: GET /sites?search=, GET /sites/{id}/drive. #>
    [CmdletBinding()] param([string]$Search = '*')
    foreach ($s in @(Invoke-CRGraphPaged "$script:Graph/sites?search=$([uri]::EscapeDataString($Search))")) {
        $d = Invoke-MgGraphRequest -Method GET -Uri "$script:Graph/sites/$($s.id)/drive?`$select=id,name,webUrl" -OutputType PSObject -ErrorAction Stop
        [pscustomobject]@{ DriveId = $d.id; Site = (Get-CRProp $s 'displayName' (Get-CRProp $s 'name' $s.id)); WebUrl = (Get-CRProp $d 'webUrl') }
    }
}

function Get-CopilotSharedItem {
    <# Walks a drive breadth-first (limits from the config) and reads the permissions of every folder and file. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$DriveId, [string]$Site = '', [int]$MaxItems = 200, [int]$MaxDepth = 3)
    $queue = [System.Collections.Generic.Queue[object]]::new()
    $queue.Enqueue([pscustomobject]@{ Uri = "$script:Graph/drives/$DriveId/root/children?`$select=id,name,folder,file&`$top=200"; Path = ''; Depth = 1 })
    $seen = 0
    while ($queue.Count -gt 0 -and $seen -lt $MaxItems) {
        $q = $queue.Dequeue()
        foreach ($i in @(Invoke-CRGraphPaged $q.Uri)) {
            if ($seen -ge $MaxItems) { break }
            $seen++
            $isFolder = $null -ne (Get-CRProp $i 'folder')
            $path = "$($q.Path)/$($i.name)"
            $perms = @(Invoke-CRGraphPaged "$script:Graph/drives/$DriveId/items/$($i.id)/permissions")
            [pscustomobject]@{ DriveId = $DriveId; Site = $Site; ItemId = $i.id; Path = $path; IsFolder = $isFolder; Permissions = $perms }
            if ($isFolder -and $q.Depth -lt $MaxDepth) {
                $queue.Enqueue([pscustomobject]@{ Uri = "$script:Graph/drives/$DriveId/items/$($i.id)/children?`$select=id,name,folder,file&`$top=200"; Path = $path; Depth = $q.Depth + 1 })
            }
        }
    }
}

function Get-CopilotUsageReport {
    <#
    NEEDS a Microsoft 365 Copilot licence in the tenant: Learn says this report only contains users who have a Copilot
    licence. Unlicensed Copilot Chat usage is not available through Graph reports (use the admin center Copilot Chat
    usage report or the Purview audit log). Needs Reports.Read.All and a report-reader role (AI Administrator, Reports Reader, ...).
    The v1.0 page describes the response as a CSV stream, so it is downloaded to a temp file and parsed.
    #>
    [CmdletBinding()] param([ValidateSet('D7', 'D28', 'D90', 'D180')][string]$Period = 'D7')
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("copilot-usage-{0}.csv" -f [guid]::NewGuid())
    try {
        Invoke-MgGraphRequest -Method GET -Uri "$script:Graph/copilot/reports/getMicrosoft365CopilotUsageUserDetail(period='$Period')" -OutputFilePath $tmp -ErrorAction Stop
        if (Test-Path -LiteralPath $tmp) { @(Import-Csv -LiteralPath $tmp) } else { @() }
    }
    finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
}

function ConvertTo-CopilotSnapshot {
    <# Bundles the collected data so the analysis can be re-run offline (and so you can diff two runs). Contains tenant data: never commit it. #>
    [CmdletBinding()]
    param($Skus, $Users, $Labels, $Items, [string]$Note = '')
    [pscustomobject]@{ collectedAt = [datetimeoffset]::UtcNow.ToString('o'); note = $Note; skus = @($Skus); users = @($Users); labels = @($Labels); items = @($Items) }
}

# ---------------------------------------------------------------- analysis (pure)
function Get-ActivePlanName($Plans) {
    @(@($Plans) | Where-Object { $_ -and $_.provisioningStatus -eq 'Success' } | ForEach-Object servicePlanName)
}

function Test-CopilotReadiness {
    <# Tenant-level and per-user readiness. A Copilot Studio trial is NOT a Microsoft 365 Copilot licence. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Skus, [Parameter(Mandatory)]$Users, [Parameter(Mandatory)]$Config)
    $r = $Config.readiness
    $copilotSkus = @(@($Skus) | Where-Object {
            $names = Get-ActivePlanName $_.servicePlans
            $_.skuPartNumber -in @($r.copilotSkuPartNumbers) -or @($names | Where-Object { $_ -in @($r.copilotAppPlans) }).Count -gt 0
        })
    $enabled = 0; $consumed = 0
    foreach ($s in $copilotSkus) { $enabled += [int](Get-CRProp (Get-CRProp $s 'prepaidUnits') 'enabled' 0); $consumed += [int](Get-CRProp $s 'consumedUnits' 0) }
    $tenant = [pscustomobject]@{
        HasCopilotLicence = ($copilotSkus.Count -gt 0)
        CopilotSkus       = @($copilotSkus | ForEach-Object skuPartNumber)
        SeatsEnabled      = $enabled
        SeatsAssigned     = $consumed
        SkuCount          = @($Skus).Count
    }
    $rows = foreach ($u in @($Users)) {
        $plans = Get-ActivePlanName $u.servicePlans
        $has = { param($list) @($plans | Where-Object { $_ -in @($list) }).Count -gt 0 }
        $copilot = & $has $r.copilotAppPlans
        $chat = & $has $r.chatEntitlementPlans
        $mailbox = & $has $r.mailboxPlans
        $apps = & $has $r.officeAppsPlans
        $notes = [System.Collections.Generic.List[string]]::new()
        if (-not $u.accountEnabled) { $notes.Add('account disabled') }
        if (-not $chat -and -not $copilot) { $notes.Add('no Copilot Chat entitlement plan') }
        if (-not $mailbox) { $notes.Add('no Exchange Online mailbox plan: mailbox-grounded answers need one') }
        if (-not $apps) { $notes.Add('no Microsoft 365 Apps plan: nothing for Copilot to sit in') }
        $status = if ($copilot) { 'Copilot licensed' } elseif ($chat -and $u.accountEnabled) { 'Copilot Chat only' } else { 'Not ready' }
        [pscustomobject]@{
            User = $u.userPrincipalName; DisplayName = $u.displayName; Status = $status
            CopilotLicence = $copilot; CopilotChat = ($chat -or $copilot); Mailbox = $mailbox; OfficeApps = $apps
            Notes = ($notes -join '; ')
        }
    }
    [pscustomobject]@{ Tenant = $tenant; Users = @($rows) }
}

function Get-CopilotLabelFinding {
    [CmdletBinding()] param([Parameter(Mandatory)][AllowEmptyCollection()]$Labels, [Parameter(Mandatory)]$Config)
    $out = [System.Collections.Generic.List[object]]::new()
    $add = { param($sev, $rule, $msg) $out.Add([pscustomobject]@{ Severity = $sev; Rule = $rule; Message = $msg }) }
    $enabled = @(@($Labels) | Where-Object { (Get-CRProp $_ 'isEnabled' $true) -eq $true })
    if ($enabled.Count -eq 0) {
        & $add 'High' 'NoLabels' 'No enabled sensitivity labels: Copilot cannot tell sensitive content from the rest, and label-based protection has nothing to enforce.'
        return @($out)
    }
    $targets = { param($l) @((([string](Get-CRProp $l 'applicableTo' '')) -split '[,\s]+') | Where-Object { $_ }) }
    $file = @($enabled | Where-Object { 'file' -in (& $targets $_) })
    $container = @($enabled | Where-Object { @(& $targets $_ | Where-Object { $_ -in 'site', 'unifiedGroup' }).Count -gt 0 })
    if ($Config.labels.requireFileLabel -and $file.Count -eq 0) { & $add 'High' 'NoFileLabel' 'No enabled label is applicable to files.' }
    if ($Config.labels.requireContainerLabel -and $container.Count -eq 0) { & $add 'Medium' 'NoContainerLabel' 'No enabled label is applicable to sites or groups (container labels), so a site cannot carry a label.' }
    if (@($enabled | Where-Object { (Get-CRProp $_ 'isDefault' $false) -eq $true }).Count -eq 0) { & $add 'Low' 'NoDefaultLabel' 'No default label: unlabeled files stay unlabeled until someone labels them.' }
    if (@($enabled | Where-Object { (Get-CRProp $_ 'applicationMode' '') -eq 'automatic' }).Count -eq 0) { & $add 'Low' 'NoAutoLabel' 'No label applies automatically: labeling depends on people.' }
    @($out)
}

function Get-PermissionSignal($Permission, $Config) {
    $link = Get-CRProp $Permission 'link'
    $scope = [string](Get-CRProp $link 'scope' '')
    if ($scope -eq 'anonymous') { return 'AnyoneLink' }
    if ($scope -eq 'organization' -and $Config.sharing.flagOrganizationLinks) { return 'OrganizationLink' }
    if ($Config.sharing.flagEveryoneExceptExternalUsers) {
        $v2 = Get-CRProp $Permission 'grantedToV2'
        $names = @(
            (Get-CRProp (Get-CRProp $v2 'siteGroup') 'displayName'), (Get-CRProp (Get-CRProp $v2 'siteGroup') 'loginName'),
            (Get-CRProp (Get-CRProp $v2 'siteUser') 'displayName'), (Get-CRProp (Get-CRProp $v2 'siteUser') 'loginName'),
            (Get-CRProp (Get-CRProp $v2 'group') 'displayName')
        ) | Where-Object { $_ }
        # The display name is what Learn documents; the claim fragment is how SharePoint is commonly seen to render the group (verify in your tenant).
        if (@($names | Where-Object { $_ -like '*Everyone except external users*' -or $_ -like '*spo-grid-all-users*' }).Count -gt 0) { return 'EveryoneExceptExternalUsers' }
    }
    $null
}

function Get-CopilotSharingFinding {
    <# One finding per distinct broad permission. SharePoint libraries don't return inheritedFrom (Learn), so a permission that repeats on a child is reported once, at the shallowest path. #>
    [CmdletBinding()] param([Parameter(Mandatory)][AllowEmptyCollection()]$Items, [Parameter(Mandatory)]$Config)
    $sev = @{ AnyoneLink = 'High'; EveryoneExceptExternalUsers = 'Medium'; OrganizationLink = 'Medium' }
    $text = @{
        AnyoneLink                  = 'An Anyone link: no sign-in needed. Copilot respects permissions, so this is not extra Copilot exposure, but it is open to the world.'
        EveryoneExceptExternalUsers = 'Shared with Everyone except external users: every internal user can open it, so Copilot can surface it for anyone in the company.'
        OrganizationLink            = 'A People-in-the-organization link: anyone signed in to the tenant can use it.'
    }
    $hints = @($Config.sharing.sensitiveNameHints | ForEach-Object { $_.ToLowerInvariant() })
    $seen = @{}
    $out = foreach ($item in (@($Items) | Sort-Object { ([string]$_.Path -split '/').Count })) {
        foreach ($p in @(Get-CRProp $item 'Permissions' @())) {
            $signal = Get-PermissionSignal $p $Config
            if (-not $signal) { continue }
            $key = "$($item.DriveId)|$signal|$(Get-CRProp $p 'id')|$(Get-CRProp (Get-CRProp $p 'link') 'webUrl')"
            if ($seen.ContainsKey($key)) { continue }
            $seen[$key] = $true
            $s = $sev[$signal]; $why = $text[$signal]
            $lower = ([string]$item.Path).ToLowerInvariant()
            if (@($hints | Where-Object { $lower.Contains($_) }).Count -gt 0) {
                if ($s -eq 'Medium') { $s = 'High' }
                $why += ' The name looks sensitive.'
            }
            [pscustomobject]@{
                Severity = $s; Signal = $signal; Site = $item.Site; Path = $item.Path; IsFolder = [bool]$item.IsFolder
                Role = (@(Get-CRProp $p 'roles' @()) -join ','); Message = $why
            }
        }
    }
    @($out | Sort-Object @{ e = { -$script:Severity[$_.Severity] } }, Site, Path)
}

function ConvertTo-CopilotMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Readiness, $LabelFindings = @(), $SharingFindings = @(), [int]$LabelCount = 0, [int]$ItemsScanned = 0, [string]$GeneratedOn = '')
    $t = $Readiness.Tenant
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine('# Microsoft 365 Copilot readiness report').AppendLine()
    if ($GeneratedOn) { $null = $sb.AppendLine("Generated: $GeneratedOn").AppendLine() }
    $null = $sb.AppendLine('## Licence').AppendLine()
    if ($t.HasCopilotLicence) { $null = $sb.AppendLine("Microsoft 365 Copilot licence found: $($t.CopilotSkus -join ', ') ($($t.SeatsAssigned) of $($t.SeatsEnabled) seats assigned).").AppendLine() }
    else { $null = $sb.AppendLine('**No Microsoft 365 Copilot licence in this tenant.** Copilot Chat with Entra accounts still works (see users below); Copilot in Word, Excel, PowerPoint, Outlook and Teams, and grounding in Microsoft Graph, need the add-on licence.').AppendLine() }
    $null = $sb.AppendLine('## Users').AppendLine().AppendLine('| User | Status | Copilot Chat | Mailbox | Microsoft 365 Apps | Notes |').AppendLine('|---|---|---|---|---|---|')
    foreach ($u in $Readiness.Users) { $null = $sb.AppendLine("| $($u.User) | $($u.Status) | $(if ($u.CopilotChat) {'yes'} else {'no'}) | $(if ($u.Mailbox) {'yes'} else {'no'}) | $(if ($u.OfficeApps) {'yes'} else {'no'}) | $($u.Notes) |") }
    $null = $sb.AppendLine().AppendLine("## Sensitivity labels ($LabelCount listed)").AppendLine()
    if (@($LabelFindings).Count -eq 0) { $null = $sb.AppendLine('No label findings.') } else { foreach ($f in $LabelFindings) { $null = $sb.AppendLine("- **$($f.Severity)** $($f.Rule): $($f.Message)") } }
    $null = $sb.AppendLine().AppendLine("## Oversharing review ($ItemsScanned items scanned)").AppendLine()
    if (@($SharingFindings).Count -eq 0) { $null = $sb.AppendLine('No broad sharing found in the scanned items.') }
    else {
        $null = $sb.AppendLine('| Severity | Signal | Site | Path | Role |').AppendLine('|---|---|---|---|---|')
        foreach ($f in $SharingFindings) { $null = $sb.AppendLine("| $($f.Severity) | $($f.Signal) | $($f.Site) | $($f.Path) | $($f.Role) |") }
    }
    $null = $sb.AppendLine().AppendLine('_Sampled walk of the sites searched, limited by `sharing.maxItemsPerDrive` and `maxDepth`. It is not a replacement for the SharePoint Advanced Management data access governance reports, which cover the whole tenant._')
    $sb.ToString()
}
Export-ModuleMember -Function Get-CopilotConfig, Get-CopilotSku, Get-CopilotUserLicence, Get-CopilotLabel, Get-CopilotDrive, Get-CopilotSharedItem, Test-CopilotReadiness, Get-CopilotLabelFinding, Get-CopilotSharingFinding, Get-CopilotUsageReport, ConvertTo-CopilotSnapshot, ConvertTo-CopilotMarkdown
