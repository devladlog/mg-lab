BeforeAll {
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        Set-Item -Path function:global:Invoke-MgGraphRequest -Value ([scriptblock]::Create("[CmdletBinding()] param(`$Method, `$Uri, `$Body, `$ContentType, `$OutputType, `$Headers, `$OutputFilePath) throw 'stub: not connected'"))
    }
    Import-Module "$PSScriptRoot/../src/AppsDeploy/AppsDeploy.psd1" -Force
    $script:cfgPath = "$PSScriptRoot/../src/apps.json"
    $script:config = Get-ADConfig -Path $cfgPath
    $script:releases = @(Get-ADReleaseChannel -Path "$PSScriptRoot/fixtures/channels.json")
    $script:clients = @(Get-Content "$PSScriptRoot/fixtures/clients.json" -Raw | ConvertFrom-Json)
    $script:rows = @(Get-ADActivationReport -Path "$PSScriptRoot/fixtures/activations.csv")
    $script:now = [datetimeoffset]::Parse('2026-11-21T12:00:00Z')
    $script:realGroup = '11111111-2222-3333-4444-555555555555'

    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json; & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 8 | Set-Content $p; $p
    }
    function script:Live-Config { Get-ADConfig -Path (New-Config { param($c) $c.intune.assignTo.groupId = $realGroup }) }

    # A tiny fake tenant of mobile apps, kept in a global so the module-scope mock can see it.
    function script:Reset-Tenant([object[]]$Apps = @()) {
        $global:T13 = @{ Apps = [System.Collections.Generic.List[object]]::new(); Calls = [System.Collections.Generic.List[object]]::new() }
        foreach ($a in $Apps) { $global:T13.Apps.Add($a) }
    }
    function script:App-From($Config, [hashtable]$Override = @{}) {
        $b = ConvertTo-ADOfficeSuiteAppBody -Config $Config
        $o = [ordered]@{ id = 'aaaaaaaa-0000-0000-0000-000000000013' }
        foreach ($k in $b.Keys) { $o[$k] = $b[$k] }
        foreach ($k in $Override.Keys) { $o[$k] = $Override[$k] }
        [pscustomobject]$o
    }
}

Describe 'Config file' {
    It 'loads the sample config' {
        $config.deployment.channel | Should -Be 'MonthlyEnterprise'
        $config.audit.maxBuildsBehind | Should -Be 2
    }
    It 'refuses a channel Learn does not list' {
        { Get-ADConfig -Path (New-Config { param($c) $c.deployment.channel = 'Monthly' }) } | Should -Throw "*channel 'Monthly' is not one of*"
    }
    It 'refuses a volume-licensed channel' {
        { Get-ADConfig -Path (New-Config { param($c) $c.deployment.channel = 'PerpetualVL2024' }) } | Should -Throw '*volume-licensed*'
    }
    It 'refuses an edition other than 32 or 64' {
        { Get-ADConfig -Path (New-Config { param($c) $c.deployment.officeClientEdition = '128' }) } | Should -Throw "*'32' or '64'*"
    }
    It 'refuses an ExcludeApp value Learn does not list' {
        { Get-ADConfig -Path (New-Config { param($c) $c.deployment.products[0].excludeApps = @('Visio') }) } | Should -Throw "*excludeApps 'Visio'*"
    }
    It 'refuses a bad language id' {
        { Get-ADConfig -Path (New-Config { param($c) $c.deployment.products[0].languages = @('english') }) } | Should -Throw "*language 'english'*"
    }
    It 'refuses a product with no languages' {
        { Get-ADConfig -Path (New-Config { param($c) $c.deployment.products[0].languages = @() }) } | Should -Throw '*at least one language*'
    }
    It 'refuses a non-boolean flag and a bad display level' {
        { Get-ADConfig -Path (New-Config { param($c) $c.deployment.acceptEula = 'yes' }) } | Should -Throw '*acceptEula must be true or false*'
        { Get-ADConfig -Path (New-Config { param($c) $c.deployment.displayLevel = 'Silent' }) } | Should -Throw '*displayLevel must be None or Full*'
    }
    It 'refuses an audit threshold that is not a positive whole number' {
        { Get-ADConfig -Path (New-Config { param($c) $c.audit.staleActivationDays = 0 }) } | Should -Throw '*staleActivationDays*'
    }
    It 'refuses a missing file and a missing deployment section' {
        { Get-ADConfig -Path "$TestDrive/nope.json" } | Should -Throw '*not found*'
        $p = Join-Path $TestDrive 'empty.json'; '{}' | Set-Content $p
        { Get-ADConfig -Path $p } | Should -Throw "*'deployment' section is missing*"
    }
}

Describe 'configuration.xml' {
    It 'builds the install file with the documented elements' {
        $x = [xml](New-ADOdtXml -Config $config)
        $x.Configuration.Add.OfficeClientEdition | Should -Be '64'
        $x.Configuration.Add.Channel | Should -Be 'MonthlyEnterprise'
        $x.Configuration.Add.Product.ID | Should -Be 'O365ProPlusRetail'
        @($x.Configuration.Add.Product.Language.ID) | Should -Be @('en-us', 'pt-pt')
        @($x.Configuration.Add.Product.ExcludeApp.ID) | Should -Be @('Lync', 'Publisher')
        $x.Configuration.Display.Level | Should -Be 'None'
        $x.Configuration.Display.AcceptEULA | Should -Be 'TRUE'
        $x.Configuration.SelectSingleNode('RemoveMSI') | Should -Not -BeNullOrEmpty
        $x.Configuration.Property.Name | Should -Be 'FORCEAPPSHUTDOWN'
    }
    It 'builds the download file without install-time elements, with SourcePath' {
        $x = [xml](New-ADOdtXml -Config $config -Mode Download -SourcePath 'C:\Downloads\Microsoft')
        $x.Configuration.Add.SourcePath | Should -Be 'C:\Downloads\Microsoft'
        $x.Configuration.SelectSingleNode('Display') | Should -BeNullOrEmpty
        $x.Configuration.SelectSingleNode('RemoveMSI') | Should -BeNullOrEmpty
        $x.Configuration.SelectSingleNode('Property') | Should -BeNullOrEmpty
    }
    It 'adds SharedComputerLicensing only when asked' {
        $c = Get-ADConfig -Path (New-Config { param($c) $c.deployment.sharedComputerLicensing = $true })
        $x = [xml](New-ADOdtXml -Config $c)
        ($x.Configuration.Property | Where-Object Name -eq 'SharedComputerLicensing').Value | Should -Be '1'
    }
    It 'passes its own validation' {
        @(Test-ADOdtXml -Xml (New-ADOdtXml -Config $config)).Count | Should -Be 0
        @(Test-ADOdtXml -Xml (New-ADOdtXml -Config $config -Mode Download)).Count | Should -Be 0
    }
    It 'accepts the example files from Microsoft Learn' {
        $learn = @'
<Configuration>
  <Add SourcePath="\\Server\Share" OfficeClientEdition="64" Channel="MonthlyEnterprise">
    <Product ID="O365ProPlusRetail"><Language ID="en-us" /><Language ID="ja-jp" /></Product>
    <Product ID="VisioProRetail"><Language ID="en-us" /><Language ID="ja-jp" /></Product>
  </Add>
  <Updates Enabled="TRUE" UpdatePath="\\Server\Share" />
  <Display Level="None" AcceptEULA="TRUE" />
</Configuration>
'@
        @(Test-ADOdtXml -Xml $learn).Count | Should -Be 0
        @(Test-ADOdtXml -Xml '<Configuration><Add OfficeClientEdition="64" Channel="MonthlyEnterprise" OfficeMgmtCOM="True"><Product ID="O365ProPlusRetail"><Language ID="MatchOS" Fallback="en-us" /></Product></Add><Updates Enabled="True" /></Configuration>').Count | Should -Be 0
        @(Test-ADOdtXml -Xml '<Configuration><Updates Channel="Current" /></Configuration>').Count | Should -Be 0
        @(Test-ADOdtXml -Xml '<Configuration><Remove All="FALSE"><Product ID="O365ProPlusRetail"><Language ID="es-es" /></Product></Remove></Configuration>').Count | Should -Be 0
    }
    It 'flags what Learn says is invalid' {
        $bad = {
            param($inner) @(Test-ADOdtXml -Xml "<Configuration>$inner</Configuration>") -join ' '
        }
        & $bad '<Add OfficeClientEdition="128"><Product ID="X"><Language ID="en-us"/></Product></Add>' | Should -BeLike '*must be 32 or 64*'
        & $bad '<Add Channel="Monthly"><Product ID="X"><Language ID="en-us"/></Product></Add>' | Should -BeLike "*Channel 'Monthly'*"
        & $bad '<Add Channel="PerpetualVL2021"><Product ID="X"><Language ID="en-us"/></Product></Add>' | Should -BeLike '*volume-licensed*'
        & $bad '<Add Version="MatchInstalled"><Product ID="X"><Language ID="en-us"/></Product></Add>' | Should -BeLike '*requires the Channel*'
        & $bad '<Add Version="2506"><Product ID="X"><Language ID="en-us"/></Product></Add>' | Should -BeLike '*Version must be a build*'
        & $bad '<Add DownloadPath="\\a\b"><Product ID="X"><Language ID="en-us"/></Product></Add>' | Should -BeLike '*DownloadPath requires a Version*'
        & $bad '<Add SourcePath="\\server\share\Office"><Product ID="X"><Language ID="en-us"/></Product></Add>' | Should -BeLike '*SourcePath must not include*'
        & $bad '<Add><Product ID="X"><Language ID="en-us"/><ExcludeApp ID="Visio"/></Product></Add>' | Should -BeLike "*ExcludeApp ID 'Visio'*"
        & $bad '<Add><Product ID="X"></Product></Add>' | Should -BeLike "*has no <Language>*"
        & $bad '<Add></Add>' | Should -BeLike '*no <Product>*'
        & $bad '<Display Level="Silent" AcceptEULA="YES"/>' | Should -BeLike '*Level must be None or Full*'
        & $bad '<Property Name="SharedComputerLicensing" Value="yes"/>' | Should -BeLike '*must be 0 or 1*'
        & $bad '<Property Name="AUTOACTIVATE" Value="1"/>' | Should -BeLike '*AUTOACTIVATE*'
        & $bad '<Bogus/>' | Should -BeLike '*Unknown element <Bogus>*'
    }
    It 'reports XML that is not well-formed, or not a Configuration' {
        (@(Test-ADOdtXml -Xml '<Configuration><Add></Configuration>') -join ' ') | Should -BeLike 'Not well-formed*'
        (@(Test-ADOdtXml -Xml '<Setup/>') -join ' ') | Should -BeLike '*Root element must be <Configuration>*'
    }
}

Describe 'Install-ADOffice (runs a real process: a stub shell script stands in for setup.exe in the tests only)' -Skip:(-not $IsLinux) {
    BeforeAll {
        $script:argLog = Join-Path $TestDrive 'args.txt'
        $script:stub = Join-Path $TestDrive 'setup.sh'
        "#!/bin/sh`necho `"`$1 `$2`" > '$argLog'`ncat `"`$2`" >> '$argLog'`nexit `${STUB_EXIT:-0}" | Set-Content $stub
        chmod +x $stub
    }
    It 'with -WhatIf writes the file but does not run setup' {
        $r = Install-ADOffice -Config $config -OdtPath $stub -WorkDir $TestDrive -WhatIf
        $r.Result | Should -Be 'WhatIf'
        Test-Path $argLog | Should -BeFalse
        Test-Path $r.ConfigFile | Should -BeTrue
    }
    It 'runs setup /configure with the generated file' {
        $r = Install-ADOffice -Config $config -OdtPath $stub -WorkDir $TestDrive -Confirm:$false
        $r.Result | Should -Be 'Done'
        $log = Get-Content $argLog -Raw
        $log | Should -BeLike '/configure *'
        $log | Should -BeLike '*<Product ID="O365ProPlusRetail">*'
    }
    It 'runs setup /download for download mode' {
        $null = Install-ADOffice -Config $config -OdtPath $stub -Mode Download -SourcePath '/srv/odt' -WorkDir $TestDrive -Confirm:$false
        (Get-Content $argLog -Raw) | Should -BeLike '/download *SourcePath="/srv/odt"*'
    }
    It 'throws when setup exits with an error' {
        $env:STUB_EXIT = '3'
        try { { Install-ADOffice -Config $config -OdtPath $stub -WorkDir $TestDrive -Confirm:$false } | Should -Throw '*exited with code 3*' } finally { Remove-Item Env:STUB_EXIT }
    }
    It 'throws when the tool is missing' {
        { Install-ADOffice -Config $config -OdtPath "$TestDrive/none.exe" -WorkDir $TestDrive } | Should -Throw '*not found*'
    }
}

Describe 'Intune officeSuiteApp body' {
    BeforeAll { $script:body = ConvertTo-ADOfficeSuiteAppBody -Config $config }
    It 'maps the config to Graph values' {
        $body['@odata.type'] | Should -Be '#microsoft.graph.officeSuiteApp'
        $body.productIds | Should -Be @('o365ProPlusRetail')
        $body.updateChannel | Should -Be 'monthlyEnterprise'
        $body.officePlatformArchitecture | Should -Be 'x64'
        $body.localesToInstall | Should -Be @('en-us', 'pt-pt')
        $body.installProgressDisplayLevel | Should -Be 'none'
        $body.excludedApps.lync | Should -BeTrue
        $body.excludedApps.publisher | Should -BeTrue
        $body.excludedApps.word | Should -BeFalse
    }
    It 'only uses properties and enum values that Learn documents for officeSuiteApp' {
        $learnProps = 'displayName', 'description', 'publisher', 'autoAcceptEula', 'productIds', 'excludedApps', 'useSharedComputerActivation', 'updateChannel', 'officeSuiteAppDefaultFileFormat', 'officePlatformArchitecture', 'localesToInstall', 'installProgressDisplayLevel', 'shouldUninstallOlderVersionsOfOffice', 'targetVersion', 'updateVersion', 'officeConfigurationXml'
        foreach ($k in $body.Keys) { if ($k -ne '@odata.type') { $k | Should -BeIn $learnProps } }
        $body.updateChannel | Should -BeIn 'none', 'current', 'deferred', 'firstReleaseCurrent', 'firstReleaseDeferred', 'monthlyEnterprise'
        $body.officePlatformArchitecture | Should -BeIn 'none', 'x86', 'x64', 'arm', 'neutral', 'arm64'
        $body.installProgressDisplayLevel | Should -BeIn 'none', 'full'
        @($body.excludedApps.Keys | Where-Object { $_ -ne '@odata.type' } | Sort-Object) | Should -Be @('access', 'bing', 'excel', 'groove', 'infoPath', 'lync', 'oneDrive', 'oneNote', 'outlook', 'powerPoint', 'publisher', 'sharePointDesigner', 'teams', 'visio', 'word')
    }
    It 'maps every ODT channel with an Intune value through the names the release API publishes' {
        # Current, Deferred (= SemiAnnual), FirstReleaseCurrent (= CurrentPreview), FirstReleaseDeferred (= SemiAnnualPreview): alternateNames in the real API data.
        $expect = @{ Current = 'current'; SemiAnnual = 'deferred'; CurrentPreview = 'firstReleaseCurrent'; SemiAnnualPreview = 'firstReleaseDeferred'; MonthlyEnterprise = 'monthlyEnterprise' }
        foreach ($ch in $expect.Keys) {
            $c = Get-ADConfig -Path (New-Config { param($c) $c.deployment.channel = $ch })
            (ConvertTo-ADOfficeSuiteAppBody -Config $c).updateChannel | Should -Be $expect[$ch]
            $rel = $releases | Where-Object name -eq $ch
            $rel | Should -Not -BeNullOrEmpty
            if ($ch -ne 'MonthlyEnterprise') { ($expect[$ch]).ToLower() | Should -BeIn (@($rel.alternateNames) + $ch | ForEach-Object { $_.ToLower() }) }
        }
    }
    It 'refuses the Beta Channel (no Graph officeUpdateChannel value)' {
        $c = Get-ADConfig -Path (New-Config { param($c) $c.deployment.channel = 'BetaChannel' })
        { ConvertTo-ADOfficeSuiteAppBody -Config $c } | Should -Throw '*no Graph officeUpdateChannel*'
    }
    It 'refuses a product id Intune does not list, and OutlookForWindows' {
        { ConvertTo-ADOfficeSuiteAppBody -Config (Get-ADConfig -Path (New-Config { param($c) $c.deployment.products[0].id = 'ProPlus2024Volume' })) } | Should -Throw '*supports only these product ids*'
        { ConvertTo-ADOfficeSuiteAppBody -Config (Get-ADConfig -Path (New-Config { param($c) $c.deployment.products[0].excludeApps = @('OutlookForWindows') }))} | Should -Throw "*'OutlookForWindows' has no property*"
    }
    It 'refuses ODT language keywords' {
        { ConvertTo-ADOfficeSuiteAppBody -Config (Get-ADConfig -Path (New-Config { param($c) $c.deployment.products[0].languages = @('MatchOS') })) } | Should -Throw '*ODT keyword*'
    }
    It 'maps 32-bit to x86' {
        (ConvertTo-ADOfficeSuiteAppBody -Config (Get-ADConfig -Path (New-Config { param($c) $c.deployment.officeClientEdition = '32' }))).officePlatformArchitecture | Should -Be 'x86'
    }
}

Describe 'Set-ADOfficeSuiteApp (Graph mocked with a small fake tenant)' {
    BeforeAll {
        Mock -ModuleName AppsDeploy Invoke-MgGraphRequest {
            $global:T13.Calls.Add([pscustomobject]@{ Method = $Method; Uri = $Uri; Body = $Body })
            if ($Method -eq 'GET') {
                if ($Uri -like '*nextpage*') { return @{ value = @($global:T13.Apps | Select-Object -Skip 2) } }
                $first = @($global:T13.Apps | Select-Object -First 2)
                $r = @{ value = $first }
                if ($global:T13.Apps.Count -gt 2) { $r['@odata.nextLink'] = '/beta/deviceAppManagement/mobileApps?nextpage=1' }
                return $r
            }
            if ($Method -eq 'POST' -and $Uri -like '*/assign') { return $null }
            if ($Method -eq 'POST') { $o = $Body | ConvertFrom-Json -AsHashtable; $o['id'] = 'bbbbbbbb-0000-0000-0000-000000000013'; $global:T13.Apps.Add([pscustomobject]$o); return $o }
            if ($Method -eq 'PATCH') { return @{} }
        }
    }
    It 'creates the app, then assigns it' {
        Reset-Tenant
        $r = Set-ADOfficeSuiteApp -Config (Live-Config) -Confirm:$false
        $r.Action | Should -Be 'Created'
        $post = $global:T13.Calls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -notlike '*/assign' }
        $post.Uri | Should -Be '/beta/deviceAppManagement/mobileApps'
        ($post.Body | ConvertFrom-Json).'@odata.type' | Should -Be '#microsoft.graph.officeSuiteApp'
        $as = $global:T13.Calls | Where-Object { $_.Uri -like '*/assign' }
        $as.Uri | Should -BeLike '*/mobileApps/bbbbbbbb-*/assign'
        $a = ($as.Body | ConvertFrom-Json).mobileAppAssignments[0]
        $a.intent | Should -Be 'required'
        $a.target.groupId | Should -Be $realGroup
        $a.target.'@odata.type' | Should -Be '#microsoft.graph.groupAssignmentTarget'
    }
    It 'with -WhatIf changes nothing' {
        Reset-Tenant
        $r = Set-ADOfficeSuiteApp -Config (Live-Config) -WhatIf
        $r.Action | Should -Be 'WhatIf-Create'
        @($global:T13.Calls | Where-Object Method -ne 'GET').Count | Should -Be 0
    }
    It 'says Unchanged on the second run and sends no PATCH' {
        $live = Live-Config
        Reset-Tenant @(App-From $live)
        $r = Set-ADOfficeSuiteApp -Config $live -Confirm:$false
        $r.Action | Should -Be 'Unchanged'
        @($global:T13.Calls | Where-Object Method -eq 'PATCH').Count | Should -Be 0
    }
    It 'patches when a property differs and names it' {
        $live = Live-Config
        Reset-Tenant @(App-From $live @{ updateChannel = 'current'; localesToInstall = @('en-us') })
        $r = Set-ADOfficeSuiteApp -Config $live -Confirm:$false
        $r.Action | Should -Be 'Updated'
        $r.Changes | Should -BeLike '*updateChannel*'
        $r.Changes | Should -BeLike '*localesToInstall*'
        $p = $global:T13.Calls | Where-Object Method -eq 'PATCH'
        $p.Uri | Should -Be '/beta/deviceAppManagement/mobileApps/aaaaaaaa-0000-0000-0000-000000000013'
    }
    It 'sees a difference inside excludedApps' {
        $live = Live-Config
        $ex = (ConvertTo-ADOfficeSuiteAppBody -Config $live).excludedApps; $ex['teams'] = $true
        Reset-Tenant @(App-From $live @{ excludedApps = $ex })
        (Set-ADOfficeSuiteApp -Config $live -WhatIf).Changes | Should -BeLike '*excludedApps.teams*'
    }
    It 'finds the app on the second page of results and ignores other app types' {
        $live = Live-Config
        Reset-Tenant @([pscustomobject]@{ '@odata.type' = '#microsoft.graph.win32LobApp'; id = '1'; displayName = 'x' }, [pscustomobject]@{ '@odata.type' = '#microsoft.graph.win32LobApp'; id = '2'; displayName = $config.intune.displayName }, (App-From $live))
        (Set-ADOfficeSuiteApp -Config $live -Confirm:$false).Action | Should -Be 'Unchanged'
    }
    It 'refuses two apps with the same name' {
        $live = Live-Config
        Reset-Tenant @((App-From $live), (App-From $live @{ id = 'cccccccc-0000-0000-0000-000000000013' }))
        { Set-ADOfficeSuiteApp -Config $live -Confirm:$false } | Should -Throw '*More than one*'
    }
    It 'refuses the zero-GUID placeholder group and an invalid intent' {
        { Set-ADOfficeSuiteApp -Config $config -WhatIf } | Should -Throw '*zero GUID placeholder*'
        $c = Get-ADConfig -Path (New-Config { param($c) $c.intune.assignTo.groupId = $realGroup; $c.intune.assignTo.intent = 'maybe' })
        { Set-ADOfficeSuiteApp -Config $c -WhatIf } | Should -Throw '*mobileAppIntent*'
    }
}

Describe 'Release discovery data (a trimmed copy of the real API answer)' {
    It 'resolves a CDN URL from the registry to its channel by GUID' {
        (Resolve-ADChannel -Url 'http://officecdn.microsoft.com/pr/55336b82-a18d-4dd6-b5f6-9e5095c314a6' -Releases $releases).name | Should -Be 'MonthlyEnterprise'
        (Resolve-ADChannel -Url 'http://officecdn.microsoft.com/pr/492350F6-3A01-4F97-B9C0-C7C6DDF67D60' -Releases $releases).name | Should -Be 'Current'
        Resolve-ADChannel -Url 'http://officecdn.microsoft.com/pr/00000000-0000-0000-0000-000000000000' -Releases $releases | Should -BeNullOrEmpty
        Resolve-ADChannel -Url 'file://share/office' -Releases $releases | Should -BeNullOrEmpty
    }
    It 'knows every channel that Learn lists for the ODT' {
        foreach ($n in 'Current', 'CurrentPreview', 'MonthlyEnterprise', 'SemiAnnual', 'SemiAnnualPreview') { $n | Should -BeIn @($releases.name) }
    }
}

Describe 'Client findings (fictional registry values, real channel data)' {
    BeforeAll { function script:Find($name) { @(Get-ADClientFinding -Client ($clients | Where-Object ComputerName -eq $name) -Config $config -Releases $releases) } }
    It 'finds nothing on a device on the right channel at the latest build' { (Find 'FIX-OK').Count | Should -Be 0 }
    It 'flags a build older than the published list' {
        $f = Find 'FIX-OLDER'; $f.Type | Should -Contain 'BuildBehind'; $f[0].Severity | Should -Be 'Medium'
    }
    It 'flags a channel mismatch and a 32-bit install' {
        $f = Find 'FIX-CURRENT'; $f.Type | Should -Contain 'ChannelMismatch'; $f.Type | Should -Contain 'ArchitectureMismatch'
    }
    It 'flags the Store installation type as High and a missing C2R install' {
        $f = Find 'FIX-STORE'; $f.Type | Should -Contain 'StoreInstallType'; $f.Type | Should -Contain 'NotInstalled'; $f[0].Severity | Should -Be 'High'
    }
    It 'counts builds behind inside the list' {
        $c = $clients[0].PSObject.Copy(); $c.PackageVersion = '16.0.20527.20170'  # fixture list: third newest or older
        $mec = $releases | Where-Object name -eq 'MonthlyEnterprise'
        $c.PackageVersion = $mec.updates[3].legacyVersion
        $f = @(Get-ADClientFinding -Client $c -Config $config -Releases $releases)
        ($f | Where-Object Type -eq 'BuildBehind').Detail | Should -BeLike '*3 releases behind*'
    }
    It 'respects maxBuildsBehind' {
        $mec = $releases | Where-Object name -eq 'MonthlyEnterprise'
        $c = $clients[0].PSObject.Copy(); $c.PackageVersion = $mec.updates[1].legacyVersion
        @(Get-ADClientFinding -Client $c -Config $config -Releases $releases).Count | Should -Be 0
    }
    It 'flags a build newer than the published list as Low' {
        $c = $clients[0].PSObject.Copy(); $c.PackageVersion = '16.0.29999.20000'
        (@(Get-ADClientFinding -Client $c -Config $config -Releases $releases) | Where-Object Type -eq 'BuildAhead').Severity | Should -Be 'Low'
    }
    It 'flags an unknown channel, and a missing product' {
        $c = $clients[0].PSObject.Copy(); $c.UpdateChannel = 'http://officecdn.microsoft.com/pr/5440fd1f-7ecb-4221-8110-145efaa6372f'
        @(Get-ADClientFinding -Client $c -Config $config -Releases $releases).Type | Should -Contain 'UnknownChannel'
        $c2 = $clients[0].PSObject.Copy(); $c2.ProductIds = 'VisioProRetail'
        @(Get-ADClientFinding -Client $c2 -Config $config -Releases $releases).Type | Should -Contain 'ProductMissing'
    }
    It 'explains the Semi-Annual to Monthly Enterprise unification on a mismatch' {
        $c = $clients[0].PSObject.Copy(); $c.UpdateChannel = 'http://officecdn.microsoft.com/pr/7ffbc6bf-bc32-4f92-8982-f9dd17fd3114'; $c.PackageVersion = ($releases | Where-Object name -eq 'SemiAnnual').latestUpdateVersion
        (@(Get-ADClientFinding -Client $c -Config $config -Releases $releases) | Where-Object Type -eq 'ChannelMismatch').Detail | Should -BeLike '*2606*'
    }
    It 'reads the client only on Windows' -Skip:$IsWindows { { Get-ADOfficeClient } | Should -Throw '*Windows registry*' }
}

Describe 'Activation audit (fictional report in the documented CSV shape)' {
    BeforeAll { $script:af = @(Get-ADActivationFinding -Rows $rows -Config $config -Now $now) }
    It 'reads the documented columns' {
        $rows[0].PSObject.Properties.Name | Should -Be @('Report Refresh Date', 'User Principal Name', 'Display Name', 'Product Type', 'Last Activated Date', 'Windows', 'Mac', 'Windows 10 Mobile', 'iOS', 'Android', 'Activated On Shared Computer')
    }
    It 'flags a user at the desktop limit' { ($af | Where-Object Type -eq 'DesktopAtLimit').User | Should -Be 'sam.demo@contoso.example' }
    It 'flags a stale activation with its age' { ($af | Where-Object Type -eq 'StaleActivation').Detail | Should -BeLike 'Last activated 172 days ago*' }
    It 'reports mobile-only users and shared computers as Info, and does not count shared against the limit' {
        ($af | Where-Object Type -eq 'MobileOnly').Severity | Should -Be 'Info'
        ($af | Where-Object Type -eq 'SharedComputer').User | Should -Be 'taylor.demo@contoso.example'
        @($af | Where-Object { $_.Type -eq 'DesktopAtLimit' -and $_.User -like 'taylor*' }).Count | Should -Be 0
    }
    It 'uses the thresholds from the config' {
        $c = Get-ADConfig -Path (New-Config { param($c) $c.audit.desktopActivationLimit = 2; $c.audit.staleActivationDays = 400 })
        $f = @(Get-ADActivationFinding -Rows $rows -Config $c -Now $now)
        @($f | Where-Object Type -eq 'DesktopAtLimit').Count | Should -Be 2   # alex has 2, sam has 5
        @($f | Where-Object Type -eq 'StaleActivation').Count | Should -Be 0
    }
    It 'reads the report through Graph with an output file (mocked)' {
        $global:T13Csv = "$PSScriptRoot/fixtures/activations.csv"
        Mock -ModuleName AppsDeploy Invoke-MgGraphRequest { Copy-Item $global:T13Csv $OutputFilePath -Force } -ParameterFilter { $OutputFilePath }
        $r = @(Get-ADActivationReport)
        $r.Count | Should -Be 5
        Should -Invoke -ModuleName AppsDeploy Invoke-MgGraphRequest -ParameterFilter { $Uri -eq '/v1.0/reports/getOffice365ActivationsUserDetail' -and $Method -eq 'GET' }
    }
}

Describe 'Markdown' {
    It 'renders a sorted table with counts' {
        $md = ConvertTo-ADMarkdown -Title 'T' -Findings $af -Asof 'x'
        $md | Should -BeLike '*4 finding(s):** 0 High / 1 Medium / 1 Low / 2 Info*'
        $md.IndexOf('| Medium |') | Should -BeLessThan $md.IndexOf('| Low |')
    }
    It 'handles no findings' { (ConvertTo-ADMarkdown -Title 'T' -Findings @()) | Should -BeLike '*0 finding(s)*' }
}
