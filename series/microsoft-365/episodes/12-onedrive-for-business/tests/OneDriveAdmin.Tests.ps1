BeforeAll {
    # Invoke-MgGraphRequest only exists after Install-Module Microsoft.Graph.Authentication: a stub with the documented parameter
    # names lets Pester mock it. When the real module is installed it is used instead (and one test checks our calls against it).
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        Set-Item -Path function:global:Invoke-MgGraphRequest -Value ([scriptblock]::Create("[CmdletBinding()] param(`$Method, `$Uri, `$Body, `$ContentType, `$OutputType, `$Headers, `$OutputFilePath) throw 'stub: not connected'"))
    }
    Import-Module "$PSScriptRoot/../src/OneDriveAdmin/OneDriveAdmin.psd1" -Force
    $script:fx = "$PSScriptRoot/fixtures"; $global:FX12 = $script:fx
    $script:blPath = "$fx/baseline.test.json"
    $script:baseline = Get-ODABaseline -Path $blPath
    $script:now = [datetimeoffset]'2026-11-21T12:00:00Z'
    $script:settings = Get-Content "$fx/settings.json" -Raw | ConvertFrom-Json
    $script:rows = @(Import-Csv "$fx/onedriveusage.csv")
    $script:tenant = '00000000-0000-0000-0000-0000000000aa'
    $script:root = 'HKLM:\SOFTWARE\Policies\Microsoft\OneDrive'

    function script:New-Baseline([scriptblock]$Change) {
        $c = Get-Content $blPath -Raw | ConvertFrom-Json -Depth 10; & $Change $c
        $p = Join-Path $TestDrive ("bl-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 10 | Set-Content $p; $p
    }
    function script:Clone($o) { $o | ConvertTo-Json -Depth 12 | ConvertFrom-Json -Depth 12 }
    function script:AccFind([object[]]$R = $rows, $B = $baseline, [long]$Default = 0) { @(Get-ODAAccountFinding -Rows $R -Baseline $B -Now $now -DefaultQuotaMB $Default) }
    function script:Row([string]$Owner, [hashtable]$Over = @{}) {
        $r = [ordered]@{ 'Report Refresh Date' = '2026-11-19'; 'Site URL' = ''; 'Owner Display Name' = 'Alex Demo'; 'Is Deleted' = 'False'; 'Last Activity Date' = '2026-11-18'; 'File Count' = '10'; 'Active File Count' = '1'
            'Storage Used (Byte)' = '1048576'; 'Storage Allocated (Byte)' = '1099511627776'; 'Owner Principal Name' = $Owner; 'Report Period' = '180' }
        foreach ($k in $Over.Keys) { $r[$k] = $Over[$k] }
        [pscustomobject]$r
    }

    # Fake tenant for the Graph calls (all GET).
    function script:Reset-Tenant { $global:T12 = @{ Calls = [System.Collections.Generic.List[object]]::new(); Deny = $false } }
    function script:Register-FakeGraph {
        Mock Invoke-MgGraphRequest -ModuleName OneDriveAdmin {
            $t = $global:T12
            $t.Calls.Add(@{ Method = $Method; Uri = $Uri; OutputFilePath = $OutputFilePath })
            switch -Regex ($Uri) {
                '/v1\.0/admin/sharepoint/settings$' { if ($t.Deny) { throw 'Forbidden (403)' }; return (Get-Content "$($global:FX12)/settings.json" -Raw | ConvertFrom-Json) }
                'getOneDriveUsageAccountDetail' { Copy-Item -LiteralPath "$($global:FX12)/onedriveusage.csv" -Destination $OutputFilePath; return }
                '/v1\.0/admin/reportSettings$' { return [pscustomobject]@{ displayConcealedNames = $true } }
            }
            throw "fake tenant: unexpected call $Method $Uri"
        }
    }

    # Fake registry for the PC side: the provider cmdlets are mocked, so this runs on any OS. Every write is recorded.
    function script:Reset-Reg {
        $global:R12 = @{ KeyExists = $false; Values = @{}; Writes = [System.Collections.Generic.List[object]]::new(); Removed = [System.Collections.Generic.List[string]]::new(); FailOn = '' }
    }
    function script:Register-FakeRegistry {
        Mock Test-Path -ModuleName OneDriveAdmin { $global:R12.KeyExists }
        Mock New-Item -ModuleName OneDriveAdmin { $global:R12.KeyExists = $true }
        Mock Get-ItemProperty -ModuleName OneDriveAdmin { $n = "$(@($Name)[0])"; if ($global:R12.Values.ContainsKey($n)) { [pscustomobject]@{ $n = $global:R12.Values[$n] } } }
        Mock New-ItemProperty -ModuleName OneDriveAdmin {
            if ($Name -eq $global:R12.FailOn) { throw "Access denied: $Name" }
            $global:R12.Values[$Name] = $Value; $global:R12.Writes.Add(@{ Name = $Name; Value = $Value; Type = $PropertyType; Path = $LiteralPath; Force = [bool]$Force })
        }
        Mock Remove-ItemProperty -ModuleName OneDriveAdmin { $n = "$(@($Name)[0])"; $global:R12.Values.Remove($n); $global:R12.Removed.Add($n) }
    }
}

Describe 'Get-ODABaseline' {
    It 'reads the shipped baseline and the test baseline' {
        (Get-ODABaseline -Path "$PSScriptRoot/../src/onedrive-baseline.json").settings.personalSiteDefaultStorageLimitInMB | Should -Be 1048576
        $baseline.accounts.inactiveDays | Should -Be 180
    }
    It 'rejects a name that is not a OneDrive setting the tool checks (a typo must not check nothing)' {
        { Get-ODABaseline -Path (New-Baseline { param($c) $c.settings | Add-Member isOneDriveEnabled $true }) } | Should -Throw '*not a OneDrive setting*'
    }
    It 'rejects a retention outside the 30 to 3650 days Learn documents' {
        { Get-ODABaseline -Path (New-Baseline { param($c) $c.settings.deletedUserPersonalSiteRetentionPeriodInDays = 29 }) } | Should -Throw '*from 30 to 3650*'
        { Get-ODABaseline -Path (New-Baseline { param($c) $c.settings.deletedUserPersonalSiteRetentionPeriodInDays = 3651 }) } | Should -Throw '*from 30 to 3650*'
        (Get-ODABaseline -Path (New-Baseline { param($c) $c.settings.deletedUserPersonalSiteRetentionPeriodInDays = 3650 })).settings.deletedUserPersonalSiteRetentionPeriodInDays | Should -Be 3650
    }
    It 'checks types, GUID lists and thresholds' {
        { Get-ODABaseline -Path (New-Baseline { param($c) $c.settings.isSyncButtonHiddenOnPersonalSite = 'no' }) } | Should -Throw '*true or false*'
        { Get-ODABaseline -Path (New-Baseline { param($c) $c.settings.allowedDomainGuidsForSyncApp = @('not-a-guid') }) } | Should -Throw '*list of GUIDs*'
        { Get-ODABaseline -Path (New-Baseline { param($c) $c.accounts.inactiveDays = 0 }) } | Should -Throw '*inactiveDays*'
        { Get-ODABaseline -Path (New-Baseline { param($c) $c.accounts.nearFullPercent = 0 }) } | Should -Throw '*nearFullPercent*'
        { Get-ODABaseline -Path (New-Baseline { param($c) $c.settings = [pscustomobject]@{} }) } | Should -Throw '*nothing to check*'
        { Get-ODABaseline -Path (New-Baseline { param($c) $c.PSObject.Properties.Remove('accounts') }) } | Should -Throw "*section 'accounts'*"
    }
}

Describe 'Get-ODASettingFinding' {
    It 'reports exactly the drifted settings, with their severity' {
        $f = @(Get-ODASettingFinding -Settings $settings -Baseline $baseline)
        ($f.Setting | Sort-Object) | Should -Be @('allowedDomainGuidsForSyncApp', 'deletedUserPersonalSiteRetentionPeriodInDays', 'isUnmanagedSyncAppForTenantRestricted')
        ($f | Where-Object Setting -eq 'isUnmanagedSyncAppForTenantRestricted').Severity | Should -Be 'High'
        ($f | Where-Object Setting -eq 'deletedUserPersonalSiteRetentionPeriodInDays').Severity | Should -Be 'Medium'
    }
    It 'explains what the unmanaged-PC restriction does when the baseline wants it on' {
        (Get-ODASettingFinding -Settings $settings -Baseline $baseline | Where-Object Setting -eq 'isUnmanagedSyncAppForTenantRestricted').Detail | Should -BeLike '*sync on any PC*'
    }
    It 'finds nothing when the tenant matches' {
        $s = Clone $settings; $s.deletedUserPersonalSiteRetentionPeriodInDays = 90; $s.isUnmanagedSyncAppForTenantRestricted = $true
        $s.allowedDomainGuidsForSyncApp = @('00000000-0000-0000-0000-0000000000D1')
        @(Get-ODASettingFinding -Settings $s -Baseline $baseline).Count | Should -Be 0
    }
    It 'reports a setting the tenant did not return as Info, never as drift' {
        $s = Clone $settings; $s.PSObject.Properties.Remove('isSyncButtonHiddenOnPersonalSite')
        $x = Get-ODASettingFinding -Settings $s -Baseline $baseline | Where-Object Setting -eq 'isSyncButtonHiddenOnPersonalSite'
        $x.Rule | Should -Be 'SettingNotReturned'; $x.Severity | Should -Be 'Info'
    }
}

Describe 'Account rows and concealed reports' {
    It 'parses bytes, dates and the used percentage, and works without a Site URL (the report may leave it empty)' {
        $j = @(Get-ODAAccountRow -Rows $rows) | Where-Object Owner -like 'jordan*'
        $j.UsedBytes | Should -Be 1013309915136; $j.UsedPercent | Should -Be 92.2; $j.LastActivity | Should -Be ([datetime]'2026-11-18')
    }
    It 'detects a concealed report and refuses to analyse it' {
        $c = @(Import-Csv "$fx/onedriveusage-concealed.csv")
        Test-ODAConcealedReport $c | Should -BeTrue; Test-ODAConcealedReport $rows | Should -BeFalse
        { Get-ODAAccountFinding -Rows $c -Baseline $baseline -Now $now } | Should -Throw '*concealed*Conceal user, group, and site names*'
    }
    It 'handles an empty report' {
        AccFind @() | Should -BeNullOrEmpty
        (Get-ODAStorageSummary -Rows @() -Baseline $baseline).Accounts | Should -Be 0
    }
}

Describe 'Get-ODAAccountFinding' {
    It 'flags every rule on the fixture and nothing else' {
        (AccFind $rows $baseline 1048576 | ForEach-Object { "$($_.Rule) $($_.Target -replace '@.*', '')" } | Sort-Object) | Should -Be @(
            'CustomQuota morgan.demo', 'DeletedRetained casey.former', 'InactiveOneDrive sam.demo', 'NearFull jordan.demo', 'NeverUsed riley.demo', 'NoActivityRecorded taylor.demo')
    }
    It 'CustomQuota only appears when the tenant default is known' {
        @(AccFind $rows $baseline 0 | Where-Object Rule -eq 'CustomQuota').Count | Should -Be 0
    }
    It 'a deleted owner is reported once, as retained, and nothing else' {
        $r = @(Row 'gone@contoso.com' @{ 'Is Deleted' = 'True'; 'Last Activity Date' = '2020-01-01'; 'Storage Used (Byte)' = '1099511627776' })
        (AccFind $r).Rule | Should -Be 'DeletedRetained'
    }
    It 'InactiveOneDrive flags the limit itself, not the day before' {
        $r = @((Row 'a@contoso.com' @{ 'Last Activity Date' = '2026-05-25' }), (Row 'b@contoso.com' @{ 'Last Activity Date' = '2026-05-26' }))
        $f = AccFind $r
        $f.Count | Should -Be 1; $f[0].Target | Should -Be 'a@contoso.com'; $f[0].Detail | Should -BeLike '*180 days ago*'
    }
    It 'NearFull flags the limit itself, and ignores an account without an allocation' {
        $r = @((Row 'q90@contoso.com' @{ 'Storage Used (Byte)' = '90'; 'Storage Allocated (Byte)' = '100' }), (Row 'q89@contoso.com' @{ 'Storage Used (Byte)' = '89'; 'Storage Allocated (Byte)' = '100' }),
            (Row 'none@contoso.com' @{ 'Storage Used (Byte)' = '999'; 'Storage Allocated (Byte)' = '' }))
        @(AccFind $r | Where-Object Rule -eq 'NearFull').Target | Should -Be @('q90@contoso.com')
    }
    It 'an unreadable number counts as zero instead of failing the audit' {
        { AccFind @(Row 'x@contoso.com' @{ 'Storage Used (Byte)' = 'n/a'; 'File Count' = '' }) } | Should -Not -Throw
    }
}

Describe 'Get-ODAStorageSummary' {
    It 'adds up the active accounts, counts the deleted ones apart and lists the biggest first' {
        $s = Get-ODAStorageSummary -Rows $rows -Baseline $baseline
        $s.Accounts | Should -Be 6; $s.DeletedAccounts | Should -Be 1; $s.UsedGB | Should -Be 1010.719
        $s.Top.Count | Should -Be 3; $s.Top[0].Owner | Should -BeLike 'jordan*'; $s.Top[1].Owner | Should -BeLike 'alex*'
    }
}

Describe 'Collection (fake Graph tenant)' {
    BeforeEach { Reset-Tenant; Register-FakeGraph }
    It 'reads the settings with one GET' {
        (Get-ODATenantSetting).personalSiteDefaultStorageLimitInMB | Should -Be 1048576
        @($global:T12.Calls).Count | Should -Be 1; $global:T12.Calls[0].Uri | Should -Be '/v1.0/admin/sharepoint/settings'
    }
    It 'turns a 403 into a message that names the permission and the roles' {
        $global:T12.Deny = $true
        { Get-ODATenantSetting } | Should -Throw '*SharePointTenantSettings.Read.All*SharePoint Administrator or Global Reader*'
    }
    It 'downloads the OneDrive usage report to a file, parses it, and removes the temp file' {
        $r = @(Get-ODAUsageReport -Period D30)
        $r.Count | Should -Be 7
        $c = $global:T12.Calls[0]
        $c.Uri | Should -Be "/v1.0/reports/getOneDriveUsageAccountDetail(period='D30')"
        Test-Path -LiteralPath $c.OutputFilePath | Should -BeFalse
    }
    It 'rejects a period the API does not support' { { Get-ODAUsageReport -Period D14 } | Should -Throw }
    It 'reads the concealed-names setting' { Get-ODAReportPrivacy | Should -BeTrue }
    It 'only ever sends GET: the tenant side is read-only' {
        Get-ODATenantSetting | Out-Null; Get-ODAUsageReport | Out-Null; Get-ODAReportPrivacy | Out-Null
        @($global:T12.Calls | Where-Object Method -ne 'GET').Count | Should -Be 0
    }
}

Describe 'Get-ODASyncPolicyPlan' {
    It 'plans silent sign-in, Files On-Demand and silent Known Folder Move for the three folders' {
        $p = @(Get-ODASyncPolicyPlan -TenantId $tenant)
        ($p | ForEach-Object { "$($_.Name)=$($_.Type):$($_.Value)" }) | Should -Be @(
            'SilentAccountConfig=DWord:1', 'FilesOnDemandEnabled=DWord:1', "KFMSilentOptIn=String:$tenant", 'KFMSilentOptInWithNotification=DWord:0',
            'KFMSilentOptInDesktop=DWord:1', 'KFMSilentOptInDocuments=DWord:1', 'KFMSilentOptInPictures=DWord:1')
    }
    It 'moves only the folders you name' {
        $p = @(Get-ODASyncPolicyPlan -TenantId $tenant -KnownFolders Documents)
        ($p.Name | Where-Object { $_ -like 'KFMSilentOptIn?*' -and $_ -ne 'KFMSilentOptInWithNotification' }) | Should -Be @('KFMSilentOptInDocuments')
    }
    It '-Notify and -BlockOptOut change one value and add one' {
        $p = @(Get-ODASyncPolicyPlan -TenantId $tenant -Notify -BlockOptOut)
        ($p | Where-Object Name -eq 'KFMSilentOptInWithNotification').Value | Should -Be 1
        ($p | Where-Object Name -eq 'KFMBlockOptOut').Value | Should -Be 1
        @(Get-ODASyncPolicyPlan -TenantId $tenant | Where-Object Name -eq 'KFMBlockOptOut').Count | Should -Be 0
    }
    It 'writes the tenant id as a lower-case string' {
        (Get-ODASyncPolicyPlan -TenantId '0000AAAA-0000-0000-0000-0000000000AA' | Where-Object Name -eq 'KFMSilentOptIn').Value | Should -Be '0000aaaa-0000-0000-0000-0000000000aa'
    }
    It 'rejects a tenant id that is not a GUID, an unknown folder and an empty folder list' {
        { Get-ODASyncPolicyPlan -TenantId 'contoso.onmicrosoft.com' } | Should -Throw '*not a GUID*'
        { Get-ODASyncPolicyPlan -TenantId $tenant -KnownFolders Downloads } | Should -Throw
        { Get-ODASyncPolicyPlan -TenantId $tenant -KnownFolders @() } | Should -Throw '*at least one*'
    }
}

Describe 'Set-ODASyncPolicy, Get-ODASyncPolicyState and Restore-ODASyncPolicy (fake registry)' {
    BeforeEach {
        Reset-Reg; Register-FakeRegistry
        $script:rb = Join-Path $TestDrive ("rb-{0}.json" -f [guid]::NewGuid())
        $script:plan = @(Get-ODASyncPolicyPlan -TenantId $tenant)
    }
    It '-WhatIf writes nothing and creates no rollback file' {
        $r = @(Set-ODASyncPolicy -Plan $plan -RollbackFile $rb -WhatIf)
        $r.Status | Select-Object -Unique | Should -Be 'WhatIf'; $r.Count | Should -Be 7
        $global:R12.Writes.Count | Should -Be 0; [IO.File]::Exists($rb) | Should -BeFalse; $global:R12.KeyExists | Should -BeFalse
    }
    It 'creates the key when it is missing and writes every value with the right type' {
        $r = @(Set-ODASyncPolicy -Plan $plan -RollbackFile $rb)
        $r.Status | Select-Object -Unique | Should -Be 'Written'
        $global:R12.KeyExists | Should -BeTrue
        $w = @($global:R12.Writes)
        $w.Count | Should -Be 7; ($w.Path | Select-Object -Unique) | Should -Be $root
        ($w | Where-Object Name -eq 'KFMSilentOptIn').Type | Should -Be 'String'
        ($w.Force | Select-Object -Unique) | Should -BeTrue
        ($w | Where-Object Name -eq 'SilentAccountConfig').Type | Should -Be 'DWord'
        $global:R12.Values.KFMSilentOptIn | Should -Be $tenant
    }
    It 'records what was there before, and what was absent, in the rollback file' {
        $global:R12.KeyExists = $true; $global:R12.Values.FilesOnDemandEnabled = 0
        Set-ODASyncPolicy -Plan $plan -RollbackFile $rb | Out-Null
        $j = Get-Content $rb -Raw | ConvertFrom-Json
        $j.root | Should -Be $root
        $fod = $j.items | Where-Object name -eq 'FilesOnDemandEnabled'
        $fod.existed | Should -BeTrue; $fod.previous | Should -Be 0; $fod.previousType | Should -Be 'DWord'
        ($j.items | Where-Object name -eq 'KFMSilentOptIn').existed | Should -BeFalse
    }
    It 'refuses to overwrite an existing rollback file' {
        Set-Content $rb '{}'
        { Set-ODASyncPolicy -Plan $plan -RollbackFile $rb } | Should -Throw '*already exists*'
        $global:R12.Writes.Count | Should -Be 0
    }
    It 'writes the rollback file before the first value, so a failure half way can still be undone' {
        $global:R12.FailOn = 'KFMSilentOptInWithNotification'
        { Set-ODASyncPolicy -Plan $plan -RollbackFile $rb } | Should -Throw '*Access denied*'
        $global:R12.Writes.Count | Should -Be 3
        @((Get-Content $rb -Raw | ConvertFrom-Json).items).Count | Should -Be 7
        $global:R12.FailOn = ''
        @(Restore-ODASyncPolicy -RollbackFile $rb).Status | Select-Object -Unique | Should -Be 'Restored'
        $global:R12.Values.Count | Should -Be 0
    }
    It 'reports Missing, Different and Compliant' {
        $global:R12.KeyExists = $true
        $global:R12.Values.SilentAccountConfig = 1; $global:R12.Values.FilesOnDemandEnabled = 0; $global:R12.Values.KFMSilentOptIn = $tenant.ToUpperInvariant()
        $s = @(Get-ODASyncPolicyState -Plan $plan)
        ($s | Where-Object Name -eq 'SilentAccountConfig').Status | Should -Be 'Compliant'
        ($s | Where-Object Name -eq 'FilesOnDemandEnabled').Status | Should -Be 'Different'
        ($s | Where-Object Name -eq 'KFMSilentOptIn').Status | Should -Be 'Compliant'
        ($s | Where-Object Name -eq 'KFMSilentOptInDesktop').Status | Should -Be 'Missing'
    }
    It 'reports everything Missing when the key does not exist' {
        @(Get-ODASyncPolicyState -Plan $plan).Status | Select-Object -Unique | Should -Be 'Missing'
    }
    It 'restores old values and removes the ones that did not exist' {
        $global:R12.KeyExists = $true; $global:R12.Values.FilesOnDemandEnabled = 0
        Set-ODASyncPolicy -Plan $plan -RollbackFile $rb | Out-Null
        $global:R12.Values.FilesOnDemandEnabled | Should -Be 1
        $r = @(Restore-ODASyncPolicy -RollbackFile $rb)
        $r.Status | Select-Object -Unique | Should -Be 'Restored'
        $global:R12.Values.FilesOnDemandEnabled | Should -Be 0
        $global:R12.Values.ContainsKey('KFMSilentOptIn') | Should -BeFalse
        $global:R12.Removed.Count | Should -Be 6
        (@($global:R12.Writes | Where-Object { $_.Name -eq 'FilesOnDemandEnabled' })[-1]).Type | Should -Be 'DWord'
    }
    It 'restore -WhatIf changes nothing' {
        Set-ODASyncPolicy -Plan $plan -RollbackFile $rb | Out-Null
        $n = $global:R12.Writes.Count
        @(Restore-ODASyncPolicy -RollbackFile $rb -WhatIf).Status | Select-Object -Unique | Should -Be 'WhatIf'
        $global:R12.Writes.Count | Should -Be $n; $global:R12.Removed.Count | Should -Be 0
    }
}

Describe 'ConvertTo-ODAMarkdown' {
    It 'writes the settings table, the account table and the storage table' {
        $f = @(Get-ODASettingFinding -Settings $settings -Baseline $baseline) + @(AccFind $rows $baseline 1048576)
        $md = ConvertTo-ODAMarkdown -Findings $f -Storage (Get-ODAStorageSummary -Rows $rows -Baseline $baseline) -GeneratedOn '2026-11-21' -Period D180
        $md | Should -BeLike '*## Tenant OneDrive settings against the baseline*'
        $md | Should -BeLike '*| High | isUnmanagedSyncAppForTenantRestricted |*'
        $md | Should -BeLike '*## Accounts (usage report, period D180)*| High | NearFull | jordan.demo@contoso.com |*'
        $md | Should -BeLike '*## Storage: 6 account(s), 1010.719 GB used, 1 deleted*'
    }
    It 'says so when everything matches' {
        $md = ConvertTo-ODAMarkdown -Findings @()
        $md | Should -BeLike '*Every baseline setting matches.*'; $md | Should -BeLike '*No findings.*'
    }
}

Describe 'Runners and module' {
    BeforeAll { $script:audit = (Resolve-Path "$PSScriptRoot/../src/Invoke-OneDriveAudit.ps1").Path; $script:pc = (Resolve-Path "$PSScriptRoot/../src/Set-OneDriveSyncPolicy.ps1").Path }
    It 'the audit runs offline on the fixtures and reports the findings' {
        $out = (& $audit -BaselineFile $blPath -SettingsFile "$fx/settings.json" -UsageFile "$fx/onedriveusage.csv" -AsOf 2026-11-21T12:00:00Z *>&1 | Out-String)
        $out | Should -BeLike '*9 finding(s)*'; $out | Should -BeLike '*6 account(s) in the report, 1010.719 GB used, 1 deleted*'
    }
    It 'the audit warns instead of failing on a concealed report, and still checks the settings' {
        $out = (& $audit -BaselineFile $blPath -SettingsFile "$fx/settings.json" -UsageFile "$fx/onedriveusage-concealed.csv" *>&1 | Out-String)
        $out | Should -BeLike '*concealed*'; $out | Should -BeLike '*isUnmanagedSyncAppForTenantRestricted*'
    }
    It 'the PC script has an Apply, a Check and a Restore parameter set, and parses' {
        $cmd = Get-Command $pc
        ($cmd.ParameterSets.Name | Sort-Object) | Should -Be @('Apply', 'Check', 'Restore')
        ($cmd.ParameterSets | Where-Object Name -eq 'Apply').Parameters.Where({ $_.IsMandatory }).Name | Should -Contain 'TenantId'
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($pc, [ref]$null, [ref]$null)
        $ast.ParamBlock.Attributes.Where({ $_.TypeName.Name -eq 'CmdletBinding' })[0].NamedArguments.Where({ $_.ArgumentName -eq 'DefaultParameterSetName' })[0].Argument.Value | Should -Be 'Apply'
    }
    It 'the PC script stops with a clear message when it is not on Windows' -Skip:$IsWindows {
        { & $pc -TenantId $tenant -WhatIf } | Should -Throw '*Windows registry*'
    }
    It 'only uses parameters that Invoke-MgGraphRequest really has' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
        Import-Module Microsoft.Graph.Authentication -Force
        $params = (Get-Command Invoke-MgGraphRequest -Module Microsoft.Graph.Authentication).Parameters.Keys
        $ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "$PSScriptRoot/../src/OneDriveAdmin/OneDriveAdmin.psm1").Path, [ref]$null, [ref]$null)
        $calls = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Invoke-MgGraphRequest' }, $true)
        $calls.Count | Should -BeGreaterThan 2
        $used = $calls | ForEach-Object { $_.CommandElements | Where-Object { $_ -is [System.Management.Automation.Language.CommandParameterAst] } | ForEach-Object ParameterName } | Sort-Object -Unique
        $used | Where-Object { $_ -notin $params } | Should -BeNullOrEmpty
        $used | Should -Contain 'OutputFilePath'
    }
    It 'only uses -PropertyType values that New-ItemProperty accepts on the registry provider' {
        $types = @(Get-ODASyncPolicyPlan -TenantId $tenant -BlockOptOut | ForEach-Object Type | Sort-Object -Unique)
        $valid = [Enum]::GetNames([Microsoft.Win32.RegistryValueKind])
        $types | Where-Object { $_ -notin $valid } | Should -BeNullOrEmpty
    }
    It 'exports what the manifest says' {
        $m = Import-PowerShellDataFile "$PSScriptRoot/../src/OneDriveAdmin/OneDriveAdmin.psd1"
        (Get-Module OneDriveAdmin).ExportedFunctions.Keys | Sort-Object | Should -Be ($m.FunctionsToExport | Sort-Object)
    }
}
