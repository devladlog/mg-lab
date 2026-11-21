BeforeAll {
    # Invoke-MgGraphRequest only exists after Install-Module Microsoft.Graph.Authentication: a stub with the documented parameter
    # names lets Pester mock it. When the real module is installed it is used instead (and one test checks our calls against it).
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        Set-Item -Path function:global:Invoke-MgGraphRequest -Value ([scriptblock]::Create("[CmdletBinding()] param(`$Method, `$Uri, `$Body, `$ContentType, `$OutputType, `$Headers, `$OutputFilePath) throw 'stub: not connected'"))
    }
    Import-Module "$PSScriptRoot/../src/CopilotReadiness/CopilotReadiness.psd1" -Force
    $script:cfgPath = "$PSScriptRoot/../src/copilot.json"
    $script:config = Get-CopilotConfig -Path $cfgPath
    $fx = "$PSScriptRoot/fixtures"
    $script:skus = @((Get-Content "$fx/skus.json" -Raw | ConvertFrom-Json).value)
    $script:users = @((Get-Content "$fx/users.json" -Raw | ConvertFrom-Json).value)
    $script:labels = @((Get-Content "$fx/labels.json" -Raw | ConvertFrom-Json).value)
    $script:drives = @((Get-Content "$fx/drives.json" -Raw | ConvertFrom-Json).drives)

    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json; & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 8 | Set-Content $p; $p
    }
    function script:Plan($name, $status = 'Success') { [pscustomobject]@{ servicePlanName = $name; provisioningStatus = $status } }

    # A tiny fake Graph tenant in a global (the module-scope mock reads it). Only GET is expected: every call is recorded.
    function script:Reset-Tenant {
        $global:T08 = @{ Calls = [System.Collections.Generic.List[object]]::new(); Skus = $skus; Users = $users; Labels = $labels; Drives = $drives }
    }
    function script:Register-FakeGraph {
        Mock Invoke-MgGraphRequest -ModuleName CopilotReadiness {
            $t = $global:T08
            $t.Calls.Add(@{ Method = $Method; Uri = $Uri })
            switch -Regex ($Uri) {
                '/v1\.0/subscribedSkus$' { return [pscustomobject]@{ value = $t.Skus } }
                '/v1\.0/users\?page2$' { return [pscustomobject]@{ value = @($t.Users | Select-Object -Skip 4) } }
                '/v1\.0/users\?' { return [pscustomobject]@{ value = @($t.Users | Select-Object -First 4); '@odata.nextLink' = '/v1.0/users?page2' } }
                '/users/(?<id>[^/]+)/licenseDetails$' {
                    $u = $t.Users | Where-Object id -eq $Matches.id
                    return [pscustomobject]@{ value = @([pscustomobject]@{ skuPartNumber = $u.licences[0]; servicePlans = $u.servicePlans }) }
                }
                '/security/dataSecurityAndGovernance/sensitivityLabels$' { return [pscustomobject]@{ value = $t.Labels } }
                '/v1\.0/sites\?search=' { return [pscustomobject]@{ value = @($t.Drives | ForEach-Object { [pscustomobject]@{ id = "site-$($_.id)"; displayName = $_.site } }) } }
                '/v1\.0/sites/site-(?<d>[^/]+)/drive' { return [pscustomobject]@{ id = $Matches.d; name = 'Documents'; webUrl = 'https://contoso.example/docs' } }
                '/drives/(?<d>[^/]+)/root/children' {
                    $d = $t.Drives | Where-Object id -eq $Matches.d
                    return [pscustomobject]@{ value = @($d.items | Where-Object { -not $_.parentId } | ForEach-Object { [pscustomobject]@{ id = $_.id; name = $_.name; folder = $(if ($_.folder) { [pscustomobject]@{ childCount = 1 } }) } }) }
                }
                '/drives/(?<d>[^/]+)/items/(?<i>[^/]+)/children' {
                    $d = $t.Drives | Where-Object id -eq $Matches.d; $i = $Matches.i
                    return [pscustomobject]@{ value = @($d.items | Where-Object parentId -eq $i | ForEach-Object { [pscustomobject]@{ id = $_.id; name = $_.name; folder = $(if ($_.folder) { [pscustomobject]@{ childCount = 1 } }) } }) }
                }
                '/drives/(?<d>[^/]+)/items/(?<i>[^/]+)/permissions$' {
                    $d = $t.Drives | Where-Object id -eq $Matches.d
                    return [pscustomobject]@{ value = @(($d.items | Where-Object id -eq $Matches.i).permissions) }
                }
                'getMicrosoft365CopilotUsageUserDetail' {
                    "Report Refresh Date,Report Period,User Principal Name,Display Name,Last Activity Date`n2026-11-20,7,alex.demo@contoso.com,Alex Demo,2026-11-19" | Set-Content -LiteralPath $OutputFilePath
                    return
                }
            }
            throw "fake tenant: unexpected call $Method $Uri"
        }
    }
    function script:Scan-All([int]$MaxDepth = 3, [int]$MaxItems = 200) {
        Register-FakeGraph; Reset-Tenant
        @(Get-CopilotDrive | ForEach-Object { Get-CopilotSharedItem -DriveId $_.DriveId -Site $_.Site -MaxDepth $MaxDepth -MaxItems $MaxItems })
    }
}

Describe 'Config file' {
    It 'loads the sample config' {
        $config.readiness.maxUsers | Should -Be 50
        'Microsoft_365_Copilot' | Should -BeIn $config.readiness.copilotSkuPartNumbers
    }
    It 'refuses a missing section' {
        { Get-CopilotConfig -Path (New-Config { param($c) $c.PSObject.Properties.Remove('sharing') }) } | Should -Throw "*section 'sharing'*"
    }
    It 'refuses an empty plan list' {
        { Get-CopilotConfig -Path (New-Config { param($c) $c.readiness.mailboxPlans = @() }) } | Should -Throw '*readiness.mailboxPlans*'
    }
    It 'refuses a maxUsers outside 1 to 1000' {
        { Get-CopilotConfig -Path (New-Config { param($c) $c.readiness.maxUsers = 0 }) } | Should -Throw '*maxUsers*'
        { Get-CopilotConfig -Path (New-Config { param($c) $c.readiness.maxUsers = 5000 }) } | Should -Throw '*maxUsers*'
    }
    It 'refuses a walk deeper than 10 and a non-numeric limit' {
        { Get-CopilotConfig -Path (New-Config { param($c) $c.sharing.maxDepth = 11 }) } | Should -Throw '*10 or less*'
        { Get-CopilotConfig -Path (New-Config { param($c) $c.sharing.maxItemsPerDrive = 'many' }) } | Should -Throw '*maxItemsPerDrive*'
    }
    It 'refuses a flag that is not true or false' {
        { Get-CopilotConfig -Path (New-Config { param($c) $c.sharing.flagOrganizationLinks = 'yes' }) } | Should -Throw '*flagOrganizationLinks*'
        { Get-CopilotConfig -Path (New-Config { param($c) $c.labels.requireFileLabel = 1 }) } | Should -Throw '*requireFileLabel*'
    }
}

Describe 'Collection (fake Graph tenant, read-only)' {
    BeforeEach { Register-FakeGraph; Reset-Tenant }
    It 'reads the subscribed SKUs' {
        @(Get-CopilotSku).Count | Should -Be 2
        $global:T08.Calls[0].Uri | Should -Be '/v1.0/subscribedSkus'
    }
    It 'pages the users and reads licenseDetails for each' {
        $r = @(Get-CopilotUserLicence -Top 50)
        $r.Count | Should -Be 6
        ($r | Where-Object userPrincipalName -eq 'alex.demo@contoso.com').servicePlans.servicePlanName | Should -Contain 'Bing_Chat_Enterprise'
        @($global:T08.Calls | Where-Object { $_.Uri -match 'licenseDetails$' }).Count | Should -Be 6
    }
    It '-Top stops early and does not read licenseDetails of the rest' {
        @(Get-CopilotUserLicence -Top 2).Count | Should -Be 2
        @($global:T08.Calls | Where-Object { $_.Uri -match 'licenseDetails$' }).Count | Should -Be 2
    }
    It 'reads the sensitivity labels from the tenant endpoint' {
        @(Get-CopilotLabel).Count | Should -Be 4
        $global:T08.Calls[0].Uri | Should -Be '/v1.0/security/dataSecurityAndGovernance/sensitivityLabels'
    }
    It 'finds the document library of each site' {
        $d = @(Get-CopilotDrive -Search 'contoso')
        $d.Site | Should -Be @('Contoso Marketing', 'Contoso Intranet')
        $d[0].DriveId | Should -Be 'drive-marketing'
    }
    It 'walks folders breadth-first and stops at MaxDepth' {
        $items = @(Get-CopilotSharedItem -DriveId 'drive-marketing' -Site 'M' -MaxDepth 3)
        $items.Path | Should -Contain '/a/b/c'
        $items.Path | Should -Not -Contain '/a/b/c/too-deep-payroll.docx'
        @(Get-CopilotSharedItem -DriveId 'drive-marketing' -MaxDepth 4).Path | Should -Contain '/a/b/c/too-deep-payroll.docx'
    }
    It 'stops at MaxItems' { @(Get-CopilotSharedItem -DriveId 'drive-marketing' -MaxItems 3).Count | Should -Be 3 }
    It 'never sends anything but GET (the review changes nothing)' {
        $null = Scan-All; $null = Get-CopilotUserLicence; $null = Get-CopilotLabel; $null = Get-CopilotSku
        $global:T08.Calls.Count | Should -BeGreaterThan 20
        @($global:T08.Calls | Where-Object { $_.Method -ne 'GET' }).Count | Should -Be 0
    }
    It 'escapes the site search term' {
        $null = Get-CopilotDrive -Search 'a b&c'
        $global:T08.Calls[0].Uri | Should -Be '/v1.0/sites?search=a%20b%26c'
    }
}

Describe 'Test-CopilotReadiness' {
    It 'reports no Copilot licence in the lab tenant, and a Copilot Studio trial is not one' {
        $r = Test-CopilotReadiness -Skus $skus -Users $users -Config $config
        $r.Tenant.HasCopilotLicence | Should -BeFalse
        $r.Tenant.SeatsEnabled | Should -Be 0
        $r.Tenant.SkuCount | Should -Be 2
    }
    It 'recognises a Copilot SKU by part number, with seats' {
        $copilot = [pscustomobject]@{ skuPartNumber = 'Microsoft_365_Copilot'; consumedUnits = 1; prepaidUnits = [pscustomobject]@{ enabled = 3 }; servicePlans = @() }
        $r = Test-CopilotReadiness -Skus ($skus + $copilot) -Users $users -Config $config
        $r.Tenant.HasCopilotLicence | Should -BeTrue
        $r.Tenant.CopilotSkus | Should -Be @('Microsoft_365_Copilot')
        ($r.Tenant.SeatsEnabled, $r.Tenant.SeatsAssigned) | Should -Be @(3, 1)
    }
    It 'recognises a Copilot SKU by its service plans when the part number is new' {
        $odd = [pscustomobject]@{ skuPartNumber = 'SOMETHING_NEW'; consumedUnits = 0; prepaidUnits = [pscustomobject]@{ enabled = 1 }; servicePlans = @(Plan 'M365_COPILOT_BUSINESS_CHAT') }
        (Test-CopilotReadiness -Skus @($odd) -Users @() -Config $config).Tenant.HasCopilotLicence | Should -BeTrue
    }
    It 'ignores a Copilot plan that is not provisioned' {
        $off = [pscustomobject]@{ skuPartNumber = 'SOMETHING_NEW'; consumedUnits = 0; prepaidUnits = [pscustomobject]@{ enabled = 1 }; servicePlans = @(Plan 'M365_COPILOT_APPS' 'Disabled') }
        (Test-CopilotReadiness -Skus @($off) -Users @() -Config $config).Tenant.HasCopilotLicence | Should -BeFalse
    }
    It 'classifies the users: Chat only, or not ready, with the reason' {
        $u = (Test-CopilotReadiness -Skus $skus -Users $users -Config $config).Users
        $by = @{}; $u | ForEach-Object { $by[$_.User] = $_ }
        $by['alex.demo@contoso.com'].Status | Should -Be 'Copilot Chat only'
        $by['alex.demo@contoso.com'].Notes | Should -BeNullOrEmpty
        $by['riley.demo@contoso.com'].Status | Should -Be 'Not ready'
        $by['riley.demo@contoso.com'].Notes | Should -BeLike '*no Copilot Chat entitlement plan*'
        $by['jordan.demo@contoso.com'].Status | Should -Be 'Not ready'
        $by['jordan.demo@contoso.com'].Notes | Should -BeLike '*account disabled*'
        $by['taylor.demo@contoso.com'].Status | Should -Be 'Copilot Chat only'
        $by['taylor.demo@contoso.com'].Mailbox | Should -BeFalse
        $by['taylor.demo@contoso.com'].Notes | Should -BeLike '*mailbox*'
    }
    It 'marks a user with a Copilot plan as Copilot licensed' {
        $x = [pscustomobject]@{ userPrincipalName = 'sam.demo@contoso.com'; displayName = 'Sam Demo'; accountEnabled = $true
            servicePlans = @(Plan 'M365_COPILOT_APPS'; Plan 'EXCHANGE_S_ENTERPRISE'; Plan 'OFFICESUBSCRIPTION') }
        $r = (Test-CopilotReadiness -Skus $skus -Users @($x) -Config $config).Users[0]
        $r.Status | Should -Be 'Copilot licensed'
        $r.CopilotChat | Should -BeTrue
    }
    It 'handles an empty tenant' {
        $r = Test-CopilotReadiness -Skus @() -Users @() -Config $config
        $r.Tenant.HasCopilotLicence | Should -BeFalse
        @($r.Users).Count | Should -Be 0
    }
}

Describe 'Get-CopilotLabelFinding' {
    It 'finds a missing container label and no auto-labeling in the sample set (a disabled label does not count)' {
        $f = @(Get-CopilotLabelFinding -Labels $labels -Config $config)
        $f.Rule | Should -Be @('NoContainerLabel', 'NoAutoLabel')
        ($f | Where-Object Rule -eq 'NoContainerLabel').Severity | Should -Be 'Medium'
    }
    It 'reports no labels at all as High' {
        $f = @(Get-CopilotLabelFinding -Labels @() -Config $config)
        $f.Count | Should -Be 1
        $f[0].Rule | Should -Be 'NoLabels'; $f[0].Severity | Should -Be 'High'
    }
    It 'treats all-disabled labels as no labels' { @(Get-CopilotLabelFinding -Labels @($labels | ForEach-Object { $c = $_ | ConvertTo-Json | ConvertFrom-Json; $c.isEnabled = $false; $c }) -Config $config)[0].Rule | Should -Be 'NoLabels' }
    It 'finds labels that cannot be applied to files' {
        $only = @([pscustomobject]@{ isEnabled = $true; isDefault = $true; applicationMode = 'automatic'; applicableTo = 'email' })
        (@(Get-CopilotLabelFinding -Labels $only -Config $config)).Rule | Should -Contain 'NoFileLabel'
    }
    It 'is clean for a complete label set' {
        $good = @([pscustomobject]@{ isEnabled = $true; isDefault = $true; applicationMode = 'automatic'; applicableTo = 'file, email, site, unifiedGroup' })
        @(Get-CopilotLabelFinding -Labels $good -Config $config).Count | Should -Be 0
    }
    It 'honours the config switches' {
        $cfg = Get-CopilotConfig -Path (New-Config { param($c) $c.labels.requireContainerLabel = $false })
        @(Get-CopilotLabelFinding -Labels $labels -Config $cfg).Rule | Should -Not -Contain 'NoContainerLabel'
    }
}

Describe 'Get-CopilotSharingFinding' {
    BeforeAll { $script:items = Scan-All }
    It 'finds the four broad permissions in the fixture, worst first' {
        $f = @(Get-CopilotSharingFinding -Items $items -Config $config)
        $f.Count | Should -Be 4
        ($f | ForEach-Object { "$($_.Severity) $($_.Signal) $($_.Path)" }) | Should -Be @(
            'High OrganizationLink /Board/minutes.docx'
            'High AnyoneLink /HR/salary-bands.xlsx'
            'Medium OrganizationLink /Campaigns/Launch plan.docx'
            'Medium EveryoneExceptExternalUsers /HR')
    }
    It 'reports Everyone except external users once, at the shallowest path (libraries return no inheritedFrom)' {
        $f = @(Get-CopilotSharingFinding -Items $items -Config $config | Where-Object Signal -eq 'EveryoneExceptExternalUsers')
        $f.Count | Should -Be 1
        $f[0].IsFolder | Should -BeTrue
    }
    It 'raises the severity when the name looks sensitive, and says so' {
        $f = @(Get-CopilotSharingFinding -Items $items -Config $config | Where-Object Path -like '*minutes*')
        $f[0].Severity | Should -Be 'High'; $f[0].Message | Should -BeLike '*looks sensitive*'
    }
    It 'ignores specific-people links, existing-access links and owners' {
        (Get-CopilotSharingFinding -Items $items -Config $config).Path | Should -Not -Contain '/Board'
        (Get-CopilotSharingFinding -Items $items -Config $config).Site | Should -Not -Contain 'Contoso Intranet'
    }
    It 'does not see items beyond MaxDepth' {
        (Get-CopilotSharingFinding -Items $items -Config $config).Path | Should -Not -Contain '/a/b/c/too-deep-payroll.docx'
        $deep = Scan-All -MaxDepth 4
        (Get-CopilotSharingFinding -Items $deep -Config $config).Path | Should -Contain '/a/b/c/too-deep-payroll.docx'
    }
    It 'follows the config switches' {
        $cfg = Get-CopilotConfig -Path (New-Config { param($c) $c.sharing.flagOrganizationLinks = $false; $c.sharing.flagEveryoneExceptExternalUsers = $false })
        @(Get-CopilotSharingFinding -Items $items -Config $cfg).Signal | Should -Be @('AnyoneLink')
    }
    It 'returns nothing for no items' { @(Get-CopilotSharingFinding -Items @() -Config $config).Count | Should -Be 0 }
    It 'gives the same answer from a saved snapshot (offline path)' {
        $snap = ConvertTo-CopilotSnapshot -Skus $skus -Users $users -Labels $labels -Items $items -Note 'fixture'
        $back = $snap | ConvertTo-Json -Depth 12 | ConvertFrom-Json
        $a = @(Get-CopilotSharingFinding -Items $items -Config $config | ForEach-Object { "$($_.Severity)|$($_.Path)" })
        $b = @(Get-CopilotSharingFinding -Items $back.items -Config $config | ForEach-Object { "$($_.Severity)|$($_.Path)" })
        $b | Should -Be $a
        (Test-CopilotReadiness -Skus $back.skus -Users $back.users -Config $config).Users.Count | Should -Be 6
    }
}

Describe 'Get-CopilotUsageReport (needs a Copilot licence in the tenant)' {
    BeforeEach { Register-FakeGraph; Reset-Tenant }
    It 'downloads the CSV report to a temp file, parses it and cleans up' {
        $r = @(Get-CopilotUsageReport -Period D28)
        $r.Count | Should -Be 1
        $r[0].'User Principal Name' | Should -Be 'alex.demo@contoso.com'
        $global:T08.Calls[0].Uri | Should -Be "/v1.0/copilot/reports/getMicrosoft365CopilotUsageUserDetail(period='D28')"
        @(Get-ChildItem ([IO.Path]::GetTempPath()) -Filter 'copilot-usage-*.csv' -ErrorAction SilentlyContinue).Count | Should -Be 0
    }
    It 'only accepts the periods Learn lists' { { Get-CopilotUsageReport -Period D30 } | Should -Throw }
}

Describe 'ConvertTo-CopilotMarkdown' {
    BeforeAll {
        $script:items = Scan-All
        $script:rd = Test-CopilotReadiness -Skus $skus -Users $users -Config $config
        $script:md = ConvertTo-CopilotMarkdown -Readiness $rd -LabelFindings @(Get-CopilotLabelFinding -Labels $labels -Config $config) `
            -SharingFindings @(Get-CopilotSharingFinding -Items $items -Config $config) -LabelCount 3 -ItemsScanned $items.Count -GeneratedOn '2026-11-21'
    }
    It 'says plainly that there is no Copilot licence' { $md | Should -BeLike '*No Microsoft 365 Copilot licence in this tenant*' }
    It 'lists every user with the Chat status' {
        $md | Should -BeLike '*| alex.demo@contoso.com | Copilot Chat only | yes |*'
        $md | Should -BeLike '*| riley.demo@contoso.com | Not ready | no |*'
    }
    It 'lists the label and sharing findings' {
        $md | Should -BeLike '*NoContainerLabel*'
        $md | Should -BeLike '*| High | AnyoneLink | Contoso Marketing | /HR/salary-bands.xlsx |*'
    }
    It 'states what the sampled walk is not' { $md | Should -BeLike '*not a replacement for the SharePoint Advanced Management*' }
    It 'reports seats when a licence exists' {
        $copilot = [pscustomobject]@{ skuPartNumber = 'Microsoft_365_Copilot'; consumedUnits = 1; prepaidUnits = [pscustomobject]@{ enabled = 3 }; servicePlans = @() }
        ConvertTo-CopilotMarkdown -Readiness (Test-CopilotReadiness -Skus @($copilot) -Users @() -Config $config) | Should -BeLike '*(1 of 3 seats assigned)*'
    }
}

Describe 'Runner, offline on the fictional snapshot' {
    BeforeAll {
        $script:runner = Resolve-Path "$PSScriptRoot/../src/Invoke-CopilotReadiness.ps1"
        $script:snap = Resolve-Path "$PSScriptRoot/fixtures/snapshot.json"
    }
    It 'the committed snapshot gives the same findings as the fake tenant walk' {
        $s = Get-Content $snap -Raw | ConvertFrom-Json
        $a = @(Get-CopilotSharingFinding -Items $s.items -Config $config | ForEach-Object { "$($_.Severity)|$($_.Signal)|$($_.Path)" })
        $b = @(Get-CopilotSharingFinding -Items (Scan-All) -Config $config | ForEach-Object { "$($_.Severity)|$($_.Signal)|$($_.Path)" })
        $a | Should -Be $b
    }
    It 'prints the tables and writes the markdown report' {
        $out = Join-Path $TestDrive 'r.md'
        $text = (& $runner -Snapshot $snap -OutFile $out) -join "`n"
        $text | Should -BeLike '*Copilot licence in tenant: NO*'
        $text | Should -BeLike '*4 broad-sharing finding(s)*'
        $text | Should -BeLike '*NoContainerLabel*'
        (Get-Content $out -Raw) | Should -BeLike '*No Microsoft 365 Copilot licence in this tenant*'
    }
    It 'refuses the usage report without a Copilot licence instead of faking one' {
        $text = (& $runner -Snapshot $snap -Check Usage 3>&1 *>&1) -join "`n"
        $text | Should -BeLike '*Usage report skipped*no Microsoft 365 Copilot licence*Nothing was faked*'
    }
    It 'rejects an unknown check' { { & $runner -Snapshot $snap -Check Everything } | Should -Throw }
}

Describe 'Our Graph calls against the real Microsoft.Graph.Authentication module' {
    It 'only uses parameters that Invoke-MgGraphRequest really has' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
        Import-Module Microsoft.Graph.Authentication -Force
        $params = (Get-Command Invoke-MgGraphRequest -Module Microsoft.Graph.Authentication).Parameters.Keys
        $ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "$PSScriptRoot/../src/CopilotReadiness/CopilotReadiness.psm1").Path, [ref]$null, [ref]$null)
        $calls = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Invoke-MgGraphRequest' }, $true)
        $calls.Count | Should -BeGreaterThan 2
        $used = $calls | ForEach-Object { $_.CommandElements | Where-Object { $_ -is [System.Management.Automation.Language.CommandParameterAst] } | ForEach-Object ParameterName } | Sort-Object -Unique
        $used | Where-Object { $_ -notin $params } | Should -BeNullOrEmpty
        $used | Should -Contain 'OutputFilePath'
    }
    It 'never calls a method other than GET' {
        $text = Get-Content "$PSScriptRoot/../src/CopilotReadiness/CopilotReadiness.psm1" -Raw
        [regex]::Matches($text, '-Method\s+(\w+)').Groups | Where-Object { $_.Name -eq 1 } | ForEach-Object Value | Sort-Object -Unique | Should -Be @('GET')
    }
}
