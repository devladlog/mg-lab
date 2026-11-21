# Contoso intranet: provision and check the hub, the departments, the navigation and the Viva Connections home site
# with PnP.PowerShell. State-changing steps are idempotent and honour -WhatIf. The caller connects (see
# Initialize-Intranet.ps1); this module never signs in and never stores a credential.
# Connections: Set-/Get-PnPHomeSite, hub and site-design cmdlets need the SharePoint ADMIN site; hub navigation is
# written on the hub site itself, so a second connection to the hub is passed in as a script block.

Set-StrictMode -Version Latest

$script:Verbs = @(
    'addContentTypesFromHub', 'createSPList', 'createSiteColumn', 'createSiteColumnXml', 'createContentType', 'addNavLink', 'removeNavLink',
    'applyTheme', 'setSiteBranding', 'setSiteLogo', 'joinHubSite', 'installSolution', 'associateExtension', 'activateSPFeature',
    'triggerFlow', 'setRegionalSettings', 'addPrincipalToSPGroup', 'setSiteExternalSharingCapability', 'enableApprovals'
)
$script:ListSubVerbs = @(
    'setDescription', 'addSPField', 'deleteSPField', 'addSPFieldXml', 'addSPLookupFieldXml', 'addSiteColumn', 'addSPView', 'removeSPView',
    'addContentType', 'removeContentType', 'setSPFieldCustomFormatter', 'associateFieldCustomizer', 'associateListViewCommandSet', 'setTitle'
)

function Read-IntranetContract {
    param([Parameter(Mandatory)] [string] $Path)
    Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json -Depth 20
}

function Test-IntranetContract {
    <# Returns a list of problems; empty means the contract is usable. #>
    param([Parameter(Mandatory)] $Contract)
    $problems = [System.Collections.Generic.List[string]]::new()
    $aliasRule = '^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$'
    $aliases = @($Contract.hub.alias) + @($Contract.spokes | ForEach-Object { $_.alias })
    foreach ($a in $aliases) { if ($a -cnotmatch $aliasRule) { $problems.Add("Alias '$a' must be 3-40 lower-case letters, digits or hyphens.") } }
    $dupes = $aliases | Group-Object | Where-Object Count -gt 1
    foreach ($d in $dupes) { $problems.Add("Alias '$($d.Name)' is used twice.") }
    if (@($Contract.spokes).Count -lt 1) { $problems.Add('At least one department site is required.') }
    if ($Contract.homeSite.alias -ne $Contract.hub.alias) { $problems.Add('The home site must be the hub (one landing page, one navigation).') }
    foreach ($n in $Contract.hubNavigation) {
        $hasSite = $null -ne $n.PSObject.Properties['site']; $hasUrl = $null -ne $n.PSObject.Properties['url']
        if ($hasSite -eq $hasUrl) { $problems.Add("Navigation node '$($n.title)' needs either 'site' or 'url'.") }
        elseif ($hasSite -and $n.site -notin ($Contract.spokes | ForEach-Object { $_.alias })) { $problems.Add("Navigation node '$($n.title)' points at unknown site '$($n.site)'.") }
        elseif ($hasUrl -and $n.url -notmatch '^https://') { $problems.Add("Navigation node '$($n.title)' must use https.") }
    }
    foreach ($s in $Contract.spokes) {
        if (-not ($Contract.hubNavigation | Where-Object { $null -ne $_.PSObject.Properties['site'] -and $_.site -eq $s.alias })) { $problems.Add("Department '$($s.alias)' is not in the hub navigation.") }
    }
    if ($Contract.hubNavigation.Count -gt 100) { $problems.Add('More than 100 hub navigation links: Learn recommends staying at or under 100.') }
    ,$problems.ToArray()
}

function Get-IntranetSiteUrl {
    param([Parameter(Mandatory)] [string] $TenantName, [Parameter(Mandatory)] [string] $Alias)
    "https://$TenantName.sharepoint.com/sites/$Alias"
}

function ConvertTo-SiteUrl {
    <# Cmdlets differ in what they return (URL strings or objects): accept both, compare without case or trailing slash. #>
    param($Item)
    if ($null -eq $Item) { return $null }
    $u = if ($Item -is [string]) { $Item } else { foreach ($p in 'SiteUrl', 'Url', 'HubSiteUrl') { if ($Item.PSObject.Properties[$p]) { $Item.$p; break } } }
    if ($u) { $u.TrimEnd('/').ToLowerInvariant() }
}

function Test-IntranetSiteVerbs {
    <# Checks a site script against the verbs Learn lists, and refuses tenant-specific ids. Returns problems. #>
    param([Parameter(Mandatory)] [string] $Path)
    $problems = [System.Collections.Generic.List[string]]::new()
    $script = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json -Depth 30
    if (-not $script.actions) { $problems.Add('The script has no actions.') }
    foreach ($a in $script.actions) {
        if ($a.verb -notin $script:Verbs) { $problems.Add("Unknown verb '$($a.verb)'.") }
        if ($a.verb -eq 'joinHubSite') { $problems.Add('joinHubSite carries a tenant-specific hubSiteId: associate sites with Add-PnPHubSiteAssociation instead.') }
        if ($a.verb -eq 'createSPList') {
            foreach ($s in $a.subactions) { if ($s.verb -notin $script:ListSubVerbs) { $problems.Add("Unknown list subaction '$($s.verb)'.") } }
            if (-not $a.listName) { $problems.Add('createSPList needs listName.') }
        }
        if ($a.verb -eq 'setSiteExternalSharingCapability' -and $a.capability -notin 'Disabled', 'ExistingExternalUserSharingOnly', 'ExternalUserSharingOnly', 'ExternalUserAndGuestSharing') { $problems.Add("Bad capability '$($a.capability)'.") }
        if ($a.verb -eq 'setSiteBranding') {
            if ($a.navigationLayout -notin 'Cascade', 'Megamenu') { $problems.Add("Bad navigationLayout '$($a.navigationLayout)'.") }
            if ($a.headerLayout -notin 'Standard', 'Compact') { $problems.Add("Bad headerLayout '$($a.headerLayout)'.") }
            if ($a.headerBackground -notin 'None', 'Neutral', 'Soft', 'Strong') { $problems.Add("Bad headerBackground '$($a.headerBackground)'.") }
        }
    }
    ,$problems.ToArray()
}

function Publish-IntranetSiteDesign {
    <# Site script + site design, created or updated by title. Returns the site design id. #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] $Contract,
        [Parameter(Mandatory)] [string] $ScriptPath,
        $Connection
    )
    $d = $Contract.siteDesign
    $content = Get-Content -LiteralPath $ScriptPath -Raw -Encoding UTF8
    $conn = @{}; if ($Connection) { $conn.Connection = $Connection }

    $script = Get-PnPSiteScript @conn | Where-Object Title -eq $d.scriptTitle | Select-Object -First 1
    if (-not $script) {
        if (-not $PSCmdlet.ShouldProcess($d.scriptTitle, 'Create site script')) { return [pscustomobject]@{ Step = 'SiteScript'; Target = $d.scriptTitle; Action = 'WhatIf'; Id = $null } }
        $script = Add-PnPSiteScript @conn -Title $d.scriptTitle -Description $d.description -Content $content
        $scriptAction = 'Created'
    }
    else {
        if ($PSCmdlet.ShouldProcess($d.scriptTitle, 'Update site script')) { Set-PnPSiteScript @conn -Identity $script.Id -Content $content | Out-Null }
        $scriptAction = 'Updated'
    }
    [pscustomobject]@{ Step = 'SiteScript'; Target = $d.scriptTitle; Action = $scriptAction; Id = $script.Id }

    $design = Get-PnPSiteDesign @conn | Where-Object Title -eq $d.title | Select-Object -First 1
    if (-not $design) {
        if (-not $PSCmdlet.ShouldProcess($d.title, 'Create site design')) { return }
        $design = Add-PnPSiteDesign @conn -Title $d.title -Description $d.description -SiteScriptIds $script.Id -WebTemplate CommunicationSite
        $designAction = 'Created'
    }
    else {
        if ($PSCmdlet.ShouldProcess($d.title, 'Update site design')) { Set-PnPSiteDesign @conn -Identity $design.Id -SiteScriptIds $script.Id | Out-Null }
        $designAction = 'Updated'
    }
    [pscustomobject]@{ Step = 'SiteDesign'; Target = $d.title; Action = $designAction; Id = $design.Id }
}

function Invoke-IntranetProvisioning {
    <#
    .SYNOPSIS  Creates (or completes) the hub, the department sites, the hub navigation and the home site.
    .PARAMETER AdminConnection  PnP connection to https://<tenant>-admin.sharepoint.com
    .PARAMETER ConnectHub       Script block that takes a site URL and returns a PnP connection to it (for the hub navigation).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] $Contract,
        [Parameter(Mandatory)] [string] $ScriptPath,
        [Parameter(Mandatory)] $AdminConnection,
        [Parameter(Mandatory)] [scriptblock] $ConnectHub,
        [string] $TenantName = $Contract.tenantName
    )
    $problems = Test-IntranetContract -Contract $Contract
    if ($problems.Count) { throw "Contract is not valid: $($problems -join ' ')" }
    $siteProblems = Test-IntranetSiteVerbs -Path $ScriptPath
    if ($siteProblems.Count) { throw "Site script is not valid: $($siteProblems -join ' ')" }

    $conn = @{ Connection = $AdminConnection }
    $hubUrl = Get-IntranetSiteUrl -TenantName $TenantName -Alias $Contract.hub.alias

    # 1. Site script and design (new sites pick the design up; existing ones can be re-run with Invoke-PnPSiteDesign)
    $design = Publish-IntranetSiteDesign -Contract $Contract -ScriptPath $ScriptPath -Connection $AdminConnection -WhatIf:$WhatIfPreference
    $design
    $designId = ($design | Where-Object Step -eq 'SiteDesign' | Select-Object -First 1)?.Id

    # 2. Sites: hub first, then the departments
    $all = @([pscustomobject]@{ Alias = $Contract.hub.alias; Title = $Contract.hub.title; Description = $Contract.hub.description }) +
           @($Contract.spokes | ForEach-Object { [pscustomobject]@{ Alias = $_.alias; Title = $_.title; Description = $_.description } })
    foreach ($s in $all) {
        $url = Get-IntranetSiteUrl -TenantName $TenantName -Alias $s.Alias
        $exists = $null -ne (Get-PnPTenantSite @conn -Identity $url -ErrorAction SilentlyContinue)
        if ($exists) { [pscustomobject]@{ Step = 'Site'; Target = $url; Action = 'Exists' }; continue }
        if ($PSCmdlet.ShouldProcess($url, 'Create communication site')) {
            $new = @{ Type = 'CommunicationSite'; Title = $s.Title; Url = $url; Description = $s.Description; Wait = $true; Connection = $AdminConnection }
            if ($designId) { $new.SiteDesignId = $designId }
            New-PnPSite @new | Out-Null
            [pscustomobject]@{ Step = 'Site'; Target = $url; Action = 'Created' }
        }
        else { [pscustomobject]@{ Step = 'Site'; Target = $url; Action = 'WhatIf' } }
    }

    # 3. Hub
    $hub = Get-PnPHubSite @conn -Identity $hubUrl -ErrorAction SilentlyContinue
    if ($hub) { [pscustomobject]@{ Step = 'Hub'; Target = $hubUrl; Action = 'Exists' } }
    elseif ($PSCmdlet.ShouldProcess($hubUrl, 'Register as hub site')) {
        Register-PnPHubSite @conn -Site $hubUrl | Out-Null
        [pscustomobject]@{ Step = 'Hub'; Target = $hubUrl; Action = 'Registered' }
    }
    else { [pscustomobject]@{ Step = 'Hub'; Target = $hubUrl; Action = 'WhatIf' } }
    if ($PSCmdlet.ShouldProcess($hubUrl, 'Set hub title and description')) {
        Set-PnPHubSite @conn -Identity $hubUrl -Title $Contract.hub.title -Description $Contract.hub.description | Out-Null
    }

    # 4. Associate the departments
    $children = @(Get-PnPHubSiteChild @conn -Identity $hubUrl -ErrorAction SilentlyContinue | ForEach-Object { ConvertTo-SiteUrl $_ })
    foreach ($sp in $Contract.spokes) {
        $url = Get-IntranetSiteUrl -TenantName $TenantName -Alias $sp.alias
        if ($children -contains (ConvertTo-SiteUrl $url)) { [pscustomobject]@{ Step = 'Association'; Target = $url; Action = 'Exists' }; continue }
        if ($PSCmdlet.ShouldProcess($url, "Associate with hub $hubUrl")) {
            Add-PnPHubSiteAssociation @conn -Site $url -HubSite $hubUrl | Out-Null
            [pscustomobject]@{ Step = 'Association'; Target = $url; Action = 'Associated' }
        }
        else { [pscustomobject]@{ Step = 'Association'; Target = $url; Action = 'WhatIf' } }
    }

    # 5. Hub navigation (top navigation bar of the hub site itself)
    $hubConn = & $ConnectHub $hubUrl
    $existing = @(Get-PnPNavigationNode -Connection $hubConn -Location TopNavigationBar | ForEach-Object { $_.Title })
    foreach ($n in $Contract.hubNavigation) {
        if ($existing -contains $n.title) { [pscustomobject]@{ Step = 'HubNavigation'; Target = $n.title; Action = 'Exists' }; continue }
        $target = if ($null -ne $n.PSObject.Properties['site']) { Get-IntranetSiteUrl -TenantName $TenantName -Alias $n.site } else { $n.url }
        if ($PSCmdlet.ShouldProcess($n.title, "Add hub navigation link to $target")) {
            $args2 = @{ Connection = $hubConn; Location = 'TopNavigationBar'; Title = $n.title; Url = $target }
            if ($null -ne $n.PSObject.Properties['external'] -and $n.external) { $args2.External = $true }
            Add-PnPNavigationNode @args2 | Out-Null
            [pscustomobject]@{ Step = 'HubNavigation'; Target = $n.title; Action = 'Added' }
        }
        else { [pscustomobject]@{ Step = 'HubNavigation'; Target = $n.title; Action = 'WhatIf' } }
    }

    # 6. Home site (Viva Connections landing page)
    $homeUrl = Get-IntranetSiteUrl -TenantName $TenantName -Alias $Contract.homeSite.alias
    $currentHome = ConvertTo-SiteUrl (Get-PnPHomeSite @conn -ErrorAction SilentlyContinue)
    if ($currentHome -eq (ConvertTo-SiteUrl $homeUrl)) { [pscustomobject]@{ Step = 'HomeSite'; Target = $homeUrl; Action = 'Exists' } }
    elseif ($PSCmdlet.ShouldProcess($homeUrl, 'Set as home site')) {
        Set-PnPHomeSite @conn -HomeSiteUrl $homeUrl -VivaConnectionsDefaultStart:([bool]$Contract.homeSite.vivaConnectionsDefaultStart) -DraftMode:([bool]$Contract.homeSite.draftMode) -Force
        [pscustomobject]@{ Step = 'HomeSite'; Target = $homeUrl; Action = 'Set' }
    }
    else { [pscustomobject]@{ Step = 'HomeSite'; Target = $homeUrl; Action = 'WhatIf' } }
}

function Test-IntranetHealth {
    <# Read-only. One row per check: Pass or Fail with the reason. Use the exit code in a pipeline. #>
    param(
        [Parameter(Mandatory)] $Contract,
        [Parameter(Mandatory)] $AdminConnection,
        [Parameter(Mandatory)] [scriptblock] $ConnectHub,
        [string] $TenantName = $Contract.tenantName
    )
    $conn = @{ Connection = $AdminConnection }
    $rows = [System.Collections.Generic.List[object]]::new()
    function Add-Row($check, $target, $ok, $detail) { $rows.Add([pscustomobject]@{ Check = $check; Target = $target; Status = $(if ($ok) { 'Pass' } else { 'Fail' }); Detail = $detail }) }

    $hubUrl = Get-IntranetSiteUrl -TenantName $TenantName -Alias $Contract.hub.alias
    $hub = Get-PnPHubSite @conn -Identity $hubUrl -ErrorAction SilentlyContinue
    Add-Row 'Hub registered' $hubUrl ([bool]$hub) $(if ($hub) { '' } else { 'Not a hub site (or does not exist yet: hub changes can take hours to show).' })

    $homeNow = ConvertTo-SiteUrl (Get-PnPHomeSite @conn -ErrorAction SilentlyContinue)
    Add-Row 'Home site is the hub' $hubUrl ($homeNow -eq (ConvertTo-SiteUrl $hubUrl)) "Home site is '$homeNow'."

    $children = @(Get-PnPHubSiteChild @conn -Identity $hubUrl -ErrorAction SilentlyContinue | ForEach-Object { ConvertTo-SiteUrl $_ })
    foreach ($s in $Contract.spokes) {
        $u = Get-IntranetSiteUrl -TenantName $TenantName -Alias $s.alias
        Add-Row 'Department in hub' $u ($children -contains (ConvertTo-SiteUrl $u)) ''
    }
    $unexpected = $children | Where-Object { $_ -notin @($Contract.spokes | ForEach-Object { ConvertTo-SiteUrl (Get-IntranetSiteUrl -TenantName $TenantName -Alias $_.alias) }) }
    Add-Row 'No unknown sites in the hub' $hubUrl (@($unexpected).Count -eq 0) $(if (@($unexpected).Count) { "Unexpected: $(@($unexpected) -join ', ')" } else { '' })

    $nodes = @(Get-PnPNavigationNode -Connection (& $ConnectHub $hubUrl) -Location TopNavigationBar)
    foreach ($n in $Contract.hubNavigation) {
        $want = if ($null -ne $n.PSObject.Properties['site']) { Get-IntranetSiteUrl -TenantName $TenantName -Alias $n.site } else { $n.url }
        $node = $nodes | Where-Object Title -eq $n.title | Select-Object -First 1
        $ok = $node -and ((ConvertTo-SiteUrl $node.Url) -eq (ConvertTo-SiteUrl $want))
        Add-Row 'Hub navigation link' $n.title ([bool]$ok) $(if (-not $node) { 'Missing.' } elseif (-not $ok) { "Points at '$($node.Url)'." } else { '' })
    }

    $design = Get-PnPSiteDesign @conn | Where-Object Title -eq $Contract.siteDesign.title | Select-Object -First 1
    Add-Row 'Site design published' $Contract.siteDesign.title ([bool]$design) ''
    $rows.ToArray()
}

Export-ModuleMember -Function Read-IntranetContract, Test-IntranetContract, Get-IntranetSiteUrl, Test-IntranetSiteVerbs, Publish-IntranetSiteDesign, Invoke-IntranetProvisioning, Test-IntranetHealth
