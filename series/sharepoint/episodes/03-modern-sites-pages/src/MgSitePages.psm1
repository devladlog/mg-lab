#Requires -Version 7.2
<#
.SYNOPSIS
    Modern sites and pages as code: lint a site template (site scripts) and page designs against what Microsoft
    Learn documents, register the template and apply it with PnP PowerShell, provision the pages, and read back
    what the template run actually did.

    Pure functions (no SharePoint needed): Import-MgJson, Get-MgSiteScriptAction, Test-MgSiteScript,
    Test-MgPageDesign, Test-MgSiteTemplate, ConvertTo-MgWebTemplateId, Resolve-MgPageToken.
    Tenant functions (PnP.PowerShell, after Connect-PnPOnline): Invoke-MgSiteTemplateRegistration,
    Invoke-MgSiteTemplateApply, Get-MgSiteTemplateRunReport, Invoke-MgPageProvisioning, Export-MgSiteScript.
#>

Set-StrictMode -Version Latest

# ---- What Learn documents (see README "References") -------------------------------------------------------------
#   300 actions or 100,000 characters per site script when applied asynchronously (UI, Add-SPOSiteDesignTask);
#   30 when applied synchronously with Invoke-SPOSiteDesign. 100 site scripts and 100 site templates per tenant.
#   WebTemplate 64 = team site, 1 = team site without a group, 68 = communication site, 69 = channel site.
$script:Limits = [ordered]@{
    MaxActionsAsync  = 300
    MaxActionsSync   = 30
    MaxCharacters    = 100000
    MaxScriptsTenant = 100
    MaxDesignsTenant = 100
    # Page Diagnostics for SharePoint baselines
    IframeAttention  = 3     # 3 or more web parts using iframes: "Attention required"
    MaxSearchRequests = 3    # modern pages: no more than 3 search requests
}

$script:WebTemplates = @{ TeamSite = 64; GrouplessTeamSite = 1; CommunicationSite = 68; ChannelSite = 69 }

# Top-level verbs and subaction verbs: the site template JSON schema page plus Microsoft's published schema
# (the schema also has deactivateSPFeature, setSiteLogoFromFile, setFooterLogo, addFile, addFolder, ...).
$script:TopVerbs = @(
    'activateSPFeature', 'addContentTypesFromHub', 'addNavLink', 'addPrincipalToSPGroup', 'applyTheme',
    'associateExtension', 'createContentType', 'createSiteColumn', 'createSiteColumnXml', 'createSPList',
    'deactivateSPFeature', 'installSolution', 'joinHubSite', 'removeNavLink', 'setFooterLogo', 'setRegionalSettings',
    'setSiteBranding', 'setSiteExternalSharingCapability', 'setSiteLogo', 'setSiteLogoFromFile', 'triggerFlow')
$script:ListVerbs = @(
    'addContentType', 'addFile', 'addFolder', 'addSiteColumn', 'addSPField', 'addSPFieldXml', 'addSPLookupFieldXml',
    'addSPView', 'associateFieldCustomizer', 'associateListViewCommandSet', 'deleteSPField', 'enableApprovals',
    'removeContentType', 'removeSiteColumn', 'removeSPView', 'setClientFormCustomFormatter', 'setDescription',
    'setDocumentTemplates', 'setSPFieldCustomFormatter', 'setTitle')
$script:ContentTypeVerbs = @('addSiteColumn', 'removeSiteColumn')

# createSPList templateType values Learn lists as supported.
$script:ListTemplates = @(100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 119, 1100)

# Actions Learn marks as automatically blocked for channel sites (template 69).
$script:ChannelBlocked = @('applyTheme', 'setSiteBranding', 'addNavLink', 'setRegionalSettings', 'addPrincipalToSPGroup',
    'setSiteExternalSharingCapability', 'joinHubSite')

# Content types that exist on team and communication sites without a script creating them.
$script:DefaultContentTypes = @('Item', 'Document', 'Folder', 'Event', 'Link', 'Announcement', 'Contact', 'Task', 'Site Page')

# ---- Page vocabulary (PnP.PowerShell 3.x enums: CanvasSectionTemplate, DefaultWebPart, PageLayoutType) ------------
$script:SectionColumns = [ordered]@{
    OneColumn = 1; OneColumnFullWidth = 1; TwoColumn = 2; ThreeColumn = 3; TwoColumnLeft = 2; TwoColumnRight = 2
    OneColumnVerticalSection = 2; TwoColumnVerticalSection = 3; ThreeColumnVerticalSection = 4
    TwoColumnLeftVerticalSection = 3; TwoColumnRightVerticalSection = 3
}
$script:WebParts = @(
    'ThirdParty', 'ContentRollup', 'BingMap', 'ContentEmbed', 'DocumentEmbed', 'Image', 'ImageGallery', 'LinkPreview',
    'NewsFeed', 'NewsReel', 'News', 'PowerBIReportEmbed', 'QuickChart', 'SiteActivity', 'VideoEmbed', 'YammerEmbed',
    'Events', 'GroupCalendar', 'Hero', 'List', 'PageTitle', 'People', 'QuickLinks', 'CustomMessageRegion', 'Divider',
    'MicrosoftForms', 'Spacer', 'ClientWebPart', 'PowerApps', 'CodeSnippet', 'PageFields', 'Weather', 'YouTube',
    'MyDocuments', 'YammerFullFeed', 'CountDown', 'ListProperties', 'MarkDown', 'Planner', 'Sites', 'CallToAction',
    'Button', 'Kindle', 'MyFeed', 'OrgChart', 'SavedForLater', 'Twitter', 'WorldClock')
$script:PageLayouts = @('Article', 'Home', 'SingleWebPartAppPage', 'RepostPage', 'HeaderlessSearchResults', 'Spaces', 'Dashboard', 'NewsDigest')
# Web parts that render an iframe: Embed, and File viewer (Learn's iframe guidance names embedded Office files).
$script:IframeWebParts = @('ContentEmbed', 'DocumentEmbed')
# Web parts Learn names as search-driven (group-level caching is offered for exactly these two).
$script:SearchWebParts = @('Events', 'ContentRollup')

function Get-MgLimits { [CmdletBinding()] param() [pscustomobject]$script:Limits }

function Import-MgJson {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json -Depth 30
}

function Get-MgProp($Object, [string]$Name, $Default = $null) {
    if ($null -ne $Object -and $Object.PSObject.Properties[$Name]) { $Object.$Name } else { $Default }
}

function New-MgFinding([string]$Rule, [string]$Severity, [string]$Target, [string]$Message) {
    [pscustomobject]@{ Rule = $Rule; Severity = $Severity; Target = $Target; Message = $Message }
}

function ConvertTo-MgWebTemplateId {
    <# .SYNOPSIS 'CommunicationSite' or '68' -> 68. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$WebTemplate)
    $s = "$WebTemplate"
    if ($script:WebTemplates.ContainsKey($s)) { return $script:WebTemplates[$s] }
    $n = 0
    if ([int]::TryParse($s, [ref]$n) -and $n -in $script:WebTemplates.Values) { return $n }
    throw "Unknown web template '$s'. Use TeamSite (64), GrouplessTeamSite (1), CommunicationSite (68) or ChannelSite (69)."
}

function Get-MgSiteScriptAction {
    <#
    .SYNOPSIS  Flattens a site script into one object per verb (actions and subactions), with a readable path.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Script)
    $i = 0
    foreach ($a in @(Get-MgProp $Script 'actions' @())) {
        $i++
        $verb = Get-MgProp $a 'verb' ''
        $label = foreach ($p in 'listName', 'name', 'displayName', 'themeName') { $v = Get-MgProp $a $p; if ($v) { $v; break } }
        $path = if ($label) { "#$i $verb '$label'" } else { "#$i $verb" }
        [pscustomobject]@{ Verb = $verb; Context = 'site'; Parent = $null; Action = $a; Path = $path }
        $context = switch ($verb) { 'createSPList' { 'list' } 'createContentType' { 'contentType' } default { $null } }
        $j = 0
        foreach ($s in @(Get-MgProp $a 'subactions' @())) {
            $j++
            $sv = Get-MgProp $s 'verb' ''
            [pscustomobject]@{ Verb = $sv; Context = $(if ($context) { $context } else { 'unknown' }); Parent = $a; Action = $s; Path = "$path / $j $sv" }
        }
    }
}

function Test-MgGuid([string]$Value) {
    $g = [guid]::Empty
    [guid]::TryParse(($Value -replace '^\{|\}$', ''), [ref]$g)
}

function Test-MgSiteScript {
    <#
    .SYNOPSIS  Lints one site script. Returns one object per finding.
    .PARAMETER Script      The parsed JSON (Import-MgJson).
    .PARAMETER Raw         The JSON text, for the character limit. Defaults to the re-serialised script.
    .PARAMETER WebTemplate The site template type the script is registered for (64, 1, 68, 69 or the PnP name).
    .PARAMETER SchemaPath  Optional: Microsoft's site script JSON schema; every schema error becomes an SS000 finding.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Script,
        [string]$Raw,
        $WebTemplate = 68,
        [string]$SchemaPath
    )
    $L = $script:Limits
    $wt = ConvertTo-MgWebTemplateId $WebTemplate
    if (-not $Raw) { $Raw = $Script | ConvertTo-Json -Depth 30 }

    if ($SchemaPath) {
        # The schema is one big anyOf, so a single bad action produces dozens of errors. Validate action by action
        # and keep one finding per action, with the most specific messages (a property path, not the verb).
        if (-not (Test-Json -Json $Raw -SchemaFile $SchemaPath -ErrorAction SilentlyContinue)) {
            $schema = Get-Content -LiteralPath $SchemaPath -Raw | ConvertFrom-Json -AsHashtable -Depth 50
            $i = 0
            foreach ($a in @(Get-MgProp $Script 'actions' @())) {
                $i++
                $verb = Get-MgProp $a 'verb' ''
                if (-not $schema.definitions.ContainsKey($verb)) {
                    New-MgFinding 'SS000' 'Error' "#$i $verb" "Doesn't validate against Microsoft's schema: '$verb' isn't one of its actions."
                    continue
                }
                # Validate the action against its own definition only, so the messages are about this verb.
                $schema.properties.actions.items = @{ '$ref' = "#/definitions/$verb" }
                $errs = $null
                $ok = Test-Json -Json (@{ actions = @($a) } | ConvertTo-Json -Depth 30) -Schema ($schema | ConvertTo-Json -Depth 50) `
                    -ErrorVariable errs -ErrorAction SilentlyContinue
                if ($ok) { continue }
                $msgs = @($errs | ForEach-Object { $_.Exception.Message -replace '^The JSON is not valid with the schema: ', '' -replace '/actions/0', '' } |
                        Select-Object -Unique -First 2)
                New-MgFinding 'SS000' 'Error' "#$i $verb" "Doesn't validate against Microsoft's schema: $($msgs -join '; ')."
            }
        }
    }

    $all = @(Get-MgSiteScriptAction -Script $Script)
    if ($all.Count -gt $L.MaxActionsAsync) {
        New-MgFinding 'SS002' 'Error' 'script' "$($all.Count) actions (counting subactions); a site script may have up to $($L.MaxActionsAsync). Split it into several scripts."
    }
    elseif ($all.Count -gt $L.MaxActionsSync) {
        New-MgFinding 'SS003' 'Warning' 'script' "$($all.Count) actions (counting subactions): too many for a synchronous Invoke-SPOSiteDesign (limit $($L.MaxActionsSync)). Apply it asynchronously (Add-SPOSiteDesignTask / Add-PnPSiteDesignTask)."
    }
    if ($Raw.Length -gt $L.MaxCharacters) {
        New-MgFinding 'SS002' 'Error' 'script' "$($Raw.Length) characters; a site script may have up to $($L.MaxCharacters)."
    }

    # Names this script creates, for the reference checks
    $siteColumns = @{}; $contentTypes = @{}
    foreach ($a in $all) {
        switch ($a.Verb) {
            'createSiteColumn' { $siteColumns[(Get-MgProp $a.Action 'internalName' '')] = $true }
            'createSiteColumnXml' {
                $x = Get-MgProp $a.Action 'schemaXml' ''
                if ($x -match '\bName="([^"]+)"') { $siteColumns[$Matches[1]] = $true }
            }
            'createContentType' { $contentTypes[(Get-MgProp $a.Action 'name' '')] = $true }
        }
    }
    $hubContentTypes = @($all | Where-Object Verb -eq 'addContentTypesFromHub').Count -gt 0

    foreach ($a in $all) {
        $act = $a.Action; $t = $a.Path
        # SS001: only documented verbs, in the right place
        $allowed = switch ($a.Context) { 'site' { $script:TopVerbs } 'list' { $script:ListVerbs } 'contentType' { $script:ContentTypeVerbs } default { @() } }
        if ($a.Context -eq 'unknown') {
            New-MgFinding 'SS001' 'Error' $t "Subactions are only valid under createSPList or createContentType."
            continue
        }
        if ($a.Verb -cnotin $allowed) {
            $where = @{ site = 'a top-level action'; list = 'a createSPList subaction'; contentType = 'a createContentType subaction' }[$a.Context]
            New-MgFinding 'SS001' 'Error' $t "'$($a.Verb)' isn't $where. Unknown verbs fail the upload with 'unable to handle action'."
            continue
        }

        switch ($a.Verb) {
            { $_ -in 'addSPField', 'createSiteColumn' } {
                if (-not (Get-MgProp $act 'id')) {
                    New-MgFinding 'SS004' 'Warning' $t "No 'id': re-applying the template can add the field again. Give every field a random GUID."
                }
            }
            { $_ -in 'addSPFieldXml', 'addSPLookupFieldXml', 'createSiteColumnXml' } {
                if ((Get-MgProp $act 'schemaXml' '') -notmatch '\bID="\{?[0-9a-fA-F-]{36}\}?"') {
                    New-MgFinding 'SS004' 'Warning' $t "Field XML without an ID attribute: re-applying the template can create the field again."
                }
            }
            'setTitle' {
                New-MgFinding 'SS005' 'Error' $t "setTitle inside createSPList renames the list, so re-applying the template can no longer update it. Use listName; rename in a separate script."
            }
            'createSPList' {
                $tt = Get-MgProp $act 'templateType'
                if ($null -ne $tt -and [int]$tt -notin $script:ListTemplates) {
                    New-MgFinding 'SS006' 'Error' $t "templateType $tt isn't one of the supported values ($($script:ListTemplates -join ', '))."
                }
            }
            'setSiteLogo' {
                if ($wt -ne 68) { New-MgFinding 'SS007' 'Error' $t "setSiteLogo only works on the communication site template (68); this template is $wt." }
            }
            'setSiteBranding' {
                if ($wt -ne 68 -and (Get-MgProp $act 'navigationLayout')) {
                    New-MgFinding 'SS007' 'Warning' $t "navigationLayout only works on communication sites (and hub navigation); this template is $wt."
                }
            }
            'addSiteColumn' {
                $n = Get-MgProp $act 'internalName' ''
                if (-not $siteColumns.ContainsKey($n)) {
                    New-MgFinding 'SS008' 'Warning' $t "Site column '$n' isn't created by this script; it must already exist on the site or the action fails."
                }
            }
            'addContentType' {
                $n = Get-MgProp $act 'name' ''
                if (-not $contentTypes.ContainsKey($n) -and $n -notin $script:DefaultContentTypes -and -not $hubContentTypes) {
                    New-MgFinding 'SS008' 'Warning' $t "Content type '$n' isn't created by this script, isn't a default one, and nothing is synced from the content type hub."
                }
            }
            'joinHubSite' { Test-MgGuidProperty $act 'hubSiteId' $t }
            'installSolution' { Test-MgGuidProperty $act 'id' $t }
            { $_ -in 'activateSPFeature', 'deactivateSPFeature' } { Test-MgGuidProperty $act 'featureId' $t }
            'setRegionalSettings' {
                $lcid = Get-MgProp $act 'locale'
                if ($null -ne $lcid) {
                    $valid = $true
                    try { $null = [cultureinfo]::GetCultureInfo([int]$lcid) } catch { $valid = $false }
                    if (-not $valid) { New-MgFinding 'SS010' 'Error' $t "locale $lcid isn't a valid culture LCID (e.g. 2070 = pt-PT, 2057 = en-GB, 1033 = en-US)." }
                }
            }
        }

        if ($wt -eq 69 -and $a.Context -eq 'site' -and $a.Verb -in $script:ChannelBlocked) {
            New-MgFinding 'SS011' 'Error' $t "'$($a.Verb)' is automatically blocked for channel sites (template 69)."
        }
    }
}

function Test-MgGuidProperty($Action, [string]$Name, [string]$Target) {
    $v = Get-MgProp $Action $Name ''
    if (-not (Test-MgGuid $v)) {
        New-MgFinding 'SS009' 'Error' $Target "'$Name' must be a GUID; got '$v'."
    }
    elseif ([guid]($v -replace '^\{|\}$', '') -eq [guid]::Empty) {
        New-MgFinding 'SS009' 'Warning' $Target "'$Name' is the empty GUID: a placeholder that was never replaced."
    }
}

function Test-MgPageDesign {
    <#
    .SYNOPSIS  Lints one page design. Returns one object per finding.
    .PARAMETER SiteType 'Communication' or 'Team' (full-width sections exist only on communication sites).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Page,
        [ValidateSet('Communication', 'Team')][string]$SiteType = 'Communication'
    )
    $L = $script:Limits
    $name = Get-MgProp $Page 'name' ''
    $p = "page '$name'"

    if ($name -notmatch '^[a-z0-9]+(-[a-z0-9]+)*$') {
        New-MgFinding 'PG007' 'Warning' $p "Page name '$name' becomes the file name and the URL. Use lowercase words and hyphens (no spaces, no symbols, no .aspx)."
    }
    $layout = Get-MgProp $Page 'layout' 'Article'
    if ($layout -notin $script:PageLayouts) {
        New-MgFinding 'PG001' 'Error' $p "Layout '$layout' isn't a page layout type ($($script:PageLayouts -join ', '))."
    }

    $iframes = 0; $search = 0; $s = 0
    foreach ($section in @(Get-MgProp $Page 'sections' @())) {
        $s++
        $tpl = Get-MgProp $section 'template' ''
        $st = "$p / section $s ($tpl)"
        $controls = @(Get-MgProp $section 'controls' @())
        $cols = $null
        if (-not $script:SectionColumns.Contains($tpl)) {
            New-MgFinding 'PG001' 'Error' $st "Section template '$tpl' doesn't exist. Use one of: $($script:SectionColumns.Keys -join ', ')."
        }
        else { $cols = $script:SectionColumns[$tpl] }
        if ($tpl -eq 'OneColumnFullWidth' -and $SiteType -ne 'Communication') {
            New-MgFinding 'PG003' 'Error' $st 'The full-width column exists only on communication sites.'
        }
        if ($controls.Count -eq 0) {
            New-MgFinding 'PG008' 'Warning' $st 'Empty section: it renders as blank space.'
        }
        foreach ($c in $controls) {
            $col = [int](Get-MgProp $c 'column' 1)
            $kind = Get-MgProp $c 'type' 'WebPart'
            $wp = Get-MgProp $c 'webPart' ''
            $ct = if ($kind -eq 'Text') { "$st / Text" } else { "$st / $wp" }
            if ($null -ne $cols -and ($col -lt 1 -or $col -gt $cols)) {
                New-MgFinding 'PG002' 'Error' $ct "Column $col doesn't exist: '$tpl' has $cols."
            }
            if ($kind -eq 'Text') { continue }
            if ($wp -notin $script:WebParts) {
                New-MgFinding 'PG004' 'Error' $ct "'$wp' isn't a known web part type."
                continue
            }
            if ($wp -in $script:IframeWebParts) { $iframes++ }
            if ($wp -in $script:SearchWebParts) { $search++ }
        }
    }

    if ($iframes -ge $L.IframeAttention) {
        New-MgFinding 'PG005' 'Error' $p "$iframes web parts use iframes (Embed, File viewer). Page Diagnostics flags 3 or more as 'Attention required'."
    }
    elseif ($iframes -gt 0) {
        New-MgFinding 'PG005' 'Warning' $p "$iframes web part(s) use iframes: an 'Improvement opportunity' in Page Diagnostics. Prefer images or links."
    }
    if ($search -gt $L.MaxSearchRequests) {
        New-MgFinding 'PG006' 'Warning' $p "$search search-driven web parts (Events, Highlighted content); modern pages should make no more than $($L.MaxSearchRequests) search requests. Turn on group-level caching or split the page."
    }
}

function Test-MgSiteTemplate {
    <#
    .SYNOPSIS  Lints a whole template folder: template.json, its site scripts and its pages.
               Returns findings with a Source (file) property.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ManifestPath,
        [string]$SchemaPath
    )
    $root = Split-Path -Parent (Resolve-Path -LiteralPath $ManifestPath)
    $m = Import-MgJson -Path $ManifestPath
    $wt = ConvertTo-MgWebTemplateId (Get-MgProp $m 'webTemplate' 'CommunicationSite')
    $siteType = if ($wt -eq 68) { 'Communication' } else { 'Team' }

    foreach ($f in @(Get-MgProp $m 'siteScripts' @())) {
        $path = Join-Path $root $f
        $raw = Get-Content -LiteralPath $path -Raw -Encoding utf8
        Test-MgSiteScript -Script ($raw | ConvertFrom-Json -Depth 30) -Raw $raw -WebTemplate $wt -SchemaPath $SchemaPath |
            Add-Member -NotePropertyName Source -NotePropertyValue $f -PassThru
    }
    $names = @{}
    foreach ($f in @(Get-MgProp $m 'pages' @())) {
        $page = Import-MgJson -Path (Join-Path $root $f)
        $n = Get-MgProp $page 'name' ''
        if ($names.ContainsKey($n)) {
            New-MgFinding 'PG009' 'Error' "page '$n'" "Two page designs use the name '$n'." | Add-Member -NotePropertyName Source -NotePropertyValue $f -PassThru
        }
        $names[$n] = $true
        Test-MgPageDesign -Page $page -SiteType $siteType | Add-Member -NotePropertyName Source -NotePropertyValue $f -PassThru
    }
    $homePage = Get-MgProp $m 'homePage'
    if ($homePage -and -not $names.ContainsKey($homePage)) {
        New-MgFinding 'PG009' 'Error' "homePage '$homePage'" "The home page isn't one of the template's pages." | Add-Member -NotePropertyName Source -NotePropertyValue 'template.json' -PassThru
    }
}

function Resolve-MgPageToken {
    <#
    .SYNOPSIS  Replaces {listid:<title>} in web part properties using a resolver scriptblock (title -> id).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][hashtable]$Properties, [Parameter(Mandatory)][scriptblock]$ListIdResolver)
    $out = @{}
    foreach ($k in $Properties.Keys) {
        $v = $Properties[$k]
        if ($v -is [string] -and $v -match '^\{listid:(.+)\}$') { $v = [string](& $ListIdResolver $Matches[1]) }
        $out[$k] = $v
    }
    $out
}

function ConvertTo-MgHashtable($Object) {
    $h = @{}
    if ($null -eq $Object) { return $h }
    foreach ($p in $Object.PSObject.Properties) { $h[$p.Name] = $p.Value }
    $h
}

function New-MgStep([string]$Action, [string]$Target, [string]$Detail = '') {
    [pscustomobject]@{ Action = $Action; Target = $Target; Detail = $Detail }
}

# ---- Tenant functions (PnP.PowerShell) --------------------------------------------------------------------------

function Invoke-MgSiteTemplateRegistration {
    <#
    .SYNOPSIS  Creates or updates the site scripts and the site template (site design). Needs a connection as a
               SharePoint admin. Idempotent: matches existing scripts and templates by title. Returns the steps and,
               last, an object with the SiteDesignId.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string]$ManifestPath, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $root = Split-Path -Parent (Resolve-Path -LiteralPath $ManifestPath)
    $m = Import-MgJson -Path $ManifestPath
    $wt = ConvertTo-MgWebTemplateId $m.webTemplate
    $pnpTemplate = ($script:WebTemplates.GetEnumerator() | Where-Object Value -eq $wt | Select-Object -First 1).Key

    $existingScripts = @(Get-PnPSiteScript @c)
    $ids = @()
    foreach ($f in @($m.siteScripts)) {
        $content = Get-Content -LiteralPath (Join-Path $root $f) -Raw -Encoding utf8
        $title = "$($m.title) - $([IO.Path]::GetFileNameWithoutExtension($f) -replace '\.site-script$', '')"
        $found = $existingScripts | Where-Object Title -eq $title | Select-Object -First 1
        if ($found) {
            if ($PSCmdlet.ShouldProcess($title, 'Update site script')) { $null = Set-PnPSiteScript @c -Identity $found.Id -Content $content }
            New-MgStep 'UpdateScript' $title
            $ids += $found.Id
        }
        else {
            $new = $null
            if ($PSCmdlet.ShouldProcess($title, 'Add site script')) { $new = Add-PnPSiteScript @c -Title $title -Content $content -Description "From $f" }
            New-MgStep 'AddScript' $title
            $ids += $(if ($new) { $new.Id } else { [guid]::Empty })
        }
    }

    $design = @(Get-PnPSiteDesign @c) | Where-Object Title -eq $m.title | Select-Object -First 1
    if ($design) {
        if ($PSCmdlet.ShouldProcess($m.title, 'Update site template')) {
            $null = Set-PnPSiteDesign @c -Identity $design.Id -SiteScriptIds $ids -Description $m.description -WebTemplate $pnpTemplate
        }
        New-MgStep 'UpdateTemplate' $m.title "$pnpTemplate ($wt), $($ids.Count) script(s)"
        $designId = $design.Id
    }
    else {
        $new = $null
        if ($PSCmdlet.ShouldProcess($m.title, 'Add site template')) {
            $new = Add-PnPSiteDesign @c -Title $m.title -SiteScriptIds $ids -Description $m.description -WebTemplate $pnpTemplate
        }
        New-MgStep 'AddTemplate' $m.title "$pnpTemplate ($wt), $($ids.Count) script(s)"
        $designId = if ($new) { $new.Id } else { [guid]::Empty }
    }
    [pscustomobject]@{ Action = 'Result'; Target = $m.title; Detail = "SiteDesignId $designId"; SiteDesignId = $designId }
}

function Invoke-MgSiteTemplateApply {
    <#
    .SYNOPSIS  Queues the template on a site asynchronously (Add-PnPSiteDesignTask: the 300-action path, the same
               one the UI uses) and returns the task.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][guid]$SiteDesignId, [Parameter(Mandatory)][string]$WebUrl, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    if ($PSCmdlet.ShouldProcess($WebUrl, "Apply site template $SiteDesignId")) {
        Add-PnPSiteDesignTask @c -SiteDesignId $SiteDesignId -WebUrl $WebUrl
    }
}

function Get-MgSiteTemplateRunReport {
    <#
    .SYNOPSIS  Reads back the latest run of a template on a site: one row per action with its outcome.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$WebUrl, [guid]$SiteDesignId, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $runArgs = @{ WebUrl = $WebUrl }; if ($SiteDesignId) { $runArgs.SiteDesignId = $SiteDesignId }
    # Runs come back as TenantSiteDesignRun objects (Id, SiteDesignId, SiteDesignTitle, ...); filter by template id
    # when you have it, otherwise the first run returned is reported.
    $run = @(Get-PnPSiteDesignRun @c @runArgs) | Select-Object -First 1
    if (-not $run) { return }
    foreach ($s in @(Get-PnPSiteDesignRunStatus @c -Run $run)) {
        # OutcomeCode prints as a word (Learn's example shows Success); OutcomeText explains failures.
        [pscustomobject]@{ Action = $s.ActionTitle; Outcome = "$($s.OutcomeCode)"; Detail = $s.OutcomeText; Script = $s.SiteScriptTitle }
    }
}

function Export-MgSiteScript {
    <#
    .SYNOPSIS  Extracts a site script from an existing site (Get-PnPSiteScriptFromWeb) so it can be linted and kept in git.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Url, [string[]]$Lists = @(), $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $args2 = @{ Url = $Url; IncludeBranding = $true; IncludeRegionalSettings = $true; IncludeSiteExternalSharingCapability = $true; IncludeLinksToExportedItems = $true }
    if ($Lists) { $args2.Lists = $Lists }
    Get-PnPSiteScriptFromWeb @c @args2
}

function Invoke-MgPageProvisioning {
    <#
    .SYNOPSIS  Creates the pages of a template on the connected site, section by section, then publishes them and
               sets the home page. Existing pages are skipped unless -Force (then they are recreated).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string]$ManifestPath, [switch]$Force, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $root = Split-Path -Parent (Resolve-Path -LiteralPath $ManifestPath)
    $m = Import-MgJson -Path $ManifestPath
    $resolver = { param($title) (Get-PnPList @c -Identity $title -ThrowExceptionIfListNotFound).Id }

    foreach ($f in @($m.pages)) {
        $page = Import-MgJson -Path (Join-Path $root $f)
        $name = $page.name
        $exists = $null
        try { $exists = Get-PnPPage @c -Identity $name -ErrorAction Stop } catch { $exists = $null }
        if ($exists -and -not $Force) { New-MgStep 'Skip' "$name.aspx" 'exists (use -Force to recreate)'; continue }
        if ($exists -and $PSCmdlet.ShouldProcess("$name.aspx", 'Remove page')) {
            Remove-PnPPage @c -Identity $name -Force
            New-MgStep 'RemovePage' "$name.aspx" 'recreate'
        }

        $add = @{ Name = $name; Title = $page.title; LayoutType = (Get-MgProp $page 'layout' 'Article') }
        $hl = Get-MgProp $page 'headerLayout'; if ($hl) { $add.HeaderLayoutType = $hl }
        $promote = Get-MgProp $page 'promoteAs'; if ($promote) { $add.PromoteAs = $promote }
        if ($PSCmdlet.ShouldProcess("$name.aspx", 'Add page')) { $null = Add-PnPPage @c @add }
        New-MgStep 'AddPage' "$name.aspx" "$($add.LayoutType)$(if ($promote) { ", $promote" })"

        $s = 0
        foreach ($section in @($page.sections)) {
            $s++
            if ($PSCmdlet.ShouldProcess("$name.aspx", "Add section $s")) {
                $null = Add-PnPPageSection @c -Page $name -SectionTemplate $section.template -Order $s
            }
            New-MgStep 'AddSection' "$name.aspx" "$s $($section.template)"
            $order = 0
            foreach ($ctl in @(Get-MgProp $section 'controls' @())) {
                $order++
                $col = [int](Get-MgProp $ctl 'column' 1)
                if ((Get-MgProp $ctl 'type' 'WebPart') -eq 'Text') {
                    if ($PSCmdlet.ShouldProcess("$name.aspx", "Add text $s/$col")) {
                        $null = Add-PnPPageTextPart @c -Page $name -Text $ctl.text -Section $s -Column $col -Order $order
                    }
                    New-MgStep 'AddText' "$name.aspx" "section $s column $col"
                }
                else {
                    $wp = @{ Page = $name; DefaultWebPartType = $ctl.webPart; Section = $s; Column = $col; Order = $order }
                    $props = ConvertTo-MgHashtable (Get-MgProp $ctl 'properties')
                    if ($props.Count) {
                        if ($WhatIfPreference) { $wp.WebPartProperties = $props }
                        else { $wp.WebPartProperties = Resolve-MgPageToken -Properties $props -ListIdResolver $resolver }
                    }
                    if ($PSCmdlet.ShouldProcess("$name.aspx", "Add $($ctl.webPart) $s/$col")) { $null = Add-PnPPageWebPart @c @wp }
                    New-MgStep 'AddWebPart' "$name.aspx" "$($ctl.webPart) in section $s column $col"
                }
            }
        }
        if ($PSCmdlet.ShouldProcess("$name.aspx", 'Publish')) { $null = Set-PnPPage @c -Identity $name -Publish }
        New-MgStep 'Publish' "$name.aspx"
    }

    $homePage = Get-MgProp $m 'homePage'
    if ($homePage) {
        if ($PSCmdlet.ShouldProcess("SitePages/$homePage.aspx", 'Set home page')) { Set-PnPHomePage @c -RootFolderRelativeUrl "SitePages/$homePage.aspx" }
        New-MgStep 'SetHomePage' "SitePages/$homePage.aspx"
    }
}

Export-ModuleMember -Function Get-MgLimits, Import-MgJson, ConvertTo-MgWebTemplateId, Get-MgSiteScriptAction,
    Test-MgSiteScript, Test-MgPageDesign, Test-MgSiteTemplate, Resolve-MgPageToken, Invoke-MgSiteTemplateRegistration,
    Invoke-MgSiteTemplateApply, Get-MgSiteTemplateRunReport, Export-MgSiteScript, Invoke-MgPageProvisioning
