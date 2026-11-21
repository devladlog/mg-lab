#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
# Invoke-Pester ./tests -Output Detailed
# The tenant tests mock the real PnP.PowerShell cmdlets (Pester copies their parameter metadata, so a wrong
# parameter name or type fails the test). They are skipped when PnP.PowerShell isn't installed.

BeforeDiscovery {
    $script:hasPnP = [bool](Get-Module -ListAvailable PnP.PowerShell)
}

BeforeAll {
    $script:src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'MgHubNav.psm1') -Force
    $script:plan = Import-MgJson -Path (Join-Path $src 'hub' 'operations.hub.json')
    $script:bad = Import-MgJson -Path (Join-Path $src 'bad' 'bad.hub.json')
    $script:hubs = @(Import-MgJson -Path (Join-Path $src 'fixtures' 'tenant-hubs.json'))
    $script:tenant = 'https://contoso.sharepoint.com'
    $script:ids = @{ 'Purchasing Team' = [guid]'00000000-0000-0000-0000-0000000000b1'; 'Facilities Team' = [guid]'00000000-0000-0000-0000-0000000000b2' }

    function Rules($f) { @($f | Where-Object { $null -ne $_ } | ForEach-Object Rule) }
    function Copy-Json($o) { $o | ConvertTo-Json -Depth 30 | ConvertFrom-Json -Depth 30 }
    function Nav([object[]]$Nodes, [bool]$Targeting = $true) { [pscustomobject]@{ megaMenu = $true; audienceTargeting = $Targeting; nodes = $Nodes } }
    function Link([string]$Title, [string]$Url, [string[]]$Audiences) {
        $n = [ordered]@{ title = $Title; url = $Url }; if ($Audiences) { $n.audiences = $Audiences }; [pscustomobject]$n
    }
    function Label([string]$Title, [object[]]$Children, [string[]]$Audiences) {
        $n = [ordered]@{ title = $Title; children = $Children }; if ($Audiences) { $n.audiences = $Audiences }; [pscustomobject]$n
    }
    # What Get-MgLiveNavigation returns for a navigation that matches the plan (audience IDs, absolute URLs).
    function Live-FromPlan($Nodes) {
        foreach ($n in @($Nodes)) {
            $kids = if ($n.PSObject.Properties['children']) { @(Live-FromPlan $n.children) } else { @() }
            $aud = if ($n.PSObject.Properties['audiences']) { @($n.audiences | ForEach-Object { "$($ids[$_])" }) } else { @() }
            $url = if ($n.PSObject.Properties['url']) { "$tenant$($n.url)" } else { 'http://linkless.header/' }
            [pscustomobject]@{ Id = 1; Title = $n.title; Url = $url; Audiences = $aud; Children = $kids }
        }
    }
    function Good-State {
        [pscustomobject]@{
            Hub = [pscustomobject]@{ ID = '00000000-0000-0000-0000-0000000000c1'; Title = 'Contoso Operations'; SiteUrl = "$tenant/sites/Operations"
                Description = 'Purchasing, facilities and the services that keep Contoso running'; LogoUrl = "$tenant/sites/Operations/SiteAssets/operations-logo.png"
                HideNameInNavigation = $false; RequiresJoinApproval = $false; ParentHubSiteId = [guid]::Empty }
            Children = @("$tenant/sites/Purchasing", "$tenant/sites/Facilities")
            AllHubs = @($hubs) + [pscustomobject]@{ ID = '00000000-0000-0000-0000-0000000000c1'; Title = 'Contoso Operations'; SiteUrl = "$tenant/sites/Operations"; ParentHubSiteId = [guid]::Empty }
            Navigation = @(Live-FromPlan $plan.navigation.nodes)
            Web = [pscustomobject]@{ NavAudienceTargetingEnabled = $true; MegaMenuEnabled = $true }
        }
    }
}

Describe 'Test-MgHubPlan' {
    It 'the Contoso Operations plan is clean' {
        @(Test-MgHubPlan -Plan $plan) | Should -HaveCount 0
    }

    It 'finds every mistake in the bad plan: 10 errors, 8 warnings' {
        $f = @(Test-MgHubPlan -Plan $bad)
        @($f | Where-Object Severity -eq 'Error') | Should -HaveCount 10
        @($f | Where-Object Severity -eq 'Warning') | Should -HaveCount 8
        (Rules $f | Sort-Object -Unique) -join ',' | Should -Be 'HB002,HB003,HB004,HB005,HB006,HB007,HN001,HN004,HN005,HN007,HN008,HN009,HN010,HN011,HN012,HN013'
    }

    It 'HB001: the hub must be a site collection URL' {
        $p = Copy-Json $plan; $p.hub.url = '/sites/Operations/SitePages'
        Rules (Test-MgHubPlan -Plan $p) | Should -Contain 'HB001'
    }

    It 'HB002 is only an error without a logo' {
        $p = Copy-Json $plan; $p.hub.hideNameInNavigation = $true
        @(Test-MgHubPlan -Plan $p) | Should -HaveCount 0
        $p.hub.logoUrl = $null
        Rules (Test-MgHubPlan -Plan $p) | Should -Be @('HB002')
    }

    It 'HB005: the empty GUID is refused, a real one accepted' {
        $p = Copy-Json $plan; $p.hub.siteDesignId = '00000000-0000-0000-0000-000000000000'
        Rules (Test-MgHubPlan -Plan $p) | Should -Be @('HB005')
        $p.hub.siteDesignId = '6c5d3a0e-0000-4000-8000-000000000001'
        @(Test-MgHubPlan -Plan $p) | Should -HaveCount 0
    }
}

Describe 'Test-MgNavigation (Learn limits and guidance)' {
    It 'flattens the tree with levels and inherited audiences' {
        $rows = @(Get-MgNavNodeList -Nodes $plan.navigation.nodes)
        $rows | Should -HaveCount 15
        ($rows | Where-Object Title -eq 'Supplier documents').Level | Should -Be 3
        ($rows | Where-Object Title -eq 'Supplier documents').ParentAudiences | Should -Be @('Purchasing Team')
        ($rows | Where-Object Title -eq 'Purchasing home').ParentAudiences | Should -HaveCount 0
    }

    It 'HN002 at 501 links on one level; HN003 above 100 links in total' {
        $many = 1..501 | ForEach-Object { Link "Site $_" "/sites/S$_" }
        $f = @(Test-MgNavigation -Navigation (Nav $many))
        Rules $f | Should -Contain 'HN002'
        Rules $f | Should -Contain 'HN003'
        $f = @(Test-MgNavigation -Navigation (Nav @(Label 'Sites' @(1..101 | ForEach-Object { Link "Site $_" "/sites/S$_" }))))
        Rules $f | Should -Be @('HN003')
    }

    It 'HN005: more than 10 audiences on one link' {
        $names = 1..11 | ForEach-Object { "Group $_" }
        Rules (Test-MgNavigation -Navigation (Nav @(Link 'Pay' '/sites/HR' $names)) -Audiences $names) | Should -Be @('HN005')
        Rules (Test-MgNavigation -Navigation (Nav @(Link 'Pay' '/sites/HR' $names[0..9])) -Audiences $names) | Should -HaveCount 0
    }

    It 'HN006: a child targeted outside its parent''s audience is only seen by people in both' {
        $n = Nav @(Label 'Team' @(Link 'Contracts' '/sites/Purchasing/SupplierDocuments' @('Facilities Team')) @('Purchasing Team'))
        Rules (Test-MgNavigation -Navigation $n -Audiences 'Purchasing Team', 'Facilities Team') | Should -Be @('HN006')
    }

    It 'HN008 and HN009: associated sites must be linked, private ones targeted' {
        $assoc = @([pscustomobject]@{ url = '/sites/Purchasing' }, [pscustomobject]@{ url = '/sites/PurchTeam'; private = $true })
        $n = Nav @((Link 'Purchasing' '/sites/Purchasing/SitePages/how-to-buy.aspx'), (Link 'Team' '/sites/PurchTeam'))
        Rules (Test-MgNavigation -Navigation $n -Associations $assoc -Audiences 'Purchasing Team') | Should -Be @('HN009')
        $n = Nav @((Link 'Purchasing' '/sites/Purchasing'), (Link 'Team' '/sites/PurchTeam' @('Purchasing Team')))
        @(Test-MgNavigation -Navigation $n -Associations $assoc -Audiences 'Purchasing Team') | Should -HaveCount 0
    }

    It 'openInNewTab is fine on QuickLaunch only' {
        $n = Nav @([pscustomobject]@{ title = 'Policy'; url = '/sites/HR'; openInNewTab = $true })
        Rules (Test-MgNavigation -Navigation $n) | Should -Be @('HN011')
        @(Test-MgNavigation -Navigation $n -Name 'quicklaunch') | Should -HaveCount 0
    }
}

Describe 'Test-MgHubHierarchy (hub-to-hub, three levels)' {
    It 'the fixture tenant (three levels) is fine, and so is the plan with no parent' {
        @(Test-MgHubHierarchy -Hubs $hubs -Plan $plan) | Should -HaveCount 0
    }

    It 'HH001: a parent at level 3 puts the new hub at level 4' {
        $p = Copy-Json $plan; $p.hub.parentHubUrl = '/sites/Portugal'
        $f = @(Test-MgHubHierarchy -Hubs $hubs -Plan $p)
        Rules $f | Should -Be @('HH001')
        $f[0].Target | Should -Be 'Contoso Operations'
        $p.hub.parentHubUrl = '/sites/Europe'
        @(Test-MgHubHierarchy -Hubs $hubs -Plan $p) | Should -HaveCount 0
    }

    It 'HH002 cycles, HH003 more than 2,000 hubs, HH004 a parent that isn''t a hub' {
        $loop = Copy-Json $hubs; $loop[0].ParentHubSiteId = $loop[2].ID
        Rules (Test-MgHubHierarchy -Hubs $loop) | Should -Contain 'HH002'
        $many = 1..2001 | ForEach-Object { [pscustomobject]@{ ID = [guid]::NewGuid().ToString(); Title = "Hub $_"; SiteUrl = "$tenant/sites/H$_"; ParentHubSiteId = '' } }
        Rules (Test-MgHubHierarchy -Hubs $many) | Should -Be @('HH003')
        $p = Copy-Json $plan; $p.hub.parentHubUrl = '/sites/NotAHub'
        Rules (Test-MgHubHierarchy -Hubs $hubs -Plan $p) | Should -Be @('HH004')
    }
}

Describe 'Compare-MgNavigation and Test-MgHubLive' {
    It 'a tenant that matches the plan has no differences (labels, audience IDs, absolute URLs)' {
        @(Compare-MgNavigation -PlanNodes $plan.navigation.nodes -LiveNodes (Live-FromPlan $plan.navigation.nodes) -AudienceIds $ids) | Should -HaveCount 0
        @(Test-MgHubLive -Plan $plan -State (Good-State) -TenantUrl $tenant -AudienceIds $ids) | Should -HaveCount 0
    }

    It 'reports missing, extra, renamed and re-targeted nodes' {
        $live = @(Live-FromPlan $plan.navigation.nodes)
        $live[0].Children[1].Audiences = @()                                     # someone removed the targeting
        $live[1].Title = 'Facility'
        $live = @($live[0], $live[1])                                            # 'Operations home' deleted
        $d = @(Compare-MgNavigation -PlanNodes $plan.navigation.nodes -LiveNodes $live -AudienceIds $ids)
        ($d | ForEach-Object Kind | Sort-Object) -join ',' | Should -Be 'Audience,Missing,Title'
    }

    It 'HL001-HL005: settings, associations, navigation and web drift' {
        $s = Good-State
        $s.Hub.Title = 'Operations'
        $s.Children = @("$tenant/sites/Purchasing", "$tenant/sites/Marketing")
        $s.Navigation = @($s.Navigation | Select-Object -First 2)
        $s.Web.NavAudienceTargetingEnabled = $false
        (Rules (Test-MgHubLive -Plan $plan -State $s -TenantUrl $tenant -AudienceIds $ids) | Sort-Object) -join ',' | Should -Be 'HL001,HL002,HL003,HL004,HL005'
        Rules (Test-MgHubLive -Plan $plan -State ([pscustomobject]@{ Hub = $null })) | Should -Be @('HL001')
    }

    It 'resolves server-relative URLs against the tenant' {
        ConvertTo-MgAbsoluteUrl '/sites/Purchasing' 'https://contoso.sharepoint.com/' | Should -Be 'https://contoso.sharepoint.com/sites/Purchasing'
        ConvertTo-MgAbsoluteUrl 'https://fabrikam.com/x' $tenant | Should -Be 'https://fabrikam.com/x'
    }
}

Describe 'Tenant functions (PnP cmdlets mocked)' -Skip:(-not $hasPnP) {
    BeforeAll {
        Import-Module PnP.PowerShell -ErrorAction Stop
    }

    It 'registers a new hub with who may associate, then sets title, description and logo' {
        $script:registered = $false
        Mock -ModuleName MgHubNav Get-PnPHubSite {
            if (-not $script:registered) { throw 'not a hub' }
            [pscustomobject]@{ ID = '00000000-0000-0000-0000-0000000000c1'; Title = 'Operations'; Description = ''; LogoUrl = ''; HideNameInNavigation = $false; RequiresJoinApproval = $false; ParentHubSiteId = [guid]::Empty }
        }
        Mock -ModuleName MgHubNav Register-PnPHubSite { $script:registered = $true }
        Mock -ModuleName MgHubNav Set-PnPHubSite { }
        Mock -ModuleName MgHubNav Grant-PnPHubSiteRights { }
        $steps = @(Invoke-MgHubRegistration -Plan $plan -TenantUrl $tenant)
        ($steps.Action -join ',') | Should -Be 'RegisterHub,SetHub'
        Should -Invoke -ModuleName MgHubNav Register-PnPHubSite -Times 1 -Exactly -ParameterFilter { "$Site" -like '*sites/Operations*' -or $Site.Url -like '*sites/Operations' }
        Should -Invoke -ModuleName MgHubNav Register-PnPHubSite -Times 1 -Exactly -ParameterFilter { $Principals -contains 'Operations Site Owners' }
        Should -Invoke -ModuleName MgHubNav Set-PnPHubSite -Times 1 -Exactly -ParameterFilter {
            $Title -eq 'Contoso Operations' -and $LogoUrl -eq 'https://contoso.sharepoint.com/sites/Operations/SiteAssets/operations-logo.png' -and $Description -like 'Purchasing, facilities*'
        }
        Should -Invoke -ModuleName MgHubNav Grant-PnPHubSiteRights -Times 0
    }

    It 'an existing, up-to-date hub only gets its rights re-granted' {
        $s = Good-State
        Mock -ModuleName MgHubNav Get-PnPHubSite { $s.Hub }
        Mock -ModuleName MgHubNav Register-PnPHubSite { throw 'should not register' }
        Mock -ModuleName MgHubNav Set-PnPHubSite { throw 'should not set' }
        Mock -ModuleName MgHubNav Grant-PnPHubSiteRights { }
        (@(Invoke-MgHubRegistration -Plan $plan -TenantUrl $tenant).Action -join ',') | Should -Be 'GrantRights'
        Should -Invoke -ModuleName MgHubNav Grant-PnPHubSiteRights -Times 1 -Exactly -ParameterFilter { $Principals -contains 'Operations Site Owners' }
    }

    It 'associates new sites, leaves members alone, moves sites from another hub only with -Move, never a hub' {
        Mock -ModuleName MgHubNav Get-PnPHubSite { [pscustomobject]@{ ID = '00000000-0000-0000-0000-0000000000c1' } }
        Mock -ModuleName MgHubNav Get-PnPTenantSite {
            $u = "$Identity"; if ($Identity.PSObject.Properties['Url']) { $u = $Identity.Url }
            if ($u -like '*Purchasing') { [pscustomobject]@{ HubSiteId = [guid]::Empty; IsHubSite = $false } }
            else { [pscustomobject]@{ HubSiteId = [guid]'00000000-0000-0000-0000-0000000000d9'; IsHubSite = $false } }
        }
        Mock -ModuleName MgHubNav Add-PnPHubSiteAssociation { }
        Mock -ModuleName MgHubNav Remove-PnPHubSiteAssociation { }
        $steps = @(Invoke-MgHubAssociation -Plan $plan -TenantUrl $tenant)
        ($steps.Action -join ',') | Should -Be 'Associate,Skip'
        $steps[1].Detail | Should -BeLike 'already in another hub*'
        Should -Invoke -ModuleName MgHubNav Add-PnPHubSiteAssociation -Times 1 -Exactly
        $steps = @(Invoke-MgHubAssociation -Plan $plan -TenantUrl $tenant -Move)
        ($steps.Action -join ',') | Should -Be 'Associate,LeaveHub,Associate'
        Should -Invoke -ModuleName MgHubNav Remove-PnPHubSiteAssociation -Times 1 -Exactly

        Mock -ModuleName MgHubNav Get-PnPTenantSite { [pscustomobject]@{ HubSiteId = [guid]'00000000-0000-0000-0000-0000000000c1'; IsHubSite = $false } }
        @(Invoke-MgHubAssociation -Plan $plan -TenantUrl $tenant) | Should -HaveCount 0
        Mock -ModuleName MgHubNav Get-PnPTenantSite { [pscustomobject]@{ HubSiteId = [guid]::Empty; IsHubSite = $true } }
        (@(Invoke-MgHubAssociation -Plan $plan -TenantUrl $tenant).Action | Sort-Object -Unique) | Should -Be 'Skip'
    }

    It 'turns on audience targeting and the mega menu, replaces the navigation and targets by group ID' {
        Mock -ModuleName MgHubNav Get-PnPWeb { [pscustomobject]@{ NavAudienceTargetingEnabled = $false; MegaMenuEnabled = $true } }
        Mock -ModuleName MgHubNav Set-PnPWeb { }
        Mock -ModuleName MgHubNav Get-PnPNavigationNode -ParameterFilter { -not $Id } { [pscustomobject]@{ Id = 2001; Title = 'Home' } }
        Mock -ModuleName MgHubNav Get-PnPNavigationNode -ParameterFilter { [bool]$Id } { [pscustomobject]@{ Id = 2001; Title = 'Home'; Url = '/sites/Operations'; AudienceIds = $null; Children = @() } }
        Mock -ModuleName MgHubNav Remove-PnPNavigationNode { }
        $script:nextId = 3000
        Mock -ModuleName MgHubNav Add-PnPNavigationNode { $script:nextId++; [pscustomobject]@{ Id = $script:nextId; Title = $Title } }
        $steps = @(Invoke-MgHubNavigation -Plan $plan -TenantUrl $tenant -AudienceIds $ids)
        Should -Invoke -ModuleName MgHubNav Set-PnPWeb -Times 1 -Exactly -ParameterFilter { $NavAudienceTargetingEnabled -eq $true -and -not $PSBoundParameters.ContainsKey('MegaMenuEnabled') }
        Should -Invoke -ModuleName MgHubNav Remove-PnPNavigationNode -Times 1 -Exactly -ParameterFilter { $Force }
        Should -Invoke -ModuleName MgHubNav Add-PnPNavigationNode -Times 15 -Exactly -ParameterFilter { "$Location" -eq 'TopNavigationBar' }
        Should -Invoke -ModuleName MgHubNav Add-PnPNavigationNode -Times 1 -Exactly -ParameterFilter {
            $Title -eq 'Purchasing team' -and @($AudienceIds) -contains [guid]'00000000-0000-0000-0000-0000000000b1' -and $Url -eq 'http://linkless.header/' -and $null -ne $Parent
        }
        Should -Invoke -ModuleName MgHubNav Add-PnPNavigationNode -Times 1 -Exactly -ParameterFilter {
            $Title -eq 'How to buy' -and $Url -eq 'https://contoso.sharepoint.com/sites/Purchasing/SitePages/how-to-buy.aspx' -and $External
        }
        Should -Invoke -ModuleName MgHubNav Add-PnPNavigationNode -Times 1 -Exactly -ParameterFilter { $Title -eq 'Operations home' -and -not $External -and $null -eq $Parent }
        ($steps | Where-Object Action -eq 'AddNode' | Where-Object Target -eq 'Purchasing > Purchasing team').Detail | Should -Be '(label) [targeted: Purchasing Team]'
    }

    It 'leaves a navigation that already matches the plan alone' {
        $live = @(Live-FromPlan $plan.navigation.nodes)
        Mock -ModuleName MgHubNav Get-MgLiveNavigation { $live }
        Mock -ModuleName MgHubNav Get-PnPWeb { [pscustomobject]@{ NavAudienceTargetingEnabled = $true; MegaMenuEnabled = $true } }
        Mock -ModuleName MgHubNav Set-PnPWeb { throw 'should not set' }
        Mock -ModuleName MgHubNav Remove-PnPNavigationNode { throw 'should not remove' }
        Mock -ModuleName MgHubNav Add-PnPNavigationNode { throw 'should not add' }
        (@(Invoke-MgHubNavigation -Plan $plan -TenantUrl $tenant -AudienceIds $ids).Action) | Should -Be 'NavUpToDate'
    }

    It 'reads the live navigation recursively, with audience IDs' {
        Mock -ModuleName MgHubNav Get-PnPNavigationNode -ParameterFilter { -not $Id } { [pscustomobject]@{ Id = 1 } }
        Mock -ModuleName MgHubNav Get-PnPNavigationNode -ParameterFilter { $Id -eq 1 } {
            [pscustomobject]@{ Id = 1; Title = 'Purchasing'; Url = 'http://linkless.header/'; AudienceIds = $null; Children = @([pscustomobject]@{ Id = 2 }) }
        }
        Mock -ModuleName MgHubNav Get-PnPNavigationNode -ParameterFilter { $Id -eq 2 } {
            [pscustomobject]@{ Id = 2; Title = 'Team'; Url = '/sites/Purchasing'; AudienceIds = [System.Collections.Generic.List[guid]]@([guid]'00000000-0000-0000-0000-0000000000b1'); Children = @() }
        }
        $n = @(Get-MgLiveNavigation)
        $n[0].Children[0].Title | Should -Be 'Team'
        $n[0].Children[0].Audiences | Should -Be @('00000000-0000-0000-0000-0000000000b1')
        Should -Invoke -ModuleName MgHubNav Get-PnPNavigationNode -Times 1 -Exactly -ParameterFilter { "$Location" -eq 'TopNavigationBar' }
    }

    It 'resolves audiences: a GUID as is, a name through Get-PnPEntraIDGroup' {
        $p = Copy-Json $plan; $p.audiences.'Facilities Team' = '00000000-0000-0000-0000-0000000000b2'
        Mock -ModuleName MgHubNav Get-PnPEntraIDGroup { [pscustomobject]@{ Id = '00000000-0000-0000-0000-0000000000b1'; DisplayName = 'Purchasing Team' } }
        $m = Resolve-MgAudience -Plan $p
        $m['Purchasing Team'] | Should -Be ([guid]'00000000-0000-0000-0000-0000000000b1')
        $m['Facilities Team'] | Should -Be ([guid]'00000000-0000-0000-0000-0000000000b2')
        Should -Invoke -ModuleName MgHubNav Get-PnPEntraIDGroup -Times 1 -Exactly
        Mock -ModuleName MgHubNav Get-PnPEntraIDGroup { }
        { Resolve-MgAudience -Plan $p } | Should -Throw '*found 0 groups*'
    }

    It 'Get-MgHubState + Test-MgHubLive: the read-back of a tenant that matches the plan has no findings' {
        $s = Good-State
        Mock -ModuleName MgHubNav Get-PnPHubSite -ParameterFilter { $Identity } { $s.Hub }
        Mock -ModuleName MgHubNav Get-PnPHubSite -ParameterFilter { -not $Identity } { $s.AllHubs }
        Mock -ModuleName MgHubNav Get-PnPHubSiteChild { $s.Children }
        Mock -ModuleName MgHubNav Get-MgLiveNavigation { $s.Navigation }
        Mock -ModuleName MgHubNav Get-PnPWeb { $s.Web }
        $state = Get-MgHubState -Plan $plan -TenantUrl $tenant
        @($state.AllHubs) | Should -HaveCount 4
        @(Test-MgHubLive -Plan $plan -State $state -TenantUrl $tenant -AudienceIds $ids) | Should -HaveCount 0
    }
}

Describe 'Entry script' {
    It 'parses, and its lint-only mode reports the bad plan' {
        $path = Join-Path $src 'Invoke-HubNavigation.ps1'
        $errors = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errors)
        $errors | Should -HaveCount 0
        $out = & pwsh -NoProfile -Command "& '$path' -PlanPath '$(Join-Path $src 'bad' 'bad.hub.json')' *>&1 | Out-String"
        ($out -join "`n") | Should -Match '10 error\(s\), 8 warning\(s\)'
    }
}
