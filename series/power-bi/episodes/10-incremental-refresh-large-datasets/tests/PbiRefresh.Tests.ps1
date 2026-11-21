# Pester 5+: enhanced refresh module. Invoke-PowerBIRestMethod is mocked with responses shaped like the Learn samples
# (tests/fixtures/rest: zero GUIDs, fictional names).
#   pwsh -NoProfile -Command "Invoke-Pester ./tests -Output Detailed"

BeforeAll {
    if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
        function global:Invoke-PowerBIRestMethod { param($Url, $Method, $Body) throw 'not mocked' }
    }
    $script:Src = Join-Path $PSScriptRoot '..' 'src' 'pipeline'
    Import-Module (Join-Path $script:Src 'PbiRefresh' 'PbiRefresh.psd1') -Force
    $script:WS = '00000000-0000-0000-0000-0000000000a1'
    $script:DS = '00000000-0000-0000-0000-0000000000b1'
    $global:PbiTest = @{ Calls = @(); Poll = @() }
    function global:Get-PbiFixture([string] $name) { Get-Content -Raw (Join-Path $PSScriptRoot 'fixtures' 'rest' $name) }
    function global:Get-PbiRoute([string] $Url, [string] $Method, $Body) {
        $global:PbiTest.Calls += , @($Method, $Url, $Body)
        if ($Method -eq 'Post') { return '' }                      # 202 Accepted: no body
        if ($Method -eq 'Delete') { return '' }
        switch -Regex ($Url) {
            '/refreshes\?\$top=1$' { (Get-PbiFixture 'refreshes-list.json' | ConvertFrom-Json).value[0..0] | ConvertTo-Json -AsArray; break }
            '/refreshes$'          { Get-PbiFixture 'refreshes-list.json'; break }
            '/refreshes/.*f1$'     { Get-PbiFixture 'refresh-completed.json'; break }
            '/refreshes/.*f3$'     { Get-PbiFixture 'refresh-failed.json'; break }
            '/refreshes/.*f2$'     {
                $s = $global:PbiTest.Poll
                $next = if ($s.Count) { $s[0] } else { 'refresh-completed.json' }
                if ($s.Count) { $global:PbiTest.Poll = @($s | Select-Object -Skip 1) }
                Get-PbiFixture $next; break }
            default                { throw "unexpected URL $Url" }
        }
    }
}

Describe 'module' {
    It 'has a valid manifest that exports five functions' {
        (Test-ModuleManifest (Join-Path $script:Src 'PbiRefresh' 'PbiRefresh.psd1')).ExportedFunctions.Count | Should -Be 5
    }
    It 'Invoke-PartitionRefresh.ps1 parses' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $script:Src 'Invoke-PartitionRefresh.ps1'), [ref]$null, [ref]$errors) | Out-Null
        $errors | Should -BeNullOrEmpty
    }
}

Describe 'New-PbiRefreshRequest' {
    It 'builds the URL and a minimal body' {
        $r = New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS
        $r.Url | Should -Be "groups/$script:WS/datasets/$script:DS/refreshes"
        ($r.Body | ConvertTo-Json -Compress) | Should -Be '{"type":"full","commitMode":"transactional"}'
    }
    It 'names a table and partitions the way Learn does' {
        $r = New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -Table Sales -Partition 2023Q103, 2023Q104
        @($r.Body.objects).Count | Should -Be 2
        ($r.Body.objects[1] | ConvertTo-Json -Compress) | Should -Be '{"table":"Sales","partition":"2023Q104"}'
    }
    It 'a table alone is one object without a partition' {
        $r = New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -Table Sales
        ($r.Body | ConvertTo-Json -Depth 5 -Compress) | Should -Match '"objects":\[\{"table":"Sales"\}\]'
    }
    It 'sends applyRefreshPolicy false and the effective date in yyyy-MM-dd' {
        (New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -SkipRefreshPolicy).Body.applyRefreshPolicy | Should -BeFalse
        (New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -EffectiveDate '2026-12-01').Body.effectiveDate | Should -Be '2026-12-01'
    }
    It 'formats the timeout as hh:mm:ss and keeps retryCount' {
        $r = New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -Timeout ([timespan]::FromMinutes(90)) -RetryCount 2 -MaxParallelism 4
        $r.Body.timeout | Should -Be '01:30:00'
        $r.Body.retryCount | Should -Be 2
        $r.Body.maxParallelism | Should -Be 4
    }
    It 'refuses partialBatch with the policy applied (Learn)' {
        { New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -CommitMode partialBatch } | Should -Throw '*partialBatch*'
        (New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -CommitMode partialBatch -SkipRefreshPolicy).Body.commitMode | Should -Be 'partialBatch'
    }
    It 'refuses a total over 24 hours, a partition without a table, and an effective date without the policy' {
        { New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -Timeout ([timespan]::FromHours(8)) -RetryCount 3 } | Should -Throw '*24 hours*'
        { New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -Partition 2023 } | Should -Throw '*needs -Table*'
        { New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -SkipRefreshPolicy -EffectiveDate '2026-12-01' } | Should -Throw '*policy*'
    }
    It "does not accept the type 'add' (not supported by the enhanced API)" {
        { New-PbiRefreshRequest -WorkspaceId $script:WS -SemanticModelId $script:DS -Type add } | Should -Throw
    }
}

Describe 'Start-PbiEnhancedRefresh' {
    BeforeEach { $global:PbiTest.Calls = @(); Mock Invoke-PowerBIRestMethod -ModuleName PbiRefresh { Get-PbiRoute $Url $Method $Body } }
    It '-WhatIf sends nothing and returns the request' {
        $r = Start-PbiEnhancedRefresh -WorkspaceId $script:WS -SemanticModelId $script:DS -Table Sales -WhatIf
        $r.Body.type | Should -Be 'full'
        $global:PbiTest.Calls.Count | Should -Be 0
    }
    It 'posts the body and returns the newest request id' {
        $id = Start-PbiEnhancedRefresh -WorkspaceId $script:WS -SemanticModelId $script:DS -Table Sales -Partition 2026Q41121 -Confirm:$false
        $id | Should -Be '00000000-0000-0000-0000-0000000000f2'
        $global:PbiTest.Calls[0][0] | Should -Be 'Post'
        $global:PbiTest.Calls[0][2] | Should -Match '"partition":"2026Q41121"'
        $global:PbiTest.Calls[1][1] | Should -Match 'refreshes\?\$top=1$'
    }
}

Describe 'reading and waiting' {
    BeforeEach { $global:PbiTest.Calls = @(); $global:PbiTest.Poll = @(); Mock Invoke-PowerBIRestMethod -ModuleName PbiRefresh { Get-PbiRoute $Url $Method $Body } }
    It 'lists the history' {
        $h = @(Get-PbiRefresh -WorkspaceId $script:WS -SemanticModelId $script:DS)
        $h.Count | Should -Be 2
        $h[1].status | Should -Be 'Completed'
    }
    It 'reads one operation with its objects' {
        (Get-PbiRefresh -WorkspaceId $script:WS -SemanticModelId $script:DS -RequestId '00000000-0000-0000-0000-0000000000f1').objects[0].partition | Should -Be '2026Q41121'
    }
    It 'waits while InProgress, then returns the completed operation' {
        $global:PbiTest.Poll = @('refresh-inprogress.json', 'refresh-inprogress.json')
        $op = Wait-PbiRefresh -WorkspaceId $script:WS -SemanticModelId $script:DS -RequestId '00000000-0000-0000-0000-0000000000f2' -PollSeconds 0
        $op.status | Should -Be 'Completed'
        @($global:PbiTest.Calls | Where-Object { $_[1] -match 'f2$' }).Count | Should -Be 3
    }
    It 'throws with the messages when the refresh failed' {
        { Wait-PbiRefresh -WorkspaceId $script:WS -SemanticModelId $script:DS -RequestId '00000000-0000-0000-0000-0000000000f3' -PollSeconds 0 } | Should -Throw '*0xC11C0020*'
    }
    It 'gives up after the timeout' {
        $global:PbiTest.Poll = @(1..50 | ForEach-Object { 'refresh-inprogress.json' })
        { Wait-PbiRefresh -WorkspaceId $script:WS -SemanticModelId $script:DS -RequestId '00000000-0000-0000-0000-0000000000f2' -PollSeconds 0 -TimeoutSeconds -1 } | Should -Throw '*still*'
    }
    It 'cancels with DELETE, and -WhatIf does not' {
        Stop-PbiRefresh -WorkspaceId $script:WS -SemanticModelId $script:DS -RequestId '00000000-0000-0000-0000-0000000000f2' -WhatIf
        $global:PbiTest.Calls.Count | Should -Be 0
        Stop-PbiRefresh -WorkspaceId $script:WS -SemanticModelId $script:DS -RequestId '00000000-0000-0000-0000-0000000000f2' -Confirm:$false
        $global:PbiTest.Calls[0][0] | Should -Be 'Delete'
    }
}

Describe 'Invoke-PartitionRefresh.ps1' {
    BeforeEach { $global:PbiTest.Calls = @(); Mock Invoke-PowerBIRestMethod -ModuleName PbiRefresh { Get-PbiRoute $Url $Method $Body } }
    It '-WhatIf prints the request and sends nothing' {
        $out = & (Join-Path $script:Src 'Invoke-PartitionRefresh.ps1') -WorkspaceId $script:WS -SemanticModelId $script:DS -Table Sales -Partition 2023Q103 -SkipRefreshPolicy -WhatIf 6>&1
        ($out -join ' ') | Should -Match 'applyRefreshPolicy":false'
        $global:PbiTest.Calls.Count | Should -Be 0
    }
}
