#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
# Invoke-Pester ./tests -Output Detailed
# - The schema tests download Microsoft's site script schema once into tests/.schema-cache/ (skipped when offline).
# - The provisioning tests mock the real PnP.PowerShell cmdlets (Pester copies their parameter metadata, so a wrong
#   parameter name or type fails the test). They are skipped when PnP.PowerShell isn't installed.

BeforeDiscovery {
    $script:hasPnP = [bool](Get-Module -ListAvailable PnP.PowerShell)
    $cache = Join-Path $PSScriptRoot '.schema-cache'
    $script:schemaPath = Join-Path $cache 'site-script.schema.json'
    if (-not (Test-Path $schemaPath)) {
        try {
            New-Item -ItemType Directory -Force -Path $cache | Out-Null
            Invoke-WebRequest -Uri 'https://developer.microsoft.com/json-schemas/sp/site-design-script-actions.schema.json' `
                -OutFile $schemaPath -TimeoutSec 30 -ErrorAction Stop
        } catch { Remove-Item $schemaPath -ErrorAction SilentlyContinue }
    }
    $script:hasSchema = Test-Path $schemaPath
}

BeforeAll {
    $src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'MgSitePages.psm1') -Force
    $script:goodManifest = Join-Path $src 'purchasing' 'template.json'
    $script:badManifest = Join-Path $src 'bad' 'template.json'
    $script:schemaPath = Join-Path $PSScriptRoot '.schema-cache' 'site-script.schema.json'

    function New-Script([object[]]$Actions) { [pscustomobject]@{ actions = @($Actions) } }
    function A([hashtable]$h) { [pscustomobject]$h }
    function Rules($findings) { @($findings | ForEach-Object Rule) }
    function New-Page([object[]]$Sections, [string]$Name = 'test-page') {
        [pscustomobject]@{ name = $Name; title = 'T'; layout = 'Article'; sections = @($Sections) }
    }
    function S([string]$Template, [object[]]$Controls) {
        [pscustomobject]@{ template = $Template; controls = @($Controls) }
    }
    function W([string]$WebPart, [int]$Column = 1) { [pscustomobject]@{ column = $Column; type = 'WebPart'; webPart = $WebPart } }
    function Navs([int]$n) { 1..$n | ForEach-Object { A @{ verb = 'addNavLink'; url = "/p$_"; displayName = "P$_"; isWebRelative = $true } } }
}

Describe 'Test-MgSiteTemplate (the two template folders)' {
    It 'the purchasing template has no findings' {
        @(Test-MgSiteTemplate -ManifestPath $goodManifest) | Should -HaveCount 0
    }

    It 'the bad template has every planted problem: 10 errors, 9 warnings' {
        $f = @(Test-MgSiteTemplate -ManifestPath $badManifest)
        @($f | Where-Object Severity -eq 'Error') | Should -HaveCount 10
        @($f | Where-Object Severity -eq 'Warning') | Should -HaveCount 9
        foreach ($r in 'SS001', 'SS004', 'SS005', 'SS006', 'SS007', 'SS008', 'SS009', 'SS010', 'PG001', 'PG002', 'PG003', 'PG004', 'PG005', 'PG006', 'PG007', 'PG008') {
            Rules $f | Should -Contain $r
        }
        ($f | Where-Object Rule -eq 'SS001').Target | Should -Match 'createList'
    }

    It 'every finding says which file it came from' {
        Test-MgSiteTemplate -ManifestPath $badManifest | ForEach-Object { $_.Source | Should -Not -BeNullOrEmpty }
    }

    It 'catches a home page that is not one of the pages, and duplicate page names' {
        $dir = Join-Path $TestDrive 'dup'; New-Item -ItemType Directory -Path (Join-Path $dir 'pages') -Force | Out-Null
        $page = '{"name":"same","title":"A","sections":[{"template":"OneColumn","controls":[{"column":1,"type":"Text","text":"x"}]}]}'
        Set-Content (Join-Path $dir 'pages' 'a.json') $page
        Set-Content (Join-Path $dir 'pages' 'b.json') $page
        Set-Content (Join-Path $dir 'template.json') '{"title":"T","webTemplate":"CommunicationSite","siteScripts":[],"pages":["pages/a.json","pages/b.json"],"homePage":"start"}'
        $f = @(Test-MgSiteTemplate -ManifestPath (Join-Path $dir 'template.json'))
        @($f | Where-Object Rule -eq 'PG009') | Should -HaveCount 2
    }
}

Describe 'Test-MgSiteScript' {
    It 'allows 30 actions for a synchronous apply; warns at 31' {
        Rules (Test-MgSiteScript -Script (New-Script (Navs 30))) | Should -Not -Contain 'SS003'
        Rules (Test-MgSiteScript -Script (New-Script (Navs 31))) | Should -Contain 'SS003'
    }

    It 'allows 300 actions; 301 is an error' {
        Rules (Test-MgSiteScript -Script (New-Script (Navs 300))) | Should -Not -Contain 'SS002'
        $r = Rules (Test-MgSiteScript -Script (New-Script (Navs 301)))
        $r | Should -Contain 'SS002'
        $r | Should -Not -Contain 'SS003'
    }

    It 'counts subactions towards the limit' {
        $subs = 1..30 | ForEach-Object { A @{ verb = 'setDescription'; description = "d$_" } }
        $list = A @{ verb = 'createSPList'; listName = 'L'; templateType = 100; subactions = @($subs) }
        # 1 action + 30 subactions = 31
        Rules (Test-MgSiteScript -Script (New-Script @($list))) | Should -Contain 'SS003'
    }

    It 'flags more than 100,000 characters' {
        $s = New-Script @(A @{ verb = 'createSPList'; listName = 'L'; templateType = 100
                subactions = @(A @{ verb = 'setDescription'; description = ('x' * 100001) }) })
        Rules (Test-MgSiteScript -Script $s) | Should -Contain 'SS002'
    }

    It 'rejects unknown verbs and verbs in the wrong place (verbs are case-sensitive)' {
        $s = New-Script @(
            (A @{ verb = 'CreateSPList'; listName = 'L'; templateType = 100 }),
            (A @{ verb = 'addSPField'; fieldType = 'Text'; displayName = 'X'; isRequired = $false }),
            (A @{ verb = 'createSPList'; listName = 'L'; templateType = 100; subactions = @(A @{ verb = 'applyTheme'; themeName = 'T' }) }),
            (A @{ verb = 'setSiteBranding'; headerLayout = 'Compact'; subactions = @(A @{ verb = 'setDescription'; description = 'x' }) }))
        @(Test-MgSiteScript -Script $s | Where-Object Rule -eq 'SS001') | Should -HaveCount 4
    }

    It 'accepts enableApprovals as a list subaction (documented on Learn, missing from the schema)' {
        $s = New-Script @(A @{ verb = 'createSPList'; listName = 'L'; templateType = 101; subactions = @(A @{ verb = 'enableApprovals' }) })
        @(Test-MgSiteScript -Script $s) | Should -HaveCount 0
    }

    It 'warns when a field has no id (re-runs can duplicate it)' {
        $s = New-Script @(A @{ verb = 'createSPList'; listName = 'L'; templateType = 100; subactions = @(
                    (A @{ verb = 'addSPField'; fieldType = 'Text'; displayName = 'A'; isRequired = $false }),
                    (A @{ verb = 'addSPField'; fieldType = 'Text'; displayName = 'B'; isRequired = $false; id = [guid]::NewGuid().ToString() }),
                    (A @{ verb = 'addSPFieldXml'; schemaXml = '<Field Type="Text" Name="C" DisplayName="C" />' }),
                    (A @{ verb = 'addSPFieldXml'; schemaXml = "<Field ID=`"{$([guid]::NewGuid())}`" Type=`"Text`" Name=`"D`" DisplayName=`"D`" />" })) })
        @(Test-MgSiteScript -Script $s | Where-Object Rule -eq 'SS004') | Should -HaveCount 2
    }

    It 'setSiteLogo works only on communication sites (68)' {
        $s = New-Script @(A @{ verb = 'setSiteLogo'; url = '/SiteAssets/logo.png' })
        Rules (Test-MgSiteScript -Script $s -WebTemplate 68) | Should -Not -Contain 'SS007'
        Rules (Test-MgSiteScript -Script $s -WebTemplate 64) | Should -Contain 'SS007'
        Rules (Test-MgSiteScript -Script $s -WebTemplate 'GrouplessTeamSite') | Should -Contain 'SS007'
    }

    It 'blocks the documented actions on channel sites (69)' {
        $s = New-Script @((A @{ verb = 'applyTheme'; themeName = 'T' }), (A @{ verb = 'joinHubSite'; hubSiteId = [guid]::NewGuid().ToString() }),
            (A @{ verb = 'createSPList'; listName = 'L'; templateType = 100 }))
        @(Test-MgSiteScript -Script $s -WebTemplate 69 | Where-Object Rule -eq 'SS011') | Should -HaveCount 2
        @(Test-MgSiteScript -Script $s -WebTemplate 68 | Where-Object Rule -eq 'SS011') | Should -HaveCount 0
    }

    It 'knows the site columns and content types the script creates itself' {
        $s = New-Script @(
            (A @{ verb = 'createSiteColumn'; fieldType = 'User'; internalName = 'ProjectOwner'; displayName = 'Owner'; isRequired = $false; id = [guid]::NewGuid().ToString() }),
            (A @{ verb = 'createSiteColumnXml'; schemaXml = "<Field ID=`"{$([guid]::NewGuid())}`" Type=`"Choice`" Name=`"Phase`" DisplayName=`"Phase`" />" }),
            (A @{ verb = 'createContentType'; name = 'Project Brief'; parentName = 'Document'; hidden = $false }),
            (A @{ verb = 'createSPList'; listName = 'L'; templateType = 101; subactions = @(
                    (A @{ verb = 'addSiteColumn'; internalName = 'ProjectOwner' }),
                    (A @{ verb = 'addSiteColumn'; internalName = 'Phase' }),
                    (A @{ verb = 'addContentType'; name = 'Project Brief' }),
                    (A @{ verb = 'addContentType'; name = 'Document' })) }))
        @(Test-MgSiteScript -Script $s) | Should -HaveCount 0
    }

    It 'trusts addContentType when content types are synced from the hub' {
        $s = New-Script @((A @{ verb = 'addContentTypesFromHub'; ids = @('0x0101') }),
            (A @{ verb = 'createSPList'; listName = 'L'; templateType = 101; subactions = @(A @{ verb = 'addContentType'; name = 'Contract' }) }))
        @(Test-MgSiteScript -Script $s) | Should -HaveCount 0
    }

    It 'checks GUIDs: invalid is an error, the empty GUID a warning, braces are fine' {
        $bad = Test-MgSiteScript -Script (New-Script @(A @{ verb = 'joinHubSite'; hubSiteId = 'my-hub' }))
        $empty = Test-MgSiteScript -Script (New-Script @(A @{ verb = 'installSolution'; id = [guid]::Empty.ToString(); name = 'x' }))
        $braced = Test-MgSiteScript -Script (New-Script @(A @{ verb = 'activateSPFeature'; featureId = "{$([guid]::NewGuid())}"; scope = 'web' }))
        $bad.Severity | Should -Be 'Error'
        $empty.Severity | Should -Be 'Warning'
        @($braced) | Should -HaveCount 0
    }

    It 'checks the locale is a real LCID (2070 pt-PT yes, 99999 no)' {
        $mk = { param($l) New-Script @(A @{ verb = 'setRegionalSettings'; timeZone = 2; locale = $l; sortOrder = 25; hourFormat = '24' }) }
        @(Test-MgSiteScript -Script (& $mk 2070)) | Should -HaveCount 0
        Rules (Test-MgSiteScript -Script (& $mk 99999)) | Should -Contain 'SS010'
    }

    It 'flags unsupported list templates' {
        Rules (Test-MgSiteScript -Script (New-Script @(A @{ verb = 'createSPList'; listName = 'L'; templateType = 1100 }))) | Should -Not -Contain 'SS006'
        Rules (Test-MgSiteScript -Script (New-Script @(A @{ verb = 'createSPList'; listName = 'L'; templateType = 171 }))) | Should -Contain 'SS006'
    }
}

Describe "Microsoft's site script schema" -Skip:(-not $hasSchema) {
    It 'the purchasing script validates against it' {
        $raw = Get-Content (Join-Path $PSScriptRoot '..' 'src' 'purchasing' 'purchasing.site-script.json') -Raw
        Test-Json -Json $raw -SchemaFile $schemaPath | Should -BeTrue
        @(Test-MgSiteTemplate -ManifestPath $goodManifest -SchemaPath $schemaPath) | Should -HaveCount 0
    }

    It 'reports one SS000 per bad action, with the reason' {
        $s = New-Script @((A @{ verb = 'addNavLink'; displayName = 'No url' }), (A @{ verb = 'setSiteBranding'; headerLayout = 'Tall' }),
            (A @{ verb = 'createList'; listName = 'L' }), (A @{ verb = 'setSiteBranding'; headerLayout = 'Compact' }))
        $f = @(Test-MgSiteScript -Script $s -SchemaPath $schemaPath | Where-Object Rule -eq 'SS000')
        $f | Should -HaveCount 3
        $f[0].Message | Should -Match 'url'
        $f[1].Message | Should -Match 'headerLayout'
        $f[2].Message | Should -Match "isn't one of its actions"
    }

    It 'documents the drift: enableApprovals is on Learn but not in the schema; addFile is in the schema but not on Learn' {
        $schema = Get-Content $schemaPath -Raw | ConvertFrom-Json -AsHashtable -Depth 50
        $schema.definitions.SPListSubactions.ContainsKey('enableApprovals') | Should -BeFalse
        $schema.definitions.SPListSubactions.ContainsKey('addFile') | Should -BeTrue
    }

    It "Learn's setRegionalSettings sample has /* comments */, so it isn't strict JSON" {
        $sample = '{ "verb": "setRegionalSettings", "timeZone": 2, /* Greenwich Mean Time */ "locale": 1050, "sortOrder": 6, "hourFormat": "24" }'
        { [System.Text.Json.JsonDocument]::Parse($sample) } | Should -Throw
    }
}

Describe 'Test-MgPageDesign' {
    It 'the three purchasing pages have no findings' {
        foreach ($p in Get-ChildItem (Join-Path $PSScriptRoot '..' 'src' 'purchasing' 'pages') -Filter *.json) {
            @(Test-MgPageDesign -Page (Import-MgJson -Path $p.FullName)) | Should -HaveCount 0 -Because $p.Name
        }
    }

    It 'two iframe web parts are a warning; three are an error' {
        (Test-MgPageDesign -Page (New-Page @(S 'TwoColumn' @((W 'ContentEmbed' 1), (W 'DocumentEmbed' 2))))).Severity | Should -Be 'Warning'
        (Test-MgPageDesign -Page (New-Page @(S 'ThreeColumn' @((W 'ContentEmbed' 1), (W 'ContentEmbed' 2), (W 'DocumentEmbed' 3))))).Severity | Should -Be 'Error'
    }

    It 'three search-driven web parts are fine; four get a warning' {
        $three = New-Page @(S 'ThreeColumn' @((W 'Events' 1), (W 'ContentRollup' 2), (W 'Events' 3)))
        $four = New-Page @(S 'TwoColumn' @((W 'Events' 1), (W 'ContentRollup' 2), (W 'Events' 1), (W 'ContentRollup' 2)))
        @(Test-MgPageDesign -Page $three) | Should -HaveCount 0
        Rules (Test-MgPageDesign -Page $four) | Should -Be @('PG006')
    }

    It 'full-width sections only on communication sites' {
        $p = New-Page @(S 'OneColumnFullWidth' @(W 'Hero'))
        @(Test-MgPageDesign -Page $p -SiteType Communication) | Should -HaveCount 0
        Rules (Test-MgPageDesign -Page $p -SiteType Team) | Should -Be @('PG003')
    }

    It 'knows the column count of each section, vertical column included' {
        @(Test-MgPageDesign -Page (New-Page @(S 'OneColumnVerticalSection' @((W 'News' 1), (W 'QuickLinks' 2))))) | Should -HaveCount 0
        Rules (Test-MgPageDesign -Page (New-Page @(S 'OneColumnVerticalSection' @(W 'News' 3)))) | Should -Be @('PG002')
        Rules (Test-MgPageDesign -Page (New-Page @(S 'TwoColumnLeft' @(W 'News' 0)))) | Should -Be @('PG002')
    }

    It 'page names are lowercase words and hyphens' {
        foreach ($ok in 'how-to-buy', 'faq', 'news-2027') { @(Test-MgPageDesign -Page (New-Page @(S 'OneColumn' @(W 'News')) $ok)) | Should -HaveCount 0 }
        foreach ($bad in 'How to buy', 'faq.aspx', 'news--x', 'Landing Page!') { Rules (Test-MgPageDesign -Page (New-Page @(S 'OneColumn' @(W 'News')) $bad)) | Should -Contain 'PG007' }
    }

    It 'unknown layouts, sections and web parts are errors' {
        $p = [pscustomobject]@{ name = 'p'; layout = 'Landing'; sections = @(S 'FourColumn' @(W 'Carousel')) }
        (Rules (Test-MgPageDesign -Page $p) | Sort-Object) | Should -Be @('PG001', 'PG001', 'PG004')
    }
}

Describe 'Helpers' {
    It 'ConvertTo-MgWebTemplateId accepts names and numbers, rejects the rest' {
        ConvertTo-MgWebTemplateId 'CommunicationSite' | Should -Be 68
        ConvertTo-MgWebTemplateId '64' | Should -Be 64
        ConvertTo-MgWebTemplateId 1 | Should -Be 1
        { ConvertTo-MgWebTemplateId 'STS#3' } | Should -Throw
    }

    It 'Resolve-MgPageToken swaps the listid token for the list id and leaves other values alone' {
        $r = Resolve-MgPageToken -Properties @{ selectedListId = '{listid:Purchasing FAQ}'; isDocumentLibrary = $false } -ListIdResolver { param($t) "id-of-$t" }
        $r.selectedListId | Should -Be 'id-of-Purchasing FAQ'
        $r.isDocumentLibrary | Should -BeFalse
    }
}

Describe 'Tenant functions (PnP cmdlets mocked)' -Skip:(-not $hasPnP) {
    BeforeAll {
        Import-Module PnP.PowerShell -ErrorAction Stop
        $script:listId = [guid]'00000000-0000-0000-0000-0000000000f1'
    }

    It 'registers scripts and the template on an empty tenant' {
        Mock -ModuleName MgSitePages Get-PnPSiteScript { @() }
        Mock -ModuleName MgSitePages Add-PnPSiteScript { [pscustomobject]@{ Id = [guid]'00000000-0000-0000-0000-0000000000a1'; Title = $Title } }
        Mock -ModuleName MgSitePages Get-PnPSiteDesign { @() }
        Mock -ModuleName MgSitePages Add-PnPSiteDesign { [pscustomobject]@{ Id = [guid]'00000000-0000-0000-0000-0000000000d1'; Title = $Title } }
        $out = @(Invoke-MgSiteTemplateRegistration -ManifestPath $goodManifest)
        Should -Invoke -ModuleName MgSitePages Add-PnPSiteScript -Times 1 -Exactly -ParameterFilter { $Title -eq 'Contoso Purchasing - purchasing' -and $Content -match 'setRegionalSettings' }
        Should -Invoke -ModuleName MgSitePages Add-PnPSiteDesign -Times 1 -Exactly -ParameterFilter {
            $WebTemplate -eq 'CommunicationSite' -and $SiteScriptIds[0] -eq [guid]'00000000-0000-0000-0000-0000000000a1' }
        $out[-1].SiteDesignId | Should -Be ([guid]'00000000-0000-0000-0000-0000000000d1')
    }

    It 'is idempotent: updates the existing script and template, adds nothing' {
        Mock -ModuleName MgSitePages Get-PnPSiteScript { @([pscustomobject]@{ Id = [guid]'00000000-0000-0000-0000-0000000000a1'; Title = 'Contoso Purchasing - purchasing' }) }
        Mock -ModuleName MgSitePages Add-PnPSiteScript { throw 'should not add' }
        Mock -ModuleName MgSitePages Set-PnPSiteScript { }
        Mock -ModuleName MgSitePages Get-PnPSiteDesign { @([pscustomobject]@{ Id = [guid]'00000000-0000-0000-0000-0000000000d1'; Title = 'Contoso Purchasing' }) }
        Mock -ModuleName MgSitePages Add-PnPSiteDesign { throw 'should not add' }
        Mock -ModuleName MgSitePages Set-PnPSiteDesign { }
        $out = @(Invoke-MgSiteTemplateRegistration -ManifestPath $goodManifest)
        ($out.Action -join ',') | Should -Be 'UpdateScript,UpdateTemplate,Result'
        Should -Invoke -ModuleName MgSitePages Set-PnPSiteScript -Times 1 -Exactly -ParameterFilter { $Identity.Id -eq [guid]'00000000-0000-0000-0000-0000000000a1' }
        Should -Invoke -ModuleName MgSitePages Set-PnPSiteDesign -Times 1 -Exactly
    }

    It '-WhatIf registers nothing but still reports the plan' {
        Mock -ModuleName MgSitePages Get-PnPSiteScript { @() }
        Mock -ModuleName MgSitePages Add-PnPSiteScript { throw 'WhatIf violated' }
        Mock -ModuleName MgSitePages Get-PnPSiteDesign { @() }
        Mock -ModuleName MgSitePages Add-PnPSiteDesign { throw 'WhatIf violated' }
        ((Invoke-MgSiteTemplateRegistration -ManifestPath $goodManifest -WhatIf).Action -join ',') | Should -Be 'AddScript,AddTemplate,Result'
    }

    It 'applies the template asynchronously' {
        Mock -ModuleName MgSitePages Add-PnPSiteDesignTask { [pscustomobject]@{ Id = [guid]::NewGuid() } }
        $null = Invoke-MgSiteTemplateApply -SiteDesignId '00000000-0000-0000-0000-0000000000d1' -WebUrl 'https://contoso.sharepoint.com/sites/Purchasing'
        Should -Invoke -ModuleName MgSitePages Add-PnPSiteDesignTask -Times 1 -Exactly -ParameterFilter {
            $SiteDesignId -eq [guid]'00000000-0000-0000-0000-0000000000d1' -and $WebUrl -match '/sites/Purchasing$' }
    }

    It 'reports each action of the last run with its outcome' {
        $run = [System.Runtime.CompilerServices.RuntimeHelpers]::GetUninitializedObject([Microsoft.Online.SharePoint.TenantAdministration.TenantSiteDesignRun])
        Mock -ModuleName MgSitePages Get-PnPSiteDesignRun { $run }
        Mock -ModuleName MgSitePages Get-PnPSiteDesignRunStatus {
            [pscustomobject]@{ ActionTitle = 'Set regional settings'; OutcomeCode = 'Success'; OutcomeText = ''; SiteScriptTitle = 's' }
            [pscustomobject]@{ ActionTitle = 'Apply theme Contoso'; OutcomeCode = 'Failure'; OutcomeText = 'Theme not found'; SiteScriptTitle = 's' }
        }
        $r = @(Get-MgSiteTemplateRunReport -WebUrl 'https://contoso.sharepoint.com/sites/Purchasing' -SiteDesignId ([guid]::NewGuid()))
        $r | Should -HaveCount 2
        $r[1].Outcome | Should -Be 'Failure'
        $r[1].Detail | Should -Be 'Theme not found'
    }

    It 'provisions the pages section by section, publishes them and sets the home page' {
        Mock -ModuleName MgSitePages Get-PnPPage { throw 'not found' }
        Mock -ModuleName MgSitePages Add-PnPPage { }
        Mock -ModuleName MgSitePages Add-PnPPageSection { }
        Mock -ModuleName MgSitePages Add-PnPPageTextPart { }
        Mock -ModuleName MgSitePages Add-PnPPageWebPart { }
        Mock -ModuleName MgSitePages Set-PnPPage { }
        Mock -ModuleName MgSitePages Set-PnPHomePage { }
        Mock -ModuleName MgSitePages Get-PnPList { [pscustomobject]@{ Id = $listId; Title = 'Purchasing FAQ' } }
        $steps = @(Invoke-MgPageProvisioning -ManifestPath $goodManifest)
        Should -Invoke -ModuleName MgSitePages Add-PnPPage -Times 3 -Exactly
        Should -Invoke -ModuleName MgSitePages Add-PnPPage -Times 1 -Exactly -ParameterFilter { $Name -eq 'news-approval-limits' -and $PromoteAs -eq 'NewsArticle' }
        Should -Invoke -ModuleName MgSitePages Add-PnPPage -Times 1 -Exactly -ParameterFilter { $Name -eq 'purchasing-home' -and $LayoutType -eq 'Home' }
        Should -Invoke -ModuleName MgSitePages Add-PnPPageSection -Times 5 -Exactly
        Should -Invoke -ModuleName MgSitePages Add-PnPPageTextPart -Times 5 -Exactly
        Should -Invoke -ModuleName MgSitePages Add-PnPPageWebPart -Times 2 -Exactly
        Should -Invoke -ModuleName MgSitePages Add-PnPPageWebPart -Times 1 -Exactly -ParameterFilter {
            $DefaultWebPartType -eq 'List' -and $Section -eq 3 -and "$($WebPartProperties)" -match [regex]::Escape("$listId") }
        Should -Invoke -ModuleName MgSitePages Set-PnPPage -Times 3 -Exactly -ParameterFilter { $Publish }
        Should -Invoke -ModuleName MgSitePages Set-PnPHomePage -Times 1 -Exactly -ParameterFilter { $RootFolderRelativeUrl -eq 'SitePages/purchasing-home.aspx' }
        $steps[-1].Action | Should -Be 'SetHomePage'
    }

    It 'skips existing pages, and recreates them with -Force' {
        Mock -ModuleName MgSitePages Get-PnPPage { [pscustomobject]@{ Name = "$($Identity.Name)" } }
        Mock -ModuleName MgSitePages Remove-PnPPage { }
        Mock -ModuleName MgSitePages Add-PnPPage { }
        Mock -ModuleName MgSitePages Add-PnPPageSection { }
        Mock -ModuleName MgSitePages Add-PnPPageTextPart { }
        Mock -ModuleName MgSitePages Add-PnPPageWebPart { }
        Mock -ModuleName MgSitePages Set-PnPPage { }
        Mock -ModuleName MgSitePages Set-PnPHomePage { }
        Mock -ModuleName MgSitePages Get-PnPList { [pscustomobject]@{ Id = $listId } }
        $skip = @(Invoke-MgPageProvisioning -ManifestPath $goodManifest)
        @($skip | Where-Object Action -eq 'Skip') | Should -HaveCount 3
        Should -Invoke -ModuleName MgSitePages Add-PnPPage -Times 0 -Exactly
        $null = Invoke-MgPageProvisioning -ManifestPath $goodManifest -Force
        Should -Invoke -ModuleName MgSitePages Remove-PnPPage -Times 3 -Exactly -ParameterFilter { $Force }
        Should -Invoke -ModuleName MgSitePages Add-PnPPage -Times 3 -Exactly
    }

    It '-WhatIf creates no page' {
        Mock -ModuleName MgSitePages Get-PnPPage { throw 'not found' }
        foreach ($c in 'Add-PnPPage', 'Add-PnPPageSection', 'Add-PnPPageTextPart', 'Add-PnPPageWebPart', 'Set-PnPPage', 'Set-PnPHomePage', 'Get-PnPList') {
            Mock -ModuleName MgSitePages $c { throw 'WhatIf violated' }
        }
        $steps = @(Invoke-MgPageProvisioning -ManifestPath $goodManifest -WhatIf)
        @($steps | Where-Object Action -eq 'AddPage') | Should -HaveCount 3
    }

    It 'exports a site script from an existing site with branding and regional settings' {
        Mock -ModuleName MgSitePages Get-PnPSiteScriptFromWeb { '{"actions":[]}' }
        Export-MgSiteScript -Url 'https://contoso.sharepoint.com/sites/HandBuilt' -Lists 'Lists/Suppliers' | Should -Be '{"actions":[]}'
        Should -Invoke -ModuleName MgSitePages Get-PnPSiteScriptFromWeb -Times 1 -Exactly -ParameterFilter {
            $IncludeBranding -and $IncludeRegionalSettings -and $Lists -contains 'Lists/Suppliers' }
    }
}
