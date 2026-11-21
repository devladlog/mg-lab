BeforeAll {
    # Exchange Online cmdlets only exist after Connect-ExchangeOnline: stubs with the documented parameter names, so
    # Pester can mock them and parameter filters bind.
    $recipientParams = @('Identity', 'SentTo', 'SentToMemberOf', 'RecipientDomainIs', 'ExceptIfSentTo', 'ExceptIfSentToMemberOf', 'ExceptIfRecipientDomainIs')
    $stubs = @{
        'Get-EOPProtectionPolicyRule' = @('Identity'); 'Get-ATPProtectionPolicyRule' = @('Identity'); 'Get-ATPBuiltInProtectionRule' = @('Identity')
        'Set-EOPProtectionPolicyRule' = $recipientParams; 'Set-ATPProtectionPolicyRule' = $recipientParams
        'Enable-EOPProtectionPolicyRule' = @('Identity'); 'Enable-ATPProtectionPolicyRule' = @('Identity')
        'Get-EXOMailbox' = @('RecipientTypeDetails', 'ResultSize'); 'Get-DistributionGroupMember' = @('Identity', 'ResultSize')
        'Get-ConfigAnalyzerPolicyRecommendation' = @('RecommendedPolicyType', 'Identity')
        'Invoke-MgGraphRequest' = @('Method', 'Uri', 'Body', 'ContentType', 'OutputType', 'Headers', 'OutputFilePath')
    }
    foreach ($n in $stubs.Keys) {
        if (Get-Command $n -ErrorAction SilentlyContinue) { continue }
        $plist = ($stubs[$n] | ForEach-Object { "`$$_" }) -join ', '
        Set-Item -Path "function:global:$n" -Value ([scriptblock]::Create("[CmdletBinding()] param($plist) throw 'stub: not connected'"))
    }
    Import-Module "$PSScriptRoot/../src/DefenderForOffice/DefenderForOffice.psd1" -Force
    $script:cfgPath = "$PSScriptRoot/../src/defender.json"
    $script:config = Get-DefenderConfig -Path $cfgPath
    $script:inventory = Get-Content "$PSScriptRoot/fixtures/inventory.json" -Raw | ConvertFrom-Json
    $script:simReport = Get-Content "$PSScriptRoot/fixtures/simulation-report.json" -Raw | ConvertFrom-Json
    $script:huntResponse = Get-Content "$PSScriptRoot/fixtures/hunting-response.json" -Raw | ConvertFrom-Json
    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json; & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 8 | Set-Content $p; $p
    }
    function script:Copy-Inventory { $inventory | ConvertTo-Json -Depth 8 | ConvertFrom-Json }
    function script:Mbx($n) { $inventory.mailboxes | Where-Object primarySmtpAddress -Like "$n@*" }
    function script:New-Rule([hashtable]$h) {
        $r = [ordered]@{ state = 'Enabled'; sentTo = @(); sentToMemberOf = @(); recipientDomainIs = @(); exceptIfSentTo = @(); exceptIfSentToMemberOf = @(); exceptIfRecipientDomainIs = @() }
        foreach ($k in $h.Keys) { $r[$k] = $h[$k] }; [pscustomobject]$r
    }
    function script:Find($Rule, $Target) { @($findings | Where-Object { $_.Rule -eq $Rule -and $_.Target -eq $Target }) }
}

Describe 'Config file' {
    It 'loads the sample config' { $config.presets.standard.recipientDomainIs | Should -Be @('contoso.onmicrosoft.com') }
    It 'refuses combined condition types (they are ANDed)' {
        { Get-DefenderConfig -Path (New-Config { param($c) $c.presets.standard | Add-Member sentToMemberOf @('all-staff@contoso.onmicrosoft.com') }) } | Should -Throw '*ANDed*'
    }
    It 'allows them only when allowCombinedConditions is true' {
        { Get-DefenderConfig -Path (New-Config { param($c) $c.presets.standard | Add-Member sentToMemberOf @('all-staff@contoso.onmicrosoft.com'); $c.allowCombinedConditions = $true }) } | Should -Not -Throw
    }
    It 'refuses a preset without any recipient condition' {
        { Get-DefenderConfig -Path (New-Config { param($c) $c.presets.strict.sentToMemberOf = @() }) } | Should -Throw '*no recipient condition*'
    }
    It 'refuses a group that is not an email address' {
        { Get-DefenderConfig -Path (New-Config { param($c) $c.presets.strict.sentToMemberOf = @('Priority Accounts') }) } | Should -Throw "*isn't an email address*"
    }
    It 'refuses a hunting lookback over 30 days' {
        { Get-DefenderConfig -Path (New-Config { param($c) $c.hunting.lookbackDays = 90 }) } | Should -Throw '*between 1 and 30*'
    }
}

Describe 'Preset rule parameters' {
    It 'Strict: priority group, everything else explicitly $null' {
        $p = ConvertTo-DOPresetRuleParameter -Preset Strict -Config $config
        $p.Identity | Should -Be 'Strict Preset Security Policy'
        $p.SentToMemberOf | Should -Be @('priority-accounts@contoso.onmicrosoft.com')
        $p.Contains('SentTo') | Should -BeTrue
        $p.SentTo | Should -BeNullOrEmpty
        $p.RecipientDomainIs | Should -BeNullOrEmpty
    }
    It 'Standard: the accepted domain' {
        $p = ConvertTo-DOPresetRuleParameter -Preset Standard -Config $config
        $p.Identity | Should -Be 'Standard Preset Security Policy'
        $p.RecipientDomainIs | Should -Be @('contoso.onmicrosoft.com')
        @($p.Keys).Count | Should -Be 7
    }
}

Describe 'Recipient scope logic (Learn: OR within a condition, AND across types, any exception excludes)' {
    It 'matches a domain condition' { Test-DORecipientInScope -Rule (New-Rule @{ recipientDomainIs = @('contoso.onmicrosoft.com') }) -Mailbox (Mbx 'jordan.demo') -Inventory $inventory | Should -BeTrue }
    It 'ORs values of one condition' { Test-DORecipientInScope -Rule (New-Rule @{ sentTo = @('Alex Demo', 'sam.demo@contoso.onmicrosoft.com') }) -Mailbox (Mbx 'sam.demo') -Inventory $inventory | Should -BeTrue }
    It 'matches SentTo by display name or alias too' { Test-DORecipientInScope -Rule (New-Rule @{ sentTo = @('Alex Demo') }) -Mailbox (Mbx 'alex.demo') -Inventory $inventory | Should -BeTrue }
    It 'ANDs different condition types: domain + group excludes non-members' {
        $r = New-Rule @{ recipientDomainIs = @('contoso.onmicrosoft.com'); sentToMemberOf = @('all-staff@contoso.onmicrosoft.com') }
        Test-DORecipientInScope -Rule $r -Mailbox (Mbx 'jordan.demo') -Inventory $inventory | Should -BeFalse
        Test-DORecipientInScope -Rule $r -Mailbox (Mbx 'alex.demo') -Inventory $inventory | Should -BeTrue
    }
    It 'lets any exception win' {
        $r = New-Rule @{ recipientDomainIs = @('contoso.onmicrosoft.com'); exceptIfSentToMemberOf = @('priority-accounts@contoso.onmicrosoft.com') }
        Test-DORecipientInScope -Rule $r -Mailbox (Mbx 'riley.demo') -Inventory $inventory | Should -BeFalse
    }
    It 'treats no conditions as everyone (Built-in protection)' { Test-DORecipientInScope -Rule (New-Rule @{}) -Mailbox (Mbx 'sam.demo') -Inventory $inventory | Should -BeTrue }
    It 'a disabled rule applies to nobody' { Test-DORecipientInScope -Rule (New-Rule @{ state = 'Disabled' }) -Mailbox (Mbx 'sam.demo') -Inventory $inventory | Should -BeFalse }
}

Describe 'Coverage' {
    BeforeAll { $script:cov = @(Get-DOProtectionCoverage -Inventory $inventory) }
    It 'Strict wins over Standard for EOP' { ($cov | Where-Object Mailbox -Like 'riley.demo@*').Eop | Should -Be 'Strict' }
    It 'falls back to Standard when the Strict Defender rule is disabled' { ($cov | Where-Object Mailbox -Like 'riley.demo@*').Defender | Should -Be 'Standard' }
    It 'leaves a non-member on defaults + Built-in protection (the AND trap)' {
        $j = $cov | Where-Object Mailbox -Like 'jordan.demo@*'
        $j.Eop | Should -Be 'Default/custom'; $j.Defender | Should -Be 'Built-in protection'
    }
    It 'shows None when the mailbox is also excluded from Built-in protection' { ($cov | Where-Object Mailbox -Like 'taylor.demo@*').Defender | Should -Be 'None' }
    It 'covers everyone once the file is applied (domain only, Strict rule enabled)' {
        $inv = Copy-Inventory
        foreach ($r in $inv.rules) { if ($r.preset -eq 'Standard') { $r.sentToMemberOf = @() }; $r.state = 'Enabled'; if ($r.kind -eq 'BuiltIn') { $r.exceptIfSentTo = @() } }
        $c = @(Get-DOProtectionCoverage -Inventory $inv)
        @($c | Where-Object { $_.Eop -notin 'Strict', 'Standard' -or $_.Defender -notin 'Strict', 'Standard' }) | Should -HaveCount 0
        @($c | Where-Object { $_.Eop -eq 'Strict' }).Count | Should -Be 2
    }
}

Describe 'Findings' {
    BeforeAll { $script:findings = @(Get-DefenderFinding -Inventory $inventory -Config $config) }
    It 'finds 13 issues in the fictional tenant' { $findings | Should -HaveCount 13 }
    It 'flags the disabled Strict Defender rule (High)' { (Find 'PresetDisabled' 'ATP rule: Strict Preset Security Policy')[0].Severity | Should -Be 'High' }
    It 'explains the combined conditions and names who falls through' {
        $f = (Find 'CombinedConditions' 'EOP rule: Standard Preset Security Policy')[0]
        $f.Detail | Should -BeLike '*ANDed*jordan.demo@contoso.onmicrosoft.com*taylor.demo@contoso.onmicrosoft.com*'
    }
    It 'reports drift from defender.json' { (Find 'Drift' 'ATP rule: Standard Preset Security Policy')[0].Detail | Should -BeLike 'SentToMemberOf*all-staff*' }
    It 'flags priority accounts that are not on Strict' {
        Find 'PriorityNotStrict' 'Mailbox: labadmin@contoso.onmicrosoft.com' | Should -HaveCount 1
        Find 'PriorityNotStrict' 'Mailbox: riley.demo@contoso.onmicrosoft.com' | Should -HaveCount 1
    }
    It 'flags mailboxes left out of the presets, and one with no Safe Links or Safe Attachments' {
        Find 'NotOnPreset' 'Mailbox: jordan.demo@contoso.onmicrosoft.com' | Should -HaveCount 1
        (Find 'NoSafeLinksOrAttachments' 'Mailbox: taylor.demo@contoso.onmicrosoft.com')[0].Severity | Should -Be 'High'
    }
    It 'flags Built-in protection exceptions' { (Find 'BuiltInProtectionExcluded' 'Rule: ATP Built-In Protection Rule')[0].Detail | Should -BeLike '*taylor.demo*' }
    It 'turns configuration analyzer rows into findings' {
        (Find 'BelowStandard' 'ATP Safe Links: Contoso Safe Links (legacy)')[0].Detail | Should -Be "AllowClickThrough is 'True', Standard recommends 'False'."
    }
    It 'flags a missing preset rule (never turned on in the portal)' {
        $inv = Copy-Inventory; $inv.rules = @($inv.rules | Where-Object { -not ($_.kind -eq 'EOP' -and $_.preset -eq 'Strict') })
        $f = @(Get-DefenderFinding -Inventory $inv -Config $config | Where-Object Rule -EQ 'PresetRuleMissing')
        $f | Should -HaveCount 1; $f[0].Detail | Should -BeLike '*Defender portal*'
    }
    It 'renders Markdown with coverage and findings' {
        $md = ConvertTo-DefenderMarkdown -Inventory $inventory -Findings $findings
        $md[0] | Should -Be '# Defender for Office 365 audit'
        $md | Should -Contain '| taylor.demo@contoso.onmicrosoft.com | Default/custom | None |'
    }
}

Describe 'Hunting' {
    It 'builds the threat summary over the requested days' {
        $q = New-DOHuntingQuery -Kind ThreatSummary -Days 7
        $q | Should -BeLike 'EmailEvents*ago(7d)*isnotempty(ThreatTypes)*by ThreatTypes, DeliveryAction, DeliveryLocation*'
    }
    It 'builds the per-recipient query' { New-DOHuntingQuery -Kind Recipient -Recipient 'sam.demo@contoso.onmicrosoft.com' -Days 1 | Should -BeLike '*RecipientEmailAddress =~ "sam.demo@contoso.onmicrosoft.com"*take 20*' }
    It 'refuses anything that could break out of the KQL string' {
        { New-DOHuntingQuery -Kind Recipient -Recipient 'x" | take 1 //@contoso.com' } | Should -Throw "*isn't a plain email address*"
    }
    It 'converts schema + results to objects, also with lowercase keys' {
        $rows = @(ConvertFrom-DOHuntingResult -Response $huntResponse)
        $rows | Should -HaveCount 2
        @($rows[0].PSObject.Properties.Name) | Should -Be @('ThreatTypes', 'DeliveryAction', 'DeliveryLocation', 'Messages', 'Recipients')
        $rows[0].DeliveryLocation | Should -Be 'Quarantine'
        $rows[1].ThreatTypes | Should -Be 'Spam'; $rows[1].Messages | Should -Be 3
    }
    It 'posts Query and Timespan to runHuntingQuery' {
        Mock -ModuleName DefenderForOffice Invoke-MgGraphRequest { $huntResponse }
        $r = @(Invoke-DOHuntingQuery -Query (New-DOHuntingQuery -Kind ThreatSummary -Days 7) -Days 7)
        $r | Should -HaveCount 2
        Should -Invoke -ModuleName DefenderForOffice Invoke-MgGraphRequest -Times 1 -ParameterFilter {
            $Method -eq 'POST' -and $Uri -eq '/v1.0/security/runHuntingQuery' -and ($Body | ConvertFrom-Json).Timespan -eq 'P7D' -and ($Body | ConvertFrom-Json).Query -like 'EmailEvents*'
        }
    }
}

Describe 'Attack simulation' {
    BeforeAll { $script:sum = Get-DOSimulationSummary -Report $simReport -Config $config }
    It 'computes compromise and report rates' {
        $sum.Targeted | Should -Be 4; $sum.Compromised | Should -Be 2; $sum.CompromisedPct | Should -Be 50
        $sum.Reported | Should -Be 1; $sum.ReportedPct | Should -Be 25
    }
    It 'shows training progress per user' { ($sum.Users | Where-Object User -Like 'Alex Demo*').Training | Should -Be '0/2' }
    It 'flags a compromise rate above the target and compromised users without training' {
        ($sum.Findings | Where-Object Rule -EQ 'CompromiseRateHigh').Detail | Should -BeLike '2 of 4 users compromised (50%)*20%*'
        ($sum.Findings | Where-Object Rule -EQ 'CompromisedNoTraining').Target | Should -Be 'User: jordan.demo@contoso.onmicrosoft.com'
    }
    It 'gets the latest simulation and pages through its users' {
        Mock -ModuleName DefenderForOffice Invoke-MgGraphRequest -ParameterFilter { $Uri -like '*simulations?*' } { [pscustomobject]@{ value = @($simReport.simulation) } }
        Mock -ModuleName DefenderForOffice Invoke-MgGraphRequest -ParameterFilter { $Uri -like '*simulationUsers' } { [pscustomobject]@{ value = @($simReport.users[0..1]); '@odata.nextLink' = 'https://graph.microsoft.com/v1.0/next-page' } }
        Mock -ModuleName DefenderForOffice Invoke-MgGraphRequest -ParameterFilter { $Uri -like '*next-page' } { [pscustomobject]@{ value = @($simReport.users[2..3]) } }
        $r = Get-DOAttackSimulationReport
        $r.users | Should -HaveCount 4
        Should -Invoke -ModuleName DefenderForOffice Invoke-MgGraphRequest -ParameterFilter { $Uri -like '*$orderby=launchDateTime desc&$top=1' } -Times 1
    }
}

Describe 'Set-DefenderPresetPolicy (mocked Exchange Online)' {
    BeforeEach {
        Mock -ModuleName DefenderForOffice Get-EOPProtectionPolicyRule { [pscustomobject]@{ Name = $Identity; State = 'Enabled' } }
        Mock -ModuleName DefenderForOffice Get-ATPProtectionPolicyRule { [pscustomobject]@{ Name = $Identity; State = 'Disabled' } }
        Mock -ModuleName DefenderForOffice Set-EOPProtectionPolicyRule { }
        Mock -ModuleName DefenderForOffice Set-ATPProtectionPolicyRule { }
        Mock -ModuleName DefenderForOffice Enable-EOPProtectionPolicyRule { }
        Mock -ModuleName DefenderForOffice Enable-ATPProtectionPolicyRule { }
    }
    It 'with -WhatIf changes nothing' {
        $r = @(Set-DefenderPresetPolicy -Config $config -WhatIf)
        $r | Should -HaveCount 4; @($r.Result | Sort-Object -Unique) | Should -Be @('WhatIf')
        Should -Invoke -ModuleName DefenderForOffice Set-EOPProtectionPolicyRule -Times 0
    }
    It 'sets recipients on all four rules, clears leftovers, enables the disabled ones' {
        $r = @(Set-DefenderPresetPolicy -Config $config -Confirm:$false)
        @($r | Where-Object Result -EQ 'Applied') | Should -HaveCount 4
        Should -Invoke -ModuleName DefenderForOffice Set-EOPProtectionPolicyRule -Times 1 -ParameterFilter {
            $Identity -eq 'Standard Preset Security Policy' -and $RecipientDomainIs -contains 'contoso.onmicrosoft.com' -and $PesterBoundParameters.ContainsKey('SentToMemberOf') -and $null -eq $SentToMemberOf
        }
        Should -Invoke -ModuleName DefenderForOffice Set-ATPProtectionPolicyRule -Times 1 -ParameterFilter { $Identity -eq 'Strict Preset Security Policy' -and $SentToMemberOf -contains 'priority-accounts@contoso.onmicrosoft.com' }
        Should -Invoke -ModuleName DefenderForOffice Enable-ATPProtectionPolicyRule -Times 2
        Should -Invoke -ModuleName DefenderForOffice Enable-EOPProtectionPolicyRule -Times 0
    }
    It 'refuses up front when a preset was never turned on in the portal' {
        Mock -ModuleName DefenderForOffice Get-ATPProtectionPolicyRule { $null }
        { Set-DefenderPresetPolicy -Config $config -Confirm:$false } | Should -Throw '*first time you turn on the preset*'
        Should -Invoke -ModuleName DefenderForOffice Set-EOPProtectionPolicyRule -Times 0
    }
}

Describe 'Get-DefenderInventory (mocked)' {
    It 'normalizes rules, mailboxes, group members and analyzer rows' {
        Mock -ModuleName DefenderForOffice Get-EOPProtectionPolicyRule { [pscustomobject]@{ Name = $Identity; State = 'Enabled'; SentToMemberOf = @('priority-accounts@contoso.onmicrosoft.com'); RecipientDomainIs = $null } }
        Mock -ModuleName DefenderForOffice Get-ATPProtectionPolicyRule { $null }
        Mock -ModuleName DefenderForOffice Get-ATPBuiltInProtectionRule { [pscustomobject]@{ Name = 'ATP Built-In Protection Rule'; State = 'Enabled'; ExceptIfSentTo = @() } }
        Mock -ModuleName DefenderForOffice Get-EXOMailbox { [pscustomobject]@{ PrimarySmtpAddress = 'riley.demo@contoso.onmicrosoft.com'; Alias = 'riley.demo'; DisplayName = 'Riley Demo'; Name = 'riley.demo' } }
        Mock -ModuleName DefenderForOffice Get-DistributionGroupMember { [pscustomobject]@{ PrimarySmtpAddress = 'riley.demo@contoso.onmicrosoft.com' } }
        Mock -ModuleName DefenderForOffice Get-ConfigAnalyzerPolicyRecommendation { [pscustomobject]@{ PolicyGroup = 'Anti-Phishing'; SettingName = 'PhishThresholdLevel'; Policy = 'Office365 AntiPhish Default'; CurrentConfiguration = '1'; Recommendation = '3' } }
        $inv = Get-DefenderInventory
        @($inv.rules | Where-Object kind -EQ 'EOP') | Should -HaveCount 2
        $inv.rules[0].recipientDomainIs | Should -HaveCount 0
        $inv.groups[0].members | Should -Be @('riley.demo@contoso.onmicrosoft.com')
        $inv.configAnalyzer[0].recommendation | Should -Be '3'
        Should -Invoke -ModuleName DefenderForOffice Get-ConfigAnalyzerPolicyRecommendation -ParameterFilter { $RecommendedPolicyType -eq 'Standard' } -Times 1
        Should -Invoke -ModuleName DefenderForOffice Get-EXOMailbox -ParameterFilter { $RecipientTypeDetails -eq 'UserMailbox' -and $ResultSize -eq 'Unlimited' } -Times 1
    }
}

Describe 'KQL compiles against the EmailEvents schema (Kusto.Language)' -Skip:(-not (Test-Path "$PSScriptRoot/kql/bin/Release/net8.0/KqlCheck.dll")) {
    It '<Kind> has no errors' -ForEach @(@{ Kind = 'ThreatSummary' }, @{ Kind = 'Recipient' }) {
        $q = if ($Kind -eq 'Recipient') { New-DOHuntingQuery -Kind Recipient -Recipient 'sam.demo@contoso.onmicrosoft.com' -Days 1 } else { New-DOHuntingQuery -Kind ThreatSummary -Days 7 }
        $f = Join-Path $TestDrive "$Kind.kql"; Set-Content -LiteralPath $f -Value $q
        $out = & dotnet "$PSScriptRoot/kql/bin/Release/net8.0/KqlCheck.dll" $f 2>&1
        $LASTEXITCODE | Should -Be 0 -Because ($out -join "`n")
    }
    It 'catches a wrong column name (proves the check works)' {
        $f = Join-Path $TestDrive 'bad.kql'; Set-Content -LiteralPath $f -Value 'EmailEvents | where Verdict == "Phish"'
        & dotnet "$PSScriptRoot/kql/bin/Release/net8.0/KqlCheck.dll" $f 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1
    }
}

Describe 'Real modules' {
    It 'Connect-ExchangeOnline and Get-EXOMailbox take the parameters we pass' -Skip:(-not (Get-Module -ListAvailable ExchangeOnlineManagement)) {
        Import-Module ExchangeOnlineManagement -ErrorAction Stop
        (Get-Command Connect-ExchangeOnline).Parameters.Keys | Should -Contain 'ShowBanner'
        $p = (Get-Command Get-EXOMailbox).Parameters.Keys
        $p | Should -Contain 'RecipientTypeDetails'; $p | Should -Contain 'ResultSize'
    }
    It 'Invoke-MgGraphRequest and Connect-MgGraph take the parameters we pass' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
        Import-Module Microsoft.Graph.Authentication -ErrorAction Stop
        $p = (Get-Command Invoke-MgGraphRequest).Parameters.Keys
        foreach ($n in 'Method', 'Uri', 'Body', 'ContentType', 'OutputType') { $p | Should -Contain $n }
        (Get-Command Connect-MgGraph).Parameters.Keys | Should -Contain 'NoWelcome'
    }
}
