# Pester 5: the script is run for real; only Invoke-RestMethod is mocked (no tenant, no network).
BeforeAll {
    $script:ps1 = Join-Path $PSScriptRoot '..' 'src' 'scripts' 'Set-BpfStage.ps1'
    $script:org = 'https://contoso.crm4.dynamics.com'
    $script:id = '00000000-0000-0000-0000-0000000000b1'
    $script:s = 1..5 | ForEach-Object { '00000000-0000-0000-0000-0000000000a{0}' -f $_ }
}
Describe 'Set-BpfStage.ps1' {
    BeforeEach { $env:DATAVERSE_TOKEN = 'test-token' }
    AfterAll { Remove-Item Env:DATAVERSE_TOKEN -ErrorAction SilentlyContinue }

    It 'refuses to run without a token' {
        Remove-Item Env:DATAVERSE_TOKEN
        { & $ps1 -OrgUrl $org -Operation ListInstances -BpfTable x } | Should -Throw '*DATAVERSE_TOKEN*'
    }
    It 'rejects an instance id that is not a GUID' {
        { & $ps1 -OrgUrl $org -Operation Abort -BpfTable x -InstanceId 'abc' } | Should -Throw '*not a GUID*'
    }
    It 'Next: reads the active path and patches activestageid and traversedpath' {
        Mock Invoke-RestMethod {
            if ($Method -eq 'GET' -and $Uri -like '*RetrieveActivePath*') {
                return [pscustomobject]@{ value = @($s[0..4] | ForEach-Object { [pscustomobject]@{ processstageid = $_ } }) }
            }
            if ($Method -eq 'GET') {
                return [pscustomobject]@{ _activestageid_value = $s[1]; traversedpath = "$($s[0]),$($s[1])"; statecode = 0 }
            }
        }
        $r = & $ps1 -OrgUrl $org -Operation Next -BpfTable cts_purchaserequestprocesses -InstanceId $id
        $r['activestageid@odata.bind'] | Should -Be "/processstages($($s[2]))"
        $r.traversedpath | Should -Be "$($s[0]),$($s[1]),$($s[2])"
        Should -Invoke Invoke-RestMethod -ParameterFilter { $Method -eq 'PATCH' -and $Uri -like "*cts_purchaserequestprocesses($id)" } -Exactly 1
        Should -Invoke Invoke-RestMethod -ParameterFilter { $Uri -like "*RetrieveActivePath(ProcessInstanceId=$id)" } -Exactly 1
    }
    It 'Next with -WhatIf sends no PATCH' {
        Mock Invoke-RestMethod {
            if ($Uri -like '*RetrieveActivePath*') { return [pscustomobject]@{ value = @($s[0..1] | ForEach-Object { [pscustomobject]@{ processstageid = $_ } }) } }
            [pscustomobject]@{ _activestageid_value = $s[0]; traversedpath = $s[0]; statecode = 0 }
        }
        & $ps1 -OrgUrl $org -Operation Next -BpfTable t -InstanceId $id -WhatIf | Out-Null
        Should -Invoke Invoke-RestMethod -ParameterFilter { $Method -eq 'PATCH' } -Exactly 0
    }
    It 'Next on the last stage tells you to finish' {
        Mock Invoke-RestMethod {
            if ($Uri -like '*RetrieveActivePath*') { return [pscustomobject]@{ value = @($s[3..4] | ForEach-Object { [pscustomobject]@{ processstageid = $_ } }) } }
            [pscustomobject]@{ _activestageid_value = $s[4]; traversedpath = ($s -join ','); statecode = 0 }
        }
        { & $ps1 -OrgUrl $org -Operation Next -BpfTable t -InstanceId $id } | Should -Throw '*Finish*'
    }
    It 'Previous drops the active stage from traversedpath' {
        Mock Invoke-RestMethod {
            if ($Method -eq 'GET') { return [pscustomobject]@{ _activestageid_value = $s[2]; traversedpath = ($s[0..2] -join ','); statecode = 0 } }
        }
        $r = & $ps1 -OrgUrl $org -Operation Previous -BpfTable t -InstanceId $id
        $r['activestageid@odata.bind'] | Should -Be "/processstages($($s[1]))"
        $r.traversedpath | Should -Be "$($s[0]),$($s[1])"
    }
    It 'does not move an aborted instance' {
        Mock Invoke-RestMethod { [pscustomobject]@{ _activestageid_value = $s[0]; traversedpath = $s[0]; statecode = 1 } }
        { & $ps1 -OrgUrl $org -Operation Next -BpfTable t -InstanceId $id } | Should -Throw '*not active*'
    }
    It 'Abort / Reactivate / Finish send the documented statecode and statuscode' -ForEach @(
        @{ op = 'Abort'; sc = 1; st = 3 }, @{ op = 'Reactivate'; sc = 0; st = 1 }, @{ op = 'Finish'; sc = 0; st = 2 }) {
        Mock Invoke-RestMethod { }
        $r = & $ps1 -OrgUrl $org -Operation $op -BpfTable t -InstanceId $id
        $r.statecode | Should -Be $sc
        $r.statuscode | Should -Be $st
        Should -Invoke Invoke-RestMethod -ParameterFilter { $Method -eq 'PATCH' -and ($Body | ConvertFrom-Json).statuscode -eq $st } -Exactly 1
    }
    It 'ListStages filters by the definition id' {
        Mock Invoke-RestMethod { [pscustomobject]@{ value = @([pscustomobject]@{ stagename = 'Submit' }) } }
        (& $ps1 -OrgUrl $org -Operation ListStages -DefinitionId $id).stagename | Should -Be 'Submit'
        Should -Invoke Invoke-RestMethod -ParameterFilter { $Uri -like "*processstages?*processid/workflowid eq $id" }
    }
}
