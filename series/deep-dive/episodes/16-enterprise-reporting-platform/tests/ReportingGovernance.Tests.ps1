BeforeAll {
    $script:Root = Resolve-Path (Join-Path $PSScriptRoot '..')
    Import-Module (Join-Path $script:Root 'scripts/ReportingGovernance.psm1') -Force
    $script:Policy = Join-Path $script:Root 'governance/policy.json'
    $script:Scan = Join-Path $script:Root 'governance/fixtures/scanResult.sample.json'
    $script:Map = Join-Path $script:Root 'governance/fixtures/security-map.csv'
    $script:Counts = Join-Path $script:Root 'governance/fixtures/requests-by-department.csv'
}

Describe 'New-ScanRequest' {
    It 'builds one getInfo request for a few workspaces, with the metadata options as query parameters' {
        $r = @(New-ScanRequest -WorkspaceId 'a', 'b' -DatasetSchema -Lineage)
        $r.Count | Should -Be 1
        $r[0].Uri | Should -Be 'https://api.powerbi.com/v1.0/myorg/admin/workspaces/getInfo?datasetSchema=true&lineage=true'
        $r[0].Body.workspaces | Should -Be @('a', 'b')
    }
    It 'splits more than 100 workspaces into batches of at most 100' {
        $ids = 1..250 | ForEach-Object { [guid]::NewGuid().ToString() }
        $r = @(New-ScanRequest -WorkspaceId $ids)
        $r.Count | Should -Be 3
        ($r | ForEach-Object { $_.Body.workspaces.Count }) | Should -Be @(100, 100, 50)
    }
    It 'drops duplicates and refuses an empty list' {
        @(New-ScanRequest -WorkspaceId 'a', 'a')[0].Body.workspaces.Count | Should -Be 1
        { New-ScanRequest -WorkspaceId @('') } | Should -Throw
    }
    It 'refuses a batch size above 100' {
        { New-ScanRequest -WorkspaceId 'a' -BatchSize 101 } | Should -Throw
    }
}

Describe 'Get-GovernanceFindings' {
    BeforeAll { $script:F = @(Get-GovernanceFindings -ScanResultPath $script:Scan -PolicyPath $script:Policy) }

    It 'finds nothing wrong in the certified production workspace and the test workspace' {
        $script:F | Where-Object { $_.Workspace -in 'Contoso Reporting [PROD]', 'Contoso Reporting [TEST]' } | Should -BeNullOrEmpty
    }
    It 'flags the ad hoc production workspace on capacity, certification, label, owner and binding' {
        $rules = $script:F | Where-Object { $_.Workspace -eq 'Contoso Adhoc Spend [PROD]' } | ForEach-Object Rule
        $rules | Should -Contain 'ProdOnCapacity'
        $rules | Should -Contain 'ProdModelCertified'
        $rules | Should -Contain 'OwnerRequired'
        $rules | Should -Contain 'ReportOnUncertifiedModel'
        @($rules | Where-Object { $_ -eq 'ProdLabelRequired' }).Count | Should -Be 2   # the model and the report
    }
    It 'flags content in a personal workspace as a warning' {
        $f = $script:F | Where-Object Rule -eq 'NoContentInPersonalWorkspace'
        $f.Severity | Should -Be 'Warning'
    }
    It 'flags a certification by someone outside the certifier list' {
        ($script:F | Where-Object Rule -eq 'CertifierNotAllowed').Item | Should -Be 'Finance model'
    }
    It 'gives eight findings in total on the sample' {
        $script:F.Count | Should -Be 8
    }
    It 'follows the policy switches' {
        $p = Get-Content $script:Policy -Raw | ConvertFrom-Json
        $p.requireCertifiedInProduction = $false
        $p.requireSensitivityLabelInProduction = $false
        $tmp = Join-Path ([IO.Path]::GetTempPath()) "policy-$([guid]::NewGuid()).json"
        try {
            $p | ConvertTo-Json | Set-Content $tmp
            $rules = Get-GovernanceFindings -ScanResultPath $script:Scan -PolicyPath $tmp | ForEach-Object Rule
            $rules | Should -Not -Contain 'ProdModelCertified'
            $rules | Should -Not -Contain 'ProdLabelRequired'
            $rules | Should -Contain 'ProdOnCapacity'
        } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
    }
    It 'fails clearly when the scan file is missing' {
        { Get-GovernanceFindings -ScanResultPath '/nope.json' -PolicyPath $script:Policy } | Should -Throw '*not found*'
    }
}

Describe 'Get-RlsExpectedCounts' {
    It 'sums the departments of each user' {
        $c = Get-RlsExpectedCounts -MapCsv $script:Map -CountsCsv $script:Counts
        $c['alex.demo@contoso.example'] | Should -Be 240
        $c['sam.demo@contoso.example'] | Should -Be 209
        $c['jordan.demo@contoso.example'] | Should -Be 310
        $c['riley.demo@contoso.example'] | Should -Be 330   # HR 180 + MKT 150
    }
    It 'refuses a mapping row for a department that has no data' {
        $tmp = Join-Path ([IO.Path]::GetTempPath()) "map-$([guid]::NewGuid()).csv"
        try {
            "UserPrincipalName,DepartmentKey`nx@contoso.example,XXX" | Set-Content $tmp
            { Get-RlsExpectedCounts -MapCsv $tmp -CountsCsv $script:Counts } | Should -Throw '*unknown department*'
        } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
    }
    It 'agrees with the mapping inside the committed model' {
        $tmdl = Get-Content (Join-Path $script:Root 'model/ContosoReporting.SemanticModel/definition/tables/SecurityMap.tmdl') -Raw
        $pairs = [regex]::Matches($tmdl, '\{"(?<u>[a-z.]+)@" & UpnDomain, "(?<d>[A-Z]+)"\}') | ForEach-Object { "$($_.Groups['u'].Value)@contoso.example,$($_.Groups['d'].Value)" }
        $csv = Import-Csv $script:Map | ForEach-Object { "$($_.UserPrincipalName),$($_.DepartmentKey)" }
        ($pairs | Sort-Object) | Should -Be ($csv | Sort-Object)
    }
}

Describe 'New-ExecuteQueriesBody' {
    It 'adds impersonatedUserName only when asked' {
        (New-ExecuteQueriesBody -Query 'EVALUATE ROW("x", 1)').Contains('impersonatedUserName') | Should -BeFalse
        (New-ExecuteQueriesBody -Query 'EVALUATE ROW("x", 1)' -ImpersonatedUserName 'a@contoso.example').impersonatedUserName | Should -Be 'a@contoso.example'
    }
    It 'sends exactly one query and refuses text that is not a DAX query' {
        @((New-ExecuteQueriesBody -Query 'EVALUATE ROW("x", 1)').queries).Count | Should -Be 1
        { New-ExecuteQueriesBody -Query 'SELECT 1' } | Should -Throw
    }
}

Describe 'Invoke-RlsCheck' {
    It 'compares the API answer for each user with the expected count' {
        Mock Invoke-RestMethod -ModuleName ReportingGovernance {
            $user = ($Body | ConvertFrom-Json).impersonatedUserName
            $n = @{ 'alex.demo@contoso.example' = 240; 'sam.demo@contoso.example' = 209; 'jordan.demo@contoso.example' = 310; 'riley.demo@contoso.example' = 999 }[$user]
            [pscustomobject]@{ results = @([pscustomobject]@{ tables = @([pscustomobject]@{ rows = @([pscustomobject]@{ '[Requests]' = $n }) }) }) }
        }
        $r = @(Invoke-RlsCheck -DatasetId ([guid]::NewGuid()) -MapCsv $script:Map -CountsCsv $script:Counts -AccessToken 'x')
        $r.Count | Should -Be 4
        ($r | Where-Object Pass).Count | Should -Be 3
        ($r | Where-Object { -not $_.Pass }).User | Should -Be 'riley.demo@contoso.example'
        Should -Invoke Invoke-RestMethod -ModuleName ReportingGovernance -Times 4 -Exactly
    }
    It 'makes no call with -WhatIf' {
        Mock Invoke-RestMethod -ModuleName ReportingGovernance { throw 'must not be called' }
        $r = @(Invoke-RlsCheck -DatasetId ([guid]::NewGuid()) -MapCsv $script:Map -CountsCsv $script:Counts -WhatIf)
        $r.Count | Should -Be 4
        Should -Invoke Invoke-RestMethod -ModuleName ReportingGovernance -Times 0 -Exactly
    }
}

Describe 'New-DeployRequest' {
    BeforeAll {
        $script:A = [guid]::NewGuid(); $script:B = [guid]::NewGuid()
    }
    It 'builds a deploy-all body' {
        $b = New-DeployRequest -SourceStageId $script:A -TargetStageId $script:B -Note 'release 1'
        $b.sourceStageId | Should -Be "$($script:A)"
        $b.note | Should -Be 'release 1'
        $b.Contains('items') | Should -BeFalse
    }
    It 'builds a selective body with item types from the API list' {
        $id = [guid]::NewGuid()
        $b = New-DeployRequest -SourceStageId $script:A -TargetStageId $script:B -Item @([pscustomobject]@{ SourceItemId = $id; ItemType = 'SemanticModel' })
        $b.items[0].itemType | Should -Be 'SemanticModel'
        $b.items[0].sourceItemId | Should -Be "$id"
    }
    It 'refuses same stage, unknown item type and a note over 1024 characters' {
        { New-DeployRequest -SourceStageId $script:A -TargetStageId $script:A } | Should -Throw
        { New-DeployRequest -SourceStageId $script:A -TargetStageId $script:B -Item @([pscustomobject]@{ SourceItemId = [guid]::NewGuid(); ItemType = 'Spaceship' }) } | Should -Throw '*Unsupported*'
        { New-DeployRequest -SourceStageId $script:A -TargetStageId $script:B -Note ('x' * 1025) } | Should -Throw
    }
}

Describe 'Invoke-PipelineDeploy' {
    It 'does nothing with -WhatIf' {
        Mock Invoke-WebRequest -ModuleName ReportingGovernance { throw 'must not be called' }
        Invoke-PipelineDeploy -PipelineId ([guid]::NewGuid()) -Body @{ a = 1 } -WhatIf
        Should -Invoke Invoke-WebRequest -ModuleName ReportingGovernance -Times 0 -Exactly
    }
    It 'follows the Location header until the operation succeeds' {
        Mock Start-Sleep -ModuleName ReportingGovernance { }
        Mock Invoke-WebRequest -ModuleName ReportingGovernance {
            [pscustomobject]@{ StatusCode = 202; Headers = @{ Location = 'https://api.fabric.microsoft.com/v1/operations/op1'; 'Retry-After' = '5' }; Content = '' }
        }
        $script:calls = 0
        Mock Invoke-RestMethod -ModuleName ReportingGovernance {
            $script:calls++
            [pscustomobject]@{ status = $(if ($script:calls -lt 2) { 'Running' } else { 'Succeeded' }) }
        }
        $r = Invoke-PipelineDeploy -PipelineId ([guid]::NewGuid()) -Body @{ a = 1 } -Confirm:$false
        $r.status | Should -Be 'Succeeded'
        Should -Invoke Invoke-RestMethod -ModuleName ReportingGovernance -Times 2 -Exactly
    }
}
