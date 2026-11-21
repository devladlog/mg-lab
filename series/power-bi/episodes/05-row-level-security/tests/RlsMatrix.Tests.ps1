# Pester 5+: the service RLS test, with Invoke-PowerBIRestMethod mocked (responses shaped like the Learn sample).
#   pwsh -NoProfile -Command "Invoke-Pester ./tests/RlsMatrix.Tests.ps1 -Output Detailed"

BeforeAll {
    if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
        # Stand-in so Pester can mock the MicrosoftPowerBIMgmt cmdlet without installing it.
        function global:Invoke-PowerBIRestMethod { param($Url, $Method, $Body) throw 'not mocked' }
    }
    $src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'service' 'RlsMatrix.psm1') -Force
    $script:Matrix = Join-Path $src 'reference' 'expected' 'rls_matrix.csv'
    $script:Expected = Import-Csv $script:Matrix

    function New-Response($who, $stores, $customers, $sales, $orders) {
        @{ results = @(@{ tables = @(@{ rows = @(@{
            '[Who]' = $who; '[Stores]' = $stores; '[Customers]' = $customers; '[Sales]' = $sales; '[Orders]' = $orders
        }) }) }) } | ConvertTo-Json -Depth 8
    }
    # What the service should answer for each user: the expected matrix itself.
    function Get-ExpectedResponse([string] $body) {
        $upn = ($body | ConvertFrom-Json).impersonatedUserName
        $row = $script:Expected | Where-Object { "$($_.UserAlias)@contoso.com" -eq $upn }
        $sales = if ([decimal]$row.'Sales Amount' -eq 0) { $null } else { [decimal]$row.'Sales Amount' }
        New-Response $upn ([int]$row.'Visible Stores') ([int]$row.'Visible Customers') $sales ([int]$row.Orders)
    }
}

Describe 'request body' {
    It 'impersonates the user, includes nulls and sends one EVALUATE query' {
        $b = New-RlsQueryBody -UserPrincipalName 'alex.demo@contoso.com' | ConvertFrom-Json
        $b.impersonatedUserName | Should -Be 'alex.demo@contoso.com'
        $b.serializerSettings.includeNulls | Should -BeTrue
        @($b.queries).Count | Should -Be 1
        $b.queries[0].query | Should -Match '^EVALUATE'
        $b.queries[0].query | Should -Match '\[Who Am I\]'
    }
}

Describe 'response parsing' {
    It 'reads the bracketed column names' {
        $r = ConvertFrom-RlsResponse (New-Response 'sam.demo@contoso.com' 1 243 366058.87 484)
        $r.Stores | Should -Be 1
        $r.Customers | Should -Be 243
        $r.Sales | Should -Be 366058.87
        $r.Who | Should -Be 'sam.demo@contoso.com'
    }
    It 'treats a BLANK sales amount (null) as zero' {
        (ConvertFrom-RlsResponse (New-Response 'x@contoso.com' 0 0 $null 0)).Sales | Should -Be 0
    }
    It 'throws on a query error' {
        $err = '{"results":[{"error":{"code":"DatasetExecuteQueriesError","message":"Query (3, 13) The value for Who Am I cannot be determined."}}]}'
        { ConvertFrom-RlsResponse $err } | Should -Throw '*DatasetExecuteQueriesError*'
    }
    It 'throws on a top-level error' {
        { ConvertFrom-RlsResponse '{"error":{"code":"PowerBINotAuthorizedException","message":""}}' } | Should -Throw '*NotAuthorized*'
    }
}

Describe 'Test-RlsMatrix' {
    It 'calls executeQueries once per service user and passes when the service matches the matrix' {
        Mock -ModuleName RlsMatrix Invoke-PowerBIRestMethod { Get-ExpectedResponse $Body }
        $r = @(Test-RlsMatrix -WorkspaceId 'ws' -DatasetId 'ds' -UpnDomain 'Contoso.com' -ExpectedPath $script:Matrix)
        $r.Count | Should -Be 5
        $r.Result | Should -Not -Contain 'FAIL'
        ($r | Where-Object User -eq 'riley.demo').Stores | Should -Be 3
        Should -Invoke -ModuleName RlsMatrix Invoke-PowerBIRestMethod -Times 5 -Exactly -ParameterFilter {
            $Method -eq 'Post' -and $Url -eq 'groups/ws/datasets/ds/executeQueries'
        }
    }
    It 'never prints the tenant domain' {
        Mock -ModuleName RlsMatrix Invoke-PowerBIRestMethod { Get-ExpectedResponse $Body }
        $out = Test-RlsMatrix -WorkspaceId 'ws' -DatasetId 'ds' -UpnDomain 'contoso.com' -ExpectedPath $script:Matrix |
            Format-Table | Out-String
        $out | Should -Not -Match 'contoso\.com'
    }
    It 'fails a user who sees every store (e.g. a workspace Contributor: RLS does not apply)' {
        Mock -ModuleName RlsMatrix Invoke-PowerBIRestMethod {
            $upn = ($Body | ConvertFrom-Json).impersonatedUserName
            if ($upn -like 'sam.demo@*') { New-Response $upn 5 301 1862401.98 2440 } else { Get-ExpectedResponse $Body }
        }
        $r = @(Test-RlsMatrix -WorkspaceId 'ws' -DatasetId 'ds' -UpnDomain 'contoso.com' -ExpectedPath $script:Matrix)
        $sam = $r | Where-Object User -eq 'sam.demo'
        $sam.Result | Should -Be 'FAIL'
        $sam.Details | Should -Match 'stores 5, expected 1'
        @($r | Where-Object Result -eq 'FAIL').Count | Should -Be 1
    }
    It 'fails when Who Am I is not the impersonated user' {
        Mock -ModuleName RlsMatrix Invoke-PowerBIRestMethod {
            $j = Get-ExpectedResponse $Body | ConvertFrom-Json -AsHashtable
            $j.results[0].tables[0].rows[0]['[Who]'] = 'labadmin@contoso.com'
            $j | ConvertTo-Json -Depth 8
        }
        $r = @(Test-RlsMatrix -WorkspaceId 'ws' -DatasetId 'ds' -UpnDomain 'contoso.com' -ExpectedPath $script:Matrix)
        $r.Result | Should -Not -Contain 'PASS'
        $r[0].Details | Should -Match 'another identity'
    }
    It 'turns an HTTP failure into a FAIL row instead of stopping' {
        Mock -ModuleName RlsMatrix Invoke-PowerBIRestMethod { throw 'Response status code does not indicate success: 401 (Unauthorized).' }
        $r = @(Test-RlsMatrix -WorkspaceId 'ws' -DatasetId 'ds' -UpnDomain 'contoso.com' -ExpectedPath $script:Matrix)
        $r.Result | Should -Not -Contain 'PASS'
        $r[0].Details | Should -Match '401'
    }
}

Describe 'Test-RlsMatrix.ps1' {
    It 'parses without errors' {
        $path = Join-Path $PSScriptRoot '..' 'src' 'service' 'Test-RlsMatrix.ps1'
        $tokens = $null; $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors) | Out-Null
        $errors | Should -BeNullOrEmpty
    }
}
