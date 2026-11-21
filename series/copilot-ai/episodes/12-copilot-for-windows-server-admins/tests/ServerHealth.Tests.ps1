BeforeAll {
    . (Join-Path $PSScriptRoot '..' 'src' 'scripts' 'Get-ServerHealth.ps1')
    $script:now = [datetime] '2026-11-20T09:00:00'
    function Run($o = @{}) {
        $p = @{ Disks = @(); Services = @(); PendingReboot = [pscustomobject]@{ ComponentServicing = $false; WindowsUpdate = $false }
                BootTime = $script:now.AddDays(-5); LastHotfix = $script:now.AddDays(-10); Now = $script:now }
        foreach ($k in $o.Keys) { $p[$k] = $o[$k] }
        @(Get-HealthFindings @p)
    }
}

Describe 'Get-HealthFindings (fixture data)' {
    It 'returns nothing for a healthy server' { (Run).Count | Should -Be 0 }
    It 'flags a disk below the free-space limit' {
        $f = Run @{ Disks = @([pscustomobject]@{ Drive = 'D:'; Size = 100GB; Free = 10GB }) }
        $f.Count | Should -Be 1
        $f[0].Check | Should -Be 'Disk'
        $f[0].Detail | Should -Match '10 % free'
    }
    It 'accepts a disk exactly at the limit' {
        (Run @{ Disks = @([pscustomobject]@{ Drive = 'C:'; Size = 100GB; Free = 15GB }) }).Count | Should -Be 0
    }
    It 'skips a disk with size 0' { (Run @{ Disks = @([pscustomobject]@{ Drive = 'E:'; Size = 0; Free = 0 }) }).Count | Should -Be 0 }
    It 'reports automatic services that are not running' {
        $f = Run @{ Services = @([pscustomobject]@{ Name = 'Spooler'; Status = 'Stopped' }, [pscustomobject]@{ Name = 'W32Time'; Status = 'Running' }) }
        $f.Count | Should -Be 1
        $f[0].Detail | Should -Match 'Spooler'
    }
    It 'reports a pending restart with the reason' {
        $f = Run @{ PendingReboot = [pscustomobject]@{ ComponentServicing = $true; WindowsUpdate = $false } }
        $f[0].Check | Should -Be 'Reboot'
        $f[0].Detail | Should -Match 'component servicing'
    }
    It 'reports long uptime' {
        (Run @{ BootTime = $script:now.AddDays(-90) })[0].Check | Should -Be 'Uptime'
    }
    It 'reports an old last hotfix' {
        (Run @{ LastHotfix = $script:now.AddDays(-100) })[0].Check | Should -Be 'Hotfix'
    }
    It 'reports a missing hotfix date as Info, not a crash' {
        $f = Run @{ LastHotfix = $null }
        $f[0].Severity | Should -Be 'Info'
    }
}

Describe 'collectors (mocked)' {
    It 'Get-PendingRebootState reads the two flags' {
        Mock Test-Path { $Path -like '*Component Based Servicing*' }
        $s = Get-PendingRebootState
        $s.ComponentServicing | Should -BeTrue
        $s.WindowsUpdate | Should -BeFalse
    }
    It 'Get-PendingRebootState does not look at PendingFileRenameOperations' {
        Mock Test-Path { $false }
        Get-PendingRebootState | Out-Null
        Should -Invoke Test-Path -Times 0 -ParameterFilter { $Path -like '*PendingFileRenameOperations*' }
    }
}
