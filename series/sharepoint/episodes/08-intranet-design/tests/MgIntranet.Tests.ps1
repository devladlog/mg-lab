#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
# Invoke-Pester ./tests -Output Detailed
# The tenant tests mock the real PnP.PowerShell cmdlets (Pester copies their parameter metadata, so a wrong
# parameter name or type fails the test). They are skipped when PnP.PowerShell isn't installed.
# Needs the episode 7 folder next to this one (MgIntranet imports ../07-hub-sites-navigation/src/MgHubNav.psm1).

BeforeDiscovery {
    $script:hasPnP = [bool](Get-Module -ListAvailable PnP.PowerShell)
}

BeforeAll {
    $script:src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'MgIntranet.psm1') -Force
    $script:bpDir = Join-Path $src 'intranet'
    $script:bp = Import-MgJson -Path (Join-Path $bpDir 'contoso-intranet.json')
    $script:theme = Import-MgJson -Path (Join-Path $bpDir 'contoso-operations.theme.json')
    $script:badDir = Join-Path $src 'bad'
    $script:bad = Import-MgJson -Path (Join-Path $badDir 'bad-intranet.json')
    $script:cyan = Import-MgJson -Path (Join-Path $badDir 'custom-cyan.theme.json')
    $script:defaults = Import-MgJson -Path (Join-Path $src 'fixtures' 'learn-default-themes.json')
    $script:tenant = 'https://contoso.sharepoint.com'
    $script:ids = @{ 'Purchasing Team' = [guid]'00000000-0000-0000-0000-0000000000b1' }

    function Rules($f) { @($f | Where-Object { $null -ne $_ } | ForEach-Object Rule) }
    function Copy-Json($o) { $o | ConvertTo-Json -Depth 30 | ConvertFrom-Json -Depth 30 }
    function Live-FromPlan($Nodes) {
        foreach ($n in @($Nodes)) {
            $kids = if ($n.PSObject.Properties['children']) { @(Live-FromPlan $n.children) } else { @() }
            $aud = if ($n.PSObject.Properties['audiences']) { @($n.audiences | ForEach-Object { "$($ids[$_])" }) } else { @() }
            $url = if ($n.PSObject.Properties['url']) { "$tenant$($n.url)" } else { 'http://linkless.header/' }
            [pscustomobject]@{ Id = 1; Title = $n.title; Url = $url; Audiences = $aud; Children = $kids }
        }
    }
    function Good-State {
        $palette = [pscustomobject]@{}; foreach ($p in $theme.palette.PSObject.Properties) { $palette | Add-Member -NotePropertyName $p.Name -NotePropertyValue $p.Value.ToLower() }
        [pscustomobject]@{
            HomeSite = "$tenant/sites/Intranet"
            OrgNewsSites = @("$tenant/sites/Intranet", "$tenant/sites/Operations")
            OrgAssetLibraries = @("$tenant/sites/Intranet/BrandImages")
            Theme = [pscustomobject]@{ Name = 'Contoso Operations'; Palette = $palette; IsInverted = $false }
            HomeVisitors = @([pscustomobject]@{ Title = 'Everyone except external users' }, [pscustomobject]@{ Title = 'Alex Demo' })
            Navigation = @(Live-FromPlan $bp.globalNavigation.nodes)
        }
    }
}

Describe 'Contrast (WCAG 2.x formula)' {
    It 'gives the known ratios: black on white 21, the same colour 1' {
        Get-MgContrastRatio '#000000' '#FFFFFF' | Should -Be 21
        Get-MgContrastRatio '#777' '#777777' | Should -Be 1
        Get-MgContrastRatio '#767676' '#FFFFFF' | Should -BeGreaterOrEqual 4.5     # the usual "lightest grey that passes"
    }

    It 'all ten default themes on Learn pass 4.5:1 on every color pair' {
        foreach ($t in $defaults.themes) { @(Test-MgTheme -Theme $t) | Should -HaveCount 0 -Because $t.name }
        @($defaults.themes) | Should -HaveCount 10
    }

    It "Learn's own Add-SPOTheme 'Custom Cyan' example fails: cyan on white is 1.25:1" {
        Get-MgContrastRatio $cyan.palette.themePrimary $cyan.palette.white | Should -Be 1.25
        $f = @(Test-MgTheme -Theme $cyan)
        Rules $f | Should -Be @('TH003', 'TH003')
        $f[0].Target | Should -Be 'Custom Cyan themePrimary on white'
    }

    It 'the Contoso Operations theme passes, with the ratios shown in the episode' {
        @(Test-MgTheme -Theme $theme) | Should -HaveCount 0
        Get-MgContrastRatio $theme.palette.themePrimary $theme.palette.white | Should -Be 7.38
        Get-MgContrastRatio $theme.palette.neutralPrimary $theme.palette.white | Should -Be 12.98
    }

    It 'TH001 missing slot, TH002 bad hex, TH004 weak pair, TH005 too many pairs, TH006 isInverted' {
        $t = Copy-Json $theme
        $t.palette.PSObject.Properties.Remove('themeDark'); $t.palette.themeLight = 'blue'
        (Rules (Test-MgTheme -Theme $t) | Sort-Object) -join ',' | Should -Be 'TH001,TH002'
        $pairs = [pscustomobject]@{ name = 'Pairs'; colorPairs = [pscustomobject]@{ light = @(1..17 | ForEach-Object { [pscustomobject]@{ accentColor = '#FFFFFF'; backgroundColor = '#007780' } }) } }
        Rules (Test-MgTheme -Theme $pairs) | Should -Be @('TH005')
        $pairs.colorPairs.light = @([pscustomobject]@{ accentColor = '#A19F9D'; backgroundColor = '#FFFFFF' })
        Rules (Test-MgTheme -Theme $pairs) | Should -Be @('TH004')
        $dark = Copy-Json $theme; $dark.palette.white = '#1b1a19'; $dark.palette.neutralPrimary = '#f3f2f1'; $dark.palette.themePrimary = '#82c7ff'; $dark.palette.neutralSecondary = '#c8c6c4'
        Rules (Test-MgTheme -Theme $dark) | Should -Be @('TH006')
        $dark.isInverted = $true
        @(Test-MgTheme -Theme $dark) | Should -HaveCount 0
    }
}

Describe 'PNG size' {
    It 'reads width and height from the header of the shipped logos' {
        $s = Get-MgPngSize -Path (Join-Path $bpDir 'assets' 'contoso-globalnav-20.png')
        "$($s.Width)x$($s.Height)" | Should -Be '20x20'
        (Get-MgPngSize -Path (Join-Path $badDir 'assets' 'logo-big.png')).Width | Should -Be 512
        Set-Content -Path (Join-Path $TestDrive 'x.png') -Value 'not a png'
        Get-MgPngSize -Path (Join-Path $TestDrive 'x.png') | Should -BeNullOrEmpty
    }
}

Describe 'Test-MgIntranet' {
    It 'the Contoso blueprint is clean' {
        @(Test-MgIntranet -Blueprint $bp -BaseDir $bpDir) | Should -HaveCount 0
    }

    It 'finds every mistake in the bad blueprint: 6 errors, 6 warnings' {
        $f = @(Test-MgIntranet -Blueprint $bad -BaseDir $badDir)
        @($f | Where-Object Severity -eq 'Error') | Should -HaveCount 6
        @($f | Where-Object Severity -eq 'Warning') | Should -HaveCount 6
        (Rules $f | Sort-Object -Unique) -join ',' | Should -Be 'HN007,IN001,IN002,IN004,IN005,IN006,IN007,IN009,TH003'
    }

    It 'IN003 above 100 news sites; IN004 above 30 asset libraries' {
        $b = Copy-Json $bp
        $b.orgNewsSites = @(1..101 | ForEach-Object { "/sites/News$_" })
        $b.orgAssets.libraries = @(1..31 | ForEach-Object { [pscustomobject]@{ url = "/sites/Intranet/Lib$_"; type = 'ImageDocumentLibrary' } })
        (Rules (Test-MgIntranet -Blueprint $b -BaseDir $bpDir) | Sort-Object) -join ',' | Should -Be 'IN003,IN004'
    }

    It 'IN008: an image above 300 KB, and a missing file' {
        $big = Join-Path $TestDrive 'hero.png'
        [System.IO.File]::WriteAllBytes($big, [byte[]]::new(301KB))
        $b = Copy-Json $bp
        $b.orgAssets.libraries[0].files = @($big, 'assets/missing.png')
        $f = @(Test-MgIntranet -Blueprint $b -BaseDir $bpDir)
        Rules $f | Should -Be @('IN008', 'IN008')
        ($f | Where-Object Severity -eq 'Error').Message | Should -BeLike 'File not found*'
    }

    It 'global navigation runs the episode 7 navigation rules, and hubs must be in it' {
        $b = Copy-Json $bp
        $b.globalNavigation.nodes[0].children[0].children = @($b.globalNavigation.nodes[0].children[0].children | Where-Object url -ne '/sites/Operations')
        $b.globalNavigation.audienceTargeting = $false
        (Rules (Test-MgIntranet -Blueprint $b -BaseDir $bpDir) | Sort-Object) -join ',' | Should -Be 'HN005,IN005'
    }

    It 'IN009: a separate global navigation set on a home site that is not a hub is only a warning' {
        $b = Copy-Json $bp; $b.globalNavigation.source = 'hubOrGlobalNavigation'
        $f = @(Test-MgIntranet -Blueprint $b -BaseDir $bpDir)
        Rules $f | Should -Be @('IN009'); $f[0].Severity | Should -Be 'Warning'
    }
}

Describe 'Test-MgIntranetLive' {
    It 'a tenant that matches the blueprint has no findings' {
        @(Test-MgIntranetLive -Blueprint $bp -State (Good-State) -Theme $theme -AudienceIds $ids) | Should -HaveCount 0
    }

    It 'IL001-IL006: home site, news, assets, theme, visitors and navigation drift' {
        $s = Good-State
        $s.HomeSite = ''; $s.OrgNewsSites = @(); $s.OrgAssetLibraries = @()
        $s.Theme.Palette.themePrimary = '#00ffff'
        $s.HomeVisitors = @([pscustomobject]@{ Title = 'Alex Demo' })
        $s.Navigation = @($s.Navigation | Select-Object -First 1)
        (Rules (Test-MgIntranetLive -Blueprint $bp -State $s -Theme $theme -AudienceIds $ids) | Sort-Object -Unique) -join ',' | Should -Be 'IL001,IL002,IL003,IL004,IL005,IL006'
        $s.Theme = $null
        Rules (Test-MgIntranetLive -Blueprint $bp -State $s -Theme $theme) | Should -Contain 'IL004'
    }
}

Describe 'Tenant functions (PnP cmdlets mocked)' -Skip:(-not $hasPnP) {
    BeforeAll {
        Import-Module PnP.PowerShell -ErrorAction Stop
    }

    It 'adds the theme with its palette as a hashtable, and applies it to the home site and the hub' {
        Mock -ModuleName MgIntranet Get-PnPTenantTheme { throw 'not found' }
        Mock -ModuleName MgIntranet Add-PnPTenantTheme { }
        Mock -ModuleName MgIntranet Set-PnPWebTheme { }
        $steps = @(Invoke-MgTenantTheme -Theme $theme -ApplyTo $bp.theme.applyTo -TenantUrl $tenant)
        ($steps.Action -join ',') | Should -Be 'AddTheme,ApplyTheme,ApplyTheme'
        Should -Invoke -ModuleName MgIntranet Add-PnPTenantTheme -Times 1 -Exactly -ParameterFilter {
            "$Identity" -like '*Contoso Operations*' -or $Identity.Name -eq 'Contoso Operations'
        }
        Should -Invoke -ModuleName MgIntranet Add-PnPTenantTheme -Times 1 -Exactly -ParameterFilter { $IsInverted -eq $false -and $Overwrite }
        Should -Invoke -ModuleName MgIntranet Set-PnPWebTheme -Times 1 -Exactly -ParameterFilter { $WebUrl -eq 'https://contoso.sharepoint.com/sites/Operations' }
    }

    It 'leaves an identical theme alone (case of hex digits ignored) but still applies it' {
        $s = Good-State
        Mock -ModuleName MgIntranet Get-PnPTenantTheme { $s.Theme }
        Mock -ModuleName MgIntranet Add-PnPTenantTheme { throw 'should not add' }
        Mock -ModuleName MgIntranet Set-PnPWebTheme { }
        ((Invoke-MgTenantTheme -Theme $theme -ApplyTo '/sites/Intranet' -TenantUrl $tenant).Action) | Should -Be 'ApplyTheme'
    }

    It 'sets the home site only when it differs, and adds only the missing news sites' {
        Mock -ModuleName MgIntranet Get-PnPHomeSite { 'https://contoso.sharepoint.com/sites/OldHome' }
        Mock -ModuleName MgIntranet Set-PnPHomeSite { }
        (Invoke-MgHomeSite -Blueprint $bp -TenantUrl $tenant).Detail | Should -Be 'was /sites/oldhome'
        Should -Invoke -ModuleName MgIntranet Set-PnPHomeSite -Times 1 -Exactly -ParameterFilter { $HomeSiteUrl -eq 'https://contoso.sharepoint.com/sites/Intranet' -and $Force }
        Mock -ModuleName MgIntranet Get-PnPHomeSite { 'https://contoso.sharepoint.com/sites/Intranet' }
        @(Invoke-MgHomeSite -Blueprint $bp -TenantUrl $tenant) | Should -HaveCount 0

        Mock -ModuleName MgIntranet Get-PnPOrgNewsSite { @('https://contoso.sharepoint.com/sites/Intranet') }
        Mock -ModuleName MgIntranet Add-PnPOrgNewsSite { }
        (Invoke-MgOrgNews -Blueprint $bp -TenantUrl $tenant).Target | Should -Be '/sites/Operations'
        Should -Invoke -ModuleName MgIntranet Add-PnPOrgNewsSite -Times 1 -Exactly -ParameterFilter { "$($OrgNewsSiteUrl.Url)$OrgNewsSiteUrl" -like '*contoso.sharepoint.com/sites/Operations*' }
    }

    It 'creates the brand library, uploads the logos and registers it as an image library with its thumbnail' {
        Mock -ModuleName MgIntranet Get-PnPOrgAssetsLibrary { [pscustomobject]@{ OrgAssetsLibraries = @() } }
        Mock -ModuleName MgIntranet Get-PnPList { $null }
        Mock -ModuleName MgIntranet New-PnPList { }
        Mock -ModuleName MgIntranet Add-PnPFile { }
        Mock -ModuleName MgIntranet Add-PnPOrgAssetsLibrary { }
        $steps = @(Invoke-MgOrgAssets -Blueprint $bp -BaseDir $bpDir -TenantUrl $tenant)
        ($steps.Action -join ',') | Should -Be 'CreateLibrary,Upload,Upload,AddOrgAssets'
        Should -Invoke -ModuleName MgIntranet New-PnPList -Times 1 -Exactly -ParameterFilter { $Title -eq 'Brand Images' -and $Url -eq 'BrandImages' -and "$Template" -eq 'DocumentLibrary' }
        Should -Invoke -ModuleName MgIntranet Add-PnPFile -Times 1 -Exactly -ParameterFilter { $Path -like '*contoso-logo-64.png' }
        Should -Invoke -ModuleName MgIntranet Add-PnPOrgAssetsLibrary -Times 1 -Exactly -ParameterFilter {
            $LibraryUrl -eq 'https://contoso.sharepoint.com/sites/Intranet/BrandImages' -and "$OrgAssetType" -eq 'ImageDocumentLibrary' -and $ThumbnailUrl -like '*/BrandImages/contoso-logo-64.png'
        }
    }

    It 'does not register a library twice' {
        Mock -ModuleName MgIntranet Get-PnPOrgAssetsLibrary { [pscustomobject]@{ OrgAssetsLibraries = @([pscustomobject]@{ LibraryUrl = [pscustomobject]@{ DecodedUrl = 'sites/Intranet/BrandImages' } }) } }
        Mock -ModuleName MgIntranet Get-PnPList { [pscustomobject]@{ Title = 'Brand Images' } }
        Mock -ModuleName MgIntranet Add-PnPFile { }
        Mock -ModuleName MgIntranet Add-PnPOrgAssetsLibrary { throw 'should not register' }
        $b = Copy-Json $bp; $b.orgAssets.libraries[0].files = @()
        @(Invoke-MgOrgAssets -Blueprint $b -BaseDir $bpDir -TenantUrl $tenant) | Should -HaveCount 0
    }

    It 'builds the home site navigation (the global navigation source) with the episode 7 module' {
        Mock -ModuleName MgIntranet Get-PnPWeb { [pscustomobject]@{ NavAudienceTargetingEnabled = $false; MegaMenuEnabled = $false } }
        Mock -ModuleName MgIntranet Set-PnPWeb { }
        Mock -ModuleName MgHubNav Get-PnPNavigationNode { @() }
        Mock -ModuleName MgHubNav Remove-PnPNavigationNode { }
        $script:nextId = 100
        Mock -ModuleName MgHubNav Add-PnPNavigationNode { $script:nextId++; [pscustomobject]@{ Id = $script:nextId } }
        $steps = @(Invoke-MgGlobalNavigation -Blueprint $bp -TenantUrl $tenant -AudienceIds $ids)
        Should -Invoke -ModuleName MgIntranet Set-PnPWeb -Times 1 -Exactly -ParameterFilter { $NavAudienceTargetingEnabled -eq $true -and $MegaMenuEnabled -eq $true }
        Should -Invoke -ModuleName MgHubNav Add-PnPNavigationNode -Times 12 -Exactly -ParameterFilter { "$Location" -eq 'TopNavigationBar' }
        Should -Invoke -ModuleName MgHubNav Add-PnPNavigationNode -Times 1 -Exactly -ParameterFilter { $Title -eq 'Purchasing team' -and @($AudienceIds) -contains $ids['Purchasing Team'] }
        Should -Invoke -ModuleName MgHubNav Remove-PnPNavigationNode -Times 0
        @($steps | Where-Object Action -eq 'AddNode') | Should -HaveCount 12
        $b = Copy-Json $bp; $b.globalNavigation.source = 'hubOrGlobalNavigation'
        (Invoke-MgGlobalNavigation -Blueprint $b -TenantUrl $tenant).Action | Should -Be 'Skip'
    }

    It 'Get-MgIntranetState + Test-MgIntranetLive: the read-back of a matching tenant has no findings' {
        $s = Good-State
        Mock -ModuleName MgIntranet Get-PnPOrgAssetsLibrary { [pscustomobject]@{ OrgAssetsLibraries = @([pscustomobject]@{ LibraryUrl = [pscustomobject]@{ DecodedUrl = "$tenant/sites/Intranet/BrandImages" } }) } }
        Mock -ModuleName MgIntranet Get-PnPGroup { [pscustomobject]@{ Title = 'Contoso Intranet Visitors' } }
        Mock -ModuleName MgIntranet Get-PnPGroupMember { $s.HomeVisitors }
        Mock -ModuleName MgIntranet Get-PnPGroupMember -ParameterFilter { -not "$Group$($Group.Name)".Contains('Visitors') } { throw 'wrong group' }
        Mock -ModuleName MgIntranet Get-PnPHomeSite { $s.HomeSite }
        Mock -ModuleName MgIntranet Get-PnPOrgNewsSite { $s.OrgNewsSites }
        Mock -ModuleName MgIntranet Get-PnPTenantTheme { $s.Theme }
        Mock -ModuleName MgIntranet Get-MgLiveNavigation { $s.Navigation }
        $state = Get-MgIntranetState -Blueprint $bp -Theme $theme
        Should -Invoke -ModuleName MgIntranet Get-PnPGroup -Times 1 -Exactly -ParameterFilter { $AssociatedVisitorGroup }
        @(Test-MgIntranetLive -Blueprint $bp -State $state -Theme $theme -AudienceIds $ids) | Should -HaveCount 0
    }
}

Describe 'Entry script' {
    It 'parses, and its lint-only mode reports the bad blueprint' {
        $path = Join-Path $src 'Invoke-IntranetDesign.ps1'
        $errors = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errors)
        $errors | Should -HaveCount 0
        $out = & pwsh -NoProfile -Command "& '$path' -BlueprintPath '$(Join-Path $badDir 'bad-intranet.json')' *>&1 | Out-String"
        ($out -join "`n") | Should -Match '6 error\(s\), 6 warning\(s\)'
    }
}
