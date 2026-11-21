BeforeAll {
    # Tests never sign in. If the real Microsoft.Graph.Authentication module isn't installed, a stub with the same
    # name lets Pester mock it.
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        function global:Invoke-MgGraphRequest { param($Method, $Uri, $Body, $Headers, $OutputFilePath, $OutputType, $ErrorAction) throw 'stub' }
    }
    Import-Module "$PSScriptRoot/../src/M365TenantHealth/M365TenantHealth.psd1" -Force
    $script:fx = "$PSScriptRoot/fixtures"
    $script:snap = Get-Content "$fx/snapshot.json" -Raw | ConvertFrom-Json
    $script:now = [datetimeoffset]'2026-11-20T09:30:00Z'
}

Describe 'ConvertTo-M365Date' {
    It 'parses ISO strings as UTC' { (ConvertTo-M365Date '2026-11-25T00:00:00Z').UtcDateTime | Should -Be ([datetime]'2026-11-25') }
    It 'treats date-only report values as UTC midnight' { (ConvertTo-M365Date '2026-11-18').Offset | Should -Be ([timespan]::Zero) }
    It 'accepts DateTime values already parsed by ConvertFrom-Json' { (ConvertTo-M365Date ([datetime]::new(2026, 11, 25, 0, 0, 0, [DateTimeKind]::Utc))).Day | Should -Be 25 }
    It 'returns null for empty values' { ConvertTo-M365Date '' | Should -BeNullOrEmpty }
}

Describe 'Service health' {
    It 'maps <Status> to <State>' -ForEach @(
        @{ Status = 'serviceOperational'; State = 'Healthy' }
        @{ Status = 'ServiceOperational'; State = 'Healthy' }      # sample responses use PascalCase
        @{ Status = 'serviceRestored'; State = 'Healthy' }
        @{ Status = 'extendedRecovery'; State = 'Recovering' }
        @{ Status = 'serviceDegradation'; State = 'Degraded' }
        @{ Status = 'serviceInterruption'; State = 'Down' }
        @{ Status = 'somethingNew'; State = 'Unknown' }
    ) { Get-M365HealthState $Status | Should -Be $State }

    It 'counts only unresolved issues per service' {
        $s = Get-M365ServiceHealthSummary -HealthOverviews $snap.healthOverviews -Issues $snap.issues
        ($s | Where-Object Service -eq 'Microsoft Teams').Incidents | Should -Be 1
        ($s | Where-Object Service -eq 'Exchange Online').Advisories | Should -Be 0   # EX000003 is resolved
    }
}

Describe 'Message center digest' {
    BeforeAll { $script:d = @(Get-M365MessageCenterDigest -Messages $snap.messages -Now $now -WithinDays 30) }
    It 'keeps deadlines in the window and recent overdue ones, soonest first' { $d.Id | Should -Be @('MC000005', 'MC000001', 'MC000002') }
    It 'drops posts without a deadline and posts overdue for more than a week' { $d.Id | Should -Not -Contain 'MC000003'; $d.Id | Should -Not -Contain 'MC000004' }
    It 'computes days left (negative when overdue)' { ($d | Where-Object Id -eq 'MC000005').DaysLeft | Should -Be -5 }
}

Describe 'Licences' {
    BeforeAll { $script:l = @(Get-M365LicenseSummary -Skus $snap.subscribedSkus) }
    It 'flags <Sku> as <Flag>' -ForEach @(
        @{ Sku = 'SPE_E5'; Flag = 'Exhausted' }
        @{ Sku = 'SPE_E3'; Flag = 'NearlyFull' }
        @{ Sku = 'AAD_PREMIUM'; Flag = 'Unused' }
        @{ Sku = 'EMSPREMIUM'; Flag = 'InGracePeriod' }
        @{ Sku = 'EMSPREMIUM'; Flag = 'Status:Warning' }
    ) { ($l | Where-Object Sku -eq $Sku).Flags | Should -Contain $Flag }
    It 'ignores free self-service SKUs' { $l.Sku | Should -Not -Contain 'FLOW_FREE' }
}

Describe 'Usage reports' {
    It 'detects a concealed report' {
        $rows = Import-Csv "$fx/activeusers-concealed.csv"
        Test-M365ConcealedReport $rows | Should -BeTrue
        { Get-M365InactiveUser -Rows $rows } | Should -Throw '*concealed*'
    }
    It 'finds licensed users inactive for 30+ days, measured from the report refresh date' {
        $idle = @(Get-M365InactiveUser -Rows $snap.activeUsers -InactiveDays 30)
        $idle.UserPrincipalName | Should -Be @('megan.sample@contoso.onmicrosoft.com', 'new.starter@contoso.onmicrosoft.com')
        ($idle | Where-Object DisplayName -eq 'Megan Sample').DaysInactive | Should -Be 48
    }
    It 'treats day 29 as active and skips deleted and unlicensed users' {
        $idle = @(Get-M365InactiveUser -Rows $snap.activeUsers -InactiveDays 30).UserPrincipalName
        $idle | Should -Not -Contain 'joao.exemplo@contoso.onmicrosoft.com'
        $idle | Should -Not -Contain 'left.company@contoso.onmicrosoft.com'
        $idle | Should -Not -Contain 'room.lisbon@contoso.onmicrosoft.com'
    }
}

Describe 'Global Administrators and Secure Score' {
    It 'reports count, guests and disabled holders' {
        $r = Get-M365GlobalAdminReport -Assignments $snap.globalAdmins
        $r.Count | Should -Be 5
        $r.Guests.DisplayName | Should -Be 'Partner Admin (Fabrikam)'
        $r.Disabled.DisplayName | Should -Be 'Former Admin'
    }
    It 'computes the latest Secure Score and the trend' {
        $s = Get-M365SecureScoreSummary -Scores $snap.secureScores
        $s.Percent | Should -Be 58
        $s.Change | Should -Be -4
    }
}

Describe 'Findings' {
    BeforeAll { $script:f = @(Get-M365TenantFinding -Snapshot $snap -Now $now) }
    It 'puts High findings first' { $f[0].Severity | Should -Be 'High' }
    It 'raises the documented Global Administrator threshold (fewer than five)' {
        $f.Title | Should -Contain '5 active Global Administrator assignments'
    }
    It 'raises the message center deadline in five days as High' {
        ($f | Where-Object Title -like 'MC000001*').Severity | Should -Be 'High'
    }
    It 'reports concealed usage data as Info instead of failing' {
        $copy = $snap | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $copy.activeUsers = @(Import-Csv "$fx/activeusers-concealed.csv")
        $copy.reportSettings.displayConcealedNames = $true
        $c = Get-M365TenantFinding -Snapshot $copy -Now $now
        ($c | Where-Object Area -eq 'Usage').Severity | Should -Be 'Info'
    }
    It 'turns a collection error into a finding and keeps going' {
        $copy = $snap | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $copy.errors = [pscustomobject]@{ secureScores = 'Forbidden' }
        $copy.secureScores = $null
        $c = Get-M365TenantFinding -Snapshot $copy -Now $now
        $c.Title | Should -Contain 'Could not collect secureScores'
        $c.Area | Should -Contain 'Licensing'
    }
    It 'renders a Markdown report' {
        $md = ConvertTo-M365HealthMarkdown -Snapshot $snap -Findings $f
        $md | Should -Match '\| High \| Privileged access \|'
        $md | Should -Match '## Service health'
    }
}

Describe 'Graph collection (mocked)' {
    It 'follows @odata.nextLink across pages' {
        Mock Invoke-MgGraphRequest -ModuleName M365TenantHealth -ParameterFilter { $Uri -eq '/v1.0/subscribedSkus' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ skuPartNumber = 'A' }); '@odata.nextLink' = 'https://graph.microsoft.com/v1.0/subscribedSkus?$skiptoken=x' }
        }
        Mock Invoke-MgGraphRequest -ModuleName M365TenantHealth -ParameterFilter { $Uri -like '*skiptoken*' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ skuPartNumber = 'B' }) }
        }
        (Invoke-M365GraphGet '/v1.0/subscribedSkus').skuPartNumber | Should -Be @('A', 'B')
        Should -Invoke Invoke-MgGraphRequest -ModuleName M365TenantHealth -Times 2 -Exactly
    }
    It 'returns single objects as-is' {
        Mock Invoke-MgGraphRequest -ModuleName M365TenantHealth { [pscustomobject]@{ displayConcealedNames = $true } }
        (Invoke-M365GraphGet '/v1.0/admin/reportSettings').displayConcealedNames | Should -BeTrue
    }
    It 'downloads a usage report to a temp file and deletes it' {
        Mock Invoke-MgGraphRequest -ModuleName M365TenantHealth {
            $script:lastTmp = $OutputFilePath
            Copy-Item "$fx/activeusers.csv" $OutputFilePath
        }
        $rows = @(Get-M365UsageReport -Report getOffice365ActiveUserDetail -Period D30)
        $rows.Count | Should -Be 2
        $rows[0].'User Principal Name' | Should -Be 'alex.demo@contoso.onmicrosoft.com'   # BOM handled
        Should -Invoke Invoke-MgGraphRequest -ModuleName M365TenantHealth -ParameterFilter { $Uri -eq "/v1.0/reports/getOffice365ActiveUserDetail(period='D30')" }
        Test-Path $script:lastTmp | Should -BeFalse
    }
    It 'records a failing section and still collects the others' {
        Mock Invoke-MgGraphRequest -ModuleName M365TenantHealth { [pscustomobject]@{ value = @() } }
        Mock Invoke-MgGraphRequest -ModuleName M365TenantHealth -ParameterFilter { $Uri -like '*secureScores*' } { throw 'Forbidden' }
        Mock Get-M365UsageReport -ModuleName M365TenantHealth { @() }
        $s = Get-M365TenantSnapshot
        $s.errors.Keys | Should -Be @('secureScores')
        $s.errors['secureScores'] | Should -Be 'Forbidden'
    }
}

Describe 'Real Microsoft Graph PowerShell parameters' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
    It 'Invoke-MgGraphRequest has every parameter the module uses' {
        $p = (Get-Command Invoke-MgGraphRequest).Parameters.Keys
        foreach ($name in 'Method', 'Uri', 'OutputType', 'OutputFilePath') { $p | Should -Contain $name }
    }
    It 'Connect-MgGraph has the parameters the run script uses' {
        $p = (Get-Command Connect-MgGraph).Parameters.Keys
        foreach ($name in 'Scopes', 'TenantId', 'ClientId', 'CertificateThumbprint', 'NoWelcome') { $p | Should -Contain $name }
    }
}
