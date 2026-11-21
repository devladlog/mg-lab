#Requires -Version 7.2
<#
.SYNOPSIS
    Intranet design as code for Contoso: a blueprint with the home site, the global navigation of the SharePoint app
    bar, organization news sites, an organization assets library for brand images, and a tenant theme whose colours
    are checked for contrast before anyone sees them. Builds on the episode 7 hub.

    Pure functions (no SharePoint needed): Import-MgJson, Get-MgContrastRatio, Get-MgPngSize, Test-MgTheme,
    Test-MgIntranet, Test-MgIntranetLive.
    Tenant functions (PnP.PowerShell, after Connect-PnPOnline): Invoke-MgTenantTheme, Invoke-MgHomeSite,
    Invoke-MgOrgNews, Invoke-MgOrgAssets, Invoke-MgGlobalNavigation, Get-MgIntranetState.

    The navigation rules (HN001-HN013) and the navigation provisioning come from the episode 7 module, MgHubNav.
#>

Set-StrictMode -Version Latest

$script:HubNavPath = Join-Path $PSScriptRoot '..' '..' '07-hub-sites-navigation' 'src' 'MgHubNav.psm1'
Import-Module $script:HubNavPath -Force

# ---- What Learn documents (see README "References") -------------------------------------------------------------
#   The home site needs to be a communication site; only one communication site can be the home site.
$script:CommunicationSite = 'SITEPAGEPUBLISHING#0'
#   Up to 100 organization news sites; the home site is automatically an organization news site.
$script:MaxOrgNewsSites = 100
#   Up to 30 organization asset libraries, all on the same site. Learn describes two types.
$script:MaxOrgAssetLibraries = 30
$script:OrgAssetTypes = @('ImageDocumentLibrary', 'OfficeTemplateLibrary')
#   Global navigation logo: 20x20 pixels, PNG. Home site logo: 64x64 pixels recommended.
$script:GlobalNavLogo = @(20, 20)
$script:SiteLogo = @(64, 64)
#   Images: 300 KB or smaller (modern portal limits).
$script:MaxImageBytes = 300KB
#   Global navigation sources offered by the home site's Global navigation settings.
$script:GlobalNavSources = @('homeSiteNavigation', 'hubOrGlobalNavigation')
#   Theme: up to 16 color pairs (new format). Palette slots of Learn's legacy-format example (Teal).
$script:MaxColorPairs = 16
$script:PaletteSlots = @('themeDarker', 'themeDark', 'themeDarkAlt', 'themePrimary', 'themeSecondary', 'themeTertiary',
    'themeLight', 'themeLighter', 'themeLighterAlt', 'neutralDark', 'neutralPrimary', 'neutralPrimaryAlt', 'neutralSecondary',
    'neutralTertiary', 'neutralTertiaryAlt', 'neutralLight', 'neutralLighter', 'neutralLighterAlt', 'neutralQuaternaryAlt',
    'neutralQuaternary', 'black', 'white')
#   WCAG 2.x minimum contrast for normal text: 4.5:1 (Learn: accessible text requirements; W3C G18).
$script:MinTextContrast = 4.5
#   Palette pairs read as text on a background (foreground, background, what it is).
$script:TextPairs = @(
    ,@('neutralPrimary', 'white', 'body text on the page background')
    ,@('neutralSecondary', 'white', 'secondary text on the page background')
    ,@('themePrimary', 'white', 'theme colour as text or links on the page background')
    ,@('white', 'themePrimary', 'white text on the theme colour')
)

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

function Get-MgKey([string]$Url) {
    if (-not $Url) { return '' }
    $k = ([uri]::UnescapeDataString($Url) -replace '^https?://[^/]+', '').TrimEnd('/').ToLowerInvariant()
    if ($k -and -not $k.StartsWith('/')) { $k = "/$k" }   # library URLs can come back without the leading slash
    $k
}

function Get-MgSiteKey([string]$Url) {
    $k = Get-MgKey $Url
    if ($k -match '^(/(sites|teams)/[^/]+)') { return $Matches[1] }
    $k
}

function ConvertTo-MgAbs([string]$Url, [string]$TenantUrl) {
    if (-not $Url -or $Url -match '^https?://' -or -not $TenantUrl) { return $Url }
    $TenantUrl.TrimEnd('/') + '/' + $Url.TrimStart('/')
}

# ---- Colour and images ---------------------------------------------------------------------------------------------

function Test-MgHexColor([string]$Hex) { $Hex -match '^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$' }

function Get-MgRelativeLuminance([string]$Hex) {
    $h = $Hex.TrimStart('#')
    if ($h.Length -eq 3) { $h = -join ($h.ToCharArray() | ForEach-Object { "$_$_" }) }
    $c = 0, 2, 4 | ForEach-Object {
        $v = [Convert]::ToInt32($h.Substring($_, 2), 16) / 255.0
        if ($v -le 0.04045) { $v / 12.92 } else { [Math]::Pow(($v + 0.055) / 1.055, 2.4) }
    }
    0.2126 * $c[0] + 0.7152 * $c[1] + 0.0722 * $c[2]
}

function Get-MgContrastRatio {
    <# .SYNOPSIS  WCAG 2.x contrast ratio of two colours (#RGB or #RRGGBB): (L1 + 0.05) / (L2 + 0.05), 1 to 21. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Foreground, [Parameter(Mandatory)][string]$Background)
    $a = Get-MgRelativeLuminance $Foreground; $b = Get-MgRelativeLuminance $Background
    $hi = [Math]::Max($a, $b); $lo = [Math]::Min($a, $b)
    [Math]::Round(($hi + 0.05) / ($lo + 0.05), 2)
}

function Get-MgPngSize {
    <# .SYNOPSIS  Width and height from a PNG's IHDR chunk (no image library needed); $null if it isn't a PNG. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $b = [System.IO.File]::ReadAllBytes($Path)
    $sig = [byte[]](0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
    if ($b.Length -lt 24 -or [Convert]::ToBase64String($b[0..7]) -ne [Convert]::ToBase64String($sig)) { return $null }
    $w = ([int]$b[16] -shl 24) -bor ([int]$b[17] -shl 16) -bor ([int]$b[18] -shl 8) -bor [int]$b[19]
    $h = ([int]$b[20] -shl 24) -bor ([int]$b[21] -shl 16) -bor ([int]$b[22] -shl 8) -bor [int]$b[23]
    [pscustomobject]@{ Width = $w; Height = $h; Bytes = $b.Length }
}

function Test-MgTheme {
    <#
    .SYNOPSIS  TH001-TH006: palette slots, hex values, text contrast (legacy palette) and color pairs (new format).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Theme, [string]$Name = (Get-MgProp $Theme 'name' 'theme'))
    $palette = Get-MgProp $Theme 'palette'
    $pairs = @(Get-MgProp (Get-MgProp $Theme 'colorPairs') 'light' @())
    if (-not $palette -and -not $pairs.Count) { New-MgFinding 'TH001' 'Error' $Name 'Neither a palette nor color pairs.'; return }
    if ($palette) {
        foreach ($s in $script:PaletteSlots | Where-Object { -not (Get-MgProp $palette $_) }) {
            New-MgFinding 'TH001' 'Error' "$Name.$s" 'Missing palette slot.'
        }
        foreach ($p in @($palette.PSObject.Properties)) {
            if (-not (Test-MgHexColor "$($p.Value)")) { New-MgFinding 'TH002' 'Error' "$Name.$($p.Name)" "'$($p.Value)' isn't a 3- or 6-digit hex colour." }
        }
        foreach ($t in $script:TextPairs) {
            $fg = "$(Get-MgProp $palette $t[0] '')"; $bg = "$(Get-MgProp $palette $t[1] '')"
            if (-not ((Test-MgHexColor $fg) -and (Test-MgHexColor $bg))) { continue }
            $r = Get-MgContrastRatio $fg $bg
            if ($r -lt $script:MinTextContrast) {
                New-MgFinding 'TH003' 'Error' "$Name $($t[0]) on $($t[1])" "Contrast $r`:1 for $($t[2]): text needs at least $($script:MinTextContrast):1."
            }
        }
        $white = "$(Get-MgProp $palette 'white' '')"; $text = "$(Get-MgProp $palette 'neutralPrimary' '')"
        if ((Test-MgHexColor $white) -and (Test-MgHexColor $text)) {
            $darkBackground = (Get-MgRelativeLuminance $white) -lt (Get-MgRelativeLuminance $text)
            if ($darkBackground -ne [bool](Get-MgProp $Theme 'isInverted' $false)) {
                New-MgFinding 'TH006' 'Warning' "$Name.isInverted" "isInverted is $([bool](Get-MgProp $Theme 'isInverted' $false)) but the background slot is $(if ($darkBackground) { 'darker' } else { 'lighter' }) than the text: isInverted should be true for dark themes."
            }
        }
    }
    if ($pairs.Count -gt $script:MaxColorPairs) {
        New-MgFinding 'TH005' 'Error' $Name "$($pairs.Count) color pairs: a theme supports up to $($script:MaxColorPairs)."
    }
    $i = 0
    foreach ($p in $pairs) {
        $i++
        $fg = "$(Get-MgProp $p 'accentColor' '')"; $bg = "$(Get-MgProp $p 'backgroundColor' '')"
        if (-not ((Test-MgHexColor $fg) -and (Test-MgHexColor $bg))) { New-MgFinding 'TH002' 'Error' "$Name pair $i" "'$fg' on '$bg' isn't a pair of hex colours."; continue }
        $r = Get-MgContrastRatio $fg $bg
        if ($r -lt $script:MinTextContrast) { New-MgFinding 'TH004' 'Error' "$Name pair $i" "$fg on $bg has contrast $r`:1: text needs at least $($script:MinTextContrast):1." }
    }
}

function Resolve-MgLocal([string]$Path, [string]$BaseDir) {
    if (-not $Path) { return $null }
    if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
    Join-Path $BaseDir $Path
}

function Test-MgImage([string]$Path, [string]$Target, [int[]]$Size, [string]$Rule, [string]$What) {
    if (-not (Test-Path -LiteralPath $Path)) { New-MgFinding $Rule 'Error' $Target "File not found: $Path"; return }
    $png = Get-MgPngSize -Path $Path
    if (-not $png) { New-MgFinding $Rule 'Warning' $Target "Not a PNG: the $What should be a PNG file."; return }
    if ($Size -and ($png.Width -ne $Size[0] -or $png.Height -ne $Size[1])) {
        New-MgFinding $Rule 'Warning' $Target "$($png.Width)x$($png.Height): the $What should be $($Size[0])x$($Size[1]) pixels."
    }
    if ($png.Bytes -gt $script:MaxImageBytes) {
        New-MgFinding 'IN008' 'Warning' $Target "$([Math]::Round($png.Bytes / 1KB)) KB: keep images at 300 KB or smaller."
    }
}

function Test-MgIntranet {
    <#
    .SYNOPSIS  Lints the intranet blueprint: home site, news, org assets, global navigation (IN001-IN009), its
               navigation tree (HN rules from episode 7) and the theme (TH rules).
    .PARAMETER BaseDir  Folder the blueprint's local files (logos, theme) are relative to.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Blueprint, [Parameter(Mandatory)][string]$BaseDir)
    $home_ = $Blueprint.homeSite
    $homeKey = Get-MgSiteKey $home_.url
    if ("$(Get-MgProp $home_ 'template' '')" -ne $script:CommunicationSite) {
        New-MgFinding 'IN001' 'Error' 'homeSite.template' "'$(Get-MgProp $home_ 'template' '')': the home site needs to be a communication site ($($script:CommunicationSite))."
    }
    $news = @(Get-MgProp $Blueprint 'orgNewsSites' @())
    if ($news | Where-Object { (Get-MgSiteKey $_) -eq $homeKey }) {
        New-MgFinding 'IN002' 'Warning' 'orgNewsSites' 'Lists the home site: a home site is automatically an organization news site.'
    }
    if ($news.Count -gt $script:MaxOrgNewsSites) {
        New-MgFinding 'IN003' 'Error' 'orgNewsSites' "$($news.Count) sites: up to $($script:MaxOrgNewsSites) organization news sites."
    }
    $libs = @(Get-MgProp (Get-MgProp $Blueprint 'orgAssets') 'libraries' @())
    if ($libs.Count -gt $script:MaxOrgAssetLibraries) {
        New-MgFinding 'IN004' 'Error' 'orgAssets' "$($libs.Count) libraries: up to $($script:MaxOrgAssetLibraries) organization asset libraries."
    }
    $sites = @($libs | ForEach-Object { Get-MgSiteKey $_.url } | Sort-Object -Unique)
    if ($sites.Count -gt 1) { New-MgFinding 'IN004' 'Error' 'orgAssets' "Libraries on $($sites.Count) sites ($($sites -join ', ')): all organization asset libraries must be on the same site." }
    foreach ($l in $libs) {
        $type = "$(Get-MgProp $l 'type' 'ImageDocumentLibrary')"
        if ($type -notin $script:OrgAssetTypes) { New-MgFinding 'IN004' 'Warning' $l.url "Type '$type': Learn describes ImageDocumentLibrary and OfficeTemplateLibrary." }
        $thumb = Get-MgProp $l 'thumbnail'
        if ($thumb -and (Get-MgSiteKey $thumb) -ne (Get-MgSiteKey $l.url)) {
            New-MgFinding 'IN004' 'Error' $l.url "Thumbnail $thumb is on another site: it must be on the same site as the library."
        }
        foreach ($f in @(Get-MgProp $l 'files' @())) {
            $p = Resolve-MgLocal $f $BaseDir
            if (-not (Test-Path -LiteralPath $p)) { New-MgFinding 'IN008' 'Error' $l.url "File not found: $f"; continue }
            $len = (Get-Item -LiteralPath $p).Length
            if ($len -gt $script:MaxImageBytes) { New-MgFinding 'IN008' 'Warning' $f "$([Math]::Round($len / 1KB)) KB: keep images at 300 KB or smaller." }
        }
    }
    $hubs = @(Get-MgProp $Blueprint 'hubs' @())
    if ([bool](Get-MgProp $home_ 'isHub' $false) -and @($hubs | Where-Object { (Get-MgSiteKey $_) -ne $homeKey }).Count -ge 1) {
        New-MgFinding 'IN006' 'Warning' 'homeSite.isHub' 'The home site is a hub and there are other hubs: a hub home site offers two global navigation sources (its site navigation or its hub navigation), so decide on purpose which list the app bar shows.'
    }
    if (Get-MgProp $home_ 'logo') { Test-MgImage (Resolve-MgLocal $home_.logo $BaseDir) 'homeSite.logo' $script:SiteLogo 'IN007' 'site logo' }

    $nav = Get-MgProp $Blueprint 'globalNavigation'
    if ($nav) {
        $source = "$(Get-MgProp $nav 'source' '')"
        if ($source -notin $script:GlobalNavSources) {
            New-MgFinding 'IN009' 'Error' 'globalNavigation.source' "'$source': the source is homeSiteNavigation or hubOrGlobalNavigation."
        }
        elseif ($source -eq 'hubOrGlobalNavigation' -and -not [bool](Get-MgProp $home_ 'isHub' $false)) {
            New-MgFinding 'IN009' 'Warning' 'globalNavigation.source' 'A separate global navigation set on a home site that isn''t a hub is edited in the browser: this script provisions the home site navigation.'
        }
        if (Get-MgProp $nav 'logo') { Test-MgImage (Resolve-MgLocal $nav.logo $BaseDir) 'globalNavigation.logo' $script:GlobalNavLogo 'IN007' 'global navigation logo' }
        $rows = @(Get-MgNavNodeList -Nodes (Get-MgProp $nav 'nodes' @()))
        foreach ($h in $hubs | Where-Object { (Get-MgSiteKey $_) -ne $homeKey }) {
            if (-not ($rows | Where-Object { $_.Url -and (Get-MgSiteKey $_.Url) -eq (Get-MgSiteKey $h) })) {
                New-MgFinding 'IN005' 'Warning' $h 'Hub not in the global navigation: add hubs to the global navigation so people can find them.'
            }
        }
        $names = @((Get-MgProp $Blueprint 'audiences' ([pscustomobject]@{})).PSObject.Properties | ForEach-Object Name)
        Test-MgNavigation -Navigation $nav -Audiences $names -Name 'global navigation'
    }
    $themeRef = Get-MgProp $Blueprint 'theme'
    if ($themeRef) {
        $tp = Resolve-MgLocal $themeRef.path $BaseDir
        if (-not (Test-Path -LiteralPath $tp)) { New-MgFinding 'TH001' 'Error' 'theme.path' "File not found: $($themeRef.path)" }
        else { Test-MgTheme -Theme (Import-MgJson -Path $tp) }
    }
}

function Test-MgIntranetLive {
    <#
    .SYNOPSIS  Compares the tenant (Get-MgIntranetState) with the blueprint: IL001-IL006.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Blueprint, [Parameter(Mandatory)]$State, $Theme, [hashtable]$AudienceIds = @{})
    $homeKey = Get-MgSiteKey $Blueprint.homeSite.url
    if ((Get-MgSiteKey "$($State.HomeSite)") -ne $homeKey) {
        New-MgFinding 'IL001' 'Error' 'home site' "Tenant home site is '$(if ($State.HomeSite) { Get-MgSiteKey "$($State.HomeSite)" } else { 'none' })', blueprint says $($Blueprint.homeSite.url)."
    }
    $news = @($State.OrgNewsSites | ForEach-Object { Get-MgSiteKey "$_" })
    foreach ($n in @(Get-MgProp $Blueprint 'orgNewsSites' @()) | Where-Object { (Get-MgSiteKey $_) -notin $news -and (Get-MgSiteKey $_) -ne $homeKey }) {
        New-MgFinding 'IL002' 'Error' $n 'Not an organization news site.'
    }
    $libs = @($State.OrgAssetLibraries | ForEach-Object { Get-MgKey "$_" })
    foreach ($l in @(Get-MgProp (Get-MgProp $Blueprint 'orgAssets') 'libraries' @()) | Where-Object { (Get-MgKey $_.url) -notin $libs }) {
        New-MgFinding 'IL003' 'Error' $l.url 'Not registered as an organization assets library.'
    }
    if ($Theme) {
        $live = $State.Theme
        if (-not $live) { New-MgFinding 'IL004' 'Error' $Theme.name 'Theme not in the tenant.' }
        else {
            $lp = Get-MgProp $live 'Palette'
            foreach ($p in @($Theme.palette.PSObject.Properties)) {
                $have = "$(Get-MgProp $lp $p.Name '')"
                if ($have.TrimStart('#').ToLowerInvariant() -ne "$($p.Value)".TrimStart('#').ToLowerInvariant()) {
                    New-MgFinding 'IL004' 'Error' "$($Theme.name).$($p.Name)" "Tenant has '$have', blueprint says '$($p.Value)'."
                }
            }
        }
    }
    $visitors = @($State.HomeVisitors | ForEach-Object { "$(Get-MgProp $_ 'Title' $_)" })
    if ('Everyone except external users' -notin $visitors) {
        New-MgFinding 'IL005' 'Error' $Blueprint.homeSite.url 'Everyone except external users isn''t a visitor: people need read access to the home site to see global navigation (and the organization assets site requires it).'
    }
    if (Get-MgProp $Blueprint 'globalNavigation') {
        foreach ($d in @(Compare-MgNavigation -PlanNodes $Blueprint.globalNavigation.nodes -LiveNodes $State.Navigation -AudienceIds $AudienceIds)) {
            New-MgFinding 'IL006' 'Error' $d.Path "$($d.Kind): $($d.Detail)."
        }
    }
}

# ---- Tenant --------------------------------------------------------------------------------------------------------

function ConvertTo-MgPaletteHashtable($Palette) {
    $h = @{}; foreach ($p in @($Palette.PSObject.Properties)) { $h[$p.Name] = "$($p.Value)" }; $h
}

function Invoke-MgTenantTheme {
    <#
    .SYNOPSIS  Adds (or overwrites) the tenant theme when its palette differs, then applies it to the blueprint's
               sites; sites associated with a hub inherit the hub's theme. Admin connection. -WhatIf.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Theme, [string[]]$ApplyTo = @(), [Parameter(Mandatory)][string]$TenantUrl, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $live = try { Get-PnPTenantTheme -Name $Theme.name -ErrorAction Stop @c } catch { $null }
    $differs = -not $live
    if ($live) {
        $lp = Get-MgProp $live 'Palette'
        foreach ($p in @($Theme.palette.PSObject.Properties)) {
            if ("$(Get-MgProp $lp $p.Name '')".TrimStart('#').ToLowerInvariant() -ne "$($p.Value)".TrimStart('#').ToLowerInvariant()) { $differs = $true; break }
        }
    }
    if ($differs) {
        if ($PSCmdlet.ShouldProcess($Theme.name, 'Add tenant theme')) {
            $null = Add-PnPTenantTheme -Identity $Theme.name -Palette (ConvertTo-MgPaletteHashtable $Theme.palette) -IsInverted ([bool](Get-MgProp $Theme 'isInverted' $false)) -Overwrite @c
        }
        New-MgStep $(if ($live) { 'UpdateTheme' } else { 'AddTheme' }) $Theme.name "$(@($Theme.palette.PSObject.Properties).Count) slots"
    }
    foreach ($u in $ApplyTo) {
        if ($PSCmdlet.ShouldProcess($u, "Apply theme $($Theme.name)")) { Set-PnPWebTheme -Theme $Theme.name -WebUrl (ConvertTo-MgAbs $u $TenantUrl) @c }
        New-MgStep 'ApplyTheme' $u $Theme.name
    }
}

function Invoke-MgHomeSite {
    <# .SYNOPSIS  Sets the home site if it isn't already the blueprint's. Admin connection. -WhatIf. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Blueprint, [Parameter(Mandatory)][string]$TenantUrl, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $current = Get-PnPHomeSite @c
    $url = ConvertTo-MgAbs $Blueprint.homeSite.url $TenantUrl
    if ((Get-MgSiteKey "$current") -eq (Get-MgSiteKey $url)) { return }
    if ($PSCmdlet.ShouldProcess($url, 'Set home site')) { $null = Set-PnPHomeSite -HomeSiteUrl $url -Force @c }
    New-MgStep 'SetHomeSite' $Blueprint.homeSite.url $(if ($current) { "was $(Get-MgSiteKey "$current")" } else { 'no home site before' })
}

function Invoke-MgOrgNews {
    <# .SYNOPSIS  Adds the missing organization news sites (the home site is one already). Admin connection. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Blueprint, [Parameter(Mandatory)][string]$TenantUrl, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $live = @(Get-PnPOrgNewsSite @c | ForEach-Object { Get-MgSiteKey "$_" })
    foreach ($n in @(Get-MgProp $Blueprint 'orgNewsSites' @())) {
        if ((Get-MgSiteKey $n) -in $live -or (Get-MgSiteKey $n) -eq (Get-MgSiteKey $Blueprint.homeSite.url)) { continue }
        if ($PSCmdlet.ShouldProcess($n, 'Add organization news site')) { $null = Add-PnPOrgNewsSite -OrgNewsSiteUrl (ConvertTo-MgAbs $n $TenantUrl) @c }
        New-MgStep 'AddOrgNews' $n
    }
}

function Invoke-MgOrgAssets {
    <#
    .SYNOPSIS  Creates the asset libraries and uploads the files (site connection), then registers each library as an
               organization assets library (admin connection; enables a private CDN by default). -WhatIf.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Blueprint, [Parameter(Mandatory)][string]$BaseDir, [Parameter(Mandatory)][string]$TenantUrl, $SiteConnection, $AdminConnection)
    $s = @{}; if ($SiteConnection) { $s.Connection = $SiteConnection }
    $a = @{}; if ($AdminConnection) { $a.Connection = $AdminConnection }
    $registered = @(foreach ($o in @(Get-PnPOrgAssetsLibrary @a)) {
            foreach ($l in @(Get-MgProp $o 'OrgAssetsLibraries' @())) { $u = Get-MgProp $l 'LibraryUrl'; Get-MgKey "$(Get-MgProp $u 'DecodedUrl' $u)" }
        })
    foreach ($l in @(Get-MgProp (Get-MgProp $Blueprint 'orgAssets') 'libraries' @())) {
        $leaf = ($l.url.TrimEnd('/') -split '/')[-1]
        $list = Get-PnPList -Identity $leaf @s
        if (-not $list) {
            if ($PSCmdlet.ShouldProcess($l.url, 'Create library')) { $null = New-PnPList -Title (Get-MgProp $l 'title' $leaf) -Template DocumentLibrary -Url $leaf @s }
            New-MgStep 'CreateLibrary' $l.url
        }
        foreach ($f in @(Get-MgProp $l 'files' @())) {
            if ($PSCmdlet.ShouldProcess($f, "Upload to $leaf")) { $null = Add-PnPFile -Path (Resolve-MgLocal $f $BaseDir) -Folder $leaf @s }
            New-MgStep 'Upload' $f $l.url
        }
        if ((Get-MgKey $l.url) -in $registered) { continue }
        $p = @{ LibraryUrl = ConvertTo-MgAbs $l.url $TenantUrl; OrgAssetType = "$(Get-MgProp $l 'type' 'ImageDocumentLibrary')" }
        if (Get-MgProp $l 'thumbnail') { $p.ThumbnailUrl = ConvertTo-MgAbs $l.thumbnail $TenantUrl }
        if ($PSCmdlet.ShouldProcess($l.url, 'Register organization assets library')) { $null = Add-PnPOrgAssetsLibrary @p @a }
        New-MgStep 'AddOrgAssets' $l.url $p.OrgAssetType
    }
}

function Invoke-MgGlobalNavigation {
    <#
    .SYNOPSIS  Builds the home site navigation that the app bar's global navigation shows (source "Home site
               navigation"), with audience targeting and the mega menu as planned. Home site connection.
               Turning global navigation on is a switch in the home site's Settings > Global navigation.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Blueprint, [Parameter(Mandatory)][string]$TenantUrl, [hashtable]$AudienceIds = @{}, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $nav = $Blueprint.globalNavigation
    if ("$(Get-MgProp $nav 'source' '')" -ne 'homeSiteNavigation') { New-MgStep 'Skip' 'global navigation' "source '$($nav.source)' isn't provisioned here"; return }
    $web = Get-PnPWeb -Includes NavAudienceTargetingEnabled, MegaMenuEnabled @c
    $set = @{}
    $t = [bool](Get-MgProp $nav 'audienceTargeting' $false); $m = [bool](Get-MgProp $nav 'megaMenu' $false)
    if ([bool](Get-MgProp $web 'NavAudienceTargetingEnabled' $false) -ne $t) { $set.NavAudienceTargetingEnabled = [switch]$t }
    if ([bool](Get-MgProp $web 'MegaMenuEnabled' $false) -ne $m) { $set.MegaMenuEnabled = [switch]$m }
    if ($set.Count) {
        if ($PSCmdlet.ShouldProcess($Blueprint.homeSite.url, "Set-PnPWeb $($set.Keys -join ', ')")) { Set-PnPWeb @set @c }
        New-MgStep 'SetWeb' $Blueprint.homeSite.url (($set.GetEnumerator() | Sort-Object Key | ForEach-Object { "$($_.Key)=$([bool]$_.Value)" }) -join ', ')
    }
    Invoke-MgNavigationTree -Nodes $nav.nodes -TenantUrl $TenantUrl -SiteUrl $Blueprint.homeSite.url -AudienceIds $AudienceIds -Label 'global navigation' -Connection $Connection -WhatIf:$WhatIfPreference
}

function Get-MgIntranetState {
    <# .SYNOPSIS  Reads what Test-MgIntranetLive compares (admin connection + home site connection). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Blueprint, $Theme, $AdminConnection, $SiteConnection)
    $a = @{}; if ($AdminConnection) { $a.Connection = $AdminConnection }
    $s = @{}; if ($SiteConnection) { $s.Connection = $SiteConnection }
    $libs = @(foreach ($o in @(Get-PnPOrgAssetsLibrary @a)) {
            foreach ($l in @(Get-MgProp $o 'OrgAssetsLibraries' @())) { $u = Get-MgProp $l 'LibraryUrl'; "$(Get-MgProp $u 'DecodedUrl' $u)" }
        })
    $visitorGroup = Get-PnPGroup -AssociatedVisitorGroup @s
    [pscustomobject]@{
        HomeSite = "$(Get-PnPHomeSite @a)"
        OrgNewsSites = @(Get-PnPOrgNewsSite @a)
        OrgAssetLibraries = $libs
        Theme = $(if ($Theme) { try { Get-PnPTenantTheme -Name $Theme.name -ErrorAction Stop @a } catch { $null } })
        HomeVisitors = @(if ($visitorGroup) { Get-PnPGroupMember -Group "$(Get-MgProp $visitorGroup 'Title' '')" @s })
        Navigation = @(Get-MgLiveNavigation -Connection $SiteConnection)
    }
}

Export-ModuleMember -Function Import-MgJson, Get-MgContrastRatio, Get-MgPngSize, Test-MgTheme, Test-MgIntranet, Test-MgIntranetLive,
    Invoke-MgTenantTheme, Invoke-MgHomeSite, Invoke-MgOrgNews, Invoke-MgOrgAssets, Invoke-MgGlobalNavigation, Get-MgIntranetState
