# Pester 5+: deployment pipeline module. Invoke-PowerBIRestMethod is mocked with responses shaped like the Learn samples
# (tests/fixtures/rest: zero GUIDs, fictional names).
#   pwsh -NoProfile -Command "Invoke-Pester ./tests -Output Detailed"

BeforeAll {
    if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
        # Stand-in so Pester can mock the MicrosoftPowerBIMgmt cmdlet without installing it.
        function global:Invoke-PowerBIRestMethod { param($Url, $Method, $Body) throw 'not mocked' }
    }
    $script:Src = Join-Path $PSScriptRoot '..' 'src' 'pipeline'
    Import-Module (Join-Path $script:Src 'PbiPipelines' 'PbiPipelines.psd1') -Force
    $script:Rest = Join-Path $PSScriptRoot 'fixtures' 'rest'
    $script:PipeId = '00000000-0000-0000-0000-0000000000a1'
    $global:PbiTest = @{ Calls = @(); Statuses = @() }

    function global:Get-PbiFixture([string] $name) { Get-Content -Raw (Join-Path $PSScriptRoot 'fixtures' 'rest' $name) }
    function global:Get-PbiRoute([string] $Url, [string] $Method, $Body) {
        $global:PbiTest.Calls += , @($Method, $Url, $Body)
        switch -Regex ($Url) {
            '^pipelines$'                     { Get-PbiFixture 'pipelines.json'; break }
            '/stages$'                        { Get-PbiFixture 'stages.json'; break }
            '/stages/0/artifacts$'            { Get-PbiFixture 'stage0.json'; break }
            '/stages/1/artifacts$'            { Get-PbiFixture 'stage1.json'; break }
            '/stages/2/artifacts$'            { '{}'; break }
            '/operations/.*c1$'               { Get-PbiFixture 'operation-ok.json'; break }
            '/operations/.*c2$'               { Get-PbiFixture 'operation-failed.json'; break }
            '/operations/.*c3$'               {
                $s = $global:PbiTest.Statuses
                $next = if ($s.Count) { $s[0] } else { 'Succeeded' }
                if ($s.Count) { $global:PbiTest.Statuses = @($s | Select-Object -Skip 1) }
                (Get-PbiFixture 'operation-ok.json') -replace '"status": "Succeeded"', "`"status`": `"$next`""; break }
            '/operations$'                    { Get-PbiFixture 'operations.json'; break }
            '/deployAll$|/Deploy$'            { Get-PbiFixture 'deploy-response.json'; break }
            '/reports$'                       { Get-PbiFixture 'reports-dev.json'; break }
            '/refreshes$'                     { ''; break }
            default                           { throw "unexpected URL $Url" }
        }
    }
    $script:D = @{ model0 = '00000000-0000-0000-0000-00000000d001'; rep1 = '00000000-0000-0000-0000-00000000e001'; rep2 = '00000000-0000-0000-0000-00000000e002' }
}

Describe 'module' {
    It 'has a valid manifest that exports eleven functions' {
        $m = Test-ModuleManifest (Join-Path $script:Src 'PbiPipelines' 'PbiPipelines.psd1')
        $m.ExportedFunctions.Count | Should -Be 11
    }
    It 'lists five rules' { @((Get-PbiPipelineRule).Keys) | Should -Be @('PD001', 'PD002', 'PD003', 'PD004', 'PD005') }
    It 'Invoke-PipelineRelease.ps1 parses' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $script:Src 'Invoke-PipelineRelease.ps1'), [ref]$null, [ref]$errors) | Out-Null
        $errors | Should -BeNullOrEmpty
    }
}

Describe 'reading a pipeline' {
    BeforeEach { Mock Invoke-PowerBIRestMethod -ModuleName PbiPipelines { Get-PbiRoute $Url $Method $Body } }
    It 'finds a pipeline by name' { (Get-PbiPipeline -Name 'Contoso Sales (Lab)').Id | Should -Be $script:PipeId }
    It 'throws for an unknown name' { { Get-PbiPipeline -Name 'Nope' } | Should -Throw '*found 0*' }
    It 'lists stages; a stage without a workspace has no WorkspaceId' {
        $s = @(Get-PbiPipelineStage -PipelineId $script:PipeId)
        $s.Count | Should -Be 3
        $s[0].WorkspaceName | Should -Be 'Contoso Sales (Lab) - Dev'
        $s[2].WorkspaceId | Should -BeNullOrEmpty
    }
    It 'flattens the items and reads both name properties' {
        $i = @(Get-PbiStageItem -PipelineId $script:PipeId -StageOrder 1)
        $i.Count | Should -Be 4
        ($i | Where-Object Type -eq 'Dataflow').Name | Should -Be 'Prep'
        ($i | Where-Object Type -eq 'SemanticModel').SourceId | Should -Be $script:D.model0
    }
}

Describe 'Compare-PbiStage' {
    BeforeEach {
        Mock Invoke-PowerBIRestMethod -ModuleName PbiPipelines { Get-PbiRoute $Url $Method $Body }
        $script:Cmp = @(Compare-PbiStage -PipelineId $script:PipeId -SourceStage 0 -TargetStage 1)
    }
    It 'pairs by the link the service keeps, not by name' {
        $paired = @($script:Cmp | Where-Object Status -eq 'Paired')
        $paired.Count | Should -Be 2
        ($paired | Where-Object Type -eq 'Report').Renamed | Should -BeTrue
        ($paired | Where-Object Type -eq 'Report').Target | Should -Be 'ContosoSales (renamed in test)'
    }
    It 'flags items that exist only in the source (new on deploy)' {
        @($script:Cmp | Where-Object Status -eq 'OnlyInSource').Source | Should -Contain 'Executive'
    }
    It 'flags a same-name item that is not paired as new in the source AND only in the target' {
        @($script:Cmp | Where-Object { $_.Status -eq 'OnlyInSource' -and $_.Source -eq 'Store managers' }).Count | Should -Be 1
        @($script:Cmp | Where-Object { $_.Status -eq 'OnlyInTarget' -and $_.Target -eq 'Store managers' }).Count | Should -Be 1
    }
}

Describe 'Test-PbiDeployment' {
    BeforeEach { Mock Invoke-PowerBIRestMethod -ModuleName PbiPipelines { Get-PbiRoute $Url $Method $Body } }
    It 'PD001: a new report whose model is neither selected nor paired in the target' {
        # drop the pairing of the model by pretending only the unpaired new report is selected and the model is unknown to the target
        Mock Invoke-PowerBIRestMethod -ModuleName PbiPipelines {
            if ($Url -like '*/stages/1/artifacts') { return '{ "datasets": [], "reports": [], "dashboards": [] }' }
            Get-PbiRoute $Url $Method $Body
        }
        $f = @(Test-PbiDeployment -PipelineId $script:PipeId -SourceStage 0 -TargetStage 1 -ItemId $script:D.rep1 -ReportModel @{ $script:D.rep1 = $script:D.model0 })
        ($f | Where-Object Rule -eq 'PD001').Severity | Should -Be 'Error'
    }
    It 'no PD001 when the model is paired in the target already' {
        $f = @(Test-PbiDeployment -PipelineId $script:PipeId -SourceStage 0 -TargetStage 1 -ItemId $script:D.rep1 -ReportModel @{ $script:D.rep1 = $script:D.model0 })
        @($f | Where-Object Rule -eq 'PD001').Count | Should -Be 0
    }
    It 'PD004: a new report with the name of an unpaired report in the target' {
        $f = @(Test-PbiDeployment -PipelineId $script:PipeId -SourceStage 0 -TargetStage 1 -ItemId $script:D.rep2)
        ($f | Where-Object Rule -eq 'PD004').Message | Should -BeLike "*'Store managers'*"
    }
    It 'PD005: ids that are not in the source stage' {
        $f = @(Test-PbiDeployment -PipelineId $script:PipeId -SourceStage 0 -TargetStage 1 -ItemId '00000000-0000-0000-0000-00000000ffff')
        $f.Rule | Should -Contain 'PD005'
    }
    It 'PD003 info when the target stage has no workspace' {
        $f = @(Test-PbiDeployment -PipelineId $script:PipeId -SourceStage 1 -TargetStage 2)
        ($f | Where-Object Rule -eq 'PD003').Severity | Should -Be 'Info'
    }
}

Describe 'New-PbiDeployRequest' {
    It 'builds Deploy All without ids' {
        $r = New-PbiDeployRequest -PipelineId $script:PipeId -SourceStage 0 -Note 'Release 1'
        $r.Kind | Should -Be 'DeployAll'
        $r.Url | Should -Be "pipelines/$($script:PipeId)/deployAll"
        $r.Body.sourceStageOrder | Should -Be 0
        $r.Body.options.allowOverwriteArtifact | Should -BeTrue
        $r.Body.note | Should -Be 'Release 1'
        $r.Body.Contains('datasets') | Should -BeFalse
    }
    It 'builds Selective Deploy with the ids and a new workspace' {
        $r = New-PbiDeployRequest -PipelineId $script:PipeId -SourceStage 1 -SemanticModelId $script:D.model0 -ReportId $script:D.rep1 -NewWorkspaceName 'Contoso Sales (Lab) - Prod'
        $r.Kind | Should -Be 'SelectiveDeploy'
        $r.Url | Should -BeLike '*/Deploy'
        $r.Body.datasets[0].sourceId | Should -Be $script:D.model0
        $r.Body.reports[0].sourceId | Should -Be $script:D.rep1
        $r.Body.newWorkspace.name | Should -Be 'Contoso Sales (Lab) - Prod'
    }
    It 'can forbid overwrite, and marks a backward deployment' {
        $r = New-PbiDeployRequest -PipelineId $script:PipeId -SourceStage 2 -Backward -NoOverwrite
        $r.Body.options.allowOverwriteArtifact | Should -BeFalse
        $r.Body.isBackwardDeployment | Should -BeTrue
    }
    It 'rejects a note over 1024 characters' {
        { New-PbiDeployRequest -PipelineId $script:PipeId -SourceStage 0 -Note ('x' * 1025) } | Should -Throw '*1024*'
    }
    It 'rejects a stage order out of range' {
        { New-PbiDeployRequest -PipelineId $script:PipeId -SourceStage 12 } | Should -Throw
    }
}

Describe 'deploying' {
    BeforeEach {
        $global:PbiTest.Calls = @()
        $global:PbiTest.Statuses = @()
        Mock Invoke-PowerBIRestMethod -ModuleName PbiPipelines { Get-PbiRoute $Url $Method $Body }
    }
    It '-WhatIf sends nothing' {
        $r = Invoke-PbiPipelineDeploy -PipelineId $script:PipeId -SourceStage 0 -WhatIf
        $r.Kind | Should -Be 'DeployAll'
        @($global:PbiTest.Calls | Where-Object { $_[0] -eq 'Post' }).Count | Should -Be 0
    }
    It 'posts the body, waits through NotStarted and Executing, returns the finished operation' {
        $global:PbiTest.Statuses = @('NotStarted', 'Executing', 'Running', 'Succeeded')
        Mock Invoke-PowerBIRestMethod -ModuleName PbiPipelines {
            if ($Url -like '*/deployAll') { $global:PbiTest.Calls += , @($Method, $Url, $Body); return (Get-PbiFixture 'deploy-response.json') -replace 'c1', 'c3' }
            Get-PbiRoute $Url $Method $Body
        }
        $op = Invoke-PbiPipelineDeploy -PipelineId $script:PipeId -SourceStage 0 -Note 'Release 1' -PollSeconds 0 -Confirm:$false
        $op.status | Should -Be 'Succeeded'
        $post = @($global:PbiTest.Calls | Where-Object { $_[0] -eq 'Post' })
        $post.Count | Should -Be 1
        ($post[0][2] | ConvertFrom-Json).note | Should -Be 'Release 1'
        @($global:PbiTest.Calls | Where-Object { $_[1] -like '*/operations/*' }).Count | Should -Be 4
    }
    It 'throws with the failed step when the operation fails' {
        { Wait-PbiPipelineOperation -PipelineId $script:PipeId -OperationId '00000000-0000-0000-0000-0000000000c2' -PollSeconds 0 } |
            Should -Throw '*Store managers: DuplicateName*'
    }
    It 'throws on a status it does not know' {
        $global:PbiTest.Statuses = @('Paused')
        { Wait-PbiPipelineOperation -PipelineId $script:PipeId -OperationId '00000000-0000-0000-0000-0000000000c3' -PollSeconds 0 } | Should -Throw '*Unknown*'
    }
    It 'times out' {
        $global:PbiTest.Statuses = @('Executing') * 50
        { Wait-PbiPipelineOperation -PipelineId $script:PipeId -OperationId '00000000-0000-0000-0000-0000000000c3' -PollSeconds 0 -TimeoutSeconds -1 } | Should -Throw '*still*'
    }
    It 'reads the deployment history' {
        $h = @(Get-PbiDeploymentHistory -PipelineId $script:PipeId)
        $h[0].From | Should -Be 0
        $h[0].To | Should -Be 1
        $h[0].New | Should -Be 2
        $h[0].Note | Should -Be 'Release 1'
    }
    It 'Start-PbiStageRefresh posts to the refreshes collection of the target workspace, -WhatIf sends nothing' {
        Start-PbiStageRefresh -WorkspaceId '00000000-0000-0000-0000-0000000000b1' -SemanticModelId $script:D.model0 -WhatIf
        @($global:PbiTest.Calls | Where-Object { $_[0] -eq 'Post' }).Count | Should -Be 0
        Start-PbiStageRefresh -WorkspaceId '00000000-0000-0000-0000-0000000000b1' -SemanticModelId $script:D.model0
        @($global:PbiTest.Calls | Where-Object { $_[0] -eq 'Post' })[0][1] | Should -Be "groups/00000000-0000-0000-0000-0000000000b1/datasets/$($script:D.model0)/refreshes"
    }
}

Describe 'Invoke-PipelineRelease.ps1' {
    BeforeEach {
        $global:PbiTest.Calls = @()
        Mock Invoke-PowerBIRestMethod -ModuleName PbiPipelines { Get-PbiRoute $Url $Method $Body }
        Mock Invoke-PowerBIRestMethod { Get-PbiRoute $Url $Method $Body }
        $script:Script = Join-Path $script:Src 'Invoke-PipelineRelease.ps1'
    }
    It '-WhatIf compares, checks, prints the request and sends no POST' {
        $out = & $script:Script -PipelineName 'Contoso Sales (Lab)' -From 0 -Note 'Release 1' -WhatIf 6>&1 | Out-String
        $out | Should -BeLike '*stage 0 (Contoso Sales (Lab) - Dev) -> stage 1 (Contoso Sales (Lab) - Test)*'
        $out | Should -BeLike '*WhatIf: pipelines/*/Deploy*'
        $out | Should -BeLike '*"datasets":[[]{"sourceId":"00000000-0000-0000-0000-00000000d001"}*'
        @($global:PbiTest.Calls | Where-Object { $_[0] -eq 'Post' }).Count | Should -Be 0
    }
    It 'refuses when the model is not in the source stage' {
        { & $script:Script -PipelineName 'Contoso Sales (Lab)' -From 0 -ModelName 'Nope' -WhatIf } | Should -Throw "*'Nope' is not in stage 0*"
    }
}
