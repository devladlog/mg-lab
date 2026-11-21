# Pester 5: the script is run for real; only Invoke-RestMethod and Start-Sleep are mocked (no tenant, no network).
BeforeAll {
    $script:ps1 = Join-Path $PSScriptRoot '..' 'src' 'scripts' 'Invoke-DataverseQuery.ps1'
    $script:org = 'https://contoso.crm4.dynamics.com'
    function New-Throttle([int]$seconds) {
        $resp = [System.Net.Http.HttpResponseMessage]::new([System.Net.HttpStatusCode]429)
        $resp.Headers.RetryAfter = [System.Net.Http.Headers.RetryConditionHeaderValue]::new([TimeSpan]::FromSeconds($seconds))
        [Microsoft.PowerShell.Commands.HttpResponseException]::new('429 Too Many Requests', $resp)
    }
}
Describe 'Invoke-DataverseQuery.ps1' {
    BeforeEach { $env:DATAVERSE_TOKEN = 'test-token' }
    AfterAll { Remove-Item Env:DATAVERSE_TOKEN -ErrorAction SilentlyContinue }

    It 'refuses to run without a token' {
        Remove-Item Env:DATAVERSE_TOKEN
        { & $ps1 -OrgUrl $org -Table opportunities } | Should -Throw '*DATAVERSE_TOKEN*'
    }
    It 'rejects a filter that contains $filter=' {
        { & $ps1 -OrgUrl $org -Table opportunities -Filter '$filter=statecode eq 1' } | Should -Throw '*expression only*'
    }
    It 'rejects an odd number of single quotes' {
        { & $ps1 -OrgUrl $org -Table opportunities -Filter "name eq 'O'Bryan'" } | Should -Throw '*single quotes*'
    }
    It 'rejects -Top together with -PageSize' {
        { & $ps1 -OrgUrl $org -Table opportunities -Top 5 -PageSize 5 } | Should -Throw '*can''t be combined*'
    }
    It 'rejects a table name that is not an entity set name' {
        { & $ps1 -OrgUrl $org -Table 'Opportunity Close' } | Should -Throw '*entity set name*'
    }
    It '-PrintOnly shows the request and sends nothing' {
        Mock Invoke-RestMethod { throw 'must not be called' }
        Remove-Item Env:DATAVERSE_TOKEN
        $out = & $ps1 -OrgUrl $org -Table opportunities -Filter 'statecode eq 0' -Select name, estimatedvalue -OrderBy 'name asc,opportunityid asc' -PageSize 50 -FormattedValues -PrintOnly 6>&1 | Out-String
        $out | Should -Match 'GET https://contoso.crm4.dynamics.com/api/data/v9.2/opportunities\?\$select=name,estimatedvalue&\$filter=statecode eq 0&\$orderby=name asc,opportunityid asc'
        $out | Should -Match 'Prefer: odata.include-annotations="OData.Community.Display.V1.FormattedValue",odata.maxpagesize=50'
        $out | Should -Not -Match 'Authorization'
        Should -Invoke Invoke-RestMethod -Exactly 0
    }
    It 'encodes & # + % inside quoted values only' {
        $out = & $ps1 -OrgUrl $org -Table accounts -Filter "contains(name,'R&D +50%') and statecode eq 0" -PrintOnly 6>&1 | Out-String
        $out | Should -Match "contains\(name,'R%26D %2B50%25'\) and statecode eq 0"
    }
    It 'follows @odata.nextLink unchanged and sends the same page size on every request' {
        Mock Invoke-RestMethod {
            if ($Uri -like '*skiptoken=2*') { return [pscustomobject]@{ value = @([pscustomobject]@{ name = 'c' }) } }
            if ($Uri -like '*skiptoken=1*') { return [pscustomobject]@{ value = @([pscustomobject]@{ name = 'b' }); '@odata.nextLink' = "$org/api/data/v9.2/opportunities?`$select=name&`$skiptoken=2" } }
            [pscustomobject]@{ value = @([pscustomobject]@{ name = 'a' }); '@odata.nextLink' = "$org/api/data/v9.2/opportunities?`$select=name&`$skiptoken=1" }
        }
        $rows = @(& $ps1 -OrgUrl $org -Table opportunities -Select name -PageSize 1 6>$null)
        $rows.name | Should -Be @('a', 'b', 'c')
        Should -Invoke Invoke-RestMethod -ParameterFilter { $Uri -eq "$org/api/data/v9.2/opportunities?`$select=name&`$skiptoken=1" } -Exactly 1
        Should -Invoke Invoke-RestMethod -Exactly 3
        Should -Invoke Invoke-RestMethod -ParameterFilter { $Headers['Prefer'] -eq 'odata.maxpagesize=1' -and $Headers['Authorization'] -eq 'Bearer test-token' } -Exactly 3
    }
    It 'stops at -MaxPages and says so' {
        Mock Invoke-RestMethod { [pscustomobject]@{ value = @([pscustomobject]@{ name = 'x' }); '@odata.nextLink' = "$org/next" } }
        $w = $null
        $rows = @(& $ps1 -OrgUrl $org -Table opportunities -MaxPages 2 -WarningVariable w -WarningAction SilentlyContinue 6>$null)
        $rows.Count | Should -Be 2
        "$w" | Should -Match 'Stopped after 2 page'
    }
    It 'waits for Retry-After on a 429 and then succeeds' {
        $script:n = 0
        Mock Start-Sleep { }
        Mock Invoke-RestMethod {
            $script:n++
            if ($script:n -eq 1) { throw (New-Throttle 7) }
            [pscustomobject]@{ value = @([pscustomobject]@{ name = 'ok' }) }
        }
        $rows = @(& $ps1 -OrgUrl $org -Table opportunities -WarningAction SilentlyContinue 6>$null)
        $rows.name | Should -Be 'ok'
        Should -Invoke Start-Sleep -ParameterFilter { $Seconds -eq 7 } -Exactly 1
        Should -Invoke Invoke-RestMethod -Exactly 2
    }
    It 'gives up after -MaxRetries throttled attempts' {
        Mock Start-Sleep { }
        Mock Invoke-RestMethod { throw (New-Throttle 1) }
        { & $ps1 -OrgUrl $org -Table opportunities -MaxRetries 2 -WarningAction SilentlyContinue 6>$null } | Should -Throw
        Should -Invoke Invoke-RestMethod -Exactly 3
    }
    It 'does not retry other errors' {
        Mock Start-Sleep { }
        Mock Invoke-RestMethod { throw 'boom' }
        { & $ps1 -OrgUrl $org -Table opportunities 6>$null } | Should -Throw 'boom'
        Should -Invoke Invoke-RestMethod -Exactly 1
    }
}
