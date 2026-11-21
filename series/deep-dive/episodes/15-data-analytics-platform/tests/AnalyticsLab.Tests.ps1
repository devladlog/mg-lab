BeforeAll {
    $script:Root = Split-Path $PSScriptRoot -Parent
    Import-Module (Join-Path $script:Root 'scripts' 'AnalyticsLab.psm1') -Force
}

Describe 'Get-AnalyticsSqlPlan' {
    It 'orders the Synapse scripts so each object exists before the next one uses it' {
        $plan = Get-AnalyticsSqlPlan -Target Synapse -StorageAccount stlabdemo
        ($plan | ForEach-Object { Split-Path $_.File -Leaf }) | Should -Be @('000-database.sql', '010-lake.sql', '020-bronze.sql', '030-silver.sql', '040-gold.sql', '060-quality.sql')
        $plan[0].Database | Should -Be 'master'
        $plan[1].Database | Should -Be 'contoso_analytics'
    }
    It 'adds the generated risk score before the quality view when asked' {
        $plan = Get-AnalyticsSqlPlan -Target Synapse -StorageAccount stlabdemo -IncludeRiskScore
        ($plan | ForEach-Object { Split-Path $_.File -Leaf }) | Should -Contain '050-risk-score.sql'
    }
    It 'every script in the plan exists in the repo' {
        foreach ($s in (Get-AnalyticsSqlPlan -Target Synapse -StorageAccount x -IncludeRiskScore) + (Get-AnalyticsSqlPlan -Target Source -FactoryName adf-x)) {
            Test-Path $s.File | Should -BeTrue -Because $s.File
        }
    }
    It 'passes the storage account name only to the data source script' {
        $plan = Get-AnalyticsSqlPlan -Target Synapse -StorageAccount stlabdemo
        ($plan | Where-Object { $_.Variables.ContainsKey('StorageAccount') }).File | Should -BeLike '*010-lake.sql'
    }
    It 'needs the factory name for the source and the storage account for Synapse' {
        { Get-AnalyticsSqlPlan -Target Source } | Should -Throw '*FactoryName*'
        { Get-AnalyticsSqlPlan -Target Synapse } | Should -Throw '*StorageAccount*'
    }
    It 'uses every sqlcmd variable the scripts declare, and only those' {
        $text = Get-Content (Join-Path $script:Root 'sql' 'synapse' '010-lake.sql') -Raw
        [regex]::Matches($text, '\$\((\w+)\)').Groups[1].Value | Sort-Object -Unique | Should -Be @('StorageAccount')
        $src = Get-Content (Join-Path $script:Root 'sql' 'source' '001-source-schema.sql') -Raw
        [regex]::Matches($src, '\$\((\w+)\)').Groups[1].Value | Sort-Object -Unique | Should -Be @('AdfName')
    }
}

Describe 'Get-SqlcmdArguments' {
    It 'uses Entra authentication, stops on error and sorts the variables' {
        $step = [pscustomobject]@{ File = 'a.sql'; Database = 'db1'; Variables = @{ B = '2'; A = '1' } }
        $a = Get-SqlcmdArguments -Server 'srv.example' -Step $step
        $a | Should -Be @('-S', 'srv.example', '-d', 'db1', '-G', '-b', '-i', 'a.sql', '-v', 'A=1', '-v', 'B=2')
    }
    It 'never puts a user name or password on the command line' {
        $step = (Get-AnalyticsSqlPlan -Target Synapse -StorageAccount s)[0]
        (Get-SqlcmdArguments -Server s -Step $step) | Should -Not -Contain '-P'
        (Get-SqlcmdArguments -Server s -Step $step) | Should -Not -Contain '-U'
    }
}

Describe 'Invoke-AnalyticsSql' {
    BeforeAll {
        function global:sqlcmd { $script:Calls += , @($args); $global:LASTEXITCODE = $script:Exit }
    }
    AfterAll { Remove-Item function:global:sqlcmd -ErrorAction SilentlyContinue }
    BeforeEach { $script:Calls = @(); $script:Exit = 0 }
    It 'runs every script in order' {
        $plan = Get-AnalyticsSqlPlan -Target Synapse -StorageAccount stlabdemo
        Invoke-AnalyticsSql -Server 'ws-ondemand.example' -Plan $plan | Out-Null
        $script:Calls.Count | Should -Be $plan.Count
        $script:Calls[0] | Should -Contain $plan[0].File
    }
    It 'does nothing under -WhatIf' {
        $plan = Get-AnalyticsSqlPlan -Target Synapse -StorageAccount stlabdemo
        Invoke-AnalyticsSql -Server 'x' -Plan $plan -WhatIf | Out-Null
        $script:Calls.Count | Should -Be 0
    }
    It 'stops at the first failing script' {
        $script:Exit = 1
        $plan = Get-AnalyticsSqlPlan -Target Synapse -StorageAccount stlabdemo
        { Invoke-AnalyticsSql -Server 'x' -Plan $plan } | Should -Throw '*000-database.sql*'
        $script:Calls.Count | Should -Be 1
    }
}

Describe 'Get-LakePullCommand' {
    It 'logs in with Entra and copies only the bronze folder' {
        $c = Get-LakePullCommand -StorageAccount stlabdemo -Destination 'C:\work\lake'
        $c | Should -BeLike '*--auth-mode login*'
        $c | Should -BeLike "*--pattern 'bronze/*'*"
        $c | Should -Not -BeLike '*account-key*'
    }
}
