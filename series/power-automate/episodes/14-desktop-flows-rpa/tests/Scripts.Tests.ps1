# Pester 5+: the scripts run for real in PowerShell; Invoke-RestMethod is the only thing mocked.
BeforeAll {
    $script:scripts = Join-Path $PSScriptRoot '..' 'src' 'scripts'
    $script:test = Join-Path $scripts 'Test-PurchaseOrder.ps1'
    $script:confirm = Join-Path $scripts 'Confirm-PurchaseOrder.ps1'
    $script:invoke = Join-Path $scripts 'Invoke-DesktopFlow.ps1'
    $script:org = 'https://contoso.crm4.dynamics.com'
    $script:flowId = '00000000-0000-0000-0000-000000000701'
    $script:session = '00000000-0000-0000-0000-000000000801'
}

Describe 'Test-PurchaseOrder.ps1' {
    It 'accepts a good order and formats the amount for a pt-PT machine' {
        $r = & $test -Supplier 'Contoso Office Supplies' -Description 'USB-C cables' -Amount '1800.5' -Culture 'pt-PT' | ConvertFrom-Json
        $r.valid | Should -BeTrue
        $r.amountInvariant | Should -Be '1800.50'
        $r.amountForApp | Should -Be '1800,50'
        $r.culture | Should -Be 'pt-PT'
    }
    It 'keeps the dot on an en-US machine' {
        ((& $test -Supplier 's' -Description 'd' -Amount '1800.5' -Culture 'en-US') | ConvertFrom-Json).amountForApp | Should -Be '1800.50'
    }
    It 'reports every problem at once' {
        $r = & $test -Supplier '' -Description ' ' -Amount 'abc' -Culture 'en-US' | ConvertFrom-Json
        $r.valid | Should -BeFalse
        $r.errors | Should -Contain 'Supplier is required'
        $r.errors | Should -Contain 'Description is required'
        $r.errors | Should -Contain 'Amount is not a number'
        $r.errorText | Should -Be 'Supplier is required; Description is required; Amount is not a number'
    }
    It 'applies the same limits as the legacy form' -ForEach @(
        @{ a = '0'; msg = 'Amount must be greater than zero' }
        @{ a = '100001'; msg = 'Amount is above the limit of 100000' }) {
        (& $test -Supplier 's' -Description 'd' -Amount $a -Culture 'en-US' | ConvertFrom-Json).errors | Should -Contain $msg
    }
    It 'rejects a supplier name longer than 60 characters' {
        $r = & $test -Supplier ('x' * 61) -Description 'd' -Amount '1' -Culture 'en-US' | ConvertFrom-Json
        $r.errors | Should -Contain 'Supplier is longer than 60 characters'
    }
    It 'writes exactly one line (what the PowerShell action returns)' {
        @(& $test -Supplier 's' -Description 'd' -Amount '1' -Culture 'en-US').Count | Should -Be 1
    }
}

Describe 'free text never becomes code (the scripts read the fields from files)' {
    It 'Test-PurchaseOrder reads Supplier, Description and Amount from -InputDir, quotes and newlines included' {
        $evil = "a'; Set-Content pwned14.txt 1; '"
        $dir = Join-Path $TestDrive 'run1'; New-Item -ItemType Directory $dir | Out-Null
        [IO.File]::WriteAllText((Join-Path $dir 'Supplier.txt'), "$evil`r`n")
        [IO.File]::WriteAllText((Join-Path $dir 'Description.txt'), "Line one`nLine two")
        [IO.File]::WriteAllText((Join-Path $dir 'Amount.txt'), '12.5')
        $r = & $test -InputDir $dir -Culture 'en-US' | ConvertFrom-Json
        $r.valid | Should -BeTrue
        Test-Path 'pwned14.txt' | Should -BeFalse
        $r.amountForApp | Should -Be '12.50'
    }
    It 'negative control: the naive inline pattern WOULD run the supplier text as code (why we do not use it)' {
        $supplier = "a'; Set-Content proof.txt 1 #"
        $pasted = "& '$test' -Supplier '$supplier' -Description 'd' -Amount '1'"   # what %Supplier% substitution produces
        Push-Location $TestDrive
        try { pwsh -NoProfile -Command $pasted | Out-Null } finally { Pop-Location }
        Test-Path (Join-Path $TestDrive 'proof.txt') | Should -BeTrue
    }
    It 'a missing field file counts as empty' {
        $dir = Join-Path $TestDrive 'run2'; New-Item -ItemType Directory $dir | Out-Null
        (& $test -InputDir $dir -Culture 'en-US' | ConvertFrom-Json).errors | Should -Contain 'Supplier is required'
    }
    It 'Confirm-PurchaseOrder reads the supplier from -InputDir' {
        $dir = Join-Path $TestDrive 'run3'; New-Item -ItemType Directory $dir | Out-Null
        [IO.File]::WriteAllText((Join-Path $dir 'Supplier.txt'), "Contoso, Lda`n")
        $ledger = Join-Path $TestDrive 'l3.csv'
        "OrderNo,SavedAtUtc,Supplier,Description,Amount,EnteredBy`n`"PO-2026-0001`",`"2026-01-05T09:00:00.0000000Z`",`"Contoso, Lda`",`"x`",10.00,`"a`"" | Set-Content $ledger
        (& $confirm -LedgerPath $ledger -InputDir $dir -Amount '10.00' -SinceUtc '2026-01-05T08:00:00Z' | ConvertFrom-Json).orderNo | Should -Be 'PO-2026-0001'
    }
}

Describe 'Confirm-PurchaseOrder.ps1' {
    BeforeAll {
        $script:ledger = Join-Path $TestDrive 'orders.csv'
        @'
OrderNo,SavedAtUtc,Supplier,Description,Amount,EnteredBy
"PO-2026-0001","2026-01-05T09:00:00.0000000Z","Contoso, Lda","Chairs ""ergonomic""",1800.50,"alex.demo"
"PO-2026-0002","2026-01-05T10:00:00.0000000Z","Fabrikam","Laptops",12500.00,"alex.demo"
"PO-2026-0003","2026-01-05T11:30:00.0000000Z","Fabrikam","Laptops",12500.00,"alex.demo"
'@ | Set-Content -LiteralPath $ledger -Encoding UTF8
    }
    It 'finds the order saved since the run started, not an older identical one' {
        $r = & $confirm -LedgerPath $ledger -Supplier 'Fabrikam' -Amount '12500.00' -SinceUtc '2026-01-05T11:00:00Z' | ConvertFrom-Json
        $r.found | Should -BeTrue
        $r.orderNo | Should -Be 'PO-2026-0003'
    }
    It 'handles quoted commas in the supplier name' {
        (& $confirm -LedgerPath $ledger -Supplier 'Contoso, Lda' -Amount '1800.50' -SinceUtc '2026-01-05T08:00:00Z' | ConvertFrom-Json).orderNo | Should -Be 'PO-2026-0001'
    }
    It 'says why when nothing matches' {
        $r = & $confirm -LedgerPath $ledger -Supplier 'Fabrikam' -Amount '12500.00' -SinceUtc '2026-01-05T12:00:00Z' | ConvertFrom-Json
        $r.found | Should -BeFalse
        $r.reason | Should -BeLike 'no matching order*'
    }
    It 'says when the ledger does not exist' {
        (& $confirm -LedgerPath (Join-Path $TestDrive 'nope.csv') -Supplier 's' -Amount '1' -SinceUtc '2026-01-05T08:00:00Z' | ConvertFrom-Json).reason | Should -Be 'ledger file not found'
    }
}

Describe 'Invoke-DesktopFlow.ps1' {
    BeforeEach { $env:DATAVERSE_TOKEN = 'test-token' }
    AfterAll { Remove-Item Env:DATAVERSE_TOKEN -ErrorAction SilentlyContinue }

    It 'sends the documented RunDesktopFlow body, inputs as a JSON string' {
        Mock Invoke-RestMethod { [pscustomobject]@{ flowsessionId = $session } }
        $r = & $invoke -OrgUrl $org -DesktopFlowId $flowId -ConnectionName 'conn-1' -Inputs @{ Supplier = 'Fabrikam'; Amount = '12500.00' } -NoWait
        $r.flowsessionId | Should -Be $session
        Should -Invoke Invoke-RestMethod -Exactly 1 -ParameterFilter {
            $Method -eq 'POST' -and $Uri -eq "$org/api/data/v9.2/workflows($flowId)/Microsoft.Dynamics.CRM.RunDesktopFlow" -and
            ($b = $Body | ConvertFrom-Json) -and $b.runMode -eq 'attended' -and $b.connectionName -eq 'conn-1' -and
            $b.timeout -eq 7200 -and ($b.inputs | ConvertFrom-Json).Supplier -eq 'Fabrikam'
        }
    }
    It '-WhatIf sends nothing' {
        Mock Invoke-RestMethod { throw 'must not be called' }
        & $invoke -OrgUrl $org -DesktopFlowId $flowId -ConnectionName 'c' -WhatIf | Out-Null
        Should -Invoke Invoke-RestMethod -Exactly 0
    }
    It 'polls until the run ends and returns the outputs' {
        $state = @{ polls = 0 }
        Mock Start-Sleep { }
        Mock Invoke-RestMethod {
            if ($Method -eq 'POST') { return [pscustomobject]@{ flowsessionId = $session } }
            if ($Uri -like '*/outputs/$value') { return [pscustomobject]@{ OrderNumber = 'PO-2026-0003' } }
            $state.polls++
            [pscustomobject]@{ statuscode = $(if ($state.polls -lt 3) { 2 } else { 4 }); statecode = 0; startedon = '2026-01-05T11:00:00Z'; completedon = '2026-01-05T11:01:00Z' }
        }
        $r = & $invoke -OrgUrl $org -DesktopFlowId $flowId -ConnectionName 'c' -PollSeconds 1
        $r.status | Should -Be 'Succeeded'
        $r.outputs.OrderNumber | Should -Be 'PO-2026-0003'
        $state.polls | Should -Be 3
    }
    It 'throws when the run fails' -ForEach @(@{ code = 8; name = 'Failed' }, @{ code = 10; name = 'TimedOut' }, @{ code = 7; name = 'Cancelled' }) {
        Mock Invoke-RestMethod {
            if ($Method -eq 'POST') { return [pscustomobject]@{ flowsessionId = $session } }
            [pscustomobject]@{ statuscode = $code; statecode = 0 }
        }
        { & $invoke -OrgUrl $org -DesktopFlowId $flowId -ConnectionName 'c' } | Should -Throw "*ended $name*"
    }
    It 'cancels the run when it gives up waiting' {
        Mock Start-Sleep { }
        Mock Invoke-RestMethod {
            if ($Method -eq 'POST' -and $Uri -like '*RunDesktopFlow') { return [pscustomobject]@{ flowsessionId = $session } }
            if ($Method -eq 'GET') { return [pscustomobject]@{ statuscode = 2 } }
        }
        { & $invoke -OrgUrl $org -DesktopFlowId $flowId -ConnectionName 'c' -PollSeconds 5 -MaxWaitSeconds 10 } | Should -Throw '*cancelled*'
        Should -Invoke Invoke-RestMethod -Exactly 1 -ParameterFilter { $Uri -like "*flowsessions($session)/Microsoft.Dynamics.CRM.CancelDesktopFlowRun" }
    }
    It 'refuses a token-less call and a bad id' {
        Remove-Item Env:DATAVERSE_TOKEN
        { & $invoke -OrgUrl $org -DesktopFlowId $flowId -ConnectionName 'c' } | Should -Throw '*DATAVERSE_TOKEN*'
        $env:DATAVERSE_TOKEN = 'x'
        { & $invoke -OrgUrl $org -DesktopFlowId 'nope' -ConnectionName 'c' } | Should -Throw '*not a GUID*'
    }
}
