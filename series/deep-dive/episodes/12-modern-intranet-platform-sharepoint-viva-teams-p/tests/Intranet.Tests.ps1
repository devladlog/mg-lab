# PnP.PowerShell is IMPORTED here, so Pester copies the real cmdlet signatures into every mock: a misspelt or
# wrong parameter in the module fails these tests. State lives in an in-memory "tenant" ($global:IntranetWorld),
# used only by the tests.
BeforeAll {
    Import-Module PnP.PowerShell -ErrorAction Stop
    $script:Root = Join-Path $PSScriptRoot '..'
    Import-Module (Join-Path $script:Root 'provision' 'Intranet.psm1') -Force
    $script:ContractPath = Join-Path $script:Root 'contract' 'intranet.json'
    $script:ScriptPath = Join-Path $script:Root 'site-scripts' 'intranet-site.json'
    $script:Contract = Read-IntranetContract -Path $script:ContractPath
    $script:Admin = [System.Runtime.CompilerServices.RuntimeHelpers]::GetUninitializedObject([PnP.PowerShell.Commands.Base.PnPConnection])
    $script:HubConn = $script:Admin
    $script:ConnectHub = { param($url) $global:IntranetWorld.HubConnectedTo = $url; $script:HubConn }

    function Invoke-Run([switch] $WhatIf) {
        Invoke-IntranetProvisioning -Contract $script:Contract -ScriptPath $script:ScriptPath -AdminConnection $script:Admin -ConnectHub $script:ConnectHub -WhatIf:$WhatIf
    }
    function Get-Health { Test-IntranetHealth -Contract $script:Contract -AdminConnection $script:Admin -ConnectHub $script:ConnectHub }
    function Copy-Contract { $script:Contract | ConvertTo-Json -Depth 20 | ConvertFrom-Json -Depth 20 }
    function New-World { @{ Sites = [System.Collections.Generic.List[string]]::new(); Hubs = [System.Collections.Generic.List[string]]::new()
        Children = [System.Collections.Generic.List[string]]::new(); Nav = [System.Collections.Generic.List[object]]::new()
        Home = $null; Scripts = [System.Collections.Generic.List[object]]::new(); Designs = [System.Collections.Generic.List[object]]::new()
        Calls = [System.Collections.Generic.List[string]]::new(); NewSite = [System.Collections.Generic.List[object]]::new(); HomeArgs = $null; HubConnectedTo = $null } }
}

Describe 'Contract' {
    It 'the shipped contract is valid' { (Test-IntranetContract -Contract $script:Contract).Count | Should -Be 0 }
    It 'rejects bad, duplicate and upper-case aliases' {
        $c = Copy-Contract; $c.spokes[0].alias = 'HR Site'; $c.spokes[1].alias = $c.spokes[2].alias
        $p = Test-IntranetContract -Contract $c
        $p | Should -Contain "Alias 'HR Site' must be 3-40 lower-case letters, digits or hyphens."
        ($p -join ' ') | Should -Match "used twice"
    }
    It 'requires the home site to be the hub' {
        $c = Copy-Contract; $c.homeSite.alias = 'contoso-hr'
        (Test-IntranetContract -Contract $c) -join ' ' | Should -Match 'home site must be the hub'
    }
    It 'rejects navigation to an unknown site, http links, and departments missing from the navigation' {
        $c = Copy-Contract; $c.hubNavigation[0].site = 'contoso-nope'; $c.hubNavigation[3].url = 'http://expenses.contoso.example'
        $p = (Test-IntranetContract -Contract $c) -join ' '
        $p | Should -Match "unknown site 'contoso-nope'"
        $p | Should -Match 'must use https'
        $p | Should -Match "'contoso-hr' is not in the hub navigation"
    }
    It 'builds site URLs from the tenant name' {
        Get-IntranetSiteUrl -TenantName 'contoso' -Alias 'contoso-hr' | Should -Be 'https://contoso.sharepoint.com/sites/contoso-hr'
    }
}

Describe 'Site script' {
    It 'uses only verbs Learn lists, valid enums, and no tenant-specific hub id' {
        (Test-IntranetSiteVerbs -Path $script:ScriptPath).Count | Should -Be 0
    }
    It 'rejects an unknown verb, joinHubSite and a bad layout' {
        $tmp = Join-Path ([IO.Path]::GetTempPath()) "site-$([guid]::NewGuid()).json"
        '{"actions":[{"verb":"makeCoffee"},{"verb":"joinHubSite","hubSiteId":"00000000-0000-0000-0000-000000000000"},{"verb":"setSiteBranding","navigationLayout":"Wide","headerLayout":"Compact","headerBackground":"None"}]}' | Set-Content $tmp
        try {
            $p = (Test-IntranetSiteVerbs -Path $tmp) -join ' '
            $p | Should -Match "Unknown verb 'makeCoffee'"
            $p | Should -Match 'joinHubSite carries'
            $p | Should -Match "Bad navigationLayout 'Wide'"
        } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
    }
    It 'creates the News Requests list with exactly the columns the contract and the flow use' {
        $s = Get-Content $script:ScriptPath -Raw | ConvertFrom-Json -Depth 30
        $list = $s.actions | Where-Object verb -eq 'createSPList'
        $list.listName | Should -Be $script:Contract.newsRequests.listTitle
        $names = @($list.subactions | Where-Object { $_.internalName } | ForEach-Object internalName) + @([regex]::Matches((($list.subactions | Where-Object verb -eq 'addSPFieldXml').schemaXml), 'StaticName="(\w+)"') | ForEach-Object { $_.Groups[1].Value })
        foreach ($c in $script:Contract.newsRequests.columns | Where-Object { $_ -ne 'Title' }) { $names | Should -Contain $c }
        $xml = ($list.subactions | Where-Object verb -eq 'addSPFieldXml').schemaXml
        foreach ($status in $script:Contract.newsRequests.statuses) { $xml | Should -Match "<CHOICE>$status</CHOICE>" }
    }
    It 'gives every field a fixed id, so re-running the script does not duplicate columns (Learn)' {
        $s = Get-Content $script:ScriptPath -Raw | ConvertFrom-Json -Depth 30
        $subs = ($s.actions | Where-Object verb -eq 'createSPList').subactions | Where-Object { $_.verb -like 'addSPField*' }
        foreach ($f in $subs) { ($f.id ?? $f.schemaXml) | Should -Match '[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}' }
    }
}

Describe 'Provisioning' {
    BeforeEach {
        $global:IntranetWorld = New-World
        Mock -ModuleName Intranet Get-PnPSiteScript { $global:IntranetWorld.Scripts }
        Mock -ModuleName Intranet Add-PnPSiteScript { $o = [pscustomobject]@{ Id = [guid]::NewGuid(); Title = $Title; Content = $Content }; $global:IntranetWorld.Scripts.Add($o); $global:IntranetWorld.Calls.Add('Add-PnPSiteScript'); $o }
        Mock -ModuleName Intranet Set-PnPSiteScript { $global:IntranetWorld.Calls.Add('Set-PnPSiteScript') }
        Mock -ModuleName Intranet Get-PnPSiteDesign { $global:IntranetWorld.Designs }
        Mock -ModuleName Intranet Add-PnPSiteDesign { $o = [pscustomobject]@{ Id = [guid]::NewGuid(); Title = $Title; Template = "$WebTemplate"; Scripts = $SiteScriptIds }; $global:IntranetWorld.Designs.Add($o); $global:IntranetWorld.Calls.Add('Add-PnPSiteDesign'); $o }
        Mock -ModuleName Intranet Set-PnPSiteDesign { $global:IntranetWorld.Calls.Add('Set-PnPSiteDesign') }
        Mock -ModuleName Intranet Get-PnPTenantSite { if ($global:IntranetWorld.Sites -contains $Identity.Url) { [pscustomobject]@{ Url = $Identity.Url } } }
        Mock -ModuleName Intranet New-PnPSite { $global:IntranetWorld.Sites.Add($Url); $global:IntranetWorld.NewSite.Add(@{ Url = $Url; Type = $Type; Title = $Title; SiteDesignId = $SiteDesignId; Wait = $Wait }); $global:IntranetWorld.Calls.Add('New-PnPSite') }
        Mock -ModuleName Intranet Get-PnPHubSite { if ($global:IntranetWorld.Hubs -contains $Identity.Url) { [pscustomobject]@{ SiteUrl = $Identity.Url } } }
        Mock -ModuleName Intranet Register-PnPHubSite { $global:IntranetWorld.Hubs.Add($Site.Url); $global:IntranetWorld.Calls.Add('Register-PnPHubSite') }
        Mock -ModuleName Intranet Set-PnPHubSite { $global:IntranetWorld.Calls.Add('Set-PnPHubSite') }
        Mock -ModuleName Intranet Get-PnPHubSiteChild { $global:IntranetWorld.Children }
        Mock -ModuleName Intranet Add-PnPHubSiteAssociation { $global:IntranetWorld.Children.Add($Site.Url); $global:IntranetWorld.Calls.Add("Add-PnPHubSiteAssociation $($Site.Url)") }
        Mock -ModuleName Intranet Get-PnPNavigationNode { $global:IntranetWorld.Nav }
        Mock -ModuleName Intranet Add-PnPNavigationNode { $global:IntranetWorld.Nav.Add([pscustomobject]@{ Title = $Title; Url = $Url; External = [bool]$External; Location = "$Location" }); $global:IntranetWorld.Calls.Add('Add-PnPNavigationNode') }
        Mock -ModuleName Intranet Get-PnPHomeSite { $global:IntranetWorld.Home }
        Mock -ModuleName Intranet Set-PnPHomeSite { $global:IntranetWorld.Home = $HomeSiteUrl; $global:IntranetWorld.HomeArgs = @{ Viva = [bool]$VivaConnectionsDefaultStart; Draft = [bool]$DraftMode }; $global:IntranetWorld.Calls.Add('Set-PnPHomeSite') }
    }

    It 'builds everything from an empty tenant, in a safe order' {
        $r = @(Invoke-Run)
        $w = $global:IntranetWorld
        $w.Sites.Count | Should -Be 4
        $w.Hubs | Should -Be @('https://contoso.sharepoint.com/sites/contoso-home')
        $w.Children.Count | Should -Be 3
        $w.Nav.Count | Should -Be 4
        $w.Home | Should -Be 'https://contoso.sharepoint.com/sites/contoso-home'
        # the design exists before any site is created, and the hub is created before the departments
        $w.Calls.IndexOf('Add-PnPSiteDesign') | Should -BeLessThan $w.Calls.IndexOf('New-PnPSite')
        $w.NewSite[0].Url | Should -Be 'https://contoso.sharepoint.com/sites/contoso-home'
        $w.Calls.IndexOf('Register-PnPHubSite') | Should -BeLessThan $w.Calls.IndexOf('Add-PnPHubSiteAssociation https://contoso.sharepoint.com/sites/contoso-hr')
        ($r | Where-Object Action -in 'Created', 'Registered', 'Associated', 'Added', 'Set').Count | Should -BeGreaterThan 10
    }
    It 'creates every site as a communication site with the design and waits for it' {
        Invoke-Run | Out-Null
        $designId = $global:IntranetWorld.Designs[0].Id
        foreach ($s in $global:IntranetWorld.NewSite) {
            $s.Type | Should -Be 'CommunicationSite'
            $s.SiteDesignId | Should -Be $designId
            $s.Wait | Should -BeTrue
        }
        $global:IntranetWorld.Designs[0].Template | Should -Be 'CommunicationSite'
    }
    It 'writes the hub navigation on the hub site, with the external link marked external' {
        Invoke-Run | Out-Null
        $global:IntranetWorld.HubConnectedTo | Should -Be 'https://contoso.sharepoint.com/sites/contoso-home'
        $global:IntranetWorld.Nav.Location | Select-Object -Unique | Should -Be 'TopNavigationBar'
        ($global:IntranetWorld.Nav | Where-Object Title -eq 'Expenses').External | Should -BeTrue
        ($global:IntranetWorld.Nav | Where-Object Title -eq 'IT Help').Url | Should -Be 'https://contoso.sharepoint.com/sites/contoso-it'
        ($global:IntranetWorld.Nav | Where-Object Title -eq 'IT Help').External | Should -BeFalse
    }
    It 'sets the home site in draft mode with Viva Connections as the default start, as the contract says' {
        Invoke-Run | Out-Null
        $global:IntranetWorld.HomeArgs.Viva | Should -BeTrue
        $global:IntranetWorld.HomeArgs.Draft | Should -BeTrue
    }
    It 'is idempotent: a second run changes nothing but refreshes the site script and design' {
        Invoke-Run | Out-Null
        $global:IntranetWorld.Calls.Clear()
        $r = @(Invoke-Run)
        ($r | Where-Object Step -in 'Site', 'Hub', 'Association', 'HubNavigation', 'HomeSite' | Where-Object Action -ne 'Exists').Count | Should -Be 0
        $global:IntranetWorld.Calls | Should -Not -Contain 'New-PnPSite'
        $global:IntranetWorld.Calls | Should -Not -Contain 'Register-PnPHubSite'
        $global:IntranetWorld.Calls | Should -Not -Contain 'Add-PnPNavigationNode'
        $global:IntranetWorld.Calls | Should -Not -Contain 'Set-PnPHomeSite'
        $global:IntranetWorld.Calls | Should -Not -Contain 'Add-PnPSiteScript'
        $global:IntranetWorld.Calls | Should -Contain 'Set-PnPSiteScript'
        $global:IntranetWorld.Calls | Should -Contain 'Set-PnPSiteDesign'
    }
    It 'completes a half-built intranet: only the missing department and link are added' {
        Invoke-Run | Out-Null
        $w = $global:IntranetWorld
        $w.Children.Remove('https://contoso.sharepoint.com/sites/contoso-ops') | Out-Null
        $w.Nav.RemoveAt(2)   # Operations link
        $w.Calls.Clear()
        Invoke-Run | Out-Null
        ($w.Calls | Where-Object { $_ -like 'Add-PnPHubSiteAssociation*' }) | Should -Be @('Add-PnPHubSiteAssociation https://contoso.sharepoint.com/sites/contoso-ops')
        ($w.Calls | Where-Object { $_ -eq 'Add-PnPNavigationNode' }).Count | Should -Be 1
    }
    It 'accepts hub children returned as objects instead of URL strings' {
        Mock -ModuleName Intranet Get-PnPHubSiteChild { $global:IntranetWorld.Children | ForEach-Object { [pscustomobject]@{ SiteUrl = "$_/" } } }
        Invoke-Run | Out-Null
        $global:IntranetWorld.Calls.Clear()
        Invoke-Run | Out-Null
        ($global:IntranetWorld.Calls | Where-Object { $_ -like 'Add-PnPHubSiteAssociation*' }).Count | Should -Be 0
    }
    It '-WhatIf changes nothing' {
        $r = @(Invoke-Run -WhatIf)
        $w = $global:IntranetWorld
        $w.Calls.Count | Should -Be 0
        $w.Sites.Count | Should -Be 0
        $w.Home | Should -BeNullOrEmpty
        ($r | Where-Object Action -eq 'WhatIf').Count | Should -BeGreaterThan 5
    }
    It 'refuses an invalid contract or script before touching the tenant' {
        $c = Copy-Contract; $c.spokes[0].alias = 'BAD'
        { Invoke-IntranetProvisioning -Contract $c -ScriptPath $script:ScriptPath -AdminConnection $script:Admin -ConnectHub $script:ConnectHub } | Should -Throw '*Contract is not valid*'
        $global:IntranetWorld.Calls.Count | Should -Be 0
    }
}

Describe 'Health check' {
    BeforeEach {
        $global:IntranetWorld = New-World
        Mock -ModuleName Intranet Get-PnPSiteDesign { $global:IntranetWorld.Designs }
        Mock -ModuleName Intranet Get-PnPHubSite { if ($global:IntranetWorld.Hubs -contains $Identity.Url) { [pscustomobject]@{ SiteUrl = $Identity.Url } } }
        Mock -ModuleName Intranet Get-PnPHubSiteChild { $global:IntranetWorld.Children }
        Mock -ModuleName Intranet Get-PnPNavigationNode { $global:IntranetWorld.Nav }
        Mock -ModuleName Intranet Get-PnPHomeSite { $global:IntranetWorld.Home }
        $w = $global:IntranetWorld
        $w.Hubs.Add('https://contoso.sharepoint.com/sites/contoso-home')
        'hr', 'it', 'ops' | ForEach-Object { $w.Children.Add("https://contoso.sharepoint.com/sites/contoso-$_") }
        $w.Home = 'https://contoso.sharepoint.com/sites/contoso-home'
        $w.Designs.Add([pscustomobject]@{ Id = [guid]::NewGuid(); Title = 'Contoso intranet site' })
        foreach ($n in $script:Contract.hubNavigation) {
            $u = if ($null -ne $n.PSObject.Properties['site']) { "https://contoso.sharepoint.com/sites/$($n.site)" } else { $n.url }
            $w.Nav.Add([pscustomobject]@{ Title = $n.title; Url = $u })
        }
    }

    It 'passes on a healthy intranet' {
        $rows = Get-Health
        ($rows | Where-Object Status -eq 'Fail').Count | Should -Be 0
        $rows.Count | Should -BeGreaterThan 10
    }
    It 'fails when the home site is something else' {
        $global:IntranetWorld.Home = 'https://contoso.sharepoint.com/sites/old-portal'
        (Get-Health | Where-Object { $_.Status -eq 'Fail' }).Check | Should -Contain 'Home site is the hub'
    }
    It 'fails for a department that left the hub, and for a site nobody planned' {
        $global:IntranetWorld.Children.Remove('https://contoso.sharepoint.com/sites/contoso-it') | Out-Null
        $global:IntranetWorld.Children.Add('https://contoso.sharepoint.com/sites/random-team')
        $fails = Get-Health | Where-Object Status -eq 'Fail'
        ($fails | Where-Object Check -eq 'Department in hub').Target | Should -Be 'https://contoso.sharepoint.com/sites/contoso-it'
        ($fails | Where-Object Check -eq 'No unknown sites in the hub').Detail | Should -Match 'random-team'
    }
    It 'fails for a missing or wrong navigation link' {
        $global:IntranetWorld.Nav.RemoveAt(0)
        ($global:IntranetWorld.Nav | Where-Object Title -eq 'IT Help').Url = 'https://contoso.sharepoint.com/sites/somewhere-else'
        $fails = Get-Health | Where-Object Status -eq 'Fail'
        ($fails | Where-Object Target -eq 'People and Culture').Detail | Should -Be 'Missing.'
        ($fails | Where-Object Target -eq 'IT Help').Detail | Should -Match 'somewhere-else'
    }
    It 'is read-only: it calls no cmdlet that changes anything' {
        Get-Health | Out-Null
        foreach ($cmd in 'New-PnPSite', 'Register-PnPHubSite', 'Add-PnPHubSiteAssociation', 'Add-PnPNavigationNode', 'Set-PnPHomeSite', 'Add-PnPSiteDesign', 'Add-PnPSiteScript') {
            $text = Get-Content (Join-Path $script:Root 'provision' 'Intranet.psm1') -Raw
            $body = [regex]::Match($text, 'function Test-IntranetHealth \{(.*?)\r?\nExport-ModuleMember', 'Singleline').Groups[1].Value
            $body | Should -Not -Match $cmd
        }
    }
}

Describe 'Entry scripts' {
    It 'parse, take the tenant and the app registration, and the provisioning one supports -WhatIf' {
        foreach ($f in 'Initialize-Intranet.ps1', 'Test-Intranet.ps1') {
            $path = Join-Path $script:Root 'provision' $f
            { [scriptblock]::Create((Get-Content $path -Raw)) } | Should -Not -Throw
            (Get-Command $path).Parameters.Keys | Should -Contain 'TenantName'
            (Get-Command $path).Parameters.Keys | Should -Contain 'ClientId'
        }
        (Get-Command (Join-Path $script:Root 'provision' 'Initialize-Intranet.ps1')).Parameters.ContainsKey('WhatIf') | Should -BeTrue
    }
    It 'never contain a secret or a real tenant' {
        foreach ($f in Get-ChildItem (Join-Path $script:Root 'provision') -File) {
            (Get-Content $f.FullName -Raw) | Should -Not -Match 'devladlog|ClientSecret|Password'
        }
    }
}
