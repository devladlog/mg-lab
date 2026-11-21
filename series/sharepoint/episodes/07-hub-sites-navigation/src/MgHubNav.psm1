#Requires -Version 7.2
<#
.SYNOPSIS
    Hub sites and hub navigation as code for the Contoso Operations hub: a hub plan (the hub, who may associate
    sites, which sites join it, and the shared navigation with audience targeting), a linter for the plan, a check
    of the tenant's hub hierarchy, provisioning with PnP PowerShell, and a read-back that compares the tenant with
    the plan.

    Pure functions (no SharePoint needed): Import-MgJson, ConvertTo-MgAbsoluteUrl, Get-MgNavNodeList,
    Test-MgNavigation, Test-MgHubPlan, Test-MgHubHierarchy, Compare-MgNavigation, Test-MgHubLive.
    Tenant functions (PnP.PowerShell, after Connect-PnPOnline): Resolve-MgAudience, Invoke-MgHubRegistration,
    Invoke-MgHubAssociation, Get-MgLiveNavigation, Invoke-MgNavigationTree, Invoke-MgHubNavigation, Get-MgHubState.

    Episode 8 imports this module for the global navigation (it is a navigation tree too).
#>

Set-StrictMode -Version Latest

# ---- What Learn documents (see README "References") -------------------------------------------------------------
#   An organization can have up to 2,000 hub sites; hub-to-hub associations count against it.
$script:MaxHubs = 2000
#   Hub to hub associations: content on sites beyond level 3 won't appear in search results.
$script:MaxHubLevels = 3
#   Cascading and mega menus support up to three levels of navigation.
$script:MaxNavLevels = 3
#   All navigation types (site, hub, global, footer) are limited to 500 child links at each level.
$script:MaxLinksPerLevel = 500
#   Recommended: fewer than 100 items in site navigation (modern portal limits); "practically ... no more than 100".
$script:RecommendedLinks = 100
#   Audience targeting on navigation: up to 10 groups per link.
$script:MaxAudiences = 10
#   Document links open in a new window and leave the site context: link to pages, not documents.
#   Not from Learn: the URL the modern navigation editor stores for a label (a node without a link). Checked in the
#   lab recording (demo.md); see README "Not verified yet".
$script:LabelUrl = 'http://linkless.header/'
$script:DocumentExtensions = @('.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.vsdx', '.txt', '.csv', '.zip')

function Import-MgJson {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json -Depth 30
}

function Get-MgProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    if ($Object.PSObject.Properties[$Name]) { $Object.$Name } else { $Default }
}

function New-MgFinding([string]$Rule, [string]$Severity, [string]$Target, [string]$Message) {
    [pscustomobject]@{ Rule = $Rule; Severity = $Severity; Target = $Target; Message = $Message }
}

function New-MgStep([string]$Action, [string]$Target, [string]$Detail = '') {
    [pscustomobject]@{ Action = $Action; Target = $Target; Detail = $Detail }
}

function Test-MgGuid([string]$Value) { $g = [guid]::Empty; [guid]::TryParse($Value, [ref]$g) }

function ConvertTo-MgAbsoluteUrl {
    <# .SYNOPSIS  '/sites/X' + 'https://contoso.sharepoint.com' -> absolute URL; absolute URLs are returned as they are. #>
    [CmdletBinding()]
    param([AllowEmptyString()][string]$Url, [string]$TenantUrl)
    if (-not $Url) { return $Url }
    if ($Url -match '^https?://') { return $Url }
    if (-not $TenantUrl) { return $Url }
    $TenantUrl.TrimEnd('/') + '/' + $Url.TrimStart('/')
}

function Get-MgUrlKey([string]$Url) {
    # Comparable form of a URL: no host, decoded, lowercase, no trailing slash.
    if (-not $Url) { return '' }
    $u = [uri]::UnescapeDataString($Url) -replace '^https?://[^/]+', ''
    $u.TrimEnd('/').ToLowerInvariant()
}

function Get-MgSiteKey([string]$Url) {
    # '/sites/Purchasing/SitePages/x.aspx' -> '/sites/purchasing' (managed path + site name).
    $k = Get-MgUrlKey $Url
    if ($k -match '^(/(sites|teams)/[^/]+)') { return $Matches[1] }
    $k
}

function Get-MgNavNodeList {
    <#
    .SYNOPSIS  Flattens a navigation tree: one row per node with its level, path, parent and effective audiences.
    #>
    [CmdletBinding()]
    param($Nodes, [int]$Level = 1, [string]$ParentPath = '', [string[]]$ParentAudiences = @())
    foreach ($n in @($Nodes | Where-Object { $null -ne $_ })) {
        $title = "$(Get-MgProp $n 'title' '')"
        $path = if ($ParentPath) { "$ParentPath > $title" } else { $title }
        $own = @(Get-MgProp $n 'audiences' @() | Where-Object { $_ })
        $children = @(Get-MgProp $n 'children' @() | Where-Object { $null -ne $_ })
        [pscustomobject]@{
            Title = $title; Url = "$(Get-MgProp $n 'url' '')"; Level = $Level; Path = $path; ParentPath = $ParentPath
            Audiences = $own; ParentAudiences = @($ParentAudiences | Where-Object { $_ }); ChildCount = $children.Count
            OpenInNewTab = [bool](Get-MgProp $n 'openInNewTab' $false)
        }
        if ($children.Count) {
            $effective = @(if ($own.Count) { $own } else { $ParentAudiences })
            Get-MgNavNodeList -Nodes $children -Level ($Level + 1) -ParentPath $path -ParentAudiences $effective
        }
    }
}

function Test-MgNavigation {
    <#
    .SYNOPSIS  Lints a navigation tree (hub, site or global navigation) against Learn's limits and guidance.
    .PARAMETER Navigation  { megaMenu, audienceTargeting, nodes: [ { title, url?, audiences?, openInNewTab?, children? } ] }
    .PARAMETER Audiences   Names the plan declares (audience targeting uses Microsoft 365 or security groups).
    .PARAMETER Associations  Associated sites ({ url, private? }) - to check that each is linked, and private ones are targeted.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Navigation, [string[]]$Audiences = @(), $Associations = @(), [string]$Name = 'navigation')
    $rows = @(Get-MgNavNodeList -Nodes (Get-MgProp $Navigation 'nodes' @()))
    $targeting = [bool](Get-MgProp $Navigation 'audienceTargeting' $false)
    $known = @($Audiences | ForEach-Object { $_.ToLowerInvariant() })

    foreach ($r in $rows) {
        $t = if ($r.Path) { $r.Path } else { '(no title)' }
        if (-not $r.Title.Trim()) { New-MgFinding 'HN013' 'Error' $t 'Empty title: every link and label needs a clear label.' }
        if ($r.Level -gt $script:MaxNavLevels) {
            New-MgFinding 'HN001' 'Error' $t "Level $($r.Level): cascading and mega menus support up to $($script:MaxNavLevels) levels."
        }
        if (-not $r.Url -and $r.ChildCount -eq 0) {
            New-MgFinding 'HN004' 'Warning' $t 'A label with no links below it: a label should always have at least one link below.'
        }
        if ($r.Audiences.Count) {
            if (-not $targeting) {
                New-MgFinding 'HN005' 'Error' $t 'Audiences set but audience targeting is off for this navigation: everyone would see the link.'
            }
            if ($r.Audiences.Count -gt $script:MaxAudiences) {
                New-MgFinding 'HN005' 'Error' $t "$($r.Audiences.Count) audiences: a link can target up to $($script:MaxAudiences) groups."
            }
            foreach ($a in $r.Audiences | Where-Object { $_.ToLowerInvariant() -notin $known }) {
                New-MgFinding 'HN005' 'Error' $t "Audience '$a' isn't declared in the plan's audiences."
            }
            if ($r.ParentAudiences.Count) {
                $parents = @($r.ParentAudiences | ForEach-Object { $_.ToLowerInvariant() })
                $outside = @($r.Audiences | Where-Object { $_.ToLowerInvariant() -notin $parents })
                if ($outside.Count) {
                    New-MgFinding 'HN006' 'Warning' $t "Targeted to $($outside -join ', ') but its parent is targeted to $($r.ParentAudiences -join ', '): targeting a parent also applies to its sub-links, so only people in both see it."
                }
            }
        }
        if ($r.Url) {
            $clean = ($r.Url -split '[?#]')[0]
            if ($r.Url.Contains('#')) { New-MgFinding 'HN012' 'Error' $t "URL '$($r.Url)' has a fragment: PnP's Add-PnPNavigationNode doesn't support fragments." }
            $ext = [System.IO.Path]::GetExtension($clean).ToLowerInvariant()
            if ($ext -in $script:DocumentExtensions) {
                New-MgFinding 'HN007' 'Warning' $t "Links to a $ext file: document links open in a new window and leave the site; link to a page that embeds or links the document."
            }
        }
        if ($r.OpenInNewTab -and $Name -ne 'quicklaunch') {
            New-MgFinding 'HN011' 'Warning' $t 'openInNewTab is ignored here: PnP can only set it on QuickLaunch nodes (SharePoint API limitation).'
        }
    }
    # Per-level counts and duplicate labels under the same parent.
    foreach ($g in $rows | Group-Object ParentPath) {
        $where = if ($g.Name) { $g.Name } else { "$Name (top level)" }
        if ($g.Count -gt $script:MaxLinksPerLevel) {
            New-MgFinding 'HN002' 'Error' $where "$($g.Count) links at one level: all navigation types are limited to $($script:MaxLinksPerLevel) child links at each level."
        }
        foreach ($d in $g.Group | Where-Object { $_.Title.Trim() } | Group-Object { $_.Title.Trim().ToLowerInvariant() } | Where-Object Count -gt 1) {
            New-MgFinding 'HN010' 'Warning' $where "'$($d.Group[0].Title)' appears $($d.Count) times at the same level: labels should be clear and mutually exclusive."
        }
    }
    $links = @($rows | Where-Object Url).Count
    if ($links -gt $script:RecommendedLinks) {
        New-MgFinding 'HN003' 'Warning' $Name "$links links: Learn recommends fewer than $($script:RecommendedLinks) items in site navigation."
    }
    # Associated sites: linked at all? Private ones only for their audience?
    foreach ($s in @($Associations | Where-Object { $null -ne $_ })) {
        $key = Get-MgSiteKey $s.url
        $linking = @($rows | Where-Object { $_.Url -and (Get-MgSiteKey $_.Url) -eq $key })
        if (-not $linking.Count) {
            New-MgFinding 'HN008' 'Warning' $s.url 'Associated site not linked from the hub navigation: associating a site does not add it to the navigation.'
        }
        elseif ([bool](Get-MgProp $s 'private' $false)) {
            foreach ($l in $linking | Where-Object { -not $_.Audiences.Count -and -not $_.ParentAudiences.Count }) {
                New-MgFinding 'HN009' 'Warning' $l.Path "Links to the private site $($s.url) for everyone: target it to the site's members or label it (private)."
            }
        }
    }
}

function Test-MgHubPlan {
    <#
    .SYNOPSIS  Lints the hub plan: hub settings (HB001-HB007) and the hub navigation (HN001-HN013).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan)
    $hub = $Plan.hub
    $url = "$(Get-MgProp $hub 'url' '')"
    if ($url -notmatch '^/(sites|teams)/[^/]+/?$') {
        New-MgFinding 'HB001' 'Error' 'hub.url' "'$url' isn't a site collection URL like /sites/Name."
    }
    if ([bool](Get-MgProp $hub 'hideNameInNavigation' $false) -and -not (Get-MgProp $hub 'logoUrl')) {
        New-MgFinding 'HB002' 'Error' 'hub.hideNameInNavigation' 'Hiding the hub name needs a logo: you can hide the name only once a logo is selected.'
    }
    if ([bool](Get-MgProp $hub 'requiresJoinApproval' $false)) {
        New-MgFinding 'HB003' 'Warning' 'hub.requiresJoinApproval' 'Join approval needs an active approval flow (Power Automate); without one, sites can''t join the hub.'
    }
    if (-not @(Get-MgProp $hub 'canAssociate' @() | Where-Object { $_ }).Count) {
        New-MgFinding 'HB004' 'Warning' 'hub.canAssociate' 'Empty: any user can associate their site with the hub. Name the users or security groups allowed to.'
    }
    $design = Get-MgProp $hub 'siteDesignId'
    if ($design) {
        if (-not (Test-MgGuid $design)) { New-MgFinding 'HB005' 'Error' 'hub.siteDesignId' "'$design' isn't a GUID (the site template ID applied to sites that join)." }
        elseif ([guid]$design -eq [guid]::Empty) { New-MgFinding 'HB005' 'Error' 'hub.siteDesignId' 'The empty GUID: use null for no template.' }
    }
    $parent = Get-MgProp $hub 'parentHubUrl'
    if ($parent -and (Get-MgSiteKey $parent) -eq (Get-MgSiteKey $url)) {
        New-MgFinding 'HB007' 'Error' 'hub.parentHubUrl' 'A hub can''t be its own parent hub.'
    }
    $seen = @{}
    foreach ($a in @(Get-MgProp $Plan 'associations' @())) {
        $k = Get-MgSiteKey $a.url
        if ($k -eq (Get-MgSiteKey $url)) { New-MgFinding 'HB006' 'Error' $a.url 'The hub site itself is listed as an associated site.'; continue }
        if ($parent -and $k -eq (Get-MgSiteKey $parent)) { New-MgFinding 'HB006' 'Error' $a.url 'The parent hub is listed as an associated site: hubs connect with a hub-to-hub association.'; continue }
        if ($seen.ContainsKey($k)) { New-MgFinding 'HB006' 'Error' $a.url "Listed twice (also as $($seen[$k])): a site can be associated with only one hub, once."; continue }
        $seen[$k] = $a.url
    }
    $names = @((Get-MgProp $Plan 'audiences' ([pscustomobject]@{})).PSObject.Properties | ForEach-Object Name)
    $members = @(Get-MgProp $Plan 'associations' @() | Where-Object { (Get-MgSiteKey $_.url) -ne (Get-MgSiteKey $url) })
    Test-MgNavigation -Navigation $Plan.navigation -Audiences $names -Associations $members -Name 'hub navigation'
}

function Test-MgHubHierarchy {
    <#
    .SYNOPSIS  Checks the tenant's hubs (as Get-PnPHubSite returns them): count, cycles and hub-to-hub depth,
               optionally with the plan's hub and parent added.
    .PARAMETER Hubs  Objects with ID, SiteUrl, Title and ParentHubSiteId.
    #>
    [CmdletBinding()]
    param($Hubs = @(), $Plan, [string]$TenantUrl)
    $list = [System.Collections.Generic.List[object]]::new()
    foreach ($h in @($Hubs | Where-Object { $null -ne $_ })) {
        $list.Add([pscustomobject]@{ Id = "$(Get-MgProp $h 'ID' (Get-MgProp $h 'Id' ''))"; Key = (Get-MgSiteKey "$(Get-MgProp $h 'SiteUrl' '')"); Title = "$(Get-MgProp $h 'Title' '')"; Parent = "$(Get-MgProp $h 'ParentHubSiteId' '')" })
    }
    if ($Plan) {
        $hk = Get-MgSiteKey $Plan.hub.url
        $me = $list | Where-Object Key -eq $hk | Select-Object -First 1
        if (-not $me) { $me = [pscustomobject]@{ Id = 'planned'; Key = $hk; Title = $Plan.hub.title; Parent = '' }; $list.Add($me) }
        $p = Get-MgProp $Plan.hub 'parentHubUrl'
        if ($p) {
            $pk = Get-MgSiteKey $p
            $ph = $list | Where-Object Key -eq $pk | Select-Object -First 1
            if (-not $ph) { New-MgFinding 'HH004' 'Error' $p 'The parent hub in the plan isn''t a hub site in the tenant (register it first).' }
            else { $me.Parent = $ph.Id }
        }
    }
    if ($list.Count -gt $script:MaxHubs) {
        New-MgFinding 'HH003' 'Error' 'tenant' "$($list.Count) hub sites: an organization can have up to $($script:MaxHubs)."
    }
    $byId = @{}; foreach ($h in $list) { if ($h.Id) { $byId[$h.Id.ToLowerInvariant()] = $h } }
    foreach ($h in $list) {
        $depth = 1; $cur = $h; $visited = @($h.Id)
        while ($cur.Parent -and $cur.Parent -ne [guid]::Empty.ToString() -and $byId.ContainsKey($cur.Parent.ToLowerInvariant())) {
            $cur = $byId[$cur.Parent.ToLowerInvariant()]
            if ($cur.Id -in $visited) { New-MgFinding 'HH002' 'Error' $h.Title 'Hub-to-hub associations form a cycle.'; $depth = -1; break }
            $visited += $cur.Id; $depth++
        }
        if ($depth -gt $script:MaxHubLevels) {
            New-MgFinding 'HH001' 'Error' $h.Title "Level $depth of hub-to-hub associations: content on sites beyond level $($script:MaxHubLevels) won't appear in search results."
        }
    }
}

function ConvertTo-MgNavShape {
    # Plan nodes or live nodes -> { Title, Url (key), Audiences (sorted ids or names), Children }
    param($Nodes, [hashtable]$AudienceIds = @{}, [switch]$Live)
    foreach ($n in @($Nodes | Where-Object { $null -ne $_ })) {
        $aud = if ($Live) { @(Get-MgProp $n 'Audiences' @() | ForEach-Object { "$_".ToLowerInvariant() }) }
        else { @(Get-MgProp $n 'audiences' @() | Where-Object { $_ } | ForEach-Object { $id = $AudienceIds[$_]; if ($id) { "$id".ToLowerInvariant() } else { "$_".ToLowerInvariant() } }) }
        [pscustomobject]@{
            Title = "$(Get-MgProp $n 'Title' (Get-MgProp $n 'title' ''))"
            Url = Get-MgUrlKey "$(Get-MgProp $n 'Url' (Get-MgProp $n 'url' ''))"
            Audiences = @($aud | Sort-Object)
            Children = @(ConvertTo-MgNavShape -Nodes (Get-MgProp $n 'Children' (Get-MgProp $n 'children' @())) -AudienceIds $AudienceIds -Live:$Live)
        }
    }
}

function Compare-MgNavigation {
    <#
    .SYNOPSIS  Differences between the plan's navigation and the live one (as Get-MgLiveNavigation returns it).
               Order matters: navigation is read top to bottom.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$PlanNodes, $LiveNodes = @(), [hashtable]$AudienceIds = @{})
    function Walk($p, $l, [string]$path) {
        $p = @($p); $l = @($l)
        $max = [Math]::Max($p.Count, $l.Count)
        for ($i = 0; $i -lt $max; $i++) {
            $a = if ($i -lt $p.Count) { $p[$i] } else { $null }
            $b = if ($i -lt $l.Count) { $l[$i] } else { $null }
            $where = if ($a) { "$path$($a.Title)" } else { "$path$($b.Title)" }
            if (-not $b) { [pscustomobject]@{ Kind = 'Missing'; Path = $where; Detail = 'in the plan, not in the tenant' }; continue }
            if (-not $a) { [pscustomobject]@{ Kind = 'Extra'; Path = $where; Detail = 'in the tenant, not in the plan' }; continue }
            if ($a.Title -cne $b.Title) { [pscustomobject]@{ Kind = 'Title'; Path = $where; Detail = "tenant has '$($b.Title)'" } }
            if ($a.Url -ne $b.Url) { [pscustomobject]@{ Kind = 'Url'; Path = $where; Detail = "plan '$($a.Url)', tenant '$($b.Url)'" } }
            if (($a.Audiences -join ',') -ne ($b.Audiences -join ',')) { [pscustomobject]@{ Kind = 'Audience'; Path = $where; Detail = "plan [$($a.Audiences -join ', ')], tenant [$($b.Audiences -join ', ')]" } }
            Walk $a.Children $b.Children "$where > "
        }
    }
    Walk @(ConvertTo-MgNavShape -Nodes $PlanNodes -AudienceIds $AudienceIds) @(ConvertTo-MgNavShape -Nodes $LiveNodes -Live) ''
}

function Test-MgHubLive {
    <#
    .SYNOPSIS  Compares the tenant (Get-MgHubState) with the plan: HL001 hub settings, HL002/HL003 associations,
               HL004 navigation, HL005 web settings, plus the hierarchy rules.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)]$State, [string]$TenantUrl, [hashtable]$AudienceIds = @{})
    $hub = $State.Hub
    if (-not $hub) { New-MgFinding 'HL001' 'Error' $Plan.hub.url 'Not registered as a hub site.'; return }
    $want = [ordered]@{
        Title = $Plan.hub.title; Description = "$(Get-MgProp $Plan.hub 'description' '')"
        LogoUrl = Get-MgUrlKey (ConvertTo-MgAbsoluteUrl "$(Get-MgProp $Plan.hub 'logoUrl' '')" $TenantUrl)
        HideNameInNavigation = [bool](Get-MgProp $Plan.hub 'hideNameInNavigation' $false)
        RequiresJoinApproval = [bool](Get-MgProp $Plan.hub 'requiresJoinApproval' $false)
    }
    foreach ($k in $want.Keys) {
        $have = Get-MgProp $hub $k
        if ($k -eq 'LogoUrl') { $have = Get-MgUrlKey "$have" }
        elseif ($k -in 'HideNameInNavigation', 'RequiresJoinApproval') { $have = [bool]$have }
        else { $have = "$have" }
        if ($have -ne $want[$k]) { New-MgFinding 'HL001' 'Error' "hub.$k" "Tenant has '$have', plan says '$($want[$k])'." }
    }
    $live = @($State.Children | ForEach-Object { Get-MgSiteKey "$(if ($_ -is [string]) { $_ } else { Get-MgProp $_ 'Url' (Get-MgProp $_ 'SiteUrl' '') })" })
    $planned = @(Get-MgProp $Plan 'associations' @() | ForEach-Object { Get-MgSiteKey $_.url })
    foreach ($p in $planned | Where-Object { $_ -notin $live }) { New-MgFinding 'HL002' 'Error' $p 'In the plan but not associated with the hub.' }
    foreach ($l in $live | Where-Object { $_ -notin $planned -and $_ -ne (Get-MgSiteKey $Plan.hub.url) }) {
        New-MgFinding 'HL003' 'Warning' $l 'Associated with the hub but not in the plan (someone allowed to associate added it).'
    }
    foreach ($d in @(Compare-MgNavigation -PlanNodes $Plan.navigation.nodes -LiveNodes $State.Navigation -AudienceIds $AudienceIds)) {
        New-MgFinding 'HL004' 'Error' $d.Path "$($d.Kind): $($d.Detail)."
    }
    $web = $State.Web
    if ($web) {
        foreach ($p in @(@('NavAudienceTargetingEnabled', 'audienceTargeting'), @('MegaMenuEnabled', 'megaMenu'))) {
            $w = [bool](Get-MgProp $Plan.navigation $p[1] $false); $h = [bool](Get-MgProp $web $p[0] $false)
            if ($w -ne $h) { New-MgFinding 'HL005' 'Error' "web.$($p[0])" "Tenant has $h, plan says $w." }
        }
    }
    Test-MgHubHierarchy -Hubs $State.AllHubs -Plan $Plan -TenantUrl $TenantUrl
}

# ---- Tenant --------------------------------------------------------------------------------------------------------

function Resolve-MgAudience {
    <#
    .SYNOPSIS  Audience names -> Entra group IDs. A GUID in the plan is used as is; otherwise Get-PnPEntraIDGroup
               looks the group up by name (needs Microsoft Graph Group.Read.All on your PnP app).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $map = @{}
    foreach ($p in @((Get-MgProp $Plan 'audiences' ([pscustomobject]@{})).PSObject.Properties)) {
        if (Test-MgGuid "$($p.Value)") { $map[$p.Name] = [guid]"$($p.Value)"; continue }
        $g = @(Get-PnPEntraIDGroup -Identity $p.Name @c)
        if ($g.Count -ne 1) { throw "Audience '$($p.Name)': found $($g.Count) groups with that name. Put the group's object ID in the plan's audiences." }
        $map[$p.Name] = [guid]"$(Get-MgProp $g[0] 'Id')"
    }
    $map
}

function Invoke-MgHubRegistration {
    <#
    .SYNOPSIS  Registers the hub (with who may associate), sets its properties and its parent hub. Idempotent,
               -WhatIf. Needs a connection to the SharePoint admin center (SharePoint Administrator).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)][string]$TenantUrl, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $hubUrl = ConvertTo-MgAbsoluteUrl $Plan.hub.url $TenantUrl
    $principals = @(Get-MgProp $Plan.hub 'canAssociate' @() | Where-Object { $_ })
    $hub = try { Get-PnPHubSite -Identity $hubUrl -ErrorAction Stop @c } catch { $null }
    if (-not $hub) {
        if ($PSCmdlet.ShouldProcess($hubUrl, 'Register hub site')) {
            $r = @{ Site = $hubUrl }; if ($principals.Count) { $r.Principals = [string[]]$principals }
            $null = Register-PnPHubSite @r @c
            $hub = Get-PnPHubSite -Identity $hubUrl @c
        }
        New-MgStep 'RegisterHub' $Plan.hub.url $(if ($principals.Count) { "can associate: $($principals -join ', ')" } else { 'anyone can associate' })
    }
    elseif ($principals.Count) {
        # Granting an existing principal again is harmless; it keeps the list in step with the plan.
        if ($PSCmdlet.ShouldProcess($hubUrl, "Grant hub rights to $($principals -join ', ')")) { $null = Grant-PnPHubSiteRights -Identity $hubUrl -Principals ([string[]]$principals) @c }
        New-MgStep 'GrantRights' $Plan.hub.url ($principals -join ', ')
    }
    $set = @{}
    $logo = ConvertTo-MgAbsoluteUrl "$(Get-MgProp $Plan.hub 'logoUrl' '')" $TenantUrl
    if ("$(Get-MgProp $hub 'Title' '')" -ne $Plan.hub.title) { $set.Title = $Plan.hub.title }
    $desc = "$(Get-MgProp $Plan.hub 'description' '')"
    if ("$(Get-MgProp $hub 'Description' '')" -ne $desc) { $set.Description = $desc }
    if ($logo -and (Get-MgUrlKey "$(Get-MgProp $hub 'LogoUrl' '')") -ne (Get-MgUrlKey $logo)) { $set.LogoUrl = $logo }
    foreach ($b in 'HideNameInNavigation', 'RequiresJoinApproval') {
        $want = [bool](Get-MgProp $Plan.hub ($b.Substring(0, 1).ToLower() + $b.Substring(1)) $false)
        if ([bool](Get-MgProp $hub $b $false) -ne $want) { $set[$b] = [switch]$want }
    }
    $design = Get-MgProp $Plan.hub 'siteDesignId'
    if ($design -and "$(Get-MgProp $hub 'SiteDesignId' '')" -ne "$design") { $set.SiteDesignId = [guid]$design }
    if ($set.Count) {
        if ($PSCmdlet.ShouldProcess($hubUrl, "Set hub properties: $($set.Keys -join ', ')")) { $null = Set-PnPHubSite -Identity $hubUrl @set @c }
        New-MgStep 'SetHub' $Plan.hub.url (($set.Keys | Sort-Object) -join ', ')
    }
    $parent = Get-MgProp $Plan.hub 'parentHubUrl'
    if ($parent) {
        $p = Get-PnPHubSite -Identity (ConvertTo-MgAbsoluteUrl $parent $TenantUrl) @c
        if ("$(Get-MgProp $hub 'ParentHubSiteId' '')" -ne "$(Get-MgProp $p 'ID' '')") {
            if ($PSCmdlet.ShouldProcess($hubUrl, "Associate with parent hub $parent")) {
                $null = Add-PnPHubToHubAssociation -SourceUrl $hubUrl -TargetUrl (ConvertTo-MgAbsoluteUrl $parent $TenantUrl) @c
            }
            New-MgStep 'HubToHub' $Plan.hub.url "parent: $parent"
        }
    }
}

function Invoke-MgHubAssociation {
    <#
    .SYNOPSIS  Associates the plan's sites with the hub. A site already in another hub is only moved with -Move;
               a site that is itself a hub is never associated this way (use parentHubUrl). -WhatIf.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)][string]$TenantUrl, [switch]$Move, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $hubUrl = ConvertTo-MgAbsoluteUrl $Plan.hub.url $TenantUrl
    $hub = Get-PnPHubSite -Identity $hubUrl @c
    $hubId = "$(Get-MgProp $hub 'ID' '')"
    foreach ($a in @(Get-MgProp $Plan 'associations' @())) {
        $url = ConvertTo-MgAbsoluteUrl $a.url $TenantUrl
        $site = Get-PnPTenantSite -Identity $url @c
        $current = "$(Get-MgProp $site 'HubSiteId' '')"
        if ([bool](Get-MgProp $site 'IsHubSite' $false)) { New-MgStep 'Skip' $a.url 'is a hub site: connect hubs with a hub-to-hub association'; continue }
        if ($current -eq $hubId) { continue }
        if ($current -and $current -ne [guid]::Empty.ToString()) {
            if (-not $Move) { New-MgStep 'Skip' $a.url "already in another hub ($current): use -Move"; continue }
            if ($PSCmdlet.ShouldProcess($url, 'Remove from its current hub')) { $null = Remove-PnPHubSiteAssociation -Site $url @c }
            New-MgStep 'LeaveHub' $a.url $current
        }
        if ($PSCmdlet.ShouldProcess($url, "Associate with $($Plan.hub.url)")) { $null = Add-PnPHubSiteAssociation -Site $url -HubSite $hubUrl @c }
        New-MgStep 'Associate' $a.url $Plan.hub.url
    }
}

function Get-MgLiveNavigation {
    <#
    .SYNOPSIS  Reads a navigation tree (TopNavigationBar by default: on a hub site, that is the hub navigation).
    #>
    [CmdletBinding()]
    param([string]$Location = 'TopNavigationBar', $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    function Read-Node($node) {
        $full = Get-PnPNavigationNode -Id $node.Id @c
        [pscustomobject]@{
            Id = $full.Id; Title = $full.Title; Url = $full.Url
            Audiences = @(Get-MgProp $full 'AudienceIds' @() | Where-Object { $_ } | ForEach-Object { "$_" })
            Children = @(Get-MgProp $full 'Children' @() | Where-Object { $null -ne $_ } | ForEach-Object { Read-Node $_ })
        }
    }
    @(Get-PnPNavigationNode -Location $Location @c | Where-Object { $null -ne $_ } | ForEach-Object { Read-Node $_ })
}

function Invoke-MgNavigationTree {
    <#
    .SYNOPSIS  Makes a navigation location match the plan's tree: no change if it already matches, otherwise the
               top-level nodes are removed (their children go with them) and the tree is added again, in order.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Nodes, [Parameter(Mandatory)][string]$TenantUrl, [string]$SiteUrl,
        [hashtable]$AudienceIds = @{}, [string]$Location = 'TopNavigationBar', [string]$Label = 'navigation', $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $live = @(Get-MgLiveNavigation -Location $Location -Connection $Connection)
    $diff = @(Compare-MgNavigation -PlanNodes $Nodes -LiveNodes $live -AudienceIds $AudienceIds)
    if (-not $diff.Count) { New-MgStep 'NavUpToDate' $Label "$Location matches the plan"; return }
    foreach ($n in $live) {
        if ($PSCmdlet.ShouldProcess("$Location '$($n.Title)'", 'Remove navigation node')) { Remove-PnPNavigationNode -Identity $n.Id -Force @c }
        New-MgStep 'RemoveNode' $n.Title $Location
    }
    $siteKey = if ($SiteUrl) { Get-MgSiteKey $SiteUrl } else { '' }
    function Add-Tree($items, $parentId, [string]$path) {
        foreach ($n in @($items | Where-Object { $null -ne $_ })) {
            $url = "$(Get-MgProp $n 'url' '')"
            $p = @{ Location = $Location; Title = $n.title }
            if ($url) {
                $p.Url = ConvertTo-MgAbsoluteUrl $url $TenantUrl
                if ($siteKey -and (Get-MgSiteKey $url) -ne $siteKey) { $p.External = $true }
            }
            else { $p.Url = $script:LabelUrl }
            if ($null -ne $parentId) { $p.Parent = $parentId }
            $aud = @(Get-MgProp $n 'audiences' @() | Where-Object { $_ } | ForEach-Object { $AudienceIds[$_] } | Where-Object { $_ })
            if ($aud.Count) { $p.AudienceIds = [System.Collections.Generic.List[guid]]::new([guid[]]$aud) }
            $where = if ($path) { "$path > $($n.title)" } else { $n.title }
            $created = $null
            if ($PSCmdlet.ShouldProcess($where, "Add $Location node")) { $created = Add-PnPNavigationNode @p @c }
            $detail = if ($url) { $url } else { '(label)' }
            if ($aud.Count) { $detail += " [targeted: $(@(Get-MgProp $n 'audiences' @()) -join ', ')]" }
            New-MgStep 'AddNode' $where $detail
            $kids = @(Get-MgProp $n 'children' @())
            if ($kids.Count) { Add-Tree $kids $(if ($created) { $created.Id } else { 0 }) $where }
        }
    }
    Add-Tree $Nodes $null ''
}

function Invoke-MgHubNavigation {
    <#
    .SYNOPSIS  Turns on audience targeting and the mega menu as planned, then builds the hub navigation. Needs a
               connection to the hub site (site owner).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)][string]$TenantUrl, [hashtable]$AudienceIds = @{}, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $web = Get-PnPWeb -Includes NavAudienceTargetingEnabled, MegaMenuEnabled @c
    $set = @{}
    $t = [bool](Get-MgProp $Plan.navigation 'audienceTargeting' $false)
    $m = [bool](Get-MgProp $Plan.navigation 'megaMenu' $false)
    if ([bool](Get-MgProp $web 'NavAudienceTargetingEnabled' $false) -ne $t) { $set.NavAudienceTargetingEnabled = [switch]$t }
    if ([bool](Get-MgProp $web 'MegaMenuEnabled' $false) -ne $m) { $set.MegaMenuEnabled = [switch]$m }
    if ($set.Count) {
        if ($PSCmdlet.ShouldProcess($Plan.hub.url, "Set-PnPWeb $($set.Keys -join ', ')")) { Set-PnPWeb @set @c }
        New-MgStep 'SetWeb' $Plan.hub.url (($set.GetEnumerator() | Sort-Object Key | ForEach-Object { "$($_.Key)=$([bool]$_.Value)" }) -join ', ')
    }
    Invoke-MgNavigationTree -Nodes $Plan.navigation.nodes -TenantUrl $TenantUrl -SiteUrl $Plan.hub.url -AudienceIds $AudienceIds -Label 'hub navigation' -Connection $Connection -WhatIf:$WhatIfPreference
}

function Get-MgHubState {
    <#
    .SYNOPSIS  Reads what Test-MgHubLive compares: the hub, its associated sites and all hubs (admin connection),
               the hub navigation and web settings (hub site connection).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)][string]$TenantUrl, $AdminConnection, $SiteConnection)
    $a = @{}; if ($AdminConnection) { $a.Connection = $AdminConnection }
    $s = @{}; if ($SiteConnection) { $s.Connection = $SiteConnection }
    $hubUrl = ConvertTo-MgAbsoluteUrl $Plan.hub.url $TenantUrl
    $hub = try { Get-PnPHubSite -Identity $hubUrl -ErrorAction Stop @a } catch { $null }
    [pscustomobject]@{
        Hub = $hub
        Children = $(if ($hub) { @(Get-PnPHubSiteChild -Identity $hubUrl @a) } else { @() })
        AllHubs = @(Get-PnPHubSite @a)
        Navigation = @(Get-MgLiveNavigation -Connection $SiteConnection)
        Web = Get-PnPWeb -Includes NavAudienceTargetingEnabled, MegaMenuEnabled @s
    }
}

Export-ModuleMember -Function Import-MgJson, ConvertTo-MgAbsoluteUrl, Get-MgNavNodeList, Test-MgNavigation, Test-MgHubPlan,
    Test-MgHubHierarchy, Compare-MgNavigation, Test-MgHubLive, Resolve-MgAudience, Invoke-MgHubRegistration,
    Invoke-MgHubAssociation, Get-MgLiveNavigation, Invoke-MgNavigationTree, Invoke-MgHubNavigation, Get-MgHubState
