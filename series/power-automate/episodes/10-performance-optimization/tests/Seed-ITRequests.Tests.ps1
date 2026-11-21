# Pester tests for scripts/Seed-ITRequests.ps1 with stand-ins for the PnP.PowerShell cmdlets.
# Run: pwsh -NoProfile -Command "Invoke-Pester tests/Seed-ITRequests.Tests.ps1 -Output Detailed"
BeforeAll {
    $script:Script = Join-Path (Split-Path $PSScriptRoot -Parent) 'src/scripts/Seed-ITRequests.ps1'
    $global:Added = [System.Collections.Generic.List[object]]::new()
    $global:Batches = 0
    $global:Removed = [System.Collections.Generic.List[int]]::new()
    $global:Existing = @()
    function global:New-PnPBatch { [pscustomobject]@{ Id = [guid]::NewGuid() } }
    function global:Invoke-PnPBatch { param($Batch) $global:Batches++ }
    function global:Add-PnPListItem { param($List, $Values, $Batch) $global:Added.Add($Values) }
    function global:Get-PnPListItem { param($List, $PageSize, $Fields) $global:Existing }
    function global:Remove-PnPListItem { param($List, $Identity, [switch]$Recycle, $Batch) $global:Removed.Add($Identity) }
    $script:Now = [datetime]::SpecifyKind([datetime]'2026-11-23T02:00:00', 'Utc')
}
Describe 'Seed-ITRequests' {
    BeforeEach { $global:Added.Clear(); $global:Batches = 0; $global:Removed.Clear() }
    It 'adds Count items in batches of BatchSize, all titled [TEST] seed' {
        & $Script -Count 250 -BatchSize 100 -Now $Now | Out-Null
        $Added.Count | Should -Be 250
        $Batches | Should -Be 3          # 100 + 100 + 50
        ($Added | Where-Object { $_.Title -notlike '[[]TEST] seed *' }).Count | Should -Be 0
    }
    It 'makes 40 % Done more than 30 days ago, 10 % Done recently, the rest open' {
        & $Script -Count 1000 -Now $Now | Out-Null
        $cutoff = $Now.AddDays(-30)
        $oldDone = $Added | Where-Object { $_.Status -eq 'Done' -and $_.DoneOn -lt $cutoff }
        $recentDone = $Added | Where-Object { $_.Status -eq 'Done' -and $_.DoneOn -ge $cutoff }
        $open = $Added | Where-Object { $_.Status -ne 'Done' }
        $oldDone.Count | Should -Be 400
        $recentDone.Count | Should -Be 100
        $open.Count | Should -Be 500
        ($open | Where-Object { $_.ContainsKey('DoneOn') }).Count | Should -Be 0
    }
    It 'does nothing with -WhatIf' {
        & $Script -Count 10 -WhatIf | Out-Null
        $Added.Count | Should -Be 0
    }
    It 'rejects absurd counts' {
        { & $Script -Count 0 } | Should -Throw
    }
    It 'cleanup removes only the seeded items' {
        $global:Existing = @(
            [pscustomobject]@{ Id = 1; FieldValues = @{ Title = '[TEST] seed 1' } },
            [pscustomobject]@{ Id = 2; FieldValues = @{ Title = 'Laptop will not boot' } },
            [pscustomobject]@{ Id = 3; FieldValues = @{ Title = '[TEST] seed 3' } })
        & $Script -Cleanup | Out-Null
        ($Removed -join ',') | Should -Be '1,3'
        $Batches | Should -Be 1
    }
}
