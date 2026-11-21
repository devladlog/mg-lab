# Pester tests for scripts/Apply-DlpPolicy.ps1 and Export-DlpPolicy.ps1 with stand-in cmdlets.
# The stand-ins exist only here: the demo runs the real Microsoft.PowerApps.Administration.PowerShell cmdlets.
# Run: pwsh -NoProfile -Command "Invoke-Pester tests/DlpScripts.Tests.ps1 -Output Detailed"
BeforeAll {
    $script:Root = Split-Path $PSScriptRoot -Parent
    $script:Apply = Join-Path $Root 'src/scripts/Apply-DlpPolicy.ps1'
    $script:Export = Join-Path $Root 'src/scripts/Export-DlpPolicy.ps1'
    $script:File = Join-Path $Root 'src/policy/it-dev.json'
    function Get-DlpPolicy { }
    function Add-ConnectorsToPolicy { param($PolicyName, $Classification, $Connectors) }
    function Set-DlpPolicy { param($PolicyName, $UpdatedPolicy) }
    function New-Policy($Default = 'General', $Business = @(), $Blocked = @()) {
        $mk = { param($ids) @($ids | ForEach-Object { [pscustomobject]@{ id = "/providers/Microsoft.PowerApps/apis/$_"; name = $_; type = 'providers/Microsoft.PowerApps/apis' } }) }
        [pscustomobject]@{ value = @([pscustomobject]@{
            name = '00000000-0000-0000-0000-00000000b001'; displayName = 'MG Lab IT DEV'
            defaultConnectorsClassification = $Default
            connectorGroups = @(
                [pscustomobject]@{ classification = 'Confidential'; connectors = (& $mk $Business) },
                [pscustomobject]@{ classification = 'General'; connectors = @() },
                [pscustomobject]@{ classification = 'Blocked'; connectors = (& $mk $Blocked) }) }) }
    }
    $script:AllBusiness = @('shared_sharepointonline', 'shared_office365', 'shared_office365users', 'shared_teams', 'shared_approvals', 'shared_commondataserviceforapps')
}
Describe 'Apply-DlpPolicy' {
    It 'does nothing when the policy already matches' {
        Mock Get-DlpPolicy { New-Policy -Business $AllBusiness }
        Mock Add-ConnectorsToPolicy { }
        Mock Set-DlpPolicy { }
        $out = & $Apply -PolicyFile $File
        Should -Invoke Add-ConnectorsToPolicy -Times 0 -Exactly
        Should -Invoke Set-DlpPolicy -Times 0 -Exactly
        ($out -join "`n") | Should -Match 'Nothing to change'
    }
    It 'moves only the connectors that differ, one call per group' {
        Mock Get-DlpPolicy { New-Policy -Business @('shared_sharepointonline', 'shared_office365') }   # 4 of 6 missing
        Mock Add-ConnectorsToPolicy { }
        $out = & $Apply -PolicyFile $File
        Should -Invoke Add-ConnectorsToPolicy -Times 1 -Exactly -ParameterFilter {
            $Classification -eq 'Confidential' -and $PolicyName -eq '00000000-0000-0000-0000-00000000b001' -and $Connectors.Count -eq 4 }
        ($out | Where-Object { $_ -like 'MOVE*' }).Count | Should -Be 4
        ($out -join "`n") | Should -Match 'MOVE\s+Approvals\s+General -> Confidential'
    }
    It 'treats a connector that is not listed as being in the default group (Get-DlpPolicy does not return those)' {
        $f = Join-Path $TestDrive 'nodefault.json'     # no defaultConnectorsClassification: leave the default alone
        '{"displayName":"MG Lab IT DEV","connectorGroups":[{"classification":"Confidential","connectors":[{"id":"shared_sharepointonline"},{"id":"shared_office365"}]}]}' | Set-Content $f
        Mock Get-DlpPolicy { New-Policy -Default 'Confidential' -Business @() }          # everything is Business by default
        Mock Add-ConnectorsToPolicy { }
        Mock Set-DlpPolicy { }
        & $Apply -PolicyFile $f | Out-Null
        Should -Invoke Add-ConnectorsToPolicy -Times 0 -Exactly                         # already Business, by default
        Should -Invoke Set-DlpPolicy -Times 0 -Exactly
    }
    It 'with -WhatIf prints the plan and changes nothing' {
        Mock Get-DlpPolicy { New-Policy }
        Mock Add-ConnectorsToPolicy { }
        Mock Set-DlpPolicy { }
        $out = & $Apply -PolicyFile $File -WhatIf
        Should -Invoke Add-ConnectorsToPolicy -Times 0 -Exactly
        Should -Invoke Set-DlpPolicy -Times 0 -Exactly
        ($out | Where-Object { $_ -like 'MOVE*' }).Count | Should -Be 6
    }
    It 'sets a different default group first, then reads the policy again before moving connectors' {
        $f = Join-Path $TestDrive 'p.json'
        '{"displayName":"MG Lab IT DEV","defaultConnectorsClassification":"Blocked","connectorGroups":[{"classification":"Blocked","connectors":[{"id":"shared_dropbox","name":"Dropbox"}]}]}' | Set-Content $f
        $global:DlpCalls = 0
        Mock Get-DlpPolicy { $global:DlpCalls++; if ($global:DlpCalls -eq 1) { New-Policy -Default 'General' } else { New-Policy -Default 'Blocked' } }
        Mock Set-DlpPolicy { }
        Mock Add-ConnectorsToPolicy { }
        $out = & $Apply -PolicyFile $f
        Should -Invoke Set-DlpPolicy -Times 1 -Exactly -ParameterFilter { $UpdatedPolicy.defaultConnectorsClassification -eq 'Blocked' }
        Should -Invoke Get-DlpPolicy -Times 2 -Exactly
        Should -Invoke Add-ConnectorsToPolicy -Times 0 -Exactly       # Dropbox is Blocked by default now: nothing to move
        ($out -join "`n") | Should -Match 'DEFAULT\s+General -> Blocked'
    }
    It 'passes name and type of each connector to Add-ConnectorsToPolicy' {
        Mock Get-DlpPolicy { New-Policy -Business @('shared_office365', 'shared_office365users', 'shared_teams', 'shared_approvals', 'shared_commondataserviceforapps') }
        Mock Add-ConnectorsToPolicy { }
        & $Apply -PolicyFile $File | Out-Null
        Should -Invoke Add-ConnectorsToPolicy -Times 1 -Exactly -ParameterFilter {
            $Connectors[0].name -eq 'SharePoint' -and $Connectors[0].type -eq 'providers/Microsoft.PowerApps/apis' -and $Connectors[0].id -like '*/shared_sharepointonline' }
    }
    It 'stops when the policy does not exist' {
        Mock Get-DlpPolicy { [pscustomobject]@{ value = @() } }
        { & $Apply -PolicyFile $File } | Should -Throw "*No data policy named 'MG Lab IT DEV'*Create it in the admin center first*"
    }
    It 'refuses an unknown classification before it calls the service' {
        $f = Join-Path $TestDrive 'bad.json'
        '{"displayName":"x","connectorGroups":[{"classification":"Business","connectors":[]}]}' | Set-Content $f
        Mock Get-DlpPolicy { throw 'must not be called' }
        { & $Apply -PolicyFile $f } | Should -Throw "*Unknown classification 'Business'*"
    }
    It 'refuses a connector listed in two groups' {
        $f = Join-Path $TestDrive 'dup.json'
        '{"displayName":"x","connectorGroups":[{"classification":"Blocked","connectors":[{"id":"shared_a"}]},{"classification":"General","connectors":[{"id":"/providers/Microsoft.PowerApps/apis/shared_A"}]}]}' | Set-Content $f
        { & $Apply -PolicyFile $f } | Should -Throw '*two groups*'
    }
}
Describe 'Export-DlpPolicy' {
    It 'writes {value: [...]} with the scope we add' {
        Mock Get-DlpPolicy { New-Policy -Business $AllBusiness }
        $out = Join-Path $TestDrive 'exported.json'
        & $Export -OutFile $out -ScopeMode only -ScopeEnvironments dev | Out-Null
        $j = Get-Content -Raw $out | ConvertFrom-Json
        $j.value.Count | Should -Be 1
        $j.value[0].displayName | Should -Be 'MG Lab IT DEV'
        $j.value[0].scope.mode | Should -Be 'only'
        @($j.value[0].scope.environments) | Should -Be @('dev')
        ($j.value[0].connectorGroups | Where-Object classification -eq 'Confidential').connectors.Count | Should -Be 6
    }
    It 'filters by display name and fails when nothing matches' {
        Mock Get-DlpPolicy { New-Policy }
        { & $Export -OutFile (Join-Path $TestDrive 'x.json') -DisplayName 'nope' } | Should -Throw "*named 'nope'*"
    }
}
