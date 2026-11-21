BeforeAll {
    . (Join-Path $PSScriptRoot '..' 'src' 'scripts' 'Get-FabricCopilotCapacity.ps1')
}

Describe 'Get-CopilotSkuVerdict' {
    It 'accepts <sku>' -ForEach @(
        @{ sku = 'F2' }, @{ sku = 'F64' }, @{ sku = 'P1' }, @{ sku = 'P5' }
    ) {
        (Get-CopilotSkuVerdict -Sku $sku -State 'Active').CopilotCapable | Should -BeTrue
    }
    It 'rejects <sku>' -ForEach @(
        @{ sku = 'F1' }, @{ sku = 'A4' }, @{ sku = 'EM1' }, @{ sku = 'FT1' }, @{ sku = 'Trial' }
    ) {
        (Get-CopilotSkuVerdict -Sku $sku -State 'Active').CopilotCapable | Should -BeFalse
    }
    It 'rejects a paused capacity even when the SKU is fine' {
        $v = Get-CopilotSkuVerdict -Sku 'F2' -State 'Inactive'
        $v.CopilotCapable | Should -BeFalse
        $v.Reason | Should -Match 'Inactive'
    }
    It 'says why a workspace without a capacity cannot use Copilot' {
        (Get-CopilotSkuVerdict -Sku '').Reason | Should -Match 'Fabric Copilot capacity'
    }
}

Describe 'Get-FabricCopilotReport' {
    BeforeAll {
        $zero = '00000000-0000-0000-0000-000000000000'
        $script:capPage1 = [pscustomobject]@{ value = @([pscustomobject]@{ id = 'c1'; displayName = 'cap-f2'; sku = 'F2'; region = 'West Europe'; state = 'Active' }); continuationToken = 'tok1' }
        $script:capPage2 = [pscustomobject]@{ value = @([pscustomobject]@{ id = 'c2'; displayName = 'cap-trial'; sku = 'FT1'; region = 'West Europe'; state = 'Active' }) }
        $script:ws = [pscustomobject]@{ value = @(
            [pscustomobject]@{ id = $zero; displayName = 'My workspace'; type = 'Personal' },
            [pscustomobject]@{ id = 'w1'; displayName = 'Contoso Sales'; type = 'Workspace'; capacityId = 'c1' },
            [pscustomobject]@{ id = 'w2'; displayName = 'Contoso Lab'; type = 'Workspace'; capacityId = 'c2' },
            [pscustomobject]@{ id = 'w3'; displayName = 'Contoso Pro'; type = 'Workspace' },
            [pscustomobject]@{ id = 'w4'; displayName = 'Elsewhere'; type = 'Workspace'; capacityId = 'c9'; capacityRegion = 'East US' }
        ) }
        $script:calls = [System.Collections.Generic.List[string]]::new()
        Mock Invoke-RestMethod {
            $script:calls.Add([string]$Uri)
            if ($Uri -like '*continuationToken=tok1') { return $script:capPage2 }
            if ($Uri -like '*/capacities*') { return $script:capPage1 }
            if ($Uri -like '*/workspaces*') { return $script:ws }
            throw "unexpected $Uri"
        }
        $script:report = @(Get-FabricCopilotReport -BaseUri 'https://example.invalid/v1' -Headers @{ Authorization = 'Bearer x' })
    }
    It 'follows the continuation token for capacities' {
        @($script:calls | Where-Object { $_ -like '*/capacities?continuationToken=tok1' }).Count | Should -Be 1
    }
    It 'skips personal workspaces' {
        $script:report.Workspace | Should -Not -Contain 'My workspace'
        $script:report.Count | Should -Be 4
    }
    It 'marks the F2 workspace capable and the trial workspace not' {
        ($script:report | Where-Object Workspace -eq 'Contoso Sales').CopilotCapable | Should -BeTrue
        $t = $script:report | Where-Object Workspace -eq 'Contoso Lab'
        $t.CopilotCapable | Should -BeFalse
        $t.Reason | Should -Match 'Trial'
    }
    It 'handles a workspace with no capacity and one whose capacity is not visible' {
        ($script:report | Where-Object Workspace -eq 'Contoso Pro').Reason | Should -Match 'No capacity'
        $e = $script:report | Where-Object Workspace -eq 'Elsewhere'
        $e.CopilotCapable | Should -BeFalse
        $e.Region | Should -Be 'East US'
    }
}
