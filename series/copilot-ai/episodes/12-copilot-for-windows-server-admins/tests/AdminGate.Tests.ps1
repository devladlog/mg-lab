BeforeAll {
    $src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'AdminGate' 'AdminGate.psm1') -Force
    function Gate([string] $Text, [string] $Mode = 'ReadOnly') { Test-AdminScript -ScriptText $Text -Mode $Mode -SkipResolution }
    function Rules($r) { @($r.Findings | ForEach-Object Rule) }
}

Describe 'parsing' {
    It 'blocks a script that does not parse (AG-X001)' {
        $r = Gate 'Get-Service -Name {'
        Rules $r | Should -Contain 'AG-X001'
        $r.ExitCode | Should -Be 2
    }
    It 'reports a clean read-only script as Clean' {
        $r = Gate 'Get-Service -Name W32Time | Select-Object Name, Status'
        $r.Verdict | Should -Be 'Clean'
        $r.ExitCode | Should -Be 0
    }
    It 'ignores change words in comments and strings' {
        $r = Gate "# Remove-Item C:\ -Recurse`nWrite-Output 'Format-Volume -DriveLetter D'"
        $r.Verdict | Should -Be 'Clean'
    }
}

Describe 'read-only mode (AG-M001)' {
    It 'blocks a state-changing cmdlet' {
        $r = Gate 'Restart-Service -Name Spooler'
        Rules $r | Should -Contain 'AG-M001'
    }
    It 'resolves aliases: rm is Remove-Item' {
        (Rules (Gate 'rm .\old.txt')) | Should -Contain 'AG-M001'
    }
    It 'allows a literal -WhatIf' {
        (Rules (Gate 'Restart-Service -Name Spooler -WhatIf')) | Should -Not -Contain 'AG-M001'
    }
    It 'does not accept -WhatIf:$false as safe' {
        (Rules (Gate 'Restart-Service -Name Spooler -WhatIf:$false')) | Should -Contain 'AG-M001'
    }
    It 'does not accept a propagated -WhatIf:$var as a literal' {
        (Rules (Gate 'Restart-Service -Name Spooler -WhatIf:$WhatIfPreference')) | Should -Contain 'AG-M001'
    }
    It 'does not flag session-only commands such as New-Object or Set-StrictMode' {
        $r = Gate "Set-StrictMode -Version Latest`n`$x = New-Object System.Text.StringBuilder"
        $r.Verdict | Should -Be 'Clean'
    }
    It 'is not applied in Change mode' {
        $text = "function Restart-Spooler {`n[CmdletBinding(SupportsShouldProcess)]param()`nRestart-Service Spooler}"
        $r = Gate $text 'Change'
        Rules $r | Should -Not -Contain 'AG-M001'
        $r.Verdict | Should -Be 'Clean'
    }
}

Describe 'dangerous execution (AG-D001)' {
    It 'blocks Invoke-Expression' { (Rules (Gate 'Invoke-Expression $x' 'Change')) | Should -Contain 'AG-D001' }
    It 'blocks the iex alias' { (Rules (Gate 'iex $x' 'Change')) | Should -Contain 'AG-D001' }
    It 'blocks download and execute' {
        (Rules (Gate 'iex (Invoke-WebRequest https://example.invalid/a.ps1).Content' 'Change')) | Should -Contain 'AG-D001'
    }
    It 'blocks -EncodedCommand and its short forms' {
        (Rules (Gate 'powershell.exe -enc SQBFAFgA' 'Change')) | Should -Contain 'AG-D001'
        (Rules (Gate 'pwsh -EncodedCommand SQBFAFgA' 'Change')) | Should -Contain 'AG-D001'
    }
    It 'blocks Set-ExecutionPolicy Bypass' {
        (Rules (Gate 'Set-ExecutionPolicy Bypass -Scope Process' 'Change')) | Should -Contain 'AG-D001'
    }
    It 'accepts Set-ExecutionPolicy RemoteSigned' {
        (Rules (Gate 'Set-ExecutionPolicy RemoteSigned -WhatIf' 'Change')) | Should -Not -Contain 'AG-D001'
    }
}

Describe 'destructive commands (AG-D002)' {
    It 'blocks Format-Volume even in Change mode' { (Rules (Gate 'Format-Volume -DriveLetter D' 'Change')) | Should -Contain 'AG-D002' }
    It 'accepts Format-Volume with a literal -WhatIf' { (Rules (Gate 'Format-Volume -DriveLetter D -WhatIf' 'Change')) | Should -Not -Contain 'AG-D002' }
    It 'blocks Remove-Item -Recurse on a drive root' { (Rules (Gate 'Remove-Item C:\ -Recurse' 'Change')) | Should -Contain 'AG-D002' }
    It 'blocks Remove-Item -Recurse on C:\Windows' { (Rules (Gate 'Remove-Item C:\Windows -Recurse' 'Change')) | Should -Contain 'AG-D002' }
    It 'does not block Remove-Item -Recurse on a temp folder' { (Rules (Gate 'Remove-Item C:\Temp\old -Recurse -WhatIf' 'Change')) | Should -Not -Contain 'AG-D002' }
    It 'blocks switching the firewall profile off' { (Rules (Gate 'Set-NetFirewallProfile -Profile Domain -Enabled False' 'Change')) | Should -Contain 'AG-D002' }
    It 'blocks Remove-ADUser' { (Rules (Gate 'Remove-ADUser -Identity jdoe' 'Change')) | Should -Contain 'AG-D002' }
    It 'blocks switching Defender real-time monitoring off' {
        (Rules (Gate 'Set-MpPreference -DisableRealtimeMonitoring $true' 'Change')) | Should -Contain 'AG-D002'
    }
}

Describe 'ShouldProcess and force (AG-C001, AG-C002)' {
    It 'warns when a change has no SupportsShouldProcess in scope' {
        (Rules (Gate 'Restart-Service Spooler' 'Change')) | Should -Contain 'AG-C001'
    }
    It 'does not warn inside a function with SupportsShouldProcess' {
        $t = "function Restart-Spooler {`n[CmdletBinding(SupportsShouldProcess)]param()`nif (`$PSCmdlet.ShouldProcess('Spooler')) { Restart-Service Spooler }}"
        (Rules (Gate $t 'Change')) | Should -Not -Contain 'AG-C001'
    }
    It 'does not accept SupportsShouldProcess = $false' {
        $t = "function Restart-Spooler {`n[CmdletBinding(SupportsShouldProcess=`$false)]param()`nRestart-Service Spooler}"
        (Rules (Gate $t 'Change')) | Should -Contain 'AG-C001'
    }
    It 'accepts a script-level SupportsShouldProcess' {
        $t = "[CmdletBinding(SupportsShouldProcess)]`nparam()`nRestart-Service Spooler"
        (Rules (Gate $t 'Change')) | Should -Not -Contain 'AG-C001'
    }
    It 'warns on -Confirm:$false' {
        (Rules (Gate 'Restart-Service Spooler -Confirm:$false' 'Change')) | Should -Contain 'AG-C002'
    }
    It 'warns on -Force for a change' {
        (Rules (Gate 'Stop-Service Spooler -Force' 'Change')) | Should -Contain 'AG-C002'
    }
    It 'does not warn on -Force for a read command' {
        (Rules (Gate 'Get-ChildItem C:\Temp -Force' 'Change')) | Should -Not -Contain 'AG-C002'
    }
}

Describe 'fan-out (AG-R001)' {
    It 'warns when Get-ADComputer pipes into a change' {
        (Rules (Gate 'Get-ADComputer -Filter * | Restart-Computer -WhatIf' 'Change')) | Should -Contain 'AG-R001'
    }
    It 'warns when a file of names pipes into a change' {
        (Rules (Gate 'Get-Content .\servers.txt | Stop-Service' 'Change')) | Should -Contain 'AG-R001'
    }
    It 'does not warn when the pipeline only reads' {
        (Rules (Gate 'Get-ADComputer -Filter * | Select-Object Name' 'Change')) | Should -Not -Contain 'AG-R001'
    }
}

Describe 'secrets (AG-S001)' {
    It 'blocks ConvertTo-SecureString -AsPlainText' {
        (Rules (Gate "`$p = ConvertTo-SecureString 'x' -AsPlainText -Force" 'Change')) | Should -Contain 'AG-S001'
    }
    It 'blocks a literal password variable' {
        (Rules (Gate "`$adminPassword = 'Pa55w0rd!'" 'Change')) | Should -Contain 'AG-S001'
    }
    It 'allows a password variable that is not a literal' {
        (Rules (Gate "`$adminPassword = Read-Host -AsSecureString" 'Change')) | Should -Not -Contain 'AG-S001'
    }
    It 'blocks a literal passed to -Password' {
        (Rules (Gate "Connect-Thing -Password 'abc'" 'Change')) | Should -Contain 'AG-S001'
    }
}

Describe 'empty catch (AG-T001)' {
    It 'warns on an empty catch' { (Rules (Gate 'try { Get-Date } catch { }')) | Should -Contain 'AG-T001' }
    It 'accepts a catch that writes an error' { (Rules (Gate 'try { Get-Date } catch { Write-Error $_ }')) | Should -Not -Contain 'AG-T001' }
}

Describe 'hallucination checks (AG-H001, AG-H002)' {
    BeforeAll {
        $fake = {
            param($Name)
            if ($Name -eq 'Get-ServerThing') {
                [pscustomobject]@{ Parameters = @{ ComputerName = [pscustomobject]@{ Aliases = @('CN') }; Name = [pscustomobject]@{ Aliases = @() } } }
            }
        }
        function GateR([string] $Text) { Test-AdminScript -ScriptText $Text -Mode Change -CommandResolver $fake }
    }
    It 'warns about a command the resolver does not know' { (Rules (GateR 'Get-Nothing')) | Should -Contain 'AG-H001' }
    It 'blocks an unknown parameter on a known command' {
        $r = GateR 'Get-ServerThing -Colour red'
        Rules $r | Should -Contain 'AG-H002'
        $r.ExitCode | Should -Be 2
    }
    It 'accepts a known parameter, an alias and a unique prefix' {
        (Rules (GateR 'Get-ServerThing -ComputerName a')) | Should -BeNullOrEmpty
        (Rules (GateR 'Get-ServerThing -CN a')) | Should -BeNullOrEmpty
        (Rules (GateR 'Get-ServerThing -Comp a')) | Should -BeNullOrEmpty
    }
    It 'accepts common parameters' { (Rules (GateR 'Get-ServerThing -Verbose -ErrorAction Stop')) | Should -BeNullOrEmpty }
    It 'does not check functions defined in the script itself' {
        (Rules (GateR "function Get-Mine { param(`$x) }`nGet-Mine -x 1")) | Should -Not -Contain 'AG-H001'
    }
    It 'works with the real Get-Command: a typo in a built-in cmdlet' {
        $r = Test-AdminScript -ScriptText 'Get-ChildItem -Foo x' -Mode ReadOnly
        Rules $r | Should -Contain 'AG-H002'
    }
    It 'works with the real Get-Command: an invented cmdlet' {
        (Rules (Test-AdminScript -ScriptText 'Get-Servise -Name Spooler' -Mode ReadOnly)) | Should -Contain 'AG-H001'
    }
    It 'accepts a real cmdlet with real parameters' {
        $r = Test-AdminScript -ScriptText 'Get-ChildItem -Path . -Recurse -File' -Mode ReadOnly
        $r.Verdict | Should -Be 'Clean'
    }
}

Describe 'files in this episode' {
    BeforeAll { $script:src = Join-Path $PSScriptRoot '..' 'src' }
    It 'Get-ServerHealth.ps1 is Clean in ReadOnly mode' {
        $r = Test-AdminScript -Path (Join-Path $script:src 'scripts' 'Get-ServerHealth.ps1') -Mode ReadOnly -SkipResolution
        $r.Findings | Should -BeNullOrEmpty
    }
    It 'safe-health-check.ps1 is Clean in ReadOnly mode' {
        (Test-AdminScript -Path (Join-Path $script:src 'samples' 'safe-health-check.ps1') -Mode ReadOnly -SkipResolution).Verdict | Should -Be 'Clean'
    }
    It 'risky-examples is blocked and triggers the expected rules' {
        $r = Test-AdminScript -Path (Join-Path $script:src 'samples' 'risky-examples.ps1.txt') -Mode Change -SkipResolution
        $r.ExitCode | Should -Be 2
        $got = Rules $r
        foreach ($rule in 'AG-D001', 'AG-D002', 'AG-S001', 'AG-C001', 'AG-C002', 'AG-R001', 'AG-T001') { $got | Should -Contain $rule }
    }
    It 'the Copilot instructions file stays small and mentions SupportsShouldProcess' {
        $f = Join-Path $script:src 'copilot-config' 'copilot-instructions.md'
        (Get-Item $f).Length | Should -BeLessThan 4000
        (Get-Content $f -Raw) | Should -Match 'SupportsShouldProcess'
    }
    It 'no script contains a literal password' {
        $hits = Get-ChildItem $script:src -Recurse -Include *.ps1, *.psm1, *.md, *.kql | Where-Object { $_.FullName -notmatch 'risky-examples' } |
            Select-String -Pattern "(?i)password\s*=\s*'[^']+'"
        $hits | Should -BeNullOrEmpty
    }
    It 'the KQL file uses only the verified Arc property names' {
        $kql = Get-Content (Join-Path $script:src 'azure' 'arc-servers.kql') -Raw
        $props = [regex]::Matches($kql, 'properties\.(\w+)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
        $ok = 'agentVersion', 'osName', 'osVersion', 'osSku', 'lastStatusChange', 'status', 'osType'
        $props | Where-Object { $ok -notcontains $_ } | Should -BeNullOrEmpty
    }
}

Describe 'command line wrapper' {
    BeforeAll { $script:cli = Join-Path $PSScriptRoot '..' 'src' 'Invoke-AdminGate.ps1'; $script:samples = Join-Path $PSScriptRoot '..' 'src' 'samples' }
    It 'exits 0 for a clean file' {
        pwsh -NoProfile -File $script:cli -Path (Join-Path $script:samples 'safe-health-check.ps1') -SkipResolution | Out-Null
        $LASTEXITCODE | Should -Be 0
    }
    It 'exits 2 and prints JSON for a risky file' {
        $out = pwsh -NoProfile -File $script:cli -Path (Join-Path $script:samples 'risky-examples.ps1.txt') -Mode Change -SkipResolution -Json
        $LASTEXITCODE | Should -Be 2
        ($out | ConvertFrom-Json).Verdict | Should -Be 'Blocked'
    }
}
