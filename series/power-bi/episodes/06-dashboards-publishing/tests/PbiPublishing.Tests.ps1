# Pester 5+: publishing checks and dashboard automation. Invoke-PowerBIRestMethod is mocked with responses shaped
# like the Learn samples (tests/fixtures/rest).
#   pwsh -NoProfile -Command "Invoke-Pester ./tests -Output Detailed"

BeforeAll {
    if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
        # Stand-in so Pester can mock the MicrosoftPowerBIMgmt cmdlet without installing it.
        function global:Invoke-PowerBIRestMethod { param($Url, $Method, $Body) throw 'not mocked' }
    }
    $script:Src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $script:Src 'PbiPublishing' 'PbiPublishing.psd1') -Force
    $script:Fixtures = Join-Path $PSScriptRoot 'fixtures'
    $script:Rest = Join-Path $script:Fixtures 'rest'
    $script:Ep05 = Join-Path $PSScriptRoot '..' '..' '05-row-level-security' 'src'

    function Get-Fixture([string] $name) { Get-Content -Raw (Join-Path $script:Rest $name) }

    # Routes a mocked REST call to the right fixture.
    function Get-RestFixture([string] $Url) {
        switch -Regex ($Url) {
            '/reports$'                 { Get-Fixture 'reports.json'; break }
            '/datasets$'                { Get-Fixture 'datasets.json'; break }
            '/dashboards$'              { Get-Fixture 'dashboards.json'; break }
            '/dashboards/[^/]+b1/tiles$' { Get-Fixture 'tiles-daily.json'; break }
            '/dashboards/[^/]+b2/tiles$' { Get-Fixture 'tiles-old.json'; break }
            default                     { throw "unexpected URL $Url" }
        }
    }
}

Describe 'module' {
    It 'has a valid manifest that exports the five functions' {
        $m = Test-ModuleManifest (Join-Path $script:Src 'PbiPublishing' 'PbiPublishing.psd1')
        @($m.ExportedFunctions.Keys | Sort-Object) | Should -Be @('Copy-PbiDashboard', 'Get-PbiPublishingRule',
            'Get-PbiWorkspaceInventory', 'Test-PbipPublishReadiness', 'Test-PbiWorkspacePublishing')
    }
    It 'lists ten rules' {
        @((Get-PbiPublishingRule).Keys).Count | Should -Be 10
    }
    It 'Invoke-PublishingCheck.ps1 parses' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $script:Src 'Invoke-PublishingCheck.ps1'), [ref]$null, [ref]$errors) | Out-Null
        $errors | Should -BeNullOrEmpty
    }
}

Describe 'Test-PbipPublishReadiness' {
    It 'flags the episode 5 project: local files, a local path parameter, RLS roles' -Skip:(-not (Test-Path (Join-Path $PSScriptRoot '..' '..' '05-row-level-security' 'src'))) {
        $f = @(Test-PbipPublishReadiness -Path $script:Ep05)
        ($f.Rule | Sort-Object) | Should -Be @('PUB001', 'PUB002', 'PUB003')
        ($f | Where-Object Rule -eq PUB001).Message | Should -Match '^6 table\(s\) read local files with File\.Contents'
        ($f | Where-Object Rule -eq PUB001).Message | Should -Match 'Store Access'
        ($f | Where-Object Rule -eq PUB003).Message | Should -Match 'Head Office, Store Managers'
    }
    It 'is silent for a cloud source without roles' {
        @(Test-PbipPublishReadiness -Path (Join-Path $script:Fixtures 'cloud-project')) | Should -BeNullOrEmpty
    }
    It 'is silent for a report with a live connection' {
        @(Test-PbipPublishReadiness -Path (Join-Path $script:Fixtures 'live-connection')) | Should -BeNullOrEmpty
    }
    It 'errors when the report points to a missing semantic model folder' {
        $f = @(Test-PbipPublishReadiness -Path (Join-Path $script:Fixtures 'broken-reference'))
        $f.Rule | Should -Be 'PUB004'
        $f.Severity | Should -Be 'Error'
    }
    It 'throws when there is no pbip file' {
        { Test-PbipPublishReadiness -Path $script:Rest } | Should -Throw '*no .pbip*'
    }
}

Describe 'Get-PbiWorkspaceInventory' {
    BeforeEach {
        Mock -ModuleName PbiPublishing Invoke-PowerBIRestMethod { Get-RestFixture $Url }
    }
    It 'reads reports, semantic models, dashboards and each dashboard''s tiles' {
        $inv = Get-PbiWorkspaceInventory -WorkspaceId 'ws'
        $inv.Reports.Count | Should -Be 1
        $inv.Datasets.Count | Should -Be 1
        $inv.Dashboards.Name | Should -Be @('Contoso Bikes - Daily', 'Old dashboard')
        $inv.Dashboards[0].Tiles.Count | Should -Be 6
        Should -Invoke -ModuleName PbiPublishing Invoke-PowerBIRestMethod -Times 5 -Exactly -ParameterFilter { $Method -eq 'Get' }
    }
    It 'only uses GET (read only)' {
        $null = Get-PbiWorkspaceInventory -WorkspaceId 'ws'
        Should -Invoke -ModuleName PbiPublishing Invoke-PowerBIRestMethod -Times 0 -ParameterFilter { $Method -ne 'Get' }
    }
}

Describe 'Test-PbiWorkspacePublishing' {
    BeforeAll {
        Mock -ModuleName PbiPublishing Invoke-PowerBIRestMethod { Get-RestFixture $Url }
        $script:Findings = @(Get-PbiWorkspaceInventory -WorkspaceId 'ws' | Test-PbiWorkspacePublishing)
    }
    It 'finds the tile whose report is gone' {
        $e = @($script:Findings | Where-Object Rule -eq 'WS001')
        $e.Count | Should -Be 1
        $e[0].Severity | Should -Be 'Error'
        $e[0].Message | Should -Match "'Old dashboard', tile 'Sales by store'"
    }
    It 'warns about the untitled tile (titles set in the report before pinning are not returned)' {
        $w = @($script:Findings | Where-Object Rule -eq 'WS002')
        $w.Count | Should -Be 1
        $w[0].Message | Should -Match "'Contoso Bikes - Daily', tile #6"
    }
    It 'flags gateway, RLS and no refresh on the semantic model' {
        ($script:Findings | Where-Object Rule -in 'WS003', 'WS004', 'WS006').Rule | Sort-Object | Should -Be @('WS003', 'WS004', 'WS006')
    }
    It 'does not flag an image tile without a report' {
        $script:Findings.Message | Should -Not -Match 'Team photo'
    }
    It 'applies the tile limit' {
        $inv = Get-PbiWorkspaceInventory -WorkspaceId 'ws'
        @($inv | Test-PbiWorkspacePublishing -MaxTiles 5 | Where-Object Rule -eq 'WS005').Count | Should -Be 1
        @($inv | Test-PbiWorkspacePublishing -MaxTiles 6 | Where-Object Rule -eq 'WS005').Count | Should -Be 0
    }
    It 'never prints IDs or e-mail addresses' {
        ($script:Findings | Format-Table -Wrap | Out-String -Width 300) | Should -Not -Match '0000-0000|@contoso'
    }
}

Describe 'Copy-PbiDashboard' {
    BeforeEach {
        $script:Calls = [System.Collections.Generic.List[object]]::new()
        Mock -ModuleName PbiPublishing Invoke-PowerBIRestMethod {
            $script:Calls.Add([pscustomobject]@{ Method = $Method; Url = $Url; Body = $Body })
            if ($Method -eq 'Post' -and $Url -match '/dashboards$') {
                '{"id":"00000000-0000-0000-0000-0000000000c1","displayName":"' + ($Body | ConvertFrom-Json).name + '","isReadOnly":false}'
            }
            elseif ($Method -eq 'Post') { '{"id":"00000000-0000-0000-0000-000000000301","title":"x"}' }
            else { Get-RestFixture $Url }
        }
    }
    It 'creates the dashboard, then clones every tile into it at the end (Tail)' {
        $r = Copy-PbiDashboard -WorkspaceId 'ws' -DashboardId '00000000-0000-0000-0000-0000000000b1' -NewName 'Contoso Bikes - Store managers'
        $r.Dashboard | Should -Be 'Contoso Bikes - Store managers'
        $r.Tiles | Should -Be 6
        $r.SameWorkspace | Should -BeTrue
        $posts = @($script:Calls | Where-Object Method -eq 'Post')
        $posts[0].Url | Should -Be 'groups/ws/dashboards'
        ($posts[0].Body | ConvertFrom-Json).name | Should -Be 'Contoso Bikes - Store managers'
        $posts.Count | Should -Be 7
        foreach ($p in $posts | Select-Object -Skip 1) {
            $p.Url | Should -Match '^groups/ws/dashboards/[0-9a-f-]+b1/tiles/[0-9a-f-]+/Clone$'
            $b = $p.Body | ConvertFrom-Json
            $b.targetDashboardId | Should -Be '00000000-0000-0000-0000-0000000000c1'
            $b.positionConflictAction | Should -Be 'Tail'
            $b.PSObject.Properties.Name | Should -Not -Contain 'targetReportId'     # same workspace: links are kept
        }
    }
    It 'rebinds report and semantic model when cloning to another workspace' {
        $null = Copy-PbiDashboard -WorkspaceId 'ws' -DashboardId '00000000-0000-0000-0000-0000000000b1' -NewName 'Prod' `
            -TargetWorkspaceId 'prod' -TargetReportId 'r2' -TargetDatasetId 'd2'
        $posts = @($script:Calls | Where-Object Method -eq 'Post')
        $posts[0].Url | Should -Be 'groups/prod/dashboards'
        $b = $posts[1].Body | ConvertFrom-Json
        ($b.targetWorkspaceId, $b.targetReportId, $b.targetModelId) | Should -Be @('prod', 'r2', 'd2')
    }
    It 'refuses another workspace without a target report (the tiles would be broken)' {
        { Copy-PbiDashboard -WorkspaceId 'ws' -DashboardId '00000000-0000-0000-0000-0000000000b1' -NewName 'x' -TargetWorkspaceId 'prod' } |
            Should -Throw '*TargetReportId*'
        @($script:Calls | Where-Object Method -eq 'Post').Count | Should -Be 0
    }
    It 'creates nothing with -WhatIf' {
        $null = Copy-PbiDashboard -WorkspaceId 'ws' -DashboardId '00000000-0000-0000-0000-0000000000b1' -NewName 'x' -WhatIf 6>$null
        @($script:Calls | Where-Object Method -eq 'Post').Count | Should -Be 0
    }
}
