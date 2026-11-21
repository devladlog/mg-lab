BeforeAll {
    $script:Root = Resolve-Path (Join-Path $PSScriptRoot '..' '..')
    Import-Module (Join-Path $script:Root 'src' 'ps' 'Digest.psm1') -Force
    $script:Sample = Join-Path $script:Root 'samples' 'requests.json'
    $script:Golden = (Get-Content -LiteralPath (Join-Path $script:Root 'expected' 'digest.txt') -Raw -Encoding utf8) -replace "`r`n", "`n"

    function script:New-Raw {
        param([string] $Code = 'PR-1', [decimal] $Budget = 1000, [string] $Department = 'IT')
        [pscustomobject]@{ Code = $Code; Title = 't'; Department = $Department; Budget = $Budget }
    }
}

Describe 'Get-RouteFor' {
    It 'uses inclusive boundaries: <cents> is <route>' -ForEach @(
        @{ Cents = 1; Route = 'TeamLead' }
        @{ Cents = 4999999; Route = 'TeamLead' }
        @{ Cents = 5000000; Route = 'Finance' }
        @{ Cents = 24999999; Route = 'Finance' }
        @{ Cents = 25000000; Route = 'Board' }
    ) {
        (Get-RouteFor -Cents $Cents).ToString() | Should -Be $Route
    }
}

Describe 'ConvertTo-Cents and Format-Money' {
    It 'keeps decimal budgets exact' {
        ConvertTo-Cents -Budget 49999.99 | Should -Be 4999999
        ConvertTo-Cents -Budget 50000.01 | Should -Be 5000001
        ConvertTo-Cents -Budget 0.29 | Should -Be 29
    }
    It 'formats with invariant culture, even when the thread culture differs' {
        $old = [cultureinfo]::CurrentCulture
        try {
            [cultureinfo]::CurrentCulture = [cultureinfo]::GetCultureInfo('pt-PT')
            Format-Money -Cents 132037075 | Should -Be '1,320,370.75'
        }
        finally { [cultureinfo]::CurrentCulture = $old }
        Format-Money -Cents 5 | Should -Be '0.05'
    }
    It 'documents a cross-language difference: a double cast ROUNDS in PowerShell' {
        # C# and JavaScript truncate 0.29 * 100 = 28.999999999999996 to 28; PowerShell casts to 29.
        [long](0.29 * 100) | Should -Be 29
        [Math]::Truncate(0.29 * 100) | Should -Be 28
    }
}

Describe 'New-Digest' {
    It 'rejects zero and negative budgets with the shared message' {
        $d = New-Digest -Raw (New-Raw 'PR-9' 0), (New-Raw 'PR-8' -5), (New-Raw 'PR-7' 10)
        $d.Rejected.Code | Should -Be @('PR-9', 'PR-8')
        $d.Rejected.Reason | Should -Be @('budget must be greater than zero', 'budget must be greater than zero')
        $d.Accepted.Count | Should -Be 1
    }
    It 'trims and upper-cases the department' {
        (New-Digest -Raw (New-Raw -Department ' hr ')).Accepted[0].Department | Should -Be 'HR'
    }
    It 'lists all three routes even when two are empty (null-conditional index)' {
        $d = New-Digest -Raw (New-Raw -Budget 10)
        @($d.Routes.Keys) | Should -Be @('TeamLead', 'Finance', 'Board')
        $d.Routes['Board'] | Should -Be 0
        $d.Routes['TeamLead'] | Should -Be 1
    }
    It 'batches in order and the last batch is short' {
        $raws = 1..9 | ForEach-Object { New-Raw "PR-$_" }
        $d = New-Digest -Raw $raws
        $d.Batches.Count | Should -Be 3
        $d.Batches[0] | Should -Be @('PR-1', 'PR-2', 'PR-3', 'PR-4')
        $d.Batches[2] | Should -Be @('PR-9')
    }
    It 'works with a single element (no array unrolling surprise)' {
        $d = New-Digest -Raw (New-Raw)
        $d.Accepted.Count | Should -Be 1
        $d.Batches.Count | Should -Be 1
        $d.Departments.Count | Should -Be 1
    }
}

Describe 'Read-DigestRequest' {
    It 'reads the 13 sample requests with exact decimals' {
        $raws = @(Read-DigestRequest -Path $script:Sample)
        $raws.Count | Should -Be 13
        $raws[1].Budget | Should -Be 49999.99
        $raws[1].Budget | Should -BeOfType [decimal]
    }
    It 'names the element and field when a property is missing' {
        $path = Join-Path $TestDrive 'bad.json'
        '[{ "code": "PR-1", "title": "t", "department": "IT", "requestedBy": "a@contoso.com" }]' | Set-Content -LiteralPath $path
        { Read-DigestRequest -Path $path } | Should -Throw "*element 0: missing 'budget'*"
    }
}

Describe 'Golden file' {
    It 'the sample digest equals expected/digest.txt' {
        Invoke-Digest -Path $script:Sample | Should -BeExactly $script:Golden
    }
    It 'the script prints the same text' {
        $out = (pwsh -NoProfile -File (Join-Path $script:Root 'src' 'ps' 'digest.ps1') $script:Sample) -join "`n"
        ($out + "`n") | Should -BeExactly $script:Golden
    }
}
