BeforeAll {
    # Security & Compliance cmdlets only exist after Connect-IPPSSession. Define stubs with the documented parameter
    # names (fixtures/learn-parameters.json) so Pester can mock them and parameter filters bind.
    $learnParams = Get-Content "$PSScriptRoot/fixtures/learn-parameters.json" -Raw | ConvertFrom-Json
    $stubParams = @{
        'Get-Label' = @('Identity'); 'Get-LabelPolicy' = @('Identity'); 'Get-ComplianceTag' = @('Identity')
        'Get-DlpCompliancePolicy' = @('Identity', 'DistributionDetail'); 'Get-RetentionCompliancePolicy' = @('Identity', 'DistributionDetail')
        'Get-DlpComplianceRule' = @('Identity', 'Policy'); 'Get-RetentionComplianceRule' = @('Identity', 'Policy')
        'Set-DlpCompliancePolicy' = @('Identity', 'Mode')
    }
    foreach ($n in 'New-Label', 'New-LabelPolicy', 'New-DlpCompliancePolicy', 'New-DlpComplianceRule', 'New-ComplianceTag', 'New-RetentionCompliancePolicy', 'New-RetentionComplianceRule') {
        $stubParams[$n] = @($learnParams.$n)
    }
    foreach ($n in $stubParams.Keys) {
        if (Get-Command $n -ErrorAction SilentlyContinue) { continue }
        $plist = ($stubParams[$n] | ForEach-Object { if ($_ -in 'DistributionDetail') { "[switch]`$$_" } else { "`$$_" } }) -join ', '
        Set-Item -Path "function:global:$n" -Value ([scriptblock]::Create("[CmdletBinding()] param($plist) throw 'stub: not connected'"))
    }
    Import-Module "$PSScriptRoot/../src/PurviewCompliance/PurviewCompliance.psd1" -Force
    $script:cfgPath = "$PSScriptRoot/../src/compliance.json"
    $script:config = Get-PurviewConfig -Path $cfgPath
    $script:inventory = Get-Content "$PSScriptRoot/fixtures/inventory.json" -Raw | ConvertFrom-Json
    $script:learn = Get-Content "$PSScriptRoot/fixtures/learn-parameters.json" -Raw | ConvertFrom-Json
    $script:now = [datetimeoffset]'2026-11-21T10:00:00Z'
    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json; & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 10 | Set-Content $p; $p
    }
    function script:Copy-Inventory { $inventory | ConvertTo-Json -Depth 10 | ConvertFrom-Json }
    function script:Find($Rule, $Target) { @($findings | Where-Object { $_.Rule -eq $Rule -and $_.Target -eq $Target }) }
    function script:Rule($PolicyIndex, $RuleIndex) { $config.dlpPolicies[$PolicyIndex].rules[$RuleIndex] }
}

Describe 'Config file' {
    It 'loads the sample config' { $config.dlpPolicies.Count | Should -Be 2 }
    It 'refuses a sensitivity label condition in a policy that includes Teams' {
        { Get-PurviewConfig -Path (New-Config { param($c) $c.dlpPolicies[1].locations += 'Teams' }) } | Should -Throw '*label condition*Teams*'
    }
    It 'refuses a policy tip longer than 256 characters' {
        { Get-PurviewConfig -Path (New-Config { param($c) $c.dlpPolicies[0].rules[0].policyTip = 'x' * 257 }) } | Should -Throw '*257 characters*256*'
    }
    It 'refuses HTML in a policy tip' {
        { Get-PurviewConfig -Path (New-Config { param($c) $c.dlpPolicies[0].rules[0].policyTip = '<b>Stop</b>' }) } | Should -Throw '*HTML*'
    }
    It 'refuses a rule without an action' {
        { Get-PurviewConfig -Path (New-Config { param($c) $r = $c.dlpPolicies[0].rules[0]; $r.notifyUser = @() }) } | Should -Throw '*needs an action*'
    }
    It 'refuses a rule without a condition' {
        { Get-PurviewConfig -Path (New-Config { param($c) $c.dlpPolicies[0].rules[0].sensitiveTypes = @() }) } | Should -Throw '*needs a condition*'
    }
    It 'refuses an unknown DLP mode' {
        { Get-PurviewConfig -Path (New-Config { param($c) $c.dlpPolicies[0].mode = 'Audit' }) } | Should -Throw '*mode must be one of*'
    }
    It 'refuses a label policy that publishes an undefined label' {
        { Get-PurviewConfig -Path (New-Config { param($c) $c.labelPolicy.labels += 'Top Secret' }) } | Should -Throw "*'Top Secret' is not defined*"
    }
    It 'refuses a label name over 64 characters' {
        { Get-PurviewConfig -Path (New-Config { param($c) $c.sensitivityLabels[0].name = 'L' * 65 }) } | Should -Throw '*longer than 64*'
    }
    It 'refuses a record label unless allowRecordLabels is set' {
        { Get-PurviewConfig -Path (New-Config { param($c) $c.retention.labels[0].isRecordLabel = $true }) } | Should -Throw '*record label*allowRecordLabels*'
        { Get-PurviewConfig -Path (New-Config { param($c) $c.retention.labels[0].isRecordLabel = $true; $c.retention.allowRecordLabels = $true }) } | Should -Not -Throw
    }
    It 'refuses Preservation Lock unless allowPreservationLock is set' {
        { Get-PurviewConfig -Path (New-Config { param($c) $c.retention.labelPolicy | Add-Member restrictiveRetention $true }) } | Should -Throw '*irreversible*'
    }
    It 'refuses a retention duration of 0' {
        { Get-PurviewConfig -Path (New-Config { param($c) $c.retention.labels[0].durationDays = 0 }) } | Should -Throw '*positive number*'
    }
}

Describe 'Sensitivity label parameters' {
    It 'maps the plain labels' {
        $p = ConvertTo-PVLabelParameter -Label $config.sensitivityLabels[0]
        $p.Name | Should -Be 'Contoso-Public'; $p.DisplayName | Should -Be 'Public'; $p.ContentType | Should -Be 'File, Email'
        $p.Contains('ApplyContentMarkingHeaderEnabled') | Should -BeFalse
    }
    It 'turns the Confidential header into content marking parameters' {
        $p = ConvertTo-PVLabelParameter -Label $config.sensitivityLabels[2]
        $p.ApplyContentMarkingHeaderEnabled | Should -BeTrue
        $p.ApplyContentMarkingHeaderText | Should -Be 'CONFIDENTIAL - Contoso internal'
        $p.ApplyContentMarkingHeaderFontColor | Should -Be '#C00000'
        $p.ApplyContentMarkingHeaderAlignment | Should -Be 'Center'
    }
    It 'publishes the label policy to the pilot mailboxes only' {
        $p = ConvertTo-PVLabelPolicyParameter -Config $config
        $p.Labels | Should -Be @('Contoso-Public', 'Contoso-General', 'Contoso-Confidential')
        $p.ExchangeLocation | Should -HaveCount 3
        $p.ExchangeLocation | Should -Not -Contain 'All'
    }
}

Describe 'DLP parameters' {
    It 'starts every policy in simulation with policy tips' {
        foreach ($pol in $config.dlpPolicies) { (ConvertTo-PVDlpPolicyParameter -Policy $pol).Mode | Should -Be 'TestWithNotifications' }
    }
    It 'maps locations to the documented *Location parameters with All' {
        $p = ConvertTo-PVDlpPolicyParameter -Policy $config.dlpPolicies[0]
        $p.ExchangeLocation | Should -Be 'All'; $p.SharePointLocation | Should -Be 'All'; $p.OneDriveLocation | Should -Be 'All'; $p.TeamsLocation | Should -Be 'All'
        (ConvertTo-PVDlpPolicyParameter -Policy $config.dlpPolicies[1]).Contains('TeamsLocation') | Should -BeFalse
    }
    It 'builds the sensitive type condition in the groups shape (min and max count)' {
        $c = ConvertTo-PVSensitiveInfoCondition -Rule (Rule 0 0)
        $c.operator | Should -Be 'And'
        $c.groups[0].sensitivetypes[0].name | Should -Be 'Credit Card Number'
        $c.groups[0].sensitivetypes[0].mincount | Should -Be 1
        $c.groups[0].sensitivetypes[0].maxcount | Should -Be 9
        (ConvertTo-PVSensitiveInfoCondition -Rule (Rule 0 1)).groups[0].sensitivetypes[0].maxcount | Should -Be -1
    }
    It 'builds the label condition with type Sensitivity' {
        $c = ConvertTo-PVSensitiveInfoCondition -Rule (Rule 1 0)
        $c.groups[0].labels[0].name | Should -Be 'Contoso-Confidential'
        $c.groups[0].labels[0].type | Should -Be 'Sensitivity'
    }
    It 'low count: notify only, no block' {
        $p = ConvertTo-PVDlpRuleParameter -Rule (Rule 0 0) -PolicyName 'Contoso - Card numbers'
        $p.Policy | Should -Be 'Contoso - Card numbers'
        $p.AccessScope | Should -Be 'NotInOrganization'
        $p.Contains('BlockAccess') | Should -BeFalse
        $p.NotifyUser | Should -Be @('Owner', 'LastModifier')
        $p.ReportSeverityLevel | Should -Be 'Medium'
    }
    It 'high count: block external, override with justification, incident report with all content' {
        $p = ConvertTo-PVDlpRuleParameter -Rule (Rule 0 1) -PolicyName 'Contoso - Card numbers'
        $p.BlockAccess | Should -BeTrue
        $p.NotifyAllowOverride | Should -Be 'WithJustification'
        $p.GenerateIncidentReport | Should -Be @('SiteAdmin')
        $p.IncidentReportContent | Should -Be 'All'
        $p.ReportSeverityLevel | Should -Be 'High'
    }
}

Describe 'Retention parameters' {
    It 'keeps for 2555 days from creation, then deletes' {
        $p = ConvertTo-PVRetentionLabelParameter -Label $config.retention.labels[0]
        $p.RetentionAction | Should -Be 'KeepAndDelete'; $p.RetentionDuration | Should -Be 2555
        $p.RetentionType | Should -Be 'CreationAgeInDays'; $p.IsRecordLabel | Should -BeFalse
    }
    It 'passes unlimited through' {
        $l = $config.retention.labels[0] | ConvertTo-Json | ConvertFrom-Json; $l.durationDays = 'unlimited'
        (ConvertTo-PVRetentionLabelParameter -Label $l).RetentionDuration | Should -Be 'unlimited'
    }
    It 'publishes with a PublishComplianceTag rule (no Name, no duration)' {
        $p = ConvertTo-PVRetentionRuleParameter -Config $config
        @($p.Keys) | Should -Be @('Policy', 'PublishComplianceTag')
        $p.PublishComplianceTag | Should -Be 'Contoso Contract - 7 years'
    }
    It 'never sets Preservation Lock by default' {
        $p = ConvertTo-PVRetentionPolicyParameter -Config $config
        $p.Contains('RestrictiveRetention') | Should -BeFalse
        $p.ExchangeLocation | Should -Be 'All'
    }
}

Describe 'Parameter names match Microsoft Learn' {
    It '<Cmdlet> uses only documented parameters' -ForEach @(
        @{ Cmdlet = 'New-Label' }, @{ Cmdlet = 'New-LabelPolicy' }, @{ Cmdlet = 'New-DlpCompliancePolicy' }, @{ Cmdlet = 'New-DlpComplianceRule' },
        @{ Cmdlet = 'New-ComplianceTag' }, @{ Cmdlet = 'New-RetentionCompliancePolicy' }, @{ Cmdlet = 'New-RetentionComplianceRule' }
    ) {
        $steps = @(Get-PurviewPlan -Config $config -Inventory ([pscustomobject]@{ labels = @(); labelPolicies = @(); dlpPolicies = @(); dlpRules = @(); retentionLabels = @(); retentionPolicies = @(); retentionRules = @() }))
        $used = @($steps | Where-Object Cmdlet -EQ $Cmdlet | ForEach-Object { $_.Params.Keys }) | Sort-Object -Unique
        $used.Count | Should -BeGreaterThan 0
        foreach ($k in $used) { $k | Should -BeIn @($learn.$Cmdlet) -Because "$Cmdlet -$k must exist on the Learn page" }
    }
}

Describe 'Plan' {
    BeforeAll { $script:plan = @(Get-PurviewPlan -Config $config -Inventory $inventory) }
    It 'creates the missing Confidential label, keeps the existing ones' {
        ($plan | Where-Object { $_.Kind -eq 'SensitivityLabel' -and $_.Name -eq 'Contoso-Confidential' }).Action | Should -Be 'Create'
        ($plan | Where-Object { $_.Kind -eq 'SensitivityLabel' -and $_.Name -eq 'Contoso-Public' }).Action | Should -Be 'Exists'
    }
    It 'reports label policy drift instead of overwriting it' {
        $s = $plan | Where-Object Kind -EQ 'LabelPolicy'
        $s.Action | Should -Be 'Drift'; $s.Detail | Should -BeLike '*Contoso-Confidential*'
    }
    It 'waits while the retention policy is Pending' {
        ($plan | Where-Object Kind -EQ 'RetentionRule').Action | Should -Be 'Wait'
    }
    It 'creates the missing DLP rule and policy, in order (policy before its rules)' {
        ($plan | Where-Object { $_.Name -eq 'Card numbers - high count' }).Action | Should -Be 'Create'
        $idxPolicy = [array]::IndexOf($plan.Name, 'Contoso - Confidential label')
        $idxRule = [array]::IndexOf($plan.Name, 'Confidential - external')
        $plan[$idxPolicy].Action | Should -Be 'Create'
        $idxPolicy | Should -BeLessThan $idxRule
    }
    It 'orders labels before label policy, retention label before its policy' {
        $kinds = @($plan.Kind)
        [array]::IndexOf($kinds, 'SensitivityLabel') | Should -BeLessThan ([array]::IndexOf($kinds, 'LabelPolicy'))
        [array]::IndexOf($kinds, 'RetentionLabel') | Should -BeLessThan ([array]::IndexOf($kinds, 'RetentionPolicy'))
    }
    It 'never changes a DLP mode on its own: different mode = Drift' {
        $inv = Copy-Inventory; $inv.dlpPolicies[0].mode = 'Enable'
        $s = @(Get-PurviewPlan -Config $config -Inventory $inv) | Where-Object { $_.Kind -eq 'DlpPolicy' -and $_.Name -eq 'Contoso - Card numbers' }
        $s.Action | Should -Be 'Drift'; $s.Detail | Should -BeLike '*-Promote*'
    }
}

Describe 'Findings' {
    BeforeAll { $script:findings = @(Get-PurviewFinding -Inventory $inventory -Config $config -Now $now) }
    It 'flags a retention policy whose distribution failed (High)' { (Find 'DistributionError' 'Retention policy: Legal records')[0].Severity | Should -Be 'High' }
    It 'notes Pending distribution as Info' { (Find 'DistributionPending' 'Retention policy: Contoso retention labels')[0].Severity | Should -Be 'Info' }
    It 'flags a simulation running longer than 15 days' {
        $f = (Find 'SimulationOverdue' 'DLP policy: Contoso - Card numbers')[0]
        $f.Severity | Should -Be 'Medium'; $f.Detail | Should -BeLike '*32 days*'
    }
    It 'does not flag a fresh simulation' {
        $inv = Copy-Inventory; $inv.dlpPolicies[0].whenChangedUtc = '2026-11-18T09:00:00Z'
        @(Get-PurviewFinding -Inventory $inv -Config $config -Now $now | Where-Object Rule -EQ 'SimulationOverdue') | Should -HaveCount 0
    }
    It 'flags a label condition in a policy that includes Teams (High)' { (Find 'LabelConditionWithTeams' 'DLP rule: HR - secret label')[0].Severity | Should -Be 'High' }
    It 'flags a label nobody can apply' { Find 'LabelNotPublished' 'Sensitivity label: Legacy-Secret' | Should -HaveCount 1 }
    It 'flags an unpublished retention label' { Find 'RetentionLabelNotPublished' 'Retention label: Contoso Contract - 7 years' | Should -HaveCount 1 }
    It 'notes record labels and Preservation Lock' {
        Find 'RecordLabel' 'Retention label: Legal Hold Record' | Should -HaveCount 1
        Find 'PreservationLock' 'Retention policy: Legal records' | Should -HaveCount 1
    }
    It 'lists what compliance.json has and the tenant lacks' {
        Find 'NotDeployed' 'SensitivityLabel: Contoso-Confidential' | Should -HaveCount 1
        Find 'NotDeployed' 'DlpPolicy: Contoso - Confidential label' | Should -HaveCount 1
        Find 'Drift' 'LabelPolicy: Contoso labels - pilot' | Should -HaveCount 1
    }
    It 'renders Markdown sorted by severity' {
        $md = ConvertTo-PurviewMarkdown -Inventory $inventory -Findings $findings -Now $now
        $md[0] | Should -Be '# Microsoft Purview audit'
        ($md | Where-Object { $_ -like '| *' } | Select-Object -Skip 2 -First 1) | Should -BeLike '| High |*'
    }
}

Describe 'DLP test content' {
    It 'validates Luhn' {
        Test-PVLuhn '4539 1488 0343 6467' | Should -BeTrue
        Test-PVLuhn '4539 1488 0343 6468' | Should -BeFalse
        Test-PVLuhn 'not a number' | Should -BeFalse
    }
    It 'generates N unique Luhn-valid 16-digit Visa-format numbers, each next to the keyword' {
        $lines = New-DlpTestContent -Count 12 -Seed 7
        $rows = @($lines | Select-Object -Skip 1)
        $rows | Should -HaveCount 12
        $numbers = foreach ($r in $rows) { ($r -match 'Visa card number (4\d{3} \d{4} \d{4} \d{4})$') | Should -BeTrue; $Matches[1] }
        foreach ($n in $numbers) { Test-PVLuhn $n | Should -BeTrue }
        @($numbers | Sort-Object -Unique) | Should -HaveCount 12
    }
    It 'is deterministic for a seed (same file every recording)' {
        (New-DlpTestContent -Count 5 -Seed 1) -join "`n" | Should -Be ((New-DlpTestContent -Count 5 -Seed 1) -join "`n")
    }
    It 'never uses the reserved test number 4111 1111 1111 1111' {
        (New-DlpTestContent -Count 200) -join "`n" | Should -Not -BeLike '*4111 1111 1111 1111*'
    }
}

Describe 'Invoke-PurviewPlan (mocked Security & Compliance)' {
    BeforeAll {
        $script:empty = [pscustomobject]@{ labels = @(); labelPolicies = @(); dlpPolicies = @(); dlpRules = @(); retentionLabels = @(); retentionPolicies = @(); retentionRules = @() }
    }
    It 'with -WhatIf calls nothing (its own WhatIf, because SCC ignores -WhatIf)' {
        Mock -ModuleName PurviewCompliance New-Label { }
        Mock -ModuleName PurviewCompliance New-DlpCompliancePolicy { }
        $r = @(Invoke-PurviewPlan -Plan @(Get-PurviewPlan -Config $config -Inventory $empty) -WhatIf)
        Should -Invoke -ModuleName PurviewCompliance New-Label -Times 0
        Should -Invoke -ModuleName PurviewCompliance New-DlpCompliancePolicy -Times 0
        @($r | Where-Object Result -EQ 'WhatIf').Count | Should -Be 12
    }
    It 'creates everything in order and never passes -WhatIf down' {
        $script:calls = [System.Collections.Generic.List[string]]::new()
        foreach ($c in 'New-Label', 'New-LabelPolicy', 'New-ComplianceTag', 'New-RetentionCompliancePolicy', 'New-RetentionComplianceRule', 'New-DlpCompliancePolicy', 'New-DlpComplianceRule') {
            Mock -ModuleName PurviewCompliance $c ([scriptblock]::Create("`$script:calls.Add('$c'); if (`$PSBoundParameters.ContainsKey('WhatIf')) { throw 'WhatIf passed' }"))
        }
        $r = @(Invoke-PurviewPlan -Plan @(Get-PurviewPlan -Config $config -Inventory $empty) -Confirm:$false)
        @($r | Where-Object Result -EQ 'Created').Count | Should -Be 12
        $calls[0] | Should -Be 'New-Label'
        $calls.IndexOf('New-LabelPolicy') | Should -Be 3
        $calls.IndexOf('New-DlpCompliancePolicy') | Should -BeLessThan $calls.IndexOf('New-DlpComplianceRule')
    }
    It 'passes the high-count rule parameters to New-DlpComplianceRule' {
        Mock -ModuleName PurviewCompliance New-DlpComplianceRule { }
        $step = @(Get-PurviewPlan -Config $config -Inventory $inventory) | Where-Object Name -EQ 'Card numbers - high count'
        Invoke-PurviewPlan -Plan @($step) -Confirm:$false | Out-Null
        Should -Invoke -ModuleName PurviewCompliance New-DlpComplianceRule -Times 1 -ParameterFilter {
            $Name -eq 'Card numbers - high count' -and $BlockAccess -eq $true -and $AccessScope -eq 'NotInOrganization' -and $NotifyAllowOverride -eq 'WithJustification'
        }
    }
    It 'stops at the first failure' {
        Mock -ModuleName PurviewCompliance New-Label { throw 'Access denied' }
        { Invoke-PurviewPlan -Plan @(Get-PurviewPlan -Config $config -Inventory $empty) -Confirm:$false } | Should -Throw "*SensitivityLabel 'Contoso-Public'*Access denied*"
    }
}

Describe 'Set-PurviewDlpMode (mocked)' {
    It 'promotes from simulation to Enable' {
        Mock -ModuleName PurviewCompliance Get-DlpCompliancePolicy { [pscustomobject]@{ Name = 'P'; Mode = 'TestWithNotifications'; DistributionStatus = 'Success' } }
        Mock -ModuleName PurviewCompliance Set-DlpCompliancePolicy { }
        (Set-PurviewDlpMode -Name 'P' -Mode Enable -Confirm:$false).From | Should -Be 'TestWithNotifications'
        Should -Invoke -ModuleName PurviewCompliance Set-DlpCompliancePolicy -Times 1 -ParameterFilter { $Mode -eq 'Enable' }
    }
    It 'refuses while distribution is Pending' {
        Mock -ModuleName PurviewCompliance Get-DlpCompliancePolicy { [pscustomobject]@{ Name = 'P'; Mode = 'TestWithNotifications'; DistributionStatus = 'Pending' } }
        { Set-PurviewDlpMode -Name 'P' -Confirm:$false } | Should -Throw '*Pending*'
    }
}

Describe 'Get-PurviewInventory (mocked)' {
    It 'normalizes cmdlet output into the inventory shape' {
        Mock -ModuleName PurviewCompliance Get-Label { [pscustomobject]@{ Name = 'Contoso-General'; DisplayName = 'General'; Guid = [guid]::Empty; Priority = 1 } }
        Mock -ModuleName PurviewCompliance Get-LabelPolicy { [pscustomobject]@{ Name = 'Contoso labels - pilot'; Labels = @('Contoso-General') } }
        Mock -ModuleName PurviewCompliance Get-DlpCompliancePolicy { [pscustomobject]@{ Name = 'Contoso - Card numbers'; Mode = 'TestWithNotifications'; DistributionStatus = 'Success'; ExchangeLocation = @('All'); TeamsLocation = @('All'); SharePointLocation = @(); OneDriveLocation = @(); WhenCreatedUTC = '2026-11-01T00:00:00Z'; WhenChangedUTC = '2026-11-01T00:00:00Z' } }
        Mock -ModuleName PurviewCompliance Get-DlpComplianceRule { [pscustomobject]@{ Name = 'Card numbers - low count'; Disabled = $false; ContentContainsSensitiveInformation = @(@{ name = 'Credit Card Number' }) } }
        Mock -ModuleName PurviewCompliance Get-ComplianceTag { [pscustomobject]@{ Name = 'Contoso Contract - 7 years'; RetentionAction = 'KeepAndDelete'; RetentionDuration = 2555; IsRecordLabel = $false } }
        Mock -ModuleName PurviewCompliance Get-RetentionCompliancePolicy { [pscustomobject]@{ Name = 'Contoso retention labels'; DistributionStatus = 'Success'; RestrictiveRetention = $false; Enabled = $true } }
        Mock -ModuleName PurviewCompliance Get-RetentionComplianceRule { [pscustomobject]@{ Name = 'r1'; PublishComplianceTag = 'Contoso Contract - 7 years' } }
        $inv = Get-PurviewInventory
        $inv.dlpPolicies[0].locations | Should -Be @('Exchange', 'Teams')
        $inv.dlpRules[0].policy | Should -Be 'Contoso - Card numbers'
        $inv.dlpRules[0].conditionJson | Should -BeLike '*Credit Card Number*'
        $inv.retentionRules[0].publishComplianceTag | Should -Be 'Contoso Contract - 7 years'
        Should -Invoke -ModuleName PurviewCompliance Get-DlpCompliancePolicy -ParameterFilter { $DistributionDetail } -Times 1
    }
}

Describe 'Real ExchangeOnlineManagement module' -Skip:(-not (Get-Module -ListAvailable ExchangeOnlineManagement)) {
    It 'Connect-IPPSSession takes the parameters the runner passes' {
        Import-Module ExchangeOnlineManagement -ErrorAction Stop
        $p = (Get-Command Connect-IPPSSession).Parameters.Keys
        $p | Should -Contain 'UserPrincipalName'
        $p | Should -Contain 'ShowBanner'
    }
}
