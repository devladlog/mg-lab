BeforeAll {
    # Invoke-MgGraphRequest only exists after Install-Module Microsoft.Graph.Authentication: a stub with the documented parameter
    # names lets Pester mock it. When the real module is installed it is used instead (and one test checks our calls against it).
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        Set-Item -Path function:global:Invoke-MgGraphRequest -Value ([scriptblock]::Create("[CmdletBinding()] param(`$Method, `$Uri, `$Body, `$ContentType, `$OutputType, `$Headers, `$OutputFilePath) throw 'stub: not connected'"))
    }
    Import-Module "$PSScriptRoot/../src/LicensingOptimization/LicensingOptimization.psd1" -Force
    $script:fx = "$PSScriptRoot/fixtures"
    $script:cfgPath = "$fx/licensing.test.json"
    $script:config = Get-LOConfig -Path $cfgPath
    $script:now = [datetimeoffset]'2026-11-21T12:00:00Z'
    $script:skus = @((Get-Content "$fx/skus.json" -Raw | ConvertFrom-Json).value)
    $script:users = @((Get-Content "$fx/users.json" -Raw | ConvertFrom-Json).value)
    $script:protectedIds = @('00000000-0000-0000-0000-000000000001')
    $script:E5 = '00000000-0000-0000-0000-00000000e500'; $script:BS = '00000000-0000-0000-0000-00000000b500'
    $script:GOV = '00000000-0000-0000-0000-000000006000'; $script:D365 = '00000000-0000-0000-0000-00000000d365'

    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json -Depth 10; & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 10 | Set-Content $p; $p
    }
    function script:Find([object[]]$Users = $users, $Cfg = $config, [string[]]$Protected = $protectedIds) {
        @(Get-LOLicenceFinding -Skus $skus -Users $Users -ProtectedUserId $Protected -Config $Cfg -Now $now)
    }
    function script:Clone($o) { $o | ConvertTo-Json -Depth 12 | ConvertFrom-Json -Depth 12 }
    function script:For-User([string]$Name, [object[]]$F = (Find)) { @($F | Where-Object User -like "$Name@*") }

    # A tiny fake Graph tenant in a global (the module-scope mock reads it). Every call is recorded.
    function script:Reset-Tenant {
        $global:T09 = @{ Calls = [System.Collections.Generic.List[object]]::new(); Skus = (Clone $skus); Users = (Clone $users); FailFor = @() }
    }
    function script:Register-FakeGraph {
        Mock Invoke-MgGraphRequest -ModuleName LicensingOptimization {
            $t = $global:T09
            $t.Calls.Add(@{ Method = $Method; Uri = $Uri; Body = $Body; ContentType = $ContentType })
            switch -Regex ($Uri) {
                '/v1\.0/subscribedSkus$' { return [pscustomobject]@{ value = $t.Skus } }
                '/v1\.0/users\?page2$' { return [pscustomobject]@{ value = @($t.Users | Select-Object -Skip 6) } }
                '/v1\.0/users\?' { return [pscustomobject]@{ value = @($t.Users | Select-Object -First 6); '@odata.nextLink' = '/v1.0/users?page2' } }
                '/v1\.0/directoryRoles\?' { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'r1'; displayName = 'Global Administrator' }, [pscustomobject]@{ id = 'r2'; displayName = 'Reports Reader' }) } }
                '/directoryRoles/r1/members' { return [pscustomobject]@{ value = @([pscustomobject]@{ '@odata.type' = '#microsoft.graph.user'; id = '00000000-0000-0000-0000-000000000001' }, [pscustomobject]@{ '@odata.type' = '#microsoft.graph.servicePrincipal'; id = '00000000-0000-0000-0000-0000000000f9' }) } }
                '/directoryRoles/r2/members' { return [pscustomobject]@{ value = @([pscustomobject]@{ '@odata.type' = '#microsoft.graph.user'; id = '00000000-0000-0000-0000-000000000001' }) } }
                '/v1\.0/users/(?<id>[^/?]+)/assignLicense$' {
                    if ($Matches.id -in $t.FailFor) { throw 'Forbidden: the license cannot be changed' }
                    $b = $Body | ConvertFrom-Json
                    $u = $t.Users | Where-Object id -eq $Matches.id
                    foreach ($r in @($b.removeLicenses)) {
                        $u.assignedLicenses = @($u.assignedLicenses | Where-Object skuId -ne $r)
                        $u.licenseAssignmentStates = @($u.licenseAssignmentStates | Where-Object { -not ($_.skuId -eq $r -and $null -eq $_.assignedByGroup) })
                        ($t.Skus | Where-Object skuId -eq $r).consumedUnits--
                    }
                    foreach ($a in @($b.addLicenses)) {
                        $u.assignedLicenses = @($u.assignedLicenses) + @([pscustomobject]@{ skuId = $a.skuId; disabledPlans = @($a.disabledPlans) })
                        $u.licenseAssignmentStates = @($u.licenseAssignmentStates) + @([pscustomobject]@{ skuId = $a.skuId; assignedByGroup = $null; state = 'Active'; error = $null })
                    }
                    return [pscustomobject]@{ id = $u.id }
                }
                '/v1\.0/users/(?<id>[^/?]+)\?' { return ($t.Users | Where-Object id -eq $Matches.id) }
            }
            throw "fake tenant: unexpected call $Method $Uri"
        }
    }
    function script:Plan([object[]]$F = (Find)) { @(Get-LOReclaimPlan -Findings $F -Config $config) }
    function script:Posts { @($global:T09.Calls | Where-Object Method -eq 'POST') }
}

Describe 'Config file' {
    It 'loads the shipped config, which reclaims nothing until you allow a SKU' {
        $c = Get-LOConfig -Path "$PSScriptRoot/../src/licensing.json"
        $c.inactivity.inactiveDays | Should -Be 90
        @($c.reclaim.allowedSkuPartNumbers).Count | Should -Be 0
        @($c.prices.perUserPerMonth.PSObject.Properties).Count | Should -Be 0
    }
    It 'loads the test config' { $config.prices.currency | Should -Be 'EUR' }
    It 'refuses a missing section' { { Get-LOConfig -Path (New-Config { param($c) $c.PSObject.Properties.Remove('reclaim') }) } | Should -Throw "*section 'reclaim'*" }
    It 'refuses inactiveDays of 0' { { Get-LOConfig -Path (New-Config { param($c) $c.inactivity.inactiveDays = 0 }) } | Should -Throw '*inactiveDays*' }
    It 'refuses a currency that is not a three-letter code' { { Get-LOConfig -Path (New-Config { param($c) $c.prices.currency = 'euros' }) } | Should -Throw '*currency*' }
    It 'refuses a negative price' { { Get-LOConfig -Path (New-Config { param($c) $c.prices.perUserPerMonth.SPE_E5 = -1 }) } | Should -Throw '*SPE_E5*' }
    It 'refuses a reclaim rule that does not exist' { { Get-LOConfig -Path (New-Config { param($c) $c.reclaim.rules = @('Everything') }) } | Should -Throw "*'Everything'*" }
    It 'refuses an empty supersededBy list' { { Get-LOConfig -Path (New-Config { param($c) $c.supersededBy.O365_BUSINESS_PREMIUM = @() }) } | Should -Throw '*supersededBy*' }
}

Describe 'Get-LOLicenceFinding: who holds a licence they do not use' {
    It 'finds an inactive user from the last sign-in when the successful one is not there' {
        $f = For-User 'jordan.demo' | Where-Object Rule -eq 'InactiveLicensed'
        @($f).Count | Should -Be 2   # E5 and Governance
        $f[0].DaysInactive | Should -Be 98   # lastNonInteractive 2026-08-15 is the newest of the two fallbacks
        $f[0].Detail | Should -BeLike '*98 days*'
    }
    It 'uses the last SUCCESSFUL sign-in: failed attempts do not keep a licence alive (Learn: lastSignInDateTime counts failures)' {
        $u = Clone $users; $a = $u | Where-Object userPrincipalName -like 'alex.demo@*'
        $a.signInActivity.lastSuccessfulSignInDateTime = '2026-06-01T10:00:00Z'; $a.signInActivity.lastSignInDateTime = '2026-11-20T10:00:00Z'
        (For-User 'alex.demo' (Find $u) | Where-Object Rule -eq 'InactiveLicensed').Count | Should -BeGreaterThan 0
    }
    It 'accepts dates as strings, as Graph returns them' {
        $u = Clone $users; $a = $u | Where-Object userPrincipalName -like 'alex.demo@*'
        $a.signInActivity.lastSuccessfulSignInDateTime = [string]'2026-06-01T10:00:00Z'
        (Find $u | Where-Object { $_.User -like 'alex.demo@*' -and $_.Rule -eq 'InactiveLicensed' }).DaysInactive | Select-Object -First 1 | Should -Be 173
    }
    It 'does not flag a user who signed in recently' { (For-User 'sam.demo' | Where-Object Rule -eq 'InactiveLicensed') | Should -BeNullOrEmpty }
    It 'flags a user who never signed in, but only after the grace period' {
        @(For-User 'riley.demo' | Where-Object Rule -eq 'NeverSignedIn').Count | Should -Be 2
        (For-User 'casey.demo') | Should -BeNullOrEmpty   # created 6 days ago
    }
    It 'flags a disabled account that still holds licences' {
        $f = For-User 'taylor.demo' | Where-Object Rule -eq 'DisabledAccountLicensed'
        @($f).Count | Should -Be 2
        ($f | Where-Object Sku -eq 'Microsoft_Entra_ID_Governance').Reclaimable | Should -BeTrue
    }
    It 'never marks a group-assigned licence as reclaimable, and says what to do instead' {
        $f = For-User 'taylor.demo' | Where-Object { $_.Sku -eq 'SPE_E5' -and $_.Rule -eq 'DisabledAccountLicensed' }
        $f.Source | Should -Be 'Group'; $f.Reclaimable | Should -BeFalse; $f.Detail | Should -BeLike '*remove the user from the group*'
    }
    It 'flags a licence another held licence covers (Business Standard next to E5)' {
        $f = For-User 'sam.demo' | Where-Object Rule -eq 'RedundantLicence'
        $f.Sku | Should -Be 'O365_BUSINESS_PREMIUM'; $f.Severity | Should -Be 'High'; $f.Reclaimable | Should -BeTrue; $f.Detail | Should -BeLike '*SPE_E5*'
    }
    It 'flags a licence that is assigned directly and through a group' {
        $f = For-User 'alex.demo' | Where-Object Rule -eq 'DuplicateDirectAndGroup'
        $f.Sku | Should -Be 'Microsoft_Entra_ID_Governance'; $f.Source | Should -Be 'Both'; $f.Reclaimable | Should -BeTrue; $f.MonthlySaving | Should -BeNullOrEmpty
    }
    It 'reports a group licensing error with the fix' {
        $f = For-User 'morgan.demo'
        $f.Rule | Should -Be 'AssignmentError'; $f.Severity | Should -Be 'High'; $f.Detail | Should -BeLike '*CountViolation*Not enough licences*'; $f.Reclaimable | Should -BeFalse
    }
    It 'protects members of an admin role, even when they would be flagged' {
        $u = Clone $users; $a = $u | Where-Object userPrincipalName -like 'labadmin@*'
        $a.signInActivity.lastSuccessfulSignInDateTime = '2026-01-01T00:00:00Z'
        $f = For-User 'labadmin' (Find $u) | Where-Object Rule -eq 'InactiveLicensed'
        @($f).Count | Should -Be 2; ($f.Reclaimable | Select-Object -Unique) | Should -BeFalse; $f[0].Detail | Should -BeLike '*holds an Entra admin role*'
    }
    It 'protects users that match protectedUsers' {
        $f = For-User 'emergency-01'
        @($f).Count | Should -Be 2; ($f.Reclaimable | Select-Object -Unique) | Should -BeFalse; $f[0].Detail | Should -BeLike '*protectedUsers*'
    }
    It 'turns the inactivity rules off, and says so, when no user has sign-in data (no Entra ID P1 or P2)' {
        $u = Clone $users; foreach ($x in $u) { $x.PSObject.Properties.Remove('signInActivity') }
        $f = Find $u
        @($f | Where-Object Rule -eq 'NoSignInData').Count | Should -Be 1
        @($f | Where-Object Rule -in 'InactiveLicensed', 'NeverSignedIn').Count | Should -Be 0
        ($f | Where-Object Rule -eq 'NoSignInData').Severity | Should -Be 'Info'
    }
    It 'reports overlapping plans between two licences when no supersede rule explains them' {
        (For-User 'dana.demo') | Should -BeNullOrEmpty   # E5 + E1 share 2 plans, the limit is 3
        $c = Get-LOConfig -Path (New-Config { param($c) $c.overlap.minSharedPlans = 2 })
        $f = For-User 'dana.demo' (Find $users $c)
        $f.Rule | Should -Be 'OverlappingPlans'; $f.Sku | Should -BeLike '*STANDARDPACK*'; $f.Reclaimable | Should -BeFalse
    }
    It 'ignores plans that are switched off in one of the licences' {
        $u = Clone $users; $d = $u | Where-Object userPrincipalName -like 'dana.demo@*'
        ($d.assignedLicenses | Where-Object skuId -eq $E5).disabledPlans = @('00000000-0000-0000-0000-0000000000a3')
        $c = Get-LOConfig -Path (New-Config { param($c) $c.overlap.minSharedPlans = 2 })
        (For-User 'dana.demo' (Find $u $c)) | Should -BeNullOrEmpty
    }
    It 'sorts the worst findings first' {
        $f = Find
        $f[0].Severity | Should -Be 'High'; $f[-1].Severity | Should -Be 'Low'
    }
    It 'attaches the monthly price to a saving rule only' {
        (For-User 'riley.demo' | Where-Object Sku -eq 'SPE_E5').MonthlySaving | Should -Be 50
        (For-User 'morgan.demo').MonthlySaving | Should -BeNullOrEmpty
    }
}

Describe 'Savings and seats' {
    It 'counts one seat per user and licence, however many rules hit it' {
        $f = Find
        $s = Get-LOSavingSummary -Findings $f -Config $config
        $s.Seats | Should -Be 6; $s.MonthlyTotal | Should -Be 122; $s.AnnualTotal | Should -Be 1464
        # the same seat hit twice (redundant AND inactive) is still one seat
        $dup = @($f | Where-Object { $_.User -like 'sam.demo@*' }) + @([pscustomobject]@{ Rule = 'InactiveLicensed'; User = 'sam.demo@contoso.example'; UserId = '00000000-0000-0000-0000-000000000003'; SkuId = $BS; Sku = 'O365_BUSINESS_PREMIUM'; Reclaimable = $true; MonthlySaving = 10 })
        (Get-LOSavingSummary -Findings $dup -Config $config).Seats | Should -Be 1
    }
    It 'does not count protected or group-assigned licences' {
        $s = Get-LOSavingSummary -Findings (Find) -Config $config
        $s.BySku.Sku | Should -Not -Contain 'Nothing'
        ($s.BySku | Where-Object Sku -eq 'SPE_E5').Seats | Should -Be 2   # jordan and riley, not emergency-01 and not taylor (group)
    }
    It 'shows no money when no price is configured' {
        $c = Get-LOConfig -Path (New-Config { param($c) $c.prices.perUserPerMonth = [pscustomobject]@{} })
        $s = Get-LOSavingSummary -Findings (Find $users $c) -Config $c
        $s.PricedSeats | Should -Be 0; $s.UnpricedSeats | Should -Be 6; $s.MonthlyTotal | Should -Be 0
    }
    It 'prices the seats that are paid for but not assigned, and skips SKUs that are not enabled' {
        $sk = Clone $skus; ($sk | Where-Object skuPartNumber -eq 'STANDARDPACK').capabilityStatus = 'Suspended'
        $r = @(Get-LOSeatSummary -Skus $sk -Config $config)
        ($r | Where-Object Sku -eq 'SPE_E5').Unassigned | Should -Be 17
        ($r | Where-Object Sku -eq 'SPE_E5').MonthlyIdleCost | Should -Be 850
        ($r | Where-Object Sku -eq 'O365_BUSINESS_PREMIUM').MonthlyIdleCost | Should -Be 40
        $r.Sku | Should -Not -Contain 'STANDARDPACK'
    }
}

Describe 'Get-LOReclaimPlan: what may be removed' {
    It 'plans only direct assignments of allowed SKUs for users who are not protected' {
        $p = Plan
        $p.Count | Should -Be 5
        ($p | ForEach-Object { "$($_.UserPrincipalName.Split('@')[0]):$($_.SkuPartNumber)" } | Sort-Object) -join ',' | Should -Be 'alex.demo:Microsoft_Entra_ID_Governance,jordan.demo:Microsoft_Entra_ID_Governance,riley.demo:Dynamics_365_Sales_Premium_Viral_Trial,sam.demo:O365_BUSINESS_PREMIUM,taylor.demo:Microsoft_Entra_ID_Governance'
    }
    It 'plans nothing when no SKU is allowed (the shipped default)' {
        $c = Get-LOConfig -Path (New-Config { param($c) $c.reclaim.allowedSkuPartNumbers = @() })
        @(Get-LOReclaimPlan -Findings (Find $users $c) -Config $c).Count | Should -Be 0
    }
    It 'never plans E5 for anyone while E5 is not allowed, even for an inactive user' { (Plan).SkuPartNumber | Should -Not -Contain 'SPE_E5' }
    It 'only plans the rules listed in reclaim.rules' {
        $c = Get-LOConfig -Path (New-Config { param($c) $c.reclaim.rules = @('RedundantLicence') })
        $p = @(Get-LOReclaimPlan -Findings (Find $users $c) -Config $c)
        $p.Count | Should -Be 1; $p[0].UserPrincipalName | Should -BeLike 'sam.demo@*'
    }
    It 'merges the rules that hit the same seat into one removal' {
        $u = Clone $users; $s = $u | Where-Object userPrincipalName -like 'sam.demo@*'
        $s.signInActivity.lastSuccessfulSignInDateTime = '2026-01-01T00:00:00Z'
        $p = @(Plan (Find $u) | Where-Object UserPrincipalName -like 'sam.demo@*')
        $p.Count | Should -Be 1; $p[0].Rules | Should -Contain 'RedundantLicence'; $p[0].Rules | Should -Contain 'InactiveLicensed'
    }
}

Describe 'Collection (fake Graph tenant)' {
    BeforeEach { Register-FakeGraph; Reset-Tenant }
    It 'lists SKUs' { @(Get-LOSku).Count | Should -Be 5 }
    It 'asks for sign-in activity and licence states, 500 per page, and follows the next link' {
        @(Get-LOUser).Count | Should -Be 10
        $c = @($global:T09.Calls | Where-Object { $_.Uri -like '*/users?*' -and $_.Uri -notlike '*page2' })
        $c[0].Uri | Should -BeLike '*signInActivity*'; $c[0].Uri | Should -BeLike '*licenseAssignmentStates*'; $c[0].Uri | Should -BeLike '*$top=500*'
    }
    It 'never asks for more than 500 per page' { Get-LOUser -Top 9000 | Out-Null; $global:T09.Calls[0].Uri | Should -BeLike '*$top=500*' }
    It 'lists admin role members once, users only' {
        $ids = @(Get-LOProtectedUserId)
        $ids.Count | Should -Be 1; $ids[0] | Should -Be '00000000-0000-0000-0000-000000000001'
    }
    It 'explains the 403 you get without Microsoft Entra ID P1 or P2' {
        Mock Invoke-MgGraphRequest -ModuleName LicensingOptimization { throw 'Forbidden: Authentication_RequestFromNonPremiumTenantOrB2CTenant' }
        { Get-LOUser } | Should -Throw '*Microsoft Entra ID P1 or P2*'
    }
    It 'only sends GET while auditing (the audit changes nothing)' {
        Get-LOSku | Out-Null; Get-LOUser | Out-Null; Get-LOProtectedUserId | Out-Null
        @($global:T09.Calls | Where-Object Method -ne 'GET').Count | Should -Be 0
    }
}

Describe 'Invoke-LOReclaim and Restore-LOReclaim (fake Graph tenant)' {
    BeforeEach { Register-FakeGraph; Reset-Tenant; $script:rb = Join-Path $TestDrive ("rollback-{0}.json" -f [guid]::NewGuid()) }
    It '-WhatIf sends nothing and writes no rollback file' {
        $r = @(Invoke-LOReclaim -Plan (Plan) -RollbackFile $rb -WhatIf)
        $r.Status | Select-Object -Unique | Should -Be 'WhatIf'
        @(Posts).Count | Should -Be 0; Test-Path $rb | Should -BeFalse
    }
    It 'removes exactly the planned SKU with the documented body, and writes the rollback file' {
        $p = @(Plan | Where-Object UserPrincipalName -like 'sam.demo@*')
        $r = @(Invoke-LOReclaim -Plan $p -RollbackFile $rb -Confirm:$false)
        $r.Status | Should -Be 'Removed'
        $post = @(Posts)
        $post.Count | Should -Be 1
        $post[0].Uri | Should -Be '/v1.0/users/00000000-0000-0000-0000-000000000003/assignLicense'
        $post[0].ContentType | Should -Be 'application/json'
        $b = $post[0].Body | ConvertFrom-Json
        @($b.addLicenses).Count | Should -Be 0
        @($b.removeLicenses) | Should -Be @($BS)
        $saved = @(Get-Content $rb -Raw | ConvertFrom-Json)
        $saved.Count | Should -Be 1; $saved[0].skuId | Should -Be $BS; $saved[0].skuPartNumber | Should -Be 'O365_BUSINESS_PREMIUM'
        # the user keeps E5
        (($global:T09.Users | Where-Object userPrincipalName -like 'sam.demo@*').assignedLicenses).skuId | Should -Be @($E5)
    }
    It 'sends a PUT/PATCH/DELETE never: only GET and POST assignLicense' {
        Invoke-LOReclaim -Plan (Plan) -RollbackFile $rb -Confirm:$false | Out-Null
        @($global:T09.Calls | Where-Object { $_.Method -notin 'GET', 'POST' }).Count | Should -Be 0
        (@(Posts) | Where-Object Uri -notlike '*/assignLicense').Count | Should -Be 0
    }
    It 'skips a licence that is no longer a direct assignment (the plan is older than the tenant)' {
        $p = @(Plan | Where-Object UserPrincipalName -like 'sam.demo@*')
        $sam = $global:T09.Users | Where-Object userPrincipalName -like 'sam.demo@*'
        $sam.licenseAssignmentStates = @($sam.licenseAssignmentStates | Where-Object skuId -ne $BS)
        $r = @(Invoke-LOReclaim -Plan $p -RollbackFile $rb -Confirm:$false)
        $r.Status | Should -Be 'Skipped'; @(Posts).Count | Should -Be 0
    }
    It 'keeps going after one failure and only records what was removed' {
        $global:T09.FailFor = @('00000000-0000-0000-0000-000000000003')
        $r = @(Invoke-LOReclaim -Plan (Plan) -RollbackFile $rb -Confirm:$false)
        ($r | Where-Object Status -eq 'Failed').Count | Should -Be 1
        ($r | Where-Object Status -eq 'Removed').Count | Should -Be 4
        @(Get-Content $rb -Raw | ConvertFrom-Json).Count | Should -Be 4
    }
    It 'refuses to overwrite an existing rollback file' {
        Set-Content $rb '[]'
        { Invoke-LOReclaim -Plan (Plan) -RollbackFile $rb -Confirm:$false } | Should -Throw '*already exists*'
        @(Posts).Count | Should -Be 0
    }
    It 'restores the licences from the rollback file, with the same disabled plans' {
        $p = @(Plan | Where-Object UserPrincipalName -like 'jordan.demo@*')
        $p[0].DisabledPlans = @('00000000-0000-0000-0000-0000000000a9')
        Invoke-LOReclaim -Plan $p -RollbackFile $rb -Confirm:$false | Out-Null
        $before = @(Posts).Count
        $r = @(Restore-LOReclaim -RollbackFile $rb -Confirm:$false)
        $r.Status | Should -Be 'Restored'
        $post = @(Posts)[$before]
        $b = $post.Body | ConvertFrom-Json
        $b.addLicenses[0].skuId | Should -Be $GOV; @($b.addLicenses[0].disabledPlans) | Should -Be @('00000000-0000-0000-0000-0000000000a9'); @($b.removeLicenses).Count | Should -Be 0
        (($global:T09.Users | Where-Object userPrincipalName -like 'jordan.demo@*').assignedLicenses).skuId | Should -Contain $GOV
    }
    It 'restore -WhatIf sends nothing' {
        Invoke-LOReclaim -Plan (Plan) -RollbackFile $rb -Confirm:$false | Out-Null
        $before = @(Posts).Count
        @(Restore-LOReclaim -RollbackFile $rb -WhatIf).Status | Select-Object -Unique | Should -Be 'WhatIf'
        @(Posts).Count | Should -Be $before
    }
    It 'does not restore into a SKU that has no free seat' {
        Invoke-LOReclaim -Plan @(Plan | Where-Object UserPrincipalName -like 'sam.demo@*') -RollbackFile $rb -Confirm:$false | Out-Null
        ($global:T09.Skus | Where-Object skuId -eq $BS).consumedUnits = 5   # all five seats taken meanwhile
        $before = @(Posts).Count
        $r = @(Restore-LOReclaim -RollbackFile $rb -Confirm:$false)
        $r.Status | Should -Be 'Failed'; $r.Message | Should -BeLike '*No free seat*'; @(Posts).Count | Should -Be $before
    }
}

Describe 'Report' {
    It 'writes findings, seats, the plan and the data-loss reminder' {
        $f = Find; $sv = Get-LOSavingSummary -Findings $f -Config $config
        $md = ConvertTo-LOMarkdown -Findings $f -Seats @(Get-LOSeatSummary -Skus $skus -Config $config) -Savings $sv -Plan (Plan) -UsersScanned 10 -GeneratedOn '2026-11-21' -Currency 'EUR'
        $md | Should -BeLike '*10 users scanned, 11 finding(s): High 2, Medium 8, Low 1, Info 0*'
        $md | Should -BeLike '*122 EUR per month, 1464 EUR per year*'
        $md | Should -BeLike '*## Reclaim plan (nothing removed yet)*'
        $md | Should -BeLike '*30 days*93 days*'
        $md | Should -BeLike '*| SPE_E5 | 25 | 8 | 17 | 850 EUR |*'
    }
    It 'says plainly when there are no prices' {
        $c = Get-LOConfig -Path (New-Config { param($c) $c.prices.perUserPerMonth = [pscustomobject]@{} })
        $f = Find $users $c
        (ConvertTo-LOMarkdown -Findings $f -Savings (Get-LOSavingSummary -Findings $f -Config $c) -UsersScanned 10) | Should -BeLike '*No prices configured*'
    }
}

Describe 'Runner and module surface' {
    It 'audits the fictional snapshot offline (child process, no Graph module needed)' {
        $out = pwsh -NoProfile -File "$PSScriptRoot/../src/Invoke-LicensingOptimization.ps1" -Snapshot "$fx/snapshot.json" -ConfigFile $cfgPath -AsOf 2026-11-21T12:00:00Z | Out-String
        $out | Should -BeLike '*10 user(s), 11 finding(s); reclaimable seats 6, potential 122 EUR per month*'
        $out | Should -BeLike '*Reclaim plan: 5 removal(s)*reclaimable but not allowed: SPE_E5*'
    }
    It 'refuses to reclaim from a snapshot' {
        $out = pwsh -NoProfile -File "$PSScriptRoot/../src/Invoke-LicensingOptimization.ps1" -Snapshot "$fx/snapshot.json" -ConfigFile $cfgPath -Reclaim -RollbackFile (Join-Path $TestDrive 'x.json') 2>&1 | Out-String
        $out | Should -BeLike '*needs live data*'
    }
    It 'only uses parameters that Invoke-MgGraphRequest really has' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
        Import-Module Microsoft.Graph.Authentication -Force
        $params = (Get-Command Invoke-MgGraphRequest -Module Microsoft.Graph.Authentication).Parameters.Keys
        $ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "$PSScriptRoot/../src/LicensingOptimization/LicensingOptimization.psm1").Path, [ref]$null, [ref]$null)
        $calls = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Invoke-MgGraphRequest' }, $true)
        $calls.Count | Should -BeGreaterThan 3
        $used = $calls | ForEach-Object { $_.CommandElements | Where-Object { $_ -is [System.Management.Automation.Language.CommandParameterAst] } | ForEach-Object ParameterName } | Sort-Object -Unique
        $used | Where-Object { $_ -notin $params } | Should -BeNullOrEmpty
        $used | Should -Contain 'Body'; $used | Should -Contain 'ContentType'
    }
    It 'exports what the manifest says' {
        $m = Import-PowerShellDataFile "$PSScriptRoot/../src/LicensingOptimization/LicensingOptimization.psd1"
        (Get-Module LicensingOptimization).ExportedFunctions.Keys | Sort-Object | Should -Be ($m.FunctionsToExport | Sort-Object)
    }
}
