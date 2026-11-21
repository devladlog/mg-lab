#requires -Modules Pester
BeforeAll {
    $script:Root = Split-Path $PSScriptRoot -Parent
    # Invoke-MgGraphRequest comes from Microsoft.Graph.Authentication. The tests mock it, so a stub is enough
    # when the module is not installed; with the real module present the mock is checked against its parameters.
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        function global:Invoke-MgGraphRequest { param($Method, $Uri, $Body, $ContentType, $OutputType) }
    }
    Import-Module (Join-Path $script:Root 'scripts/ZeroTrust.psm1') -Force
    $script:Values = @{
        pilotGroupId               = '11111111-1111-1111-1111-111111111111'
        breakGlassGroupId          = '22222222-2222-2222-2222-222222222222'
        phishingResistantStrengthId = '33333333-3333-3333-3333-333333333333'
    }
    function script:Get-Expanded([string]$file) {
        Expand-CaTemplate -Template (Get-Content (Join-Path $script:Root "entra/policies/$file") -Raw) -Values $script:Values | ConvertFrom-Json -Depth 20
    }
}

Describe 'Policy templates' {
    BeforeDiscovery {
        $script:Files = Get-ChildItem (Join-Path (Split-Path $PSScriptRoot -Parent) 'entra/policies') -Filter *.json | ForEach-Object { @{ Name = $_.Name } }
    }
    It '<Name> expands, parses and passes the linter' -ForEach $script:Files {
        $p = Get-Expanded $Name
        (Test-CaPolicy -Policy $p) | Should -BeNullOrEmpty
    }
    It '<Name> starts in report-only' -ForEach $script:Files {
        (Get-Expanded $Name).state | Should -Be 'enabledForReportingButNotEnforced'
    }
    It '<Name> excludes the break-glass group' -ForEach $script:Files {
        (Get-Expanded $Name).conditions.users.excludeGroups | Should -Contain $script:Values.breakGlassGroupId
    }
    It 'the folder holds exactly three policies' {
        @(Get-ChildItem (Join-Path $script:Root 'entra/policies') -Filter *.json).Count | Should -Be 3
    }
    It 'CT001 blocks only the two legacy client types' {
        $p = Get-Expanded 'ct001-block-legacy-auth.json'
        $p.conditions.clientAppTypes | Should -Be @('exchangeActiveSync', 'other')
        $p.grantControls.builtInControls | Should -Be @('block')
    }
    It 'CT002 targets five directory roles by template id and uses an authentication strength, not mfa' {
        $p = Get-Expanded 'ct002-admins-phishing-resistant-mfa.json'
        @($p.conditions.users.includeRoles).Count | Should -Be 5
        $p.conditions.users.includeRoles | Should -Contain '62e90394-69f5-4237-9190-012177145e10'   # Global Administrator
        $p.grantControls.authenticationStrength.id | Should -Be $script:Values.phishingResistantStrengthId
        $p.grantControls.PSObject.Properties.Name | Should -Not -Contain 'builtInControls'
    }
    It 'CT003 is limited to Windows (Learn: report-only compliance checks prompt macOS, iOS and Android users)' {
        $p = Get-Expanded 'ct003-office365-compliant-device.json'
        $p.conditions.platforms.includePlatforms | Should -Be @('windows')
        $p.conditions.applications.includeApplications | Should -Be @('Office365')
        $p.grantControls.builtInControls | Should -Contain 'compliantDevice'
        $p.sessionControls.signInFrequency.value | Should -Be 12
    }
    It 'role template ids in CT002 are unique GUIDs' {
        $ids = (Get-Expanded 'ct002-admins-phishing-resistant-mfa.json').conditions.users.includeRoles
        ($ids | Select-Object -Unique).Count | Should -Be $ids.Count
        $ids | ForEach-Object { $_ | Should -Match '^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$' }
    }
}

Describe 'Expand-CaTemplate' {
    It 'replaces every token' {
        Expand-CaTemplate -Template '{"a":"{{x}}","b":"{{ y }}"}' -Values @{ x = '1'; y = '2' } | Should -Be '{"a":"1","b":"2"}'
    }
    It 'throws on a token without a value' {
        { Expand-CaTemplate -Template '{{x}} {{missing}}' -Values @{ x = '1' } } | Should -Throw "*missing*"
    }
    It 'throws on an empty value' {
        { Expand-CaTemplate -Template '{{x}}' -Values @{ x = ' ' } } | Should -Throw
    }
}

Describe 'Test-CaPolicy' {
    BeforeEach {
        $script:Good = Get-Expanded 'ct003-office365-compliant-device.json'
    }
    It 'accepts a good policy' { Test-CaPolicy -Policy $script:Good | Should -BeNullOrEmpty }
    It 'rejects an enabled policy unless -AllowEnforced' {
        $script:Good.state = 'enabled'
        Test-CaPolicy -Policy $script:Good | Should -Match 'report-only'
        Test-CaPolicy -Policy $script:Good -AllowEnforced | Should -BeNullOrEmpty
    }
    It 'rejects a policy without the break-glass exclusion' {
        $script:Good.conditions.users.excludeGroups = @()
        Test-CaPolicy -Policy $script:Good | Should -Match 'break-glass'
    }
    It 'rejects a policy that targets nobody' {
        $script:Good.conditions.users.includeGroups = @()
        Test-CaPolicy -Policy $script:Good | Should -Match 'targets nobody'
    }
    It 'rejects mfa together with an authentication strength' {
        $script:Good.grantControls | Add-Member authenticationStrength ([pscustomobject]@{ id = 'x' })
        Test-CaPolicy -Policy $script:Good | Should -Match 'cannot be combined'
    }
    It 'rejects values that are not in the Graph enums' {
        $script:Good.conditions.clientAppTypes = @('desktop')
        $script:Good.grantControls.builtInControls = @('mfa', 'allowEverything')
        $r = Test-CaPolicy -Policy $script:Good
        ($r -join '|') | Should -Match "clientAppTypes value 'desktop'"
        ($r -join '|') | Should -Match "builtInControls value 'allowEverything'"
    }
    It 'rejects block combined with another control' {
        $script:Good.grantControls.builtInControls = @('block', 'mfa')
        Test-CaPolicy -Policy $script:Good | Should -Match "'block' is combined"
    }
    It 'reports a policy with missing sections instead of throwing' {
        $r = Test-CaPolicy -Policy ([pscustomobject]@{ displayName = 'x'; state = 'disabled' })
        $r.Count | Should -BeGreaterThan 2
    }
}

Describe 'Publish-CaPolicy' {
    BeforeEach {
        $script:Calls = [System.Collections.Generic.List[object]]::new()
        $script:Existing = @()
        Mock -ModuleName ZeroTrust Invoke-MgGraphRequest {
            $script:Calls.Add(@{ Method = $Method; Uri = $Uri; Body = $Body })
            if ($Method -eq 'GET') { return @{ value = $script:Existing } }
            if ($Method -eq 'POST') { return @{ id = 'new-id'; state = ($Body | ConvertFrom-Json).state } }
        }
        $script:Tpl = Join-Path $script:Root 'entra/policies/ct001-block-legacy-auth.json'
    }
    It 'creates a missing policy in report-only' {
        $r = Publish-CaPolicy -TemplatePath $script:Tpl -Values $script:Values
        $r.Action | Should -Be 'created'
        $r.State | Should -Be 'enabledForReportingButNotEnforced'
        ($script:Calls | Where-Object Method -eq 'POST').Uri | Should -Be '/v1.0/identity/conditionalAccess/policies'
    }
    It 'updates a policy that has the same name (idempotent)' {
        $script:Existing = @(@{ id = 'abc'; displayName = 'CT001 Block legacy authentication' })
        $r = Publish-CaPolicy -TemplatePath $script:Tpl -Values $script:Values
        $r.Action | Should -Be 'updated'
        ($script:Calls | Where-Object Method -eq 'PATCH').Uri | Should -Be '/v1.0/identity/conditionalAccess/policies/abc'
        $script:Calls | Where-Object Method -eq 'POST' | Should -BeNullOrEmpty
    }
    It '-WhatIf writes nothing' {
        Publish-CaPolicy -TemplatePath $script:Tpl -Values $script:Values -WhatIf | Should -BeNullOrEmpty
        $script:Calls | Where-Object { $_.Method -ne 'GET' } | Should -BeNullOrEmpty
    }
    It 'sends enabled only with -Enforce' {
        Publish-CaPolicy -TemplatePath $script:Tpl -Values $script:Values -Enforce | Out-Null
        (($script:Calls | Where-Object Method -eq 'POST').Body | ConvertFrom-Json).state | Should -Be 'enabled'
    }
    It 'refuses a template with a missing token and calls nothing' {
        { Publish-CaPolicy -TemplatePath $script:Tpl -Values @{ pilotGroupId = 'x' } } | Should -Throw '*breakGlassGroupId*'
        $script:Calls.Count | Should -Be 0
    }
    It 'refuses two policies with the same name' {
        $script:Existing = @(@{ id = '1'; displayName = 'CT001 Block legacy authentication' }, @{ id = '2'; displayName = 'CT001 Block legacy authentication' })
        { Publish-CaPolicy -TemplatePath $script:Tpl -Values $script:Values } | Should -Throw '*More than one*'
    }
}

Describe 'Resolve-AuthStrengthId and Initialize-LabGroup' {
    It 'finds exactly one built-in phishing-resistant strength' {
        Mock -ModuleName ZeroTrust Invoke-MgGraphRequest { @{ value = @(
                    @{ id = 'a'; policyType = 'builtIn'; displayName = 'Multifactor authentication' },
                    @{ id = 'b'; policyType = 'builtIn'; displayName = 'Phishing-resistant MFA' },
                    @{ id = 'c'; policyType = 'custom'; displayName = 'Phishing-resistant, our own' }) } }
        Resolve-AuthStrengthId | Should -Be 'b'
    }
    It 'throws when nothing matches' {
        Mock -ModuleName ZeroTrust Invoke-MgGraphRequest { @{ value = @() } }
        { Resolve-AuthStrengthId } | Should -Throw '*found 0*'
    }
    It 'reuses an existing group' {
        Mock -ModuleName ZeroTrust Invoke-MgGraphRequest { @{ value = @(@{ id = 'g1' }) } }
        Initialize-LabGroup -DisplayName 'ct-zt-pilot' | Should -Be 'g1'
        Should -Invoke -ModuleName ZeroTrust Invoke-MgGraphRequest -Times 1 -Exactly
    }
    It 'creates a missing security group, not mail enabled' {
        $script:Posted = $null
        Mock -ModuleName ZeroTrust Invoke-MgGraphRequest {
            if ($Method -eq 'GET') { return @{ value = @() } }
            $script:Posted = $Body; @{ id = 'g2' }
        }
        Initialize-LabGroup -DisplayName 'ct-zt-pilot' | Should -Be 'g2'
        $b = $script:Posted | ConvertFrom-Json
        $b.securityEnabled | Should -BeTrue
        $b.mailEnabled | Should -BeFalse
    }
}

Describe 'Get-CaReportOnlyImpact' {
    It 'counts the report-only results per policy across pages and ignores other policies' {
        $script:Page = 0
        Mock -ModuleName ZeroTrust Invoke-MgGraphRequest {
            $script:Page++
            if ($script:Page -eq 1) {
                return @{ '@odata.nextLink' = 'https://graph.microsoft.com/v1.0/auditLogs/signIns?$skiptoken=2'; value = @(
                        @{ appliedConditionalAccessPolicies = @(
                                @{ displayName = 'CT003 Office 365 needs a compliant Windows device'; result = 'reportOnlyFailure' },
                                @{ displayName = 'Some other policy'; result = 'failure' }) },
                        @{ appliedConditionalAccessPolicies = @(
                                @{ displayName = 'CT003 Office 365 needs a compliant Windows device'; result = 'reportOnlySuccess' },
                                @{ displayName = 'CT001 Block legacy authentication'; result = 'reportOnlyNotApplied' }) }) }
            }
            @{ value = @(@{ appliedConditionalAccessPolicies = @(
                            @{ displayName = 'CT003 Office 365 needs a compliant Windows device'; result = 'reportOnlyFailure' },
                            @{ displayName = 'CT003 Office 365 needs a compliant Windows device'; result = 'reportOnlyInterrupted' }) }) }
        }
        $r = @(Get-CaReportOnlyImpact -Hours 24 -Now ([datetime]'2026-11-21T12:00:00Z'))
        $r.Count | Should -Be 2
        $ct3 = $r | Where-Object Policy -like 'CT003*'
        $ct3.WouldFail | Should -Be 2
        $ct3.WouldPass | Should -Be 1
        $ct3.UserActionNeeded | Should -Be 1
        ($r | Where-Object Policy -like 'CT001*').NotApplied | Should -Be 1
    }
    It 'asks only for the last N hours' {
        $script:Uri = $null
        Mock -ModuleName ZeroTrust Invoke-MgGraphRequest { if (-not $script:Uri) { $script:Uri = $Uri }; @{ value = @() } }
        Get-CaReportOnlyImpact -Hours 6 -Now ([datetime]'2026-11-21T12:00:00Z') | Out-Null
        $script:Uri | Should -Match 'createdDateTime ge 2026-11-21T06:00:00Z'
    }
}

Describe 'Intune compliance policy' {
    BeforeAll {
        # Property names of windows10CompliancePolicy in Graph v1.0 (Learn, resource type page), plus the relationship we post inline.
        $script:Documented = 'displayName description version passwordRequired passwordBlockSimple passwordRequiredToUnlockFromIdle passwordMinutesOfInactivityBeforeLock passwordExpirationDays passwordMinimumLength passwordMinimumCharacterSetCount passwordRequiredType passwordPreviousPasswordBlockCount requireHealthyDeviceReport osMinimumVersion osMaximumVersion mobileOsMinimumVersion mobileOsMaximumVersion earlyLaunchAntiMalwareDriverEnabled bitLockerEnabled secureBootEnabled codeIntegrityEnabled storageRequireEncryption scheduledActionsForRule'.Split(' ')
        $script:Pol = Get-Content (Join-Path $script:Root 'intune/windows-compliance.json') -Raw | ConvertFrom-Json -Depth 20
    }
    It 'is a windows10CompliancePolicy' { $script:Pol.'@odata.type' | Should -Be '#microsoft.graph.windows10CompliancePolicy' }
    It 'uses only properties Learn documents for the resource' {
        $names = $script:Pol.PSObject.Properties.Name | Where-Object { $_ -ne '@odata.type' }
        $names | Where-Object { $_ -notin $script:Documented } | Should -BeNullOrEmpty
    }
    It 'has one and only one block action (Learn requirement)' {
        $actions = @($script:Pol.scheduledActionsForRule.scheduledActionConfigurations | Where-Object actionType -eq 'block')
        $actions.Count | Should -Be 1
        $script:Pol.scheduledActionsForRule[0].ruleName | Should -Be 'PasswordRequired'
    }
    It 'requires encryption, secure boot and a minimum OS build' {
        $script:Pol.bitLockerEnabled | Should -BeTrue
        $script:Pol.secureBootEnabled | Should -BeTrue
        [version]$script:Pol.osMinimumVersion | Should -BeGreaterOrEqual ([version]'10.0.22621.0')
    }
    It 'is created once and assigned to the group' {
        $script:Calls = [System.Collections.Generic.List[object]]::new()
        Mock -ModuleName ZeroTrust Invoke-MgGraphRequest {
            $script:Calls.Add(@{ Method = $Method; Uri = $Uri; Body = $Body })
            if ($Method -eq 'GET') { return @{ value = @() } }
            if ($Uri -like '*/assign') { return @{} }
            @{ id = 'pol1' }
        }
        $r = Publish-CompliancePolicy -Path (Join-Path $script:Root 'intune/windows-compliance.json') -GroupId 'grp1'
        $r.Action | Should -Be 'created'
        $assign = $script:Calls | Where-Object { $_.Uri -like '*/pol1/assign' }
        ($assign.Body | ConvertFrom-Json).assignments[0].target.groupId | Should -Be 'grp1'
    }
    It 'reuses a policy of the same name and still assigns it' {
        $script:Calls = [System.Collections.Generic.List[object]]::new()
        Mock -ModuleName ZeroTrust Invoke-MgGraphRequest {
            $script:Calls.Add(@{ Method = $Method; Uri = $Uri })
            if ($Method -eq 'GET') { return @{ value = @(@{ id = 'old'; displayName = 'CT Windows corporate baseline' }) } }
            @{}
        }
        (Publish-CompliancePolicy -Path (Join-Path $script:Root 'intune/windows-compliance.json') -GroupId 'grp1').Action | Should -Be 'reused'
        $script:Calls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -notlike '*/assign' } | Should -BeNullOrEmpty
    }
}

Describe 'Deploy-ZeroTrust.ps1 -WhatIf' {
    It 'reads, validates all templates and writes nothing' {
        Mock -ModuleName ZeroTrust Invoke-MgGraphRequest {
            if ($Uri -like '*authenticationStrengthPolicies') { return @{ value = @(@{ id = 's1'; policyType = 'builtIn'; displayName = 'Phishing-resistant MFA' }) } }
            @{ value = @() }
        }
        & (Join-Path $script:Root 'scripts/Deploy-ZeroTrust.ps1') -WhatIf | Out-Null
        Should -Invoke -ModuleName ZeroTrust Invoke-MgGraphRequest -Times 0 -Exactly -ParameterFilter { $Method -ne 'GET' }
        Should -Invoke -ModuleName ZeroTrust Invoke-MgGraphRequest -Times 3 -Exactly -ParameterFilter { $Uri -like '*conditionalAccess/policies' }
        Should -Invoke -ModuleName ZeroTrust Invoke-MgGraphRequest -Times 1 -Exactly -ParameterFilter { $Uri -like '*deviceCompliancePolicies*' }
    }
}
