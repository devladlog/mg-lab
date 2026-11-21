# The News Requests list (site script), the contract and the approval flow must agree on names and statuses.
BeforeAll {
    $script:Root = Join-Path $PSScriptRoot '..'
    $script:Contract = Get-Content (Join-Path $script:Root 'contract' 'intranet.json') -Raw | ConvertFrom-Json -Depth 20
    $script:FlowText = Get-Content (Join-Path $script:Root 'flow' 'news-approval.definition.json') -Raw
    $script:Flow = $script:FlowText | ConvertFrom-Json -Depth 50
    function Get-Actions($actions) {
        foreach ($p in $actions.PSObject.Properties) {
            $p.Value
            if ($p.Value.PSObject.Properties['actions']) { Get-Actions $p.Value.actions }
            if ($p.Value.PSObject.Properties['else']) { Get-Actions $p.Value.else.actions }
        }
    }
    $script:All = @(Get-Actions $script:Flow.actions)
}

Describe 'News approval flow' {
    It 'uses standard connectors only (SharePoint, Approvals): no premium licence for requesters or approvers' {
        $apis = @($script:FlowText | Select-String -Pattern '/providers/Microsoft\.PowerApps/apis/(shared_\w+)' -AllMatches).Matches | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
        $apis | Should -Be @('shared_approvals', 'shared_sharepointonline')
    }
    It 'every runAfter points at an action that exists' {
        $names = @($script:Flow.actions.PSObject.Properties.Name)
        foreach ($a in $script:Flow.actions.PSObject.Properties.Value) {
            foreach ($dep in $a.runAfter.PSObject.Properties.Name) { $names | Should -Contain $dep }
        }
    }
    It 'every column it reads or writes exists in the contract (or is a SharePoint built-in)' {
        $builtIn = @('ID', 'Title', 'Author', '{Link}')
        $names = [regex]::Matches($script:FlowText, "(?:body|item)/([A-Za-z{}]+)") | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique |
            Where-Object { $_ -notin @('value', 'outcome', 'responses') }
        foreach ($n in $names) { ($builtIn + $script:Contract.newsRequests.columns) | Should -Contain $n }
    }
    It 'writes only statuses that are choices of the status column, once each' {
        $written = [regex]::Matches($script:FlowText, "item/$($script:Contract.newsRequests.statusColumn)/Value"": ""([^""]+)""") | ForEach-Object { $_.Groups[1].Value }
        $written | Should -Be @('Approved', 'Rejected')
        foreach ($s in $written) { $script:Contract.newsRequests.statuses | Should -Contain $s }
    }
    It 'asks for approval before it changes any item, and handles both outcomes' {
        $script:Flow.actions.Condition_approved.runAfter.Start_and_wait_for_an_approval | Should -Contain 'Succeeded'
        @($script:Flow.actions.Condition_approved.actions.PSObject.Properties.Name) | Should -Be @('Set_status_Approved')
        @($script:Flow.actions.Condition_approved.else.actions.PSObject.Properties.Name) | Should -Be @('Set_status_Rejected')
    }
    It 'points at the hub site and the News Requests list through parameters, not hard-coded values' {
        $script:FlowText | Should -Not -Match 'sharepoint\.com/sites/(?!contoso-home)'
        ($script:All | Where-Object { $_.inputs.parameters.table }).inputs.parameters.table | Select-Object -Unique | Should -Be "@parameters('News Requests list (mgl_NewsRequestsList)')"
    }
    It 'has no real address or tenant in it' {
        $script:FlowText | Should -Not -Match 'devladlog'
        $script:FlowText | Should -Match 'comms@contoso\.example'
    }
}
