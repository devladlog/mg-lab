BeforeAll {
    # Invoke-MgGraphRequest only exists after Install-Module Microsoft.Graph.Authentication: a stub with the documented parameter
    # names lets Pester mock it. When the real module is installed it is used instead (and one test checks our calls against it).
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        Set-Item -Path function:global:Invoke-MgGraphRequest -Value ([scriptblock]::Create("[CmdletBinding()] param(`$Method, `$Uri, `$Body, `$ContentType, `$OutputType, `$Headers, `$OutputFilePath) throw 'stub: not connected'"))
    }
    Import-Module "$PSScriptRoot/../src/SharePointAdmin/SharePointAdmin.psd1" -Force
    $script:fx = "$PSScriptRoot/fixtures"
    $script:blPath = "$fx/baseline.test.json"
    $script:baseline = Get-SPABaseline -Path $blPath
    $script:now = [datetimeoffset]'2026-11-21T12:00:00Z'
    $script:settings = Get-Content "$fx/settings.json" -Raw | ConvertFrom-Json
    $script:rows = @(Import-Csv "$fx/siteusage.csv")

    function script:New-Baseline([scriptblock]$Change) {
        $c = Get-Content $blPath -Raw | ConvertFrom-Json -Depth 10; & $Change $c
        $p = Join-Path $TestDrive ("bl-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 10 | Set-Content $p; $p
    }
    function script:Clone($o) { $o | ConvertTo-Json -Depth 12 | ConvertFrom-Json -Depth 12 }
    function script:SiteFind([object[]]$R = $rows, $B = $baseline) { @(Get-SPASiteFinding -Rows $R -Baseline $B -Now $now) }
    function script:SettingFind($S = $settings, $B = $baseline) { @(Get-SPASettingFinding -Settings $S -Baseline $B) }
    function script:Row([string]$Url, [hashtable]$Over = @{}) {
        $r = [ordered]@{ 'Report Refresh Date' = '2026-11-19'; 'Site Id' = '00000000-0000-0000-0000-000000000099'; 'Site URL' = $Url; 'Owner Display Name' = 'Alex Demo'; 'Is Deleted' = 'False'; 'Last Activity Date' = '2026-11-18'
            'File Count' = '10'; 'Active File Count' = '1'; 'Page View Count' = '1'; 'Visited Page Count' = '1'; 'Storage Used (Byte)' = '1048576'; 'Storage Allocated (Byte)' = '26843545600'
            'Root Web Template' = 'Team Site'; 'Owner Principal Name' = 'alex.demo@contoso.com'; 'Report Period' = '180' }
        foreach ($k in $Over.Keys) { $r[$k] = $Over[$k] }
        [pscustomobject]$r
    }

    # A tiny fake tenant in a global (the module-scope mock reads it). Every call is recorded.
    function script:Reset-Tenant {
        $global:T11 = @{ Calls = [System.Collections.Generic.List[object]]::new(); Settings = (Clone $settings); FailFor = @(); ReportFile = "$fx/siteusage.csv"; Deny = $false }
    }
    function script:Register-FakeGraph {
        Mock Invoke-MgGraphRequest -ModuleName SharePointAdmin {
            $t = $global:T11
            $t.Calls.Add(@{ Method = $Method; Uri = $Uri; Body = $Body; ContentType = $ContentType; OutputFilePath = $OutputFilePath })
            switch -Regex ($Uri) {
                '/v1\.0/admin/sharepoint/settings$' {
                    if ($t.Deny) { throw 'Forbidden (403)' }
                    if ($Method -eq 'GET') { return (Clone $t.Settings) }
                    $b = $Body | ConvertFrom-Json -AsHashtable
                    foreach ($k in $b.Keys) {
                        if ($k -in $t.FailFor) { throw "BadRequest: cannot set $k" }
                        if ($null -eq $t.Settings.PSObject.Properties[$k]) { $t.Settings | Add-Member -NotePropertyName $k -NotePropertyValue $b[$k] } else { $t.Settings.$k = $b[$k] }
                    }
                    return (Clone $t.Settings)
                }
                'getSharePointSiteUsageDetail' { Copy-Item -LiteralPath $t.ReportFile -Destination $OutputFilePath; return }
                '/v1\.0/admin/reportSettings$' { return [pscustomobject]@{ displayConcealedNames = $true } }
            }
            throw "fake tenant: unexpected call $Method $Uri"
        }
    }
    function script:Patches { @($global:T11.Calls | Where-Object Method -eq 'PATCH') }
}

Describe 'Get-SPABaseline' {
    It 'reads the shipped baseline and the test baseline' {
        (Get-SPABaseline -Path "$PSScriptRoot/../src/sharepoint-baseline.json").settings.sharingCapability | Should -Be 'externalUserSharingOnly'
        $baseline.sites.inactiveDays | Should -Be 90
    }
    It 'ships read-only: nothing may be remediated by default' {
        @((Get-SPABaseline -Path "$PSScriptRoot/../src/sharepoint-baseline.json").remediate.allowedSettings).Count | Should -Be 0
    }
    It 'rejects a setting name that is not a tenant property (a typo must not check nothing)' {
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.settings | Add-Member isSharingEnabled $true }) } | Should -Throw "*not a tenant setting*"
    }
    It 'rejects the read-only and the object properties' {
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.settings | Add-Member availableManagedPathsForSiteCreation @('/sites/') }) } | Should -Throw '*not a tenant setting*'
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.settings | Add-Member idleSessionSignOut ([pscustomobject]@{ isEnabled = $true }) }) } | Should -Throw '*not supported*'
    }
    It 'checks the type and the allowed values of each setting' {
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.settings.sharingCapability = 'everyone' }) } | Should -Throw '*sharingCapability must be one of*'
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.settings.isLegacyAuthProtocolsEnabled = 'no' }) } | Should -Throw '*true or false*'
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.settings | Add-Member siteCreationDefaultStorageLimitInMB -1 }) } | Should -Throw '*whole number*'
    }
    It 'rejects thresholds out of range and an allowed setting that is not in the baseline' {
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.sites.inactiveDays = 0 }) } | Should -Throw '*inactiveDays*'
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.sites.nearQuotaPercent = 101 }) } | Should -Throw '*nearQuotaPercent*'
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.remediate.allowedSettings = @('isLoopEnabled') }) } | Should -Throw '*not a setting in the baseline*'
    }
    It 'rejects an empty or incomplete baseline' {
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.settings = [pscustomobject]@{} }) } | Should -Throw '*nothing to check*'
        { Get-SPABaseline -Path (New-Baseline { param($c) $c.PSObject.Properties.Remove('sites') }) } | Should -Throw "*section 'sites'*"
    }
}

Describe 'Get-SPASettingFinding' {
    It 'reports exactly the drifted settings' {
        $f = SettingFind
        ($f.Setting | Sort-Object) | Should -Be @('isResharingByExternalUsersEnabled', 'sharingCapability')
        ($f | Where-Object Setting -eq 'sharingCapability').Severity | Should -Be 'High'
        ($f | Where-Object Setting -eq 'isResharingByExternalUsersEnabled').Severity | Should -Be 'Medium'
    }
    It 'says more permissive for a wider sharing level and keeps the severity' {
        (SettingFind | Where-Object Setting -eq 'sharingCapability').Detail | Should -BeLike '*more permissive*'
    }
    It 'says stricter, and lowers the severity, for a narrower sharing level' {
        $s = Clone $settings; $s.sharingCapability = 'disabled'
        $x = SettingFind $s | Where-Object Setting -eq 'sharingCapability'
        $x.Detail | Should -BeLike '*stricter*'; $x.Severity | Should -Be 'Low'
    }
    It 'finds nothing when the tenant matches the baseline' {
        $s = Clone $settings; $s.sharingCapability = 'externalUserSharingOnly'; $s.isResharingByExternalUsersEnabled = $false
        SettingFind $s | Should -BeNullOrEmpty
    }
    It 'compares lists as sets, ignoring order and case' {
        $b = Get-SPABaseline -Path (New-Baseline { param($c) $c.settings | Add-Member sharingAllowedDomainList @('Contoso.com', 'fabrikam.com') })
        $s = Clone $settings; $s.sharingAllowedDomainList = @('fabrikam.com', 'contoso.com')
        (SettingFind $s $b | Where-Object Setting -eq 'sharingAllowedDomainList') | Should -BeNullOrEmpty
        $s.sharingAllowedDomainList = @('contoso.com')
        (SettingFind $s $b | Where-Object Setting -eq 'sharingAllowedDomainList').Rule | Should -Be 'SettingDrift'
    }
    It 'an empty baseline list drifts when the tenant has entries' {
        $b = Get-SPABaseline -Path (New-Baseline { param($c) $c.settings | Add-Member sharingBlockedDomainList @() })
        $s = Clone $settings; $s.sharingBlockedDomainList = @('example.org')
        (SettingFind $s $b | Where-Object Setting -eq 'sharingBlockedDomainList').Current | Should -Be @('example.org')
    }
    It 'reports a setting the tenant did not return as Info, never as drift' {
        $s = Clone $settings; $s.PSObject.Properties.Remove('isLegacyAuthProtocolsEnabled')
        $x = SettingFind $s | Where-Object Setting -eq 'isLegacyAuthProtocolsEnabled'
        $x.Rule | Should -Be 'SettingNotReturned'; $x.Severity | Should -Be 'Info'
    }
    It 'does not treat a boolean as equal to a string' {
        $s = Clone $settings; $s.isLegacyAuthProtocolsEnabled = 'false'
        (SettingFind $s | Where-Object Setting -eq 'isLegacyAuthProtocolsEnabled').Rule | Should -Be 'SettingDrift'
    }
}

Describe 'Site rows and concealed reports' {
    It 'leaves out deleted sites and the ignored URL patterns' {
        $r = @(Get-SPASiteRow -Rows $rows -Baseline $baseline)
        $r.Count | Should -Be 6
        $r.Url | Should -Not -Contain 'https://contoso.sharepoint.com/sites/deleted-old'
        $r.Url | Should -Not -Contain 'https://contoso.sharepoint.com/sites/contentTypeHub'
    }
    It 'parses bytes, dates and the used percentage' {
        $hr = @(Get-SPASiteRow -Rows $rows -Baseline $baseline) | Where-Object Url -like '*/hr'
        $hr.UsedBytes | Should -Be 25769803776; $hr.UsedPercent | Should -Be 96; $hr.LastActivity | Should -Be ([datetime]'2026-11-17')
    }
    It 'detects a concealed report (site URLs are hashes) and refuses to analyse it' {
        $c = @(Import-Csv "$fx/siteusage-concealed.csv")
        Test-SPAConcealedReport $c | Should -BeTrue
        Test-SPAConcealedReport $rows | Should -BeFalse
        { Get-SPASiteFinding -Rows $c -Baseline $baseline -Now $now } | Should -Throw '*concealed*Conceal user, group, and site names*'
    }
    It 'handles an empty report' {
        SiteFind @() | Should -BeNullOrEmpty
        (Get-SPAStorageSummary -Rows @() -Baseline $baseline).Sites | Should -Be 0
    }
}

Describe 'Get-SPASiteFinding' {
    It 'flags every rule on the fixture and nothing else' {
        $f = SiteFind
        ($f | ForEach-Object { "$($_.Rule) $($_.Target -replace '^.*/', '')" } | Sort-Object) | Should -Be @(
            'EmptySite new-empty', 'InactiveSite projects-archive', 'NearQuota hr', 'NoActivityRecorded new-empty', 'NoOwner orphan')
    }
    It 'InactiveSite counts days against the as-of date, and the limit itself is flagged' {
        $b = Get-SPABaseline -Path (New-Baseline { param($c) $c.sites.inactiveDays = 10 })
        $r = @((Row 'https://contoso.sharepoint.com/sites/a' @{ 'Last Activity Date' = '2026-11-11' }), (Row 'https://contoso.sharepoint.com/sites/b' @{ 'Last Activity Date' = '2026-11-12' }))
        $f = SiteFind $r $b
        $f.Count | Should -Be 1; $f[0].Target | Should -BeLike '*/a'; $f[0].Detail | Should -BeLike '*10 days ago*'
    }
    It 'NearQuota flags the limit itself, and ignores a site without an allocation' {
        $r = @((Row 'https://contoso.sharepoint.com/sites/q90' @{ 'Storage Used (Byte)' = '90'; 'Storage Allocated (Byte)' = '100' }),
            (Row 'https://contoso.sharepoint.com/sites/q89' @{ 'Storage Used (Byte)' = '89'; 'Storage Allocated (Byte)' = '100' }),
            (Row 'https://contoso.sharepoint.com/sites/noalloc' @{ 'Storage Used (Byte)' = '999'; 'Storage Allocated (Byte)' = '' }))
        @(SiteFind $r | Where-Object Rule -eq 'NearQuota').Target | Should -Be @('https://contoso.sharepoint.com/sites/q90')
    }
    It 'a site with activity today is not inactive' {
        SiteFind @(Row 'https://contoso.sharepoint.com/sites/t' @{ 'Last Activity Date' = '2026-11-21' }) | Should -BeNullOrEmpty
    }
    It 'an unreadable number counts as zero instead of failing the audit' {
        $r = @(Row 'https://contoso.sharepoint.com/sites/x' @{ 'Storage Used (Byte)' = 'n/a'; 'File Count' = '' })
        (SiteFind $r).Rule | Should -Be 'EmptySite'
    }
}

Describe 'Get-SPAStorageSummary' {
    It 'adds up the used storage and lists the biggest sites first' {
        $s = Get-SPAStorageSummary -Rows $rows -Baseline $baseline
        $s.Sites | Should -Be 6; $s.UsedGB | Should -Be 36.054
        $s.Top.Count | Should -Be 3
        $s.Top[0].Url | Should -BeLike '*/hr'; $s.Top[1].Url | Should -BeLike '*/projects-archive'; $s.Top[2].Url | Should -BeLike '*/finance'
    }
}

Describe 'Get-SPARemediationPlan' {
    It 'plans only a drifted setting that is also allowed' {
        $p = @(Get-SPARemediationPlan -Findings (SettingFind) -Baseline $baseline)
        $p.Count | Should -Be 1; $p[0].Setting | Should -Be 'isResharingByExternalUsersEnabled'; $p[0].Expected | Should -BeFalse
    }
    It 'plans nothing when no setting is allowed (the shipped default)' {
        $b = Get-SPABaseline -Path (New-Baseline { param($c) $c.remediate.allowedSettings = @() })
        @(Get-SPARemediationPlan -Findings (SettingFind $settings $b) -Baseline $b).Count | Should -Be 0
    }
    It 'never plans a site finding or a missing setting' {
        $f = @(SiteFind) + @([pscustomobject]@{ Rule = 'SettingNotReturned'; Setting = 'isResharingByExternalUsersEnabled' })
        @(Get-SPARemediationPlan -Findings $f -Baseline $baseline).Count | Should -Be 0
    }
}

Describe 'Collection (fake Graph tenant)' {
    BeforeEach { Reset-Tenant; Register-FakeGraph }
    It 'reads the settings with one GET' {
        (Get-SPATenantSetting).sharingCapability | Should -Be 'externalUserAndGuestSharing'
        @($global:T11.Calls).Count | Should -Be 1; $global:T11.Calls[0].Uri | Should -Be '/v1.0/admin/sharepoint/settings'
    }
    It 'turns a 403 into a message that names the permission and the roles' {
        $global:T11.Deny = $true
        { Get-SPATenantSetting } | Should -Throw '*SharePointTenantSettings.Read.All*SharePoint Administrator or Global Reader*'
    }
    It 'downloads the usage report to a file, parses it, and removes the temp file' {
        $r = @(Get-SPASiteUsageReport -Period D90)
        $r.Count | Should -Be 8; $r[1].'Site URL' | Should -Be 'https://contoso.sharepoint.com/sites/finance'
        $c = $global:T11.Calls[0]
        $c.Uri | Should -Be "/v1.0/reports/getSharePointSiteUsageDetail(period='D90')"
        Test-Path -LiteralPath $c.OutputFilePath | Should -BeFalse
    }
    It 'rejects a period the API does not support' { { Get-SPASiteUsageReport -Period D14 } | Should -Throw }
    It 'reads the concealed-names setting, and answers null when it cannot' {
        Get-SPAReportPrivacy | Should -BeTrue
        Mock Invoke-MgGraphRequest -ModuleName SharePointAdmin { throw 'Forbidden' }
        Get-SPAReportPrivacy | Should -BeNullOrEmpty
    }
    It 'only sends GET while auditing (the audit changes nothing)' {
        Get-SPATenantSetting | Out-Null; Get-SPASiteUsageReport | Out-Null; Get-SPAReportPrivacy | Out-Null
        @($global:T11.Calls | Where-Object Method -ne 'GET').Count | Should -Be 0
    }
}

Describe 'Invoke-SPARemediation and Restore-SPARemediation (fake Graph tenant)' {
    BeforeEach {
        Reset-Tenant; Register-FakeGraph
        $script:rb = Join-Path $TestDrive ("rb-{0}.json" -f [guid]::NewGuid())
        $script:plan = @(Get-SPARemediationPlan -Findings (SettingFind) -Baseline $baseline)
    }
    It '-WhatIf sends nothing and writes no rollback file' {
        $r = @(Invoke-SPARemediation -Plan $plan -RollbackFile $rb -WhatIf)
        $r.Status | Should -Be 'WhatIf'; @(Patches).Count | Should -Be 0; Test-Path $rb | Should -BeFalse
    }
    It 'changes one property per PATCH, with only that property in the body' {
        $r = @(Invoke-SPARemediation -Plan $plan -RollbackFile $rb -Confirm:$false)
        $r.Status | Should -Be 'Changed'
        @(Patches).Count | Should -Be 1
        $b = @(Patches)[0].Body | ConvertFrom-Json -AsHashtable
        $b.Keys | Should -Be @('isResharingByExternalUsersEnabled'); $b.isResharingByExternalUsersEnabled | Should -BeFalse
        @(Patches)[0].ContentType | Should -Be 'application/json'
        $global:T11.Settings.isResharingByExternalUsersEnabled | Should -BeFalse
        $global:T11.Settings.sharingCapability | Should -Be 'externalUserAndGuestSharing'   # untouched: not allowed
    }
    It 'writes the previous value to the rollback file' {
        Invoke-SPARemediation -Plan $plan -RollbackFile $rb -Confirm:$false | Out-Null
        $i = @(Get-Content $rb -Raw | ConvertFrom-Json)
        $i.Count | Should -Be 1; $i[0].setting | Should -Be 'isResharingByExternalUsersEnabled'; $i[0].previous | Should -BeTrue; $i[0].applied | Should -BeFalse
    }
    It 'refuses to overwrite an existing rollback file' {
        Set-Content $rb '[]'
        { Invoke-SPARemediation -Plan $plan -RollbackFile $rb -Confirm:$false } | Should -Throw '*already exists*'
        @(Patches).Count | Should -Be 0
    }
    It 'skips a setting that already matches when re-read, and sends nothing' {
        $global:T11.Settings.isResharingByExternalUsersEnabled = $false
        $r = @(Invoke-SPARemediation -Plan $plan -RollbackFile $rb -Confirm:$false)
        $r.Status | Should -Be 'Skipped'; @(Patches).Count | Should -Be 0; Test-Path $rb | Should -BeFalse
    }
    It 'stops at the first failure and keeps a rollback file with what did change' {
        $b = Get-SPABaseline -Path (New-Baseline { param($c) $c.remediate.allowedSettings = @('isResharingByExternalUsersEnabled', 'sharingCapability') })
        $p = @(Get-SPARemediationPlan -Findings (SettingFind $settings $b) -Baseline $b)
        $p.Count | Should -Be 2
        $global:T11.FailFor = @($p[1].Setting)
        $r = @(Invoke-SPARemediation -Plan $p -RollbackFile $rb -Confirm:$false)
        $r[0].Status | Should -Be 'Changed'; $r[1].Status | Should -Be 'Failed'; $r[1].Message | Should -BeLike '*cannot set*'
        @(Get-Content $rb -Raw | ConvertFrom-Json).Count | Should -Be 1
    }
    It 'does not run the later changes after a failure' {
        $b = Get-SPABaseline -Path (New-Baseline { param($c) $c.remediate.allowedSettings = @('isResharingByExternalUsersEnabled', 'sharingCapability') })
        $p = @(Get-SPARemediationPlan -Findings (SettingFind $settings $b) -Baseline $b)
        $global:T11.FailFor = @($p[0].Setting)
        $r = @(Invoke-SPARemediation -Plan $p -RollbackFile $rb -Confirm:$false)
        $r[0].Status | Should -Be 'Failed'; $r[1].Status | Should -Be 'NotRun'; @(Patches).Count | Should -Be 1
    }
    It 'sends a list setting as a JSON array, even with one entry' {
        $b = Get-SPABaseline -Path (New-Baseline { param($c) $c.settings | Add-Member sharingBlockedDomainList @('example.org'); $c.remediate.allowedSettings = @('sharingBlockedDomainList') })
        $p = @(Get-SPARemediationPlan -Findings (SettingFind $settings $b) -Baseline $b)
        Invoke-SPARemediation -Plan $p -RollbackFile $rb -Confirm:$false | Out-Null
        @(Patches)[0].Body | Should -Be '{"sharingBlockedDomainList":["example.org"]}'
    }
    It 'restores the previous value from the rollback file' {
        Invoke-SPARemediation -Plan $plan -RollbackFile $rb -Confirm:$false | Out-Null
        $r = @(Restore-SPARemediation -RollbackFile $rb -Confirm:$false)
        $r.Status | Should -Be 'Restored'
        $global:T11.Settings.isResharingByExternalUsersEnabled | Should -BeTrue
    }
    It 'does not overwrite a setting that someone changed after the remediation' {
        Invoke-SPARemediation -Plan $plan -RollbackFile $rb -Confirm:$false | Out-Null
        $global:T11.Settings.isResharingByExternalUsersEnabled = $true   # someone else put it back
        $before = @(Patches).Count
        $r = @(Restore-SPARemediation -RollbackFile $rb -Confirm:$false)
        $r.Status | Should -Be 'Skipped'; @(Patches).Count | Should -Be $before
    }
    It 'restore -WhatIf sends nothing' {
        Invoke-SPARemediation -Plan $plan -RollbackFile $rb -Confirm:$false | Out-Null
        $before = @(Patches).Count
        @(Restore-SPARemediation -RollbackFile $rb -WhatIf).Status | Should -Be 'WhatIf'; @(Patches).Count | Should -Be $before
    }
    It 'an empty plan does nothing' { @(Invoke-SPARemediation -Plan @() -RollbackFile $rb -Confirm:$false).Count | Should -Be 0 }
}

Describe 'ConvertTo-SPAMarkdown' {
    It 'writes the settings table, the site table, the storage table and the plan' {
        $f = @(SettingFind) + @(SiteFind)
        $md = ConvertTo-SPAMarkdown -Findings $f -Storage (Get-SPAStorageSummary -Rows $rows -Baseline $baseline) -Plan @(Get-SPARemediationPlan -Findings $f -Baseline $baseline) -GeneratedOn '2026-11-21' -Period D180
        $md | Should -BeLike '*## Tenant settings against the baseline*'
        $md | Should -BeLike '*| High | sharingCapability |*more permissive*'
        $md | Should -BeLike '*## Site hygiene (usage report, period D180)*'
        $md | Should -BeLike '*| High | NearQuota |*'
        $md | Should -BeLike '*## Storage: 6 site(s), 36.054 GB used*'
        $md | Should -BeLike '*## Remediation plan (nothing changed yet)*| isResharingByExternalUsersEnabled | true | false |*'
    }
    It 'says so when everything matches' {
        $md = ConvertTo-SPAMarkdown -Findings @()
        $md | Should -BeLike '*Every baseline setting matches.*'; $md | Should -BeLike '*No findings.*'
    }
}

Describe 'Runner and module' {
    BeforeAll { $script:runner = (Resolve-Path "$PSScriptRoot/../src/Invoke-SharePointAdmin.ps1").Path }
    It 'runs offline on the fixtures and reports the findings' {
        $out = (& $runner -BaselineFile $blPath -SettingsFile "$fx/settings.json" -UsageFile "$fx/siteusage.csv" -AsOf 2026-11-21T12:00:00Z *>&1 | Out-String)
        $out | Should -BeLike '*7 finding(s); remediation plan 1 change(s)*'
        $out | Should -BeLike '*6 site(s) in the report, 36.054 GB used*'
    }
    It 'refuses -Remediate on saved data' {
        { & $runner -BaselineFile $blPath -SettingsFile "$fx/settings.json" -UsageFile "$fx/siteusage.csv" -Remediate -RollbackFile (Join-Path $TestDrive 'x.json') } | Should -Throw '*needs the live tenant*'
    }
    It 'warns instead of failing on a concealed report, and still checks the settings' {
        $out = (& $runner -BaselineFile $blPath -SettingsFile "$fx/settings.json" -UsageFile "$fx/siteusage-concealed.csv" *>&1 | Out-String)
        $out | Should -BeLike '*concealed*'; $out | Should -BeLike '*sharingCapability*'
    }
    It 'only uses parameters that Invoke-MgGraphRequest really has' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
        Import-Module Microsoft.Graph.Authentication -Force
        $params = (Get-Command Invoke-MgGraphRequest -Module Microsoft.Graph.Authentication).Parameters.Keys
        $ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "$PSScriptRoot/../src/SharePointAdmin/SharePointAdmin.psm1").Path, [ref]$null, [ref]$null)
        $calls = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Invoke-MgGraphRequest' }, $true)
        $calls.Count | Should -BeGreaterThan 3
        $used = $calls | ForEach-Object { $_.CommandElements | Where-Object { $_ -is [System.Management.Automation.Language.CommandParameterAst] } | ForEach-Object ParameterName } | Sort-Object -Unique
        $used | Where-Object { $_ -notin $params } | Should -BeNullOrEmpty
        $used | Should -Contain 'Body'; $used | Should -Contain 'OutputFilePath'
    }
    It 'exports what the manifest says' {
        $m = Import-PowerShellDataFile "$PSScriptRoot/../src/SharePointAdmin/SharePointAdmin.psd1"
        (Get-Module SharePointAdmin).ExportedFunctions.Keys | Sort-Object | Should -Be ($m.FunctionsToExport | Sort-Object)
    }
}
