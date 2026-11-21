# Pester tests for setup/New-LabBusinessCentral.ps1. They run anywhere (Linux included): docker, BcContainerHelper and the
# API are replaced by Pester mocks, which is only for these automated tests. The real run is on the recording laptop (demo.md).
# The DPAPI round trip needs Windows and is skipped elsewhere.

BeforeAll {
    $script:Script = Join-Path $PSScriptRoot '..' 'setup' 'New-LabBusinessCentral.ps1'
    . $script:Script            # dot-sourcing only defines the functions: the main block is skipped
    $script:IsWin = [Environment]::OSVersion.Platform -eq 'Win32NT'
    function global:Get-FakeSecret { ConvertTo-SecureString -String 'unit-test-only' -AsPlainText -Force }
}

Describe 'script file' {
    It 'parses without syntax errors' {
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script:Script), [ref]$null, [ref]$errors)
        $errors | Should -BeNullOrEmpty
    }
    It 'never prints the password or the plain text variable' {
        $lines = Get-Content $script:Script | Where-Object { $_ -match 'Write-(Host|Output|Verbose|Warning)' }
        ($lines | Where-Object { $_ -match '\$plain|ConvertTo-PlainInMemory|\$env:BC_PASSWORD|\.Password' }) | Should -BeNullOrEmpty
    }
    It 'uses the cmdlets and parameters verified against Learn and the BcContainerHelper source' {
        $text = Get-Content $script:Script -Raw
        foreach ($needle in 'Get-BcArtifactUrl', "type = 'Sandbox'", "select = 'Latest'", 'New-BcContainer', '-auth NavUserPassword',
                            '-Credential $credential', '-memoryLimit', '-updateHosts', '-assignPremiumPlan', 'Remove-BcContainer -containerName') {
            $text | Should -Match ([regex]::Escape($needle))
        }
    }
}

Describe 'Test-DockerReady' {
    It 'says Docker is missing' {
        Mock Get-DockerCommand { $null }
        $r = Test-DockerReady
        $r.Ok | Should -BeFalse; $r.Installed | Should -BeFalse; $r.Message | Should -Match 'not installed'
    }
    It 'explains how to switch when Docker is in Linux mode' {
        Mock Get-DockerCommand { 'docker' }
        Mock Invoke-Docker { $global:LASTEXITCODE = 0; 'linux' }
        $r = Test-DockerReady
        $r.Ok | Should -BeFalse; $r.Mode | Should -Be 'linux'
        $r.Message | Should -Match 'Switch to Windows Containers'
    }
    It 'is ready in Windows mode' {
        Mock Get-DockerCommand { 'docker' }
        Mock Invoke-Docker { $global:LASTEXITCODE = 0; 'windows' }
        (Test-DockerReady).Ok | Should -BeTrue
    }
    It 'reports an engine that does not answer' {
        Mock Get-DockerCommand { 'docker' }
        Mock Invoke-Docker { $global:LASTEXITCODE = 1; '' }
        $r = Test-DockerReady
        $r.Ok | Should -BeFalse; $r.Message | Should -Match 'engine does not answer'
    }
}

Describe 'Get-LabContainerState' {
    It 'maps docker ps output' {
        Mock Invoke-Docker { '' }
        Get-LabContainerState -Name 'mglab-bc' | Should -Be 'missing'
        Mock Invoke-Docker { 'mglab-bc|Up 3 minutes (healthy)' }
        Get-LabContainerState -Name 'mglab-bc' | Should -Be 'running'
        Mock Invoke-Docker { 'mglab-bc|Exited (0) 2 hours ago' }
        Get-LabContainerState -Name 'mglab-bc' | Should -Be 'stopped'
    }
    It 'asks docker for an exact name' {
        Mock Invoke-Docker { '' }
        Get-LabContainerState -Name 'mglab-bc' | Out-Null
        Should -Invoke Invoke-Docker -ParameterFilter { $Arguments -contains 'name=^mglab-bc$' }
    }
}

Describe 'New-LabPassword' {
    It 'is 24 characters, alphanumeric, with upper, lower and digit' {
        1..40 | ForEach-Object {
            $p = New-LabPassword
            $p.Length | Should -Be 24
            $p | Should -MatchExactly '^[A-Za-z0-9]{24}$'
            $p | Should -MatchExactly '[A-Z]'; $p | Should -MatchExactly '[a-z]'; $p | Should -Match '[0-9]'
        }
    }
    It 'is different every time' {
        (1..30 | ForEach-Object { New-LabPassword } | Select-Object -Unique).Count | Should -Be 30
    }
}

Describe 'secret storage' {
    It 'builds the path under the secrets folder' {
        Get-LabSecretPath -Folder 'E:\MGLab\secrets' -Name 'mglab-bc' | Should -Match 'mglab-bc\.admin\.dpapi$'
    }
    It 'refuses to "encrypt" on a non-Windows host (SecureString is not encrypted there, per Learn)' -Skip:$script:IsWin {
        { Save-LabSecret -Path (Join-Path $TestDrive 's.dpapi') -Secret (Get-FakeSecret) } | Should -Throw '*only available on Windows*'
    }
    It 'round-trips through DPAPI and the file does not contain the plain text' -Skip:(-not $script:IsWin) {
        $p = Join-Path $TestDrive 'x.dpapi'
        Save-LabSecret -Path $p -Secret (Get-FakeSecret)
        (Get-Content $p -Raw) | Should -Not -Match 'unit-test-only'
        ConvertTo-PlainInMemory (Read-LabSecret -Path $p) | Should -Be 'unit-test-only'
    }
    It 'returns nothing when the file does not exist' {
        Read-LabSecret -Path (Join-Path $TestDrive 'missing.dpapi') | Should -BeNullOrEmpty
    }
}

Describe 'Get-LabBaseUrl' {
    It 'is http, port 7048, server instance BC' { Get-LabBaseUrl -Name 'mglab-bc' | Should -Be 'http://mglab-bc:7048/BC' }
}

Describe 'Wait-LabApi' {
    It 'returns the companies once the API answers, after a retry' {
        $script:calls = 0
        Mock Start-Sleep {}
        Mock Invoke-LabApi { $script:calls++; if ($script:calls -lt 2) { throw 'starting' }; [pscustomobject]@{ value = @([pscustomobject]@{ name = 'CRONUS USA, Inc.' }) } }
        $r = Wait-LabApi -BaseUrl 'http://x:7048/BC' -User admin -Secret (Get-FakeSecret) -TimeoutSec 60
        $r.Count | Should -Be 1; $r[0].name | Should -Be 'CRONUS USA, Inc.'; $script:calls | Should -Be 2
    }
    It 'turns a 401 into the Learn hint about the web service access key' {
        Mock Start-Sleep {}
        Mock Invoke-LabApi { $e = New-Object System.Exception 'unauthorized'; $e | Add-Member -NotePropertyName Response -NotePropertyValue ([pscustomobject]@{ StatusCode = 401 }); throw $e }
        { Wait-LabApi -BaseUrl 'http://x:7048/BC' -User admin -Secret (Get-FakeSecret) -TimeoutSec 60 } | Should -Throw '*web service access key*'
    }
    It 'turns a 405 into the Learn hint about enabling the APIs' {
        Mock Start-Sleep {}
        Mock Invoke-LabApi { $e = New-Object System.Exception 'nope'; $e | Add-Member -NotePropertyName Response -NotePropertyValue ([pscustomobject]@{ StatusCode = 405 }); throw $e }
        { Wait-LabApi -BaseUrl 'http://x:7048/BC' -User admin -Secret (Get-FakeSecret) -TimeoutSec 60 } | Should -Throw '*ApiServicesEnabled*'
    }
    It 'gives up with the last error after the timeout' {
        Mock Start-Sleep {}
        Mock Invoke-LabApi { throw 'connection refused' }
        { Wait-LabApi -BaseUrl 'http://x:7048/BC' -User admin -Secret (Get-FakeSecret) -TimeoutSec 1 } | Should -Throw '*did not answer*connection refused*'
    }
}

Describe 'Assert-Prerequisites' {
    It 'refuses a non-Windows host' -Skip:$script:IsWin {
        { Assert-Prerequisites } | Should -Throw '*Windows recording laptop*'
    }
    It 'refuses PowerShell 7 unless allowed (Learn: known issue with the BC admin modules in 28.0)' {
        Mock Test-IsWindowsHost { $true }
        Mock Test-IsAdministrator { $true }
        Mock Test-DockerReady { [pscustomobject]@{ Ok = $true; Message = 'ok' } }
        if ($PSVersionTable.PSEdition -eq 'Core') {
            { Assert-Prerequisites } | Should -Throw '*Windows PowerShell 5.1*'
            { Assert-Prerequisites -AllowPowerShell7 } | Should -Not -Throw
        } else {
            { Assert-Prerequisites } | Should -Not -Throw
        }
    }
    It 'needs an elevated prompt' {
        Mock Test-IsWindowsHost { $true }
        Mock Test-IsAdministrator { $false }
        { Assert-Prerequisites -AllowPowerShell7 } | Should -Throw '*elevated*'
    }
    It 'passes the Docker message through when Docker is not ready' {
        Mock Test-IsWindowsHost { $true }
        Mock Test-IsAdministrator { $true }
        Mock Test-DockerReady { [pscustomobject]@{ Ok = $false; Message = 'Docker is in linux-containers mode' } }
        { Assert-Prerequisites -AllowPowerShell7 } | Should -Throw '*linux-containers*'
    }
}

Describe 'Invoke-LabMain (idempotency)' {
    BeforeEach {
        Mock Assert-Prerequisites {}
        Mock Invoke-LabCreate { Get-FakeSecret }
        Mock Invoke-LabRemove {}
        Mock Invoke-Docker {}
        Mock Wait-LabApi { @([pscustomobject]@{ name = 'CRONUS USA, Inc.' }) }
        Mock Write-Host {}
    }
    It 'leaves a running container with a secret alone' {
        Mock Get-LabContainerState { 'running' }
        Mock Read-LabSecret { Get-FakeSecret }
        Invoke-LabMain -AcceptEula
        Should -Invoke Invoke-LabCreate -Times 0
        Should -Invoke Invoke-LabRemove -Times 0
        Should -Invoke Wait-LabApi -Times 1
    }
    It 'starts a stopped container instead of creating a new one' {
        Mock Get-LabContainerState { 'stopped' }
        Mock Read-LabSecret { Get-FakeSecret }
        Invoke-LabMain -AcceptEula
        Should -Invoke Invoke-Docker -ParameterFilter { $Arguments[0] -eq 'start' -and $Arguments[1] -eq 'mglab-bc' } -Times 1
        Should -Invoke Invoke-LabCreate -Times 0
    }
    It 'creates the container when it is missing' {
        Mock Get-LabContainerState { 'missing' }
        Mock Read-LabSecret { $null }
        Invoke-LabMain -AcceptEula
        Should -Invoke Invoke-LabCreate -Times 1
        Should -Invoke Wait-LabApi -Times 1
    }
    It 'stops with a clear message when the container exists but its password is unknown' {
        Mock Get-LabContainerState { 'running' }
        Mock Read-LabSecret { $null }
        { Invoke-LabMain -AcceptEula } | Should -Throw '*-Recreate*'
        Should -Invoke Wait-LabApi -Times 0
    }
    It '-Recreate removes the old container and creates a new one' {
        Mock Get-LabContainerState { 'running' }
        Mock Read-LabSecret { Get-FakeSecret }
        Invoke-LabMain -AcceptEula -Recreate
        Should -Invoke Invoke-LabRemove -Times 1
        Should -Invoke Invoke-LabCreate -Times 1
    }
    It '-Remove only tears down' {
        Mock Test-IsAdministrator { $true }
        Invoke-LabMain -Remove
        Should -Invoke Invoke-LabRemove -Times 1
        Should -Invoke Invoke-LabCreate -Times 0
        Should -Invoke Assert-Prerequisites -Times 0
    }
    It '-SetEnv sets the three variables without writing the password anywhere' {
        Mock Read-LabSecret { Get-FakeSecret }
        $before = @($env:BC_BASE_URL, $env:BC_USER, $env:BC_PASSWORD)
        try {
            Invoke-LabMain -SetEnv
            $env:BC_BASE_URL | Should -Be 'http://mglab-bc:7048/BC'
            $env:BC_USER | Should -Be 'admin'
            $env:BC_PASSWORD | Should -Be 'unit-test-only'
            Should -Invoke Write-Host -ParameterFilter { "$Object" -match 'unit-test-only' } -Times 0
        } finally { $env:BC_BASE_URL, $env:BC_USER, $env:BC_PASSWORD = $before }
    }
}

Describe 'Invoke-LabCreate' {
    It 'refuses to run without -AcceptEula and touches nothing' {
        Mock Initialize-BcContainerHelper {}
        Mock Save-LabSecret {}
        { Invoke-LabCreate -Name 'mglab-bc' -Country us -Version '' -Memory 8G -User admin -SecretPath 'x' } | Should -Throw '*-AcceptEula*'
        Should -Invoke Initialize-BcContainerHelper -Times 0
        Should -Invoke Save-LabSecret -Times 0
    }
    It 'saves the secret before creating the container and passes the verified parameters' {
        $script:order = @()
        Mock Initialize-BcContainerHelper {}
        Mock Get-LabArtifactUrl { 'https://bcartifacts.example/sandbox/28.0.1.0/us' }
        Mock Save-LabSecret { $script:order += 'save' }
        function global:New-BcContainer { param([switch]$accept_eula, $containerName, $artifactUrl, $auth, $Credential, $memoryLimit, [switch]$updateHosts, [switch]$assignPremiumPlan, $shortcuts, $isolation) $script:order += 'create'; $script:bound = $PSBoundParameters }
        try {
            Invoke-LabCreate -Name 'mglab-bc' -Country us -Version '' -Memory 8G -User admin -SecretPath 'x' -AcceptEula | Out-Null
        } finally { Remove-Item function:global:New-BcContainer }
        $script:order | Should -Be @('save', 'create')
        $script:bound.auth | Should -Be 'NavUserPassword'
        $script:bound.containerName | Should -Be 'mglab-bc'
        $script:bound.memoryLimit | Should -Be '8G'
        $script:bound.Credential.UserName | Should -Be 'admin'
        $script:bound.updateHosts.IsPresent | Should -BeTrue
        $script:bound.ContainsKey('isolation') | Should -BeFalse
    }
    It 'passes -isolation only when asked' {
        $script:bound = $null
        Mock Initialize-BcContainerHelper {}
        Mock Get-LabArtifactUrl { 'https://bcartifacts.example/sandbox/28.0.1.0/us' }
        Mock Save-LabSecret {}
        function global:New-BcContainer { param([switch]$accept_eula, $containerName, $artifactUrl, $auth, $Credential, $memoryLimit, [switch]$updateHosts, [switch]$assignPremiumPlan, $shortcuts, $isolation) $script:bound = $PSBoundParameters }
        try {
            Invoke-LabCreate -Name 'mglab-bc' -Country us -Version '' -Memory 8G -User admin -SecretPath 'x' -Isolation hyperv -AcceptEula | Out-Null
        } finally { Remove-Item function:global:New-BcContainer }
        $script:bound.isolation | Should -Be 'hyperv'
    }
}
