BeforeAll {
    $script:ModulePath = Join-Path $PSScriptRoot '..' 'src' 'OnboardingSync' 'Modules' 'OnboardingSync'
    Import-Module $script:ModulePath -Force
    $script:Templates = Get-Content (Join-Path $PSScriptRoot '..' 'src' 'OnboardingSync' 'config' 'task-templates.json') -Raw | ConvertFrom-Json
}

Describe 'Sign-in names' {
    It 'strips Portuguese accents and uses first given name + last surname' {
        ConvertTo-OnbUpnAlias -GivenName 'João Maria' -Surname 'Conceição Gonçalves' | Should -Be 'joao.goncalves'
        ConvertTo-OnbUpnAlias -GivenName 'Ana Rita' -Surname 'Sousa Ferreira' | Should -Be 'ana.ferreira'
    }
    It 'maps letters that Unicode decomposition does not split' {
        ConvertTo-OnbUpnAlias -GivenName 'Jürgen' -Surname 'Weiß' | Should -Be 'jurgen.weiss'
        ConvertTo-OnbUpnAlias -GivenName 'Søren' -Surname 'Łukasz' | Should -Be 'soren.lukasz'
    }
    It 'drops apostrophes and spaces but keeps hyphens' {
        ConvertTo-OnbUpnAlias -GivenName "Mary-Jane" -Surname "O'Brien" | Should -Be 'mary-jane.obrien'
    }
    It 'never produces characters a UPN cannot contain' {
        $alias = ConvertTo-OnbUpnAlias -GivenName 'Ângela' -Surname 'Simões-Araújo'
        $alias | Should -Match '^[a-z0-9.-]+$'
        $alias | Should -Be 'angela.simoes-araujo'
    }
    It 'refuses a name that becomes empty' {
        { ConvertTo-OnbUpnAlias -GivenName '***' -Surname 'Demo' } | Should -Throw "*sign-in name*"
    }
    It 'offers alias, alias2 ... alias9' {
        $c = Get-OnbUpnCandidates -Alias 'casey.demo' -Domain 'contoso.com'
        $c.Count | Should -Be 9
        $c[0] | Should -Be 'casey.demo@contoso.com'
        $c[1] | Should -Be 'casey.demo2@contoso.com'
        $c[-1] | Should -Be 'casey.demo9@contoso.com'
    }
    It 'derives a stable employee ID within the 16-character limit' {
        Get-OnbEmployeeId -ItemId 7 | Should -Be 'NH00007'
        (Get-OnbEmployeeId -ItemId 123456).Length | Should -BeLessOrEqual 16
        { Get-OnbEmployeeId -ItemId 0 } | Should -Throw
    }
}

Describe 'Dates and time zones' {
    It 'hire date is 09:00 Lisbon time in UTC, winter and summer' {
        ConvertTo-OnbHireDateTime -StartDate ([datetime]'2026-12-01') -TimeZoneId 'Europe/Lisbon' | Should -Be '2026-12-01T09:00:00Z'
        ConvertTo-OnbHireDateTime -StartDate ([datetime]'2027-07-01') -TimeZoneId 'Europe/Lisbon' | Should -Be '2027-07-01T08:00:00Z'
    }
    It 'reads a SharePoint date-only value back as the local calendar date' {
        (ConvertTo-OnbLocalDate -Value '2027-06-30T23:00:00Z' -TimeZoneId 'Europe/Lisbon').ToString('yyyy-MM-dd') | Should -Be '2027-07-01'
        (ConvertTo-OnbLocalDate -Value '2026-12-01T00:00:00Z' -TimeZoneId 'Europe/Lisbon').ToString('yyyy-MM-dd') | Should -Be '2026-12-01'
    }
    It 'accepts the DateTime that ConvertFrom-Json produces' {
        $parsed = ('{"d":"2027-06-30T23:00:00Z"}' | ConvertFrom-Json).d
        $parsed | Should -BeOfType [datetime]
        (ConvertTo-OnbLocalDate -Value $parsed -TimeZoneId 'Europe/Lisbon').ToString('yyyy-MM-dd') | Should -Be '2027-07-01'
        (ConvertTo-OnbUtc $parsed).Offset | Should -Be ([timespan]::Zero)
    }
    It 'counts business days around a weekend' {
        # 2026-12-07 is a Monday
        (Get-OnbBusinessDay -Date ([datetime]'2026-12-07') -Offset -1).ToString('yyyy-MM-dd') | Should -Be '2026-12-04'
        (Get-OnbBusinessDay -Date ([datetime]'2026-12-07') -Offset -3).ToString('yyyy-MM-dd') | Should -Be '2026-12-02'
        (Get-OnbBusinessDay -Date ([datetime]'2026-12-04') -Offset 1).ToString('yyyy-MM-dd') | Should -Be '2026-12-07'
        (Get-OnbBusinessDay -Date ([datetime]'2026-12-05') -Offset 0).ToString('yyyy-MM-dd') | Should -Be '2026-12-07'
    }
}

Describe 'Validation' {
    BeforeAll {
        $script:Valid = @{ OnbGivenName = 'Casey'; OnbSurname = 'Demo'; OnbJobTitle = 'Sales representative'; OnbManagerEmail = 'sam.demo@contoso.com'
                           OnbDepartment = 'Sales'; OnbStartDate = [datetime]'2026-12-07'; OnbUsageLocation = 'PT' }
        $script:Departments = @('Sales', 'Finance', 'Operations', 'IT')
    }
    It 'accepts a complete request' {
        Test-OnbRequest -Fields $script:Valid -Departments $script:Departments -Today ([datetime]'2026-11-21') | Should -BeNullOrEmpty
    }
    It 'reports every missing field at once' {
        $p = Test-OnbRequest -Fields @{ OnbGivenName = 'Casey' } -Departments $script:Departments -Today ([datetime]'2026-11-21')
        $p | Should -Contain 'OnbSurname is required.'
        $p | Should -Contain 'OnbManagerEmail is required.'
        $p | Should -Contain 'OnbStartDate is required.'
    }
    It 'rejects a start date in the past (the joiner workflows would never fire)' {
        $f = $script:Valid.Clone(); $f.OnbStartDate = [datetime]'2026-11-20'
        Test-OnbRequest -Fields $f -Departments $script:Departments -Today ([datetime]'2026-11-21') | Should -Match 'in the past'
    }
    It 'accepts today as a start date' {
        $f = $script:Valid.Clone(); $f.OnbStartDate = [datetime]'2026-11-21'
        Test-OnbRequest -Fields $f -Departments $script:Departments -Today ([datetime]'2026-11-21') | Should -BeNullOrEmpty
    }
    It 'rejects unknown departments, bad e-mails and bad usage locations' {
        $f = $script:Valid.Clone(); $f.OnbDepartment = 'Marketing'; $f.OnbManagerEmail = 'sam'; $f.OnbUsageLocation = 'pt'
        $p = Test-OnbRequest -Fields $f -Departments $script:Departments -Today ([datetime]'2026-11-21')
        $p.Count | Should -Be 3
    }
}

Describe 'SCIM payload' {
    BeforeAll {
        $script:Op = New-OnbScimOperation -Fields @{ OnbGivenName = ' Casey '; OnbSurname = 'Demo'; OnbJobTitle = 'Sales representative'; OnbDepartment = 'Sales' } `
            -EmployeeId 'NH00007' -UserPrincipalName 'casey.demo@contoso.com' -ManagerEmployeeId 'E1002' -HireDateUtc '2026-12-07T09:00:00Z'
        $script:Json = New-OnbScimBulkRequest -Operations @($script:Op) | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable -DateKind String
    }
    It 'is a SCIM BulkRequest with failOnErrors null, like the Learn examples' {
        $script:Json.schemas | Should -Be @('urn:ietf:params:scim:api:messages:2.0:BulkRequest')
        $script:Json.ContainsKey('failOnErrors') | Should -BeTrue
        $script:Json.Operations[0].method | Should -Be 'POST'
        $script:Json.Operations[0].path | Should -Be '/Users'
    }
    It 'uses the employee ID as externalId and bulkId' {
        $d = $script:Json.Operations[0].data
        $d.externalId | Should -Be 'NH00007'
        $script:Json.Operations[0].bulkId | Should -Be 'NH00007'
        $d.userName | Should -Be 'casey.demo@contoso.com'
        $d.displayName | Should -Be 'Casey Demo'
    }
    It 'creates the account disabled; day one enables it' {
        $script:Json.Operations[0].data.active | Should -BeFalse
    }
    It 'points the manager at the manager''s employeeId' {
        $script:Json.Operations[0].data['urn:ietf:params:scim:schemas:extension:enterprise:2.0:User'].manager.value | Should -Be 'E1002'
    }
    It 'declares every schema it uses' {
        $d = $script:Json.Operations[0].data
        foreach ($ns in $d.schemas) {
            if ($ns -ne 'urn:ietf:params:scim:schemas:core:2.0:User') { $d.ContainsKey($ns) | Should -BeTrue -Because "$ns is declared" }
        }
        $d['urn:ietf:params:scim:schemas:extension:contoso:1.0:User'].HireDate | Should -Be '2026-12-07T09:00:00Z'
        $d['urn:ietf:params:scim:schemas:extension:contoso:1.0:User'].UsageLocation | Should -Be 'PT'
    }
    It 'refuses more than 50 operations per request' {
        { New-OnbScimBulkRequest -Operations @(1..51 | ForEach-Object { $script:Op }) } | Should -Throw '*at most 50*'
        { New-OnbScimBulkRequest -Operations @() } | Should -Throw
    }
}

Describe 'Task plan' {
    It 'adds department tasks and resolves owners' {
        $plan = @(New-OnbTaskPlan -RequestId 7 -StartDate ([datetime]'2026-12-07') -Department 'Sales' -ManagerEmail 'sam.demo@contoso.com' -NewHireUpn 'casey.demo@contoso.com' -Templates $script:Templates)
        $plan.Count | Should -Be 7
        ($plan | Where-Object OnbTaskKey -eq 'laptop').OnbDueDate | Should -Be '2026-12-02'
        ($plan | Where-Object OnbTaskKey -eq 'crm-access').OnbOwnerEmail | Should -Be 'sam.demo@contoso.com'
        ($plan | Where-Object OnbTaskKey -eq 'mfa').OnbOwnerEmail | Should -Be 'casey.demo@contoso.com'
        ($plan | Where-Object OnbTaskKey -eq 'contract').OnbOwnerEmail | Should -BeNullOrEmpty
    }
    It 'uses only default tasks for a department without extras' {
        @(New-OnbTaskPlan -RequestId 1 -StartDate ([datetime]'2026-12-07') -Department 'IT' -ManagerEmail 'a@b.c' -NewHireUpn 'x@b.c' -Templates $script:Templates).Count | Should -Be 6
    }
}

Describe 'Graph client' {
    BeforeEach {
        Mock -ModuleName OnboardingSync Get-OnbAccessToken { 'test-token' }
        Mock -ModuleName OnboardingSync Start-Sleep { }
    }
    It 'retries 429 using Retry-After, then returns the parsed body' {
        $script:n = 0
        Mock -ModuleName OnboardingSync Invoke-WebRequest {
            $script:n++
            if ($script:n -eq 1) { return [pscustomobject]@{ StatusCode = 429; Content = ''; Headers = @{ 'Retry-After' = @('7') } } }
            [pscustomobject]@{ StatusCode = 200; Content = '{"value":[{"id":"1"}]}'; Headers = @{} }
        }
        $r = Invoke-OnbGraph -Path '/users'
        $r.StatusCode | Should -Be 200
        $r.Body.value[0].id | Should -Be '1'
        Should -Invoke -ModuleName OnboardingSync Start-Sleep -Times 1 -Exactly -ParameterFilter { $Seconds -eq 7 }
    }
    It 'gives up after the last attempt and returns the error' {
        Mock -ModuleName OnboardingSync Invoke-WebRequest { [pscustomobject]@{ StatusCode = 503; Content = '{"error":{"message":"busy"}}'; Headers = @{} } }
        $r = Invoke-OnbGraph -Path '/users' -MaxAttempts 3
        $r.StatusCode | Should -Be 503
        Should -Invoke -ModuleName OnboardingSync Invoke-WebRequest -Times 3 -Exactly
    }
    It 'does not retry a 412' {
        Mock -ModuleName OnboardingSync Invoke-WebRequest { [pscustomobject]@{ StatusCode = 412; Content = ''; Headers = @{} } }
        (Invoke-OnbGraph -Method PATCH -Path '/x' -Body @{ a = 1 } -IfMatch '"e,1"').StatusCode | Should -Be 412
        Should -Invoke -ModuleName OnboardingSync Invoke-WebRequest -Times 1 -Exactly
    }
    It 'sends bearer token, If-Match and the SCIM content type' {
        Mock -ModuleName OnboardingSync Invoke-WebRequest { [pscustomobject]@{ StatusCode = 202; Content = ''; Headers = @{} } }
        Invoke-OnbGraph -Method POST -Path '/servicePrincipals/1/synchronization/jobs/2/bulkUpload' -Body @{ a = 'ã' } -ContentType 'application/scim+json' -IfMatch '"x"' | Out-Null
        Should -Invoke -ModuleName OnboardingSync Invoke-WebRequest -ParameterFilter {
            $Headers.Authorization -eq 'Bearer test-token' -and $Headers['If-Match'] -eq '"x"' -and
            $ContentType -like 'application/scim+json*' -and [System.Text.Encoding]::UTF8.GetString($Body) -eq '{"a":"ã"}'
        }
    }
    It 'refuses to send the token anywhere but Microsoft Graph' {
        { Invoke-OnbGraph -Path 'https://evil.example.com/v1.0/users' } | Should -Throw '*Refusing*'
    }
    It 'falls back to exponential delays without Retry-After' {
        Get-OnbRetryDelay -Headers @{} -Attempt 1 | Should -Be 2
        Get-OnbRetryDelay -Headers @{} -Attempt 3 | Should -Be 8
        Get-OnbRetryDelay -Headers @{ 'Retry-After' = @('600') } -Attempt 1 | Should -Be 60
    }
}

Describe 'Managed identity token' {
    BeforeEach {
        $env:IDENTITY_ENDPOINT = 'http://localhost:8081/msi/token'
        $env:IDENTITY_HEADER = 'header-value'
        InModuleScope OnboardingSync { $script:TokenCache = $null }
    }
    AfterEach { Remove-Item Env:IDENTITY_ENDPOINT, Env:IDENTITY_HEADER -ErrorAction SilentlyContinue }

    It 'asks the local endpoint for a Graph token for the user-assigned identity, then caches it' {
        Mock -ModuleName OnboardingSync Invoke-RestMethod {
            [pscustomobject]@{ access_token = 'abc'; expires_on = [string][datetimeoffset]::UtcNow.AddHours(1).ToUnixTimeSeconds() }
        }
        Get-OnbAccessToken -ClientId '00000000-0000-0000-0000-000000000009' | Should -Be 'abc'
        Get-OnbAccessToken -ClientId '00000000-0000-0000-0000-000000000009' | Should -Be 'abc'
        Should -Invoke -ModuleName OnboardingSync Invoke-RestMethod -Times 1 -Exactly -ParameterFilter {
            $Uri -like 'http://localhost:8081/msi/token?resource=https%3A%2F%2Fgraph.microsoft.com&api-version=2019-08-01&client_id=00000000-0000-0000-0000-000000000009' -and
            $Headers['X-IDENTITY-HEADER'] -eq 'header-value'
        }
    }
    It 'refreshes a token that expires within five minutes' {
        Mock -ModuleName OnboardingSync Invoke-RestMethod { [pscustomobject]@{ access_token = 'short'; expires_on = [string][datetimeoffset]::UtcNow.AddMinutes(2).ToUnixTimeSeconds() } }
        Get-OnbAccessToken | Out-Null
        Get-OnbAccessToken | Out-Null
        Should -Invoke -ModuleName OnboardingSync Invoke-RestMethod -Times 2 -Exactly
    }
    It 'explains itself outside Azure' {
        Remove-Item Env:IDENTITY_ENDPOINT
        { Get-OnbAccessToken } | Should -Throw '*managed identity endpoint*'
    }
}
