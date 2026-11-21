# Pester 5+: shared-model audit and parameter wiring. Invoke-PowerBIRestMethod is mocked with responses shaped like the
# Learn samples (tests/fixtures/rest).
#   pwsh -NoProfile -Command "Invoke-Pester ./tests -Output Detailed"

BeforeAll {
    if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
        # Stand-in so Pester can mock the MicrosoftPowerBIMgmt cmdlet without installing it.
        function global:Invoke-PowerBIRestMethod { param($Url, $Method, $Body) throw 'not mocked' }
    }
    $script:Src = Join-Path $PSScriptRoot '..' 'src' 'service'
    Import-Module (Join-Path $script:Src 'PbiShared' 'PbiShared.psd1') -Force
    $script:Rest = Join-Path $PSScriptRoot 'fixtures' 'rest'
    $script:DataWs = '00000000-0000-0000-0000-0000000000d1'
    $script:SalesWs = '00000000-0000-0000-0000-0000000000d2'

    function Get-Fixture([string] $name) { Get-Content -Raw (Join-Path $script:Rest $name) }
    function Get-RestFixture([string] $Url) {
        $suffix = if ($Url -like "*$($script:DataWs)*") { 'data' } else { 'sales' }
        switch -Regex ($Url) {
            '/datasets$'                { Get-Fixture "datasets-$suffix.json"; break }
            '/reports$'                 { Get-Fixture "reports-$suffix.json"; break }
            '/dataflows$'               { Get-Fixture "dataflows-$suffix.json"; break }
            '/datasets/upstreamDataflows$' { Get-Fixture "links-$suffix.json"; break }
            default                     { throw "unexpected URL $Url" }
        }
    }
    $script:Workspaces = [ordered]@{ 'Contoso Data (Lab)' = $script:DataWs; 'Contoso Sales (Lab)' = $script:SalesWs }
}

Describe 'module' {
    It 'has a valid manifest that exports four functions' {
        $m = Test-ModuleManifest (Join-Path $script:Src 'PbiShared' 'PbiShared.psd1')
        @($m.ExportedFunctions.Keys | Sort-Object) | Should -Be @('Get-PbiSharedModelInventory', 'Get-PbiSharedModelRule',
            'Set-PbiModelParameter', 'Test-PbiSharedModel')
    }
    It 'lists four rules' {
        @((Get-PbiSharedModelRule).Keys) | Should -Be @('SM001', 'SM002', 'SM003', 'SM004')
    }
    It 'Invoke-SharedModelCheck.ps1 parses' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $script:Src 'Invoke-SharedModelCheck.ps1'), [ref]$null, [ref]$errors) | Out-Null
        $errors | Should -BeNullOrEmpty
    }
}

Describe 'Get-PbiSharedModelInventory' {
    BeforeEach {
        Mock Invoke-PowerBIRestMethod -ModuleName PbiShared { Get-RestFixture $Url }
        $script:Inv = Get-PbiSharedModelInventory -Workspace $script:Workspaces
    }
    It 'reads four endpoints per workspace, read only' {
        Should -Invoke Invoke-PowerBIRestMethod -ModuleName PbiShared -Times 8 -Exactly
        Should -Invoke Invoke-PowerBIRestMethod -ModuleName PbiShared -Times 0 -Exactly -ParameterFilter { $Method -ne 'Get' }
    }
    It 'keeps the names it was given and what each workspace holds' {
        $script:Inv.Workspaces.Name | Should -Be @('Contoso Data (Lab)', 'Contoso Sales (Lab)')
        $script:Inv.Workspaces[0].Dataflows.name | Should -Be 'Contoso Bikes Prep'
        $script:Inv.Workspaces[1].Reports.Count | Should -Be 4
    }
}

Describe 'Test-PbiSharedModel' {
    BeforeAll {
        Mock Invoke-PowerBIRestMethod -ModuleName PbiShared { Get-RestFixture $Url }
        $inv = Get-PbiSharedModelInventory -Workspace $script:Workspaces
        $script:Findings = @($inv | Test-PbiSharedModel -DataWorkspace 'Contoso Data (Lab)')
    }
    It 'SM001: the same model name in two workspaces' {
        $f = $script:Findings | Where-Object Rule -eq SM001
        @($f).Count | Should -Be 1
        $f.Severity | Should -Be Warning
        $f.Message | Should -Match "'ContosoSales' exists in Contoso Data \(Lab\) and Contoso Sales \(Lab\)"
    }
    It 'SM002: thin reports of the shared model, by name and workspace' {
        $f = $script:Findings | Where-Object Rule -eq SM002
        @($f).Count | Should -Be 1
        $f.Message | Should -Match "^'ContosoSales' in Contoso Data \(Lab\) is used by 1 report\(s\) in other workspaces: StoreManagers \(Contoso Sales \(Lab\)\)"
    }
    It 'SM004: a report whose model is nowhere; paginated reports are skipped' {
        $f = @($script:Findings | Where-Object Rule -eq SM004)
        $f.Count | Should -Be 1
        $f[0].Message | Should -Match "^report 'Orphan' in Contoso Sales \(Lab\)"
    }
    It 'SM003 is silent when the data workspace model has an upstream dataflow' {
        @($script:Findings | Where-Object Rule -eq SM003) | Should -BeNullOrEmpty
    }
    It 'SM003 fires when it has none' {
        Mock Invoke-PowerBIRestMethod -ModuleName PbiShared {
            if ($Url -like '*/datasets/upstreamDataflows') { '{ "value": [] }' } else { Get-RestFixture $Url }
        }
        $inv = Get-PbiSharedModelInventory -Workspace $script:Workspaces
        $f = @($inv | Test-PbiSharedModel -DataWorkspace 'Contoso Data (Lab)' | Where-Object Rule -eq SM003)
        $f.Count | Should -Be 1
        $f[0].Message | Should -Be "semantic model 'ContosoSales' in Contoso Data (Lab) has no upstream dataflow: it prepares its own data"
    }
    It 'never prints an ID or an e-mail address' {
        $text = ($script:Findings | ForEach-Object Message) -join "`n"
        $text | Should -Not -Match '[0-9a-f]{8}-[0-9a-f]{4}'
        $text | Should -Not -Match '@'
    }
}

Describe 'Set-PbiModelParameter' {
    BeforeEach {
        Mock Invoke-PowerBIRestMethod -ModuleName PbiShared { '' }
    }
    It 'posts updateDetails to Default.UpdateParameters' {
        $r = Set-PbiModelParameter -WorkspaceId $script:DataWs -DatasetId 'm1' -Parameter @{ WorkspaceId = $script:DataWs; DataflowId = 'df1' }
        Should -Invoke Invoke-PowerBIRestMethod -ModuleName PbiShared -Times 1 -Exactly -ParameterFilter {
            $Method -eq 'Post' -and $Url -eq "groups/$($script:DataWs)/datasets/m1/Default.UpdateParameters" -and
            ($Body | ConvertFrom-Json).updateDetails.Count -eq 2 -and
            (($Body | ConvertFrom-Json).updateDetails | Where-Object name -eq DataflowId).newValue -eq 'df1'
        }
        $r.Updated | Should -Be @('DataflowId', 'WorkspaceId')
        $r.NextStep | Should -Match 'refresh'
    }
    It '-WhatIf calls nothing' {
        Set-PbiModelParameter -WorkspaceId 'w' -DatasetId 'm' -Parameter @{ DataflowId = 'x' } -WhatIf
        Should -Invoke Invoke-PowerBIRestMethod -ModuleName PbiShared -Times 0 -Exactly
    }
    It 'refuses an empty list (Learn: the parameter list can''t be empty)' {
        { Set-PbiModelParameter -WorkspaceId 'w' -DatasetId 'm' -Parameter @{} } | Should -Throw '*empty*'
    }
}
