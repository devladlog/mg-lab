using namespace System.Management.Automation.Language

BeforeAll {
    $script:Src = Join-Path $PSScriptRoot '../src'
    $script:Fixtures = Join-Path $PSScriptRoot 'fixtures'
    $script:Sample = Join-Path $PSScriptRoot '../sample'
    Import-Module (Join-Path $script:Src 'CoreLab/CoreLab.psd1') -Force
    $script:ConfigPath = Join-Path $script:Src 'core-lab.json'
    $script:Config = Read-CoreLabConfig -Path $script:ConfigPath
    function Get-Facts([string] $Name) { Get-Content -Raw (Join-Path $script:Fixtures "facts-$Name.json") | ConvertFrom-Json }
    function Get-ConfigCopy { Get-Content -Raw $script:ConfigPath | ConvertFrom-Json }
    function Save-Config($Cfg) { $p = Join-Path ([IO.Path]::GetTempPath()) ("corelab-" + [guid]::NewGuid().ToString('N') + '.json'); $Cfg | ConvertTo-Json -Depth 8 | Set-Content $p; $p }
    function Test-Facts($Facts, $Cfg = $script:Config) {
        $f = @(); foreach ($h in @($Facts.Hosts)) { $f += @(Test-CoreHost -Facts $h -Config $Cfg) }
        , @($f | Sort-Object @{ Expression = { @{ High = 0; Medium = 1; Low = 2; Info = 3 }[$_.Severity] } }, Target, Check)
    }
    function Get-Checks($Findings, [string] $Target) { @($Findings | Where-Object { $_.Target -eq $Target } | ForEach-Object Check) }
    function Get-Dockerfile([string] $Name) { Get-Content -Raw (Join-Path $script:Fixtures $Name) }
    # Windows-only commands do not exist on this Linux box: define stand-ins so the collector code can run for real
    $global:CoreStub = @{}
    function global:Get-ItemProperty { [CmdletBinding()] param($Path) if ($global:CoreStub.LevelsFail) { throw 'Cannot find path ServerLevels' }; $o = New-Object psobject; foreach ($l in $global:CoreStub.Levels) { Add-Member -InputObject $o -NotePropertyName $l -NotePropertyValue 1 }; Add-Member -InputObject $o -NotePropertyName PSPath -NotePropertyValue 'x'; $o }
    function global:Get-WindowsFeature { [CmdletBinding()] param() if ($global:CoreStub.FeaturesFail) { throw 'feature query failed' }; foreach ($n in $global:CoreStub.Features) { [pscustomobject]@{ Name = $n; Installed = $true } }; [pscustomobject]@{ Name = 'Fax'; Installed = $false } }
    function global:Get-WindowsCapability { [CmdletBinding()] param([switch] $Online, $Name) [pscustomobject]@{ Name = 'OpenSSH.Client~~~~0.0.1.0'; State = 'NotPresent' }; if ($global:CoreStub.AppState) { [pscustomobject]@{ Name = 'ServerCore.AppCompatibility~~~~0.0.1.0'; State = $global:CoreStub.AppState } } }
    function global:Get-CimInstance { [CmdletBinding()] param($ClassName, $Filter)
        if ($ClassName -eq 'Win32_OperatingSystem') { [pscustomobject]@{ Caption = 'Microsoft Windows Server 2025 Datacenter'; Version = '10.0.26100'; TotalVisibleMemorySize = 2097152; FreePhysicalMemory = 1048576 } }
        else { $global:CoreStub.DiskFilter = $Filter; [pscustomobject]@{ Size = 64424509440; FreeSpace = 51539607552 } } }
    function global:Get-Service { [CmdletBinding()] param() [pscustomobject]@{ Name = 'WinRM'; Status = 'Running' }; [pscustomobject]@{ Name = 'Spooler'; Status = 'Stopped' }; [pscustomobject]@{ Name = 'EventLog'; Status = 'Running' } }
    function global:Get-NetFirewallRule { [CmdletBinding()] param($DisplayGroup) [pscustomobject]@{ Enabled = 'True' }; [pscustomobject]@{ Enabled = 'True' }; [pscustomobject]@{ Enabled = 'False' } }
    function global:Restart-Computer { [CmdletBinding()] param($ComputerName, [switch] $Force, $Credential) }
}

AfterAll {
    foreach ($n in 'Get-ItemProperty', 'Get-WindowsFeature', 'Get-WindowsCapability', 'Get-CimInstance', 'Get-Service', 'Get-NetFirewallRule', 'Restart-Computer') { Remove-Item "function:global:$n" -ErrorAction SilentlyContinue }
    Remove-Variable -Name CoreStub -Scope Global -ErrorAction SilentlyContinue
}

Describe 'Read-CoreLabConfig' {
    It 'reads the shipped config' {
        $script:Config.Targets.Count | Should -Be 5
        @($script:Config.DesktopOnlyFeatures) | Should -Contain 'RSAT-ADCS'
    }
    It 'refuses Nano Server as a host, with the reason' {
        $c = Get-ConfigCopy; $c.Targets[0].ExpectedInstall = 'Nano'
        { Read-CoreLabConfig -Path (Save-Config $c) } | Should -Throw '*container base image*'
    }
    It 'refuses an unknown install option' {
        $c = Get-ConfigCopy; $c.Targets[0].ExpectedInstall = 'Minimal'
        { Read-CoreLabConfig -Path (Save-Config $c) } | Should -Throw '*Core or DesktopExperience*'
    }
    It 'wants a reason for every Desktop Experience server' {
        $c = Get-ConfigCopy; $c.Targets[2].PSObject.Properties.Remove('Reason')
        { Read-CoreLabConfig -Path (Save-Config $c) } | Should -Throw '*needs a Reason*'
    }
    It 'refuses the App Compatibility FOD on a Desktop Experience server (Learn: Server Core only)' {
        $c = Get-ConfigCopy; $c.Targets[2].AppCompat = 'Required'
        { Read-CoreLabConfig -Path (Save-Config $c) } | Should -Throw '*only installs on Server Core*'
    }
    It 'refuses duplicate targets and an unknown AppCompat value' {
        $c = Get-ConfigCopy; $c.Targets[1].Name = 'con-dc01'
        { Read-CoreLabConfig -Path (Save-Config $c) } | Should -Throw '*Duplicate*'
        $c = Get-ConfigCopy; $c.Targets[1].AppCompat = 'Maybe'
        { Read-CoreLabConfig -Path (Save-Config $c) } | Should -Throw '*Required or No*'
    }
    It 'refuses characters in the two values that end up inside generated scripts' {
        $c = Get-ConfigCopy; $c.Setup.FodSourcePath = "D:\x'; calc"
        { Read-CoreLabConfig -Path (Save-Config $c) } | Should -Throw '*FodSourcePath*'
        $c = Get-ConfigCopy; $c.Setup.AppCompatCapability = 'ServerCore.AppCompatibility~~~~0.0.1.0; calc'
        { Read-CoreLabConfig -Path (Save-Config $c) } | Should -Throw '*AppCompatCapability*'
        $c = Get-ConfigCopy; $c.Setup.FodSourcePath = 'D:\LanguagesAndOptionalFeatures'
        { Read-CoreLabConfig -Path (Save-Config $c) } | Should -Not -Throw
    }
}

Describe 'Get-CoreInstallType' {
    It 'reads the additive server levels (Learn)' {
        Get-CoreInstallType -ServerLevels 'ServerCore' | Should -Be 'Core'
        Get-CoreInstallType -ServerLevels 'ServerCore', 'Server-GuiMgmt' | Should -Be 'MinimalInterface'
        Get-CoreInstallType -ServerLevels 'ServerCore', 'Server-GuiMgmt', 'ServerGuiShell' | Should -Be 'DesktopExperience'
        Get-CoreInstallType -ServerLevels @() | Should -Be 'Unknown'
    }
}

Describe 'The collector, run for real against stand-ins for the Windows commands' {
    BeforeEach {
        $global:CoreStub = @{ Levels = @('ServerCore'); Features = @('PowerShell', 'Web-Server'); AppState = 'Installed' }
        $script:OldCn = $env:COMPUTERNAME; $script:OldSd = $env:SystemDrive
        $env:COMPUTERNAME = 'CON-TEST01'; $env:SystemDrive = 'C:'
    }
    AfterEach { $env:COMPUTERNAME = $script:OldCn; $env:SystemDrive = $script:OldSd }
    It 'builds the facts the rules need' {
        $f = & (Get-CoreCollectorScript)
        $f.ComputerName | Should -Be 'CON-TEST01'
        $f.Unreachable | Should -BeFalse
        Get-CoreInstallType -ServerLevels $f.ServerLevels | Should -Be 'Core'
        @($f.InstalledFeatures) | Should -Be @('PowerShell', 'Web-Server')
        $f.AppCompatState | Should -Be 'Installed'
        $f.WinRmService | Should -Be 'Running'
        $f.WinRmFirewallRulesEnabled | Should -Be 2
        $f.RunningServices | Should -Be 2
        $f.SystemDriveSizeGB | Should -Be 60
        $f.SystemDriveUsedGB | Should -Be 12
        $f.MemoryUsedMB | Should -Be 1024
        @($f.Errors).Count | Should -Be 0
    }
    It 'asks for the system drive only' {
        $null = & (Get-CoreCollectorScript)
        $global:CoreStub.DiskFilter | Should -Be "DeviceID='C:'"
    }
    It 'says NotListed when the FOD does not exist on this edition' {
        $global:CoreStub.AppState = $null
        (& (Get-CoreCollectorScript)).AppCompatState | Should -Be 'NotListed'
    }
    It 'turns a failing query into an error row and keeps the rest' {
        $global:CoreStub.FeaturesFail = $true; $global:CoreStub.LevelsFail = $true
        $f = & (Get-CoreCollectorScript)
        @($f.Errors).Count | Should -Be 2
        ($f.Errors -join ' ') | Should -BeLike '*ServerLevels*'
        @($f.InstalledFeatures).Count | Should -Be 0
        $f.SystemDriveUsedGB | Should -Be 12
    }
}

Describe 'The collector is read-only and Windows PowerShell 5.1 safe' {
    BeforeAll { $script:Ast = [Parser]::ParseInput((Get-CoreCollectorScript).ToString(), [ref]$null, [ref]$null) }
    It 'uses no syntax that Windows PowerShell 5.1 cannot parse' {
        @($script:Ast.FindAll({ param($n) $n -is [TernaryExpressionAst] -or $n -is [PipelineChainAst] }, $true)).Count | Should -Be 0
        (Get-CoreCollectorScript).ToString() | Should -Not -Match '\?\?|\?\.|\?\['
    }
    It 'calls no command that changes state' {
        $cmds = @($script:Ast.FindAll({ param($n) $n -is [CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
        @($cmds | Where-Object { $_ -match '^(Set|Remove|Install|Uninstall|Enable|Disable|Start|Stop|Restart|Clear|Move|Copy|Rename|Add|Register|Unregister|Update|Import|Out|Invoke|Write)-' }).Count | Should -Be 0
        @($cmds | Where-Object { $_ -match '^New-' -and $_ -ne 'New-Object' }).Count | Should -Be 0
    }
    It 'only calls the commands we expect' {
        $allowed = @('Get-CimInstance', 'Get-ItemProperty', 'Get-NetFirewallRule', 'Get-Service', 'Get-WindowsCapability', 'Get-WindowsFeature', 'New-Object', 'Where-Object', 'ForEach-Object')
        $cmds = @($script:Ast.FindAll({ param($n) $n -is [CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ } | Sort-Object -Unique)
        @($cmds | Where-Object { $allowed -notcontains $_ }) | Should -BeNullOrEmpty
        $cmds | Should -Contain 'Get-WindowsFeature'
    }
}

Describe 'Get-CoreFacts' {
    It 'turns a server that does not answer into a fact' {
        Mock Invoke-Command { throw 'WinRM cannot complete the operation.' } -ModuleName CoreLab
        $f = @(Get-CoreFacts -ComputerName 'CON-X1', 'CON-X2')
        $f.Count | Should -Be 2
        $f[0].Unreachable | Should -BeTrue
        $f[1].ComputerName | Should -Be 'CON-X2'
        $f[0].Errors[0] | Should -BeLike '*WinRM*'
    }
    It 'passes the collector and the credential, and strips the remoting properties' {
        Mock Invoke-Command { [pscustomobject]@{ ComputerName = 'CON-X1'; PSComputerName = 'CON-X1'; RunspaceId = [guid]::NewGuid(); Unreachable = $false } } -ModuleName CoreLab
        $cred = [pscredential]::new('CONTOSO\lab', (ConvertTo-SecureString 'x' -AsPlainText -Force))
        $f = @(Get-CoreFacts -ComputerName 'CON-X1' -Credential $cred)
        $f[0].PSObject.Properties.Name | Should -Not -Contain 'RunspaceId'
        Should -Invoke Invoke-Command -ModuleName CoreLab -Times 1 -ParameterFilter { $Credential -and $ScriptBlock.ToString() -eq (Get-CoreCollectorScript).ToString() }
    }
}

Describe 'Test-CoreHost on the lab as it is today' {
    BeforeAll { $script:F = Test-Facts (Get-Facts 'before') }
    It 'finds 6 things, 1 of them high' {
        $script:F.Count | Should -Be 6
        @($script:F | Where-Object Severity -eq 'High').Count | Should -Be 1
    }
    It 'treats a Core server that does not answer as high, and stops there' {
        Get-Checks $script:F 'CON-CLI01' | Should -Be @('Unreachable')
        ($script:F | Where-Object Check -eq 'Unreachable').Fix | Should -BeLike '*SConfig*option 4*'
    }
    It 'asks for the App Compatibility FOD where the config says it is required' {
        Get-Checks $script:F 'CON-SRV01' | Should -Be @('AppCompatMissing')
        ($script:F | Where-Object Check -eq 'AppCompatMissing').Message | Should -BeLike '*mmc.exe*'
    }
    It 'flags the missing firewall rules and the big system drive on the SQL server' {
        Get-Checks $script:F 'CON-SQL01' | Should -Be @('WinRmFirewall', 'FootprintHigh')
    }
    It 'accepts a Desktop Experience server that has a reason, and lists what would block Core' {
        Get-Checks $script:F 'CON-SRV02' | Should -Be @('CoreBlockers', 'DesktopJustified')
        $b = ($script:F | Where-Object Check -eq 'CoreBlockers').Message
        $b | Should -BeLike '*6 installed feature(s)*'
        $b | Should -BeLike '*Hyper-V-Tools*RSAT-ADCS*Web-Mgmt-Console*'
    }
    It 'says nothing about a healthy domain controller' {
        Get-Checks $script:F 'CON-DC01' | Should -BeNullOrEmpty
    }
}

Describe 'The lab after the fixes, and a neglected one' {
    It 'has only the two information rows left after the fixes' {
        $f = Test-Facts (Get-Facts 'after')
        $f.Count | Should -Be 2
        @($f | Where-Object Severity -ne 'Info').Count | Should -Be 0
    }
    It 'finds a wrong install type in both directions' {
        $f = Test-Facts (Get-Facts 'bad')
        ($f | Where-Object { $_.Target -eq 'CON-DC01' -and $_.Check -eq 'InstallTypeMismatch' }).Message | Should -BeLike '*Expected Core, found DesktopExperience*no in-place conversion*'
        ($f | Where-Object { $_.Target -eq 'CON-SRV02' -and $_.Check -eq 'InstallTypeMismatch' }).Message | Should -BeLike '*Expected DesktopExperience, found Core*'
        ($f | Where-Object { $_.Target -eq 'CON-DC01' -and $_.Check -eq 'CoreBlockers' }).Message | Should -BeLike '*RSAT-ADCS*'
    }
    It 'finds a FOD nobody needs, a host it does not know, and an unreadable install type' {
        $f = Test-Facts (Get-Facts 'bad')
        Get-Checks $f 'CON-SQL01' | Should -Contain 'AppCompatNotNeeded'
        Get-Checks $f 'CON-SQL01' | Should -Contain 'FootprintHigh'
        Get-Checks $f 'CON-OLD99' | Should -Be @('UnknownHost')
        Get-Checks $f 'CON-CLI01' | Should -Be @('CollectorError', 'InstallTypeUnknown')
    }
    It 'reports collector errors as findings, not as silence' {
        $f = Test-Facts (Get-Facts 'bad')
        ($f | Where-Object { $_.Target -eq 'CON-SQL01' -and $_.Check -eq 'CollectorError' }).Message | Should -BeLike 'Get-WindowsFeature*'
    }
    It 'does not ask for firewall rules when the number is unknown (-1)' {
        Get-Checks (Test-Facts (Get-Facts 'bad')) 'CON-CLI01' | Should -Not -Contain 'WinRmFirewall'
    }
    It 'follows the policy in the config, not a constant' {
        $c = Get-ConfigCopy; $c.Policy.MaxCoreSystemDriveUsedGB = 25
        Get-Checks (Test-Facts (Get-Facts 'bad') (Read-CoreLabConfig -Path (Save-Config $c))) 'CON-SQL01' | Should -Not -Contain 'FootprintHigh'
    }
}

Describe 'Get-CoreFootprint' {
    It 'averages by install type over the servers that answered' {
        $fp = @(Get-CoreFootprint -Hosts @((Get-Facts 'before').Hosts))
        $fp.Count | Should -Be 2
        $core = $fp | Where-Object InstallType -eq 'Core'
        $core.Hosts | Should -Be 3
        $core.AvgDiskUsedGB | Should -Be 14.1
        $core.AvgMemoryUsedMB | Should -Be 1050
        $core.AvgRunningServices | Should -Be 48
        $core.AvgFeatures | Should -Be 7.7
        ($fp | Where-Object InstallType -eq 'DesktopExperience').AvgDiskUsedGB | Should -Be 24.8
    }
    It 'returns nothing when no server answered' {
        @(Get-CoreFootprint -Hosts @([pscustomobject]@{ ComputerName = 'A'; Unreachable = $true })).Count | Should -Be 0
    }
}

Describe 'Test-NanoDockerfile' {
    It 'finds Windows PowerShell in a Nano Server stage, with the line numbers' {
        $f = @(Test-NanoDockerfile -Content (Get-Dockerfile 'Dockerfile.nano-bad') -Name 'bad' -Config $script:Config)
        $ps = @($f | Where-Object Check -eq 'NanoNoPowerShell')
        $ps.Count | Should -Be 2
        @($ps | ForEach-Object Target | Sort-Object) | Should -Be @('bad:11', 'bad:8')
        $ps[0].Severity | Should -Be 'High'
        $ps[0].Message | Should -BeLike '*no PowerShell (Learn)*'
    }
    It 'flags an unpinned tag where there is one, and only there' {
        $f = @(Test-NanoDockerfile -Content (Get-Dockerfile 'Dockerfile.nano-bad') -Name 'bad' -Config $script:Config)
        @($f | Where-Object Check -eq 'UnpinnedTag').Count | Should -Be 1
        ($f | Where-Object Check -eq 'UnpinnedTag').Target | Should -Be 'bad:7'
    }
    It 'passes the fixed file, including a continuation line with a custom escape character' {
        @(Test-NanoDockerfile -Content (Get-Dockerfile 'Dockerfile.nano-good') -Name 'good' -Config $script:Config).Count | Should -Be 0
    }
    It 'does not blame a Server Core stage for PowerShell, and says that Nano may fit' {
        $f = @(Test-NanoDockerfile -Content (Get-Dockerfile 'Dockerfile.servercore') -Name 'core' -Config $script:Config)
        $f.Count | Should -Be 1
        $f[0].Check | Should -Be 'ServerCoreBase'
        $f[0].Severity | Should -Be 'Info'
    }
    It 'follows a stage that is built FROM an earlier stage' {
        $d = "FROM mcr.microsoft.com/windows/nanoserver:ltsc2025 AS base`nFROM base AS final`nRUN powershell -Command Get-Date`n"
        $f = @(Test-NanoDockerfile -Content $d -Name 'x' -Config $script:Config)
        $f.Count | Should -Be 1
        $f[0].Target | Should -Be 'x:3'
    }
    It 'reads a nanoserver variant of another image, and accepts a digest as a pin' {
        $d = "FROM mcr.microsoft.com/dotnet/aspnet:9.0-nanoserver-ltsc2025`nSHELL [`"powershell.exe`"]`n"
        @(Test-NanoDockerfile -Content $d -Name 'x' -Config $script:Config | Where-Object Check -eq 'NanoNoPowerShell').Count | Should -Be 1
        $d = "FROM mcr.microsoft.com/windows/nanoserver@sha256:0123456789abcdef`nRUN cmd /c echo ok`n"
        @(Test-NanoDockerfile -Content $d -Name 'x' -Config $script:Config).Count | Should -Be 0
    }
    It 'leaves PowerShell 7, other words and other instructions alone' {
        $d = "FROM mcr.microsoft.com/windows/nanoserver:ltsc2025`nRUN pwsh -c Get-Date`nRUN echo powershell-is-absent`nCOPY powershell.zip C:\`n"
        @(Test-NanoDockerfile -Content $d -Name 'x' -Config $script:Config).Count | Should -Be 0
    }
    It 'accepts an unpinned tag when the policy says so' {
        $c = Get-ConfigCopy; $c.Policy.RequirePinnedImageTag = $false
        $cfg = Read-CoreLabConfig -Path (Save-Config $c)
        @(Test-NanoDockerfile -Content "FROM mcr.microsoft.com/windows/nanoserver`n" -Name 'x' -Config $cfg).Count | Should -Be 0
    }
}

Describe 'The setup plan' {
    BeforeAll { $script:Plan = @(Get-CoreSetupPlan -Hosts @((Get-Facts 'before').Hosts) -Config $script:Config) }
    It 'has a step for each finding that can be fixed from here, in order' {
        @($script:Plan | ForEach-Object { "$($_.Target):$($_.Id)" }) | Should -Be @('CON-SRV01:AppCompatFod', 'CON-SRV01:Restart', 'CON-SQL01:WinRmFirewall', 'CON-CLI01:Console')
    }
    It 'makes the unreachable server a manual step that points at SConfig, and says why not remotely' {
        $s = $script:Plan | Where-Object Id -eq 'Console'
        $s.Kind | Should -Be 'Manual'
        $s.Description | Should -BeLike '*option 4*cannot run in a remote PowerShell session*'
        $s.Script | Should -BeNullOrEmpty
    }
    It 'generates scripts that parse, with the values quoted' {
        foreach ($s in @($script:Plan | Where-Object Kind -eq 'Run')) {
            $err = $null; [void][Parser]::ParseInput($s.Script, [ref]$null, [ref]$err)
            @($err).Count | Should -Be 0
        }
        ($script:Plan | Where-Object Id -eq 'AppCompatFod').Script | Should -BeLike "*Add-WindowsCapability -Online -Name 'ServerCore.AppCompatibility~~~~0.0.1.0'*"
        ($script:Plan | Where-Object Id -eq 'WinRmFirewall').Script | Should -Be 'Enable-NetFirewallRule -DisplayGroup "Windows Remote Management"'
    }
    It 'uses a local source for the FOD when the config gives one' {
        $c = Get-ConfigCopy; $c.Setup.FodSourcePath = 'D:\LanguagesAndOptionalFeatures'
        $p = @(Get-CoreSetupPlan -Hosts @((Get-Facts 'before').Hosts) -Config (Read-CoreLabConfig -Path (Save-Config $c)))
        $s = $p | Where-Object Id -eq 'AppCompatFod'
        $s.Script | Should -BeLike "*-Source 'D:\LanguagesAndOptionalFeatures' -LimitAccess*"
        $s.Description | Should -BeLike '*D:\LanguagesAndOptionalFeatures*'
    }
    It 'marks the restart as needing a switch' {
        ($script:Plan | Where-Object Id -eq 'Restart').NeedsSwitch | Should -Be 'AllowRestart'
    }
    It 'plans a rebuild, never a conversion, for a server of the wrong install type' {
        $p = @(Get-CoreSetupPlan -Hosts @((Get-Facts 'bad').Hosts) -Config $script:Config)
        @($p | Where-Object Id -eq 'Rebuild').Count | Should -Be 2
        (($p | Where-Object Id -eq 'Rebuild')[0]).Description | Should -BeLike '*no in-place conversion*'
        @($p | Where-Object { $_.Id -eq 'Rebuild' -and $_.Kind -ne 'Manual' }).Count | Should -Be 0
    }
    It 'has nothing to do on the fixed lab' {
        @(Get-CoreSetupPlan -Hosts @((Get-Facts 'after').Hosts) -Config $script:Config).Count | Should -Be 0
    }
}

Describe 'Invoke-CoreSetupPlan' {
    BeforeEach {
        $script:Plan = @(Get-CoreSetupPlan -Hosts @((Get-Facts 'before').Hosts) -Config $script:Config)
        Mock Invoke-Command { [pscustomobject]@{ RestartNeeded = $true } } -ModuleName CoreLab
        Mock Restart-Computer { } -ModuleName CoreLab
    }
    It 'with -WhatIf runs nothing and restarts nothing' {
        $r = @(Invoke-CoreSetupPlan -Plan $script:Plan -AllowRestart -WhatIf)
        Should -Invoke Invoke-Command -ModuleName CoreLab -Times 0
        Should -Invoke Restart-Computer -ModuleName CoreLab -Times 0
        @($r | Where-Object Result -eq 'Manual').Count | Should -Be 1
    }
    It 'runs the Run steps, reports the restart need, and skips the restart without the switch' {
        $r = @(Invoke-CoreSetupPlan -Plan $script:Plan)
        Should -Invoke Invoke-Command -ModuleName CoreLab -Times 2
        Should -Invoke Restart-Computer -ModuleName CoreLab -Times 0
        ($r | Where-Object Id -eq 'AppCompatFod').Detail | Should -Be 'restart needed'
        ($r | Where-Object Id -eq 'Restart').Result | Should -Be 'Skipped'
        ($r | Where-Object Id -eq 'Restart').Detail | Should -BeLike '*-AllowRestart*'
        ($r | Where-Object Id -eq 'Console').Result | Should -Be 'Manual'
    }
    It 'restarts only with -AllowRestart, once, on the right server' {
        $null = Invoke-CoreSetupPlan -Plan $script:Plan -AllowRestart
        Should -Invoke Restart-Computer -ModuleName CoreLab -Times 1 -ParameterFilter { $ComputerName -eq 'CON-SRV01' -and $Force }
    }
    It 'never runs a manual step' {
        $null = Invoke-CoreSetupPlan -Plan $script:Plan -AllowRestart
        Should -Invoke Invoke-Command -ModuleName CoreLab -Times 0 -ParameterFilter { $ComputerName -eq 'CON-CLI01' }
    }
    It 'stops a server at its first failure and goes on with the others' {
        Mock Invoke-Command { if ($ComputerName -eq 'CON-SRV01') { throw 'Source files not found.' }; $null } -ModuleName CoreLab
        $r = @(Invoke-CoreSetupPlan -Plan $script:Plan -AllowRestart)
        ($r | Where-Object Id -eq 'AppCompatFod').Result | Should -Be 'Failed'
        ($r | Where-Object Id -eq 'Restart').Result | Should -Be 'Skipped'
        ($r | Where-Object Id -eq 'Restart').Detail | Should -BeLike '*earlier step*'
        ($r | Where-Object Id -eq 'WinRmFirewall').Result | Should -Be 'Done'
        Should -Invoke Restart-Computer -ModuleName CoreLab -Times 0
    }
}

Describe 'Report and entry scripts' {
    It 'writes the report with the footprint table and a row for a server that did not answer' {
        $h = @((Get-Facts 'before').Hosts)
        $md = ConvertTo-CoreMarkdown -Hosts $h -Findings (Test-Facts (Get-Facts 'before'))
        $md | Should -BeLike '*# Server Core check*## Footprint by install type*not a benchmark*'
        $md | Should -BeLike '*| CON-CLI01 | no answer |*'
        $md | Should -BeLike '*| Core | 3 | 14.1 | 1050 | 48 | 7.7 |*'
    }
    It 'keeps the committed samples equal to what the scripts print' {
        $out = Join-Path ([IO.Path]::GetTempPath()) ('core-' + [guid]::NewGuid().ToString('N') + '.md')
        foreach ($n in 'before', 'after', 'bad') {
            $null = & pwsh -NoProfile -File (Join-Path $script:Src 'Invoke-CoreCheck.ps1') -FromFacts (Join-Path $script:Fixtures "facts-$n.json") -OutFile $out
            # Compare text, not line endings (Windows writes CRLF, the committed samples are LF).
            ((Get-Content -Raw $out) -replace "`r`n", "`n") | Should -Be ((Get-Content -Raw (Join-Path $script:Sample "check-$n.md")) -replace "`r`n", "`n")
        }
    }
    It 'exits 1 with -FailOnHigh when there is a high finding, 0 when there is none' {
        $null = & pwsh -NoProfile -File (Join-Path $script:Src 'Invoke-CoreCheck.ps1') -FromFacts (Join-Path $script:Fixtures 'facts-before.json') -FailOnHigh
        $LASTEXITCODE | Should -Be 1
        $null = & pwsh -NoProfile -File (Join-Path $script:Src 'Invoke-CoreCheck.ps1') -FromFacts (Join-Path $script:Fixtures 'facts-after.json') -FailOnHigh
        $LASTEXITCODE | Should -Be 0
    }
    It 'checks a Dockerfile from the entry script' {
        $o = (& pwsh -NoProfile -File (Join-Path $script:Src 'Invoke-CoreCheck.ps1') -FromFacts (Join-Path $script:Fixtures 'facts-after.json') -Dockerfile (Join-Path $script:Fixtures 'Dockerfile.nano-bad')) -join "`n"
        $o | Should -BeLike '*NanoNoPowerShell*'
        $o | Should -BeLike '*, 2 high.*'
    }
    It 'prints the plan and the What if lines for the deploy script, and no restart without the switch' {
        $o = (& pwsh -NoProfile -File (Join-Path $script:Src 'Deploy-CoreLab.ps1') -FromFacts (Join-Path $script:Fixtures 'facts-before.json') -WhatIf 2>&1) -join "`n"
        $o | Should -BeLike '*What if*App Compatibility FOD*CON-SRV01*'
        $o | Should -BeLike '*What if*Windows Remote Management*CON-SQL01*'
        $o | Should -BeLike '*Skipped*-AllowRestart*'
        $o | Should -Not -BeLike '*What if*Restart the server*'
    }
}
