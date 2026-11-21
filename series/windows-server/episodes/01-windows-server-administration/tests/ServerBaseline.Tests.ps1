using namespace System.Management.Automation.Language

BeforeAll {
    $src = Join-Path $PSScriptRoot '../src'
    Import-Module (Join-Path $src 'ServerBaseline/ServerBaseline.psd1') -Force
    $script:Baseline = Get-Content -Raw (Join-Path $src 'baseline.json') | ConvertFrom-Json
    $script:Now = [datetime]::new(2026, 11, 20, 9, 0, 0, [DateTimeKind]::Utc)

    function Get-Fixture([string] $Name) {
        Get-Content -Raw (Join-Path $PSScriptRoot "fixtures/$Name.json") | ConvertFrom-Json | ConvertTo-SbSnapshot
    }
    function Get-Check($Snapshot, [string] $Check) {
        @(Test-SbBaseline -Snapshot $Snapshot -Baseline $script:Baseline -Now $script:Now | Where-Object Check -eq $Check)
    }
}

Describe 'Collector script' {
    BeforeAll {
        $script:Ast = (Get-SbCollectorScript).Ast
        $script:Find = { param($predicate) @($script:Ast.FindAll($predicate, $true)) }
    }

    It 'has no PowerShell 7-only syntax (remote sessions run Windows PowerShell 5.1 by default)' {
        $ternary = & $script:Find { param($n) $n -is [TernaryExpressionAst] }
        $chain = & $script:Find { param($n) $n -is [PipelineChainAst] }
        $coalesce = & $script:Find {
            param($n)
            ($n -is [BinaryExpressionAst] -and "$($n.Operator)" -eq 'QuestionQuestion') -or
            ($n -is [AssignmentStatementAst] -and "$($n.Operator)" -eq 'QuestionQuestionEquals')
        }
        $nullConditional = & $script:Find {
            param($n) ($n -is [MemberExpressionAst] -and $n.NullConditional) -or
            ($n -is [IndexExpressionAst] -and $n.NullConditional)
        }
        $ternary.Count + $chain.Count + $coalesce.Count + $nullConditional.Count | Should -Be 0
    }

    It 'calls no ServerBaseline function (it must be self-contained to run remotely)' {
        $exported = (Get-Module ServerBaseline).ExportedFunctions.Keys
        $commands = (& $script:Find { param($n) $n -is [CommandAst] }) |
            ForEach-Object { $_.GetCommandName() }
        $commands | Where-Object { $_ -in $exported } | Should -BeNullOrEmpty
    }

    It 'reads local Administrators by SID, not by its English name' {
        (Get-SbCollectorScript).ToString() | Should -Match "Get-LocalGroupMember -SID 'S-1-5-32-544'"
    }
}

Describe 'ConvertTo-SbSnapshot' {
    It 'drops the properties remoting adds' {
        $remote = Get-Content -Raw (Join-Path $PSScriptRoot 'fixtures/con-app01.json') | ConvertFrom-Json
        $remote | Add-Member PSComputerName 'CON-APP01'
        $remote | Add-Member RunspaceId ([guid]::Empty)
        $snap = $remote | ConvertTo-SbSnapshot
        $snap.PSObject.Properties.Name | Should -Not -Contain 'PSComputerName'
        $snap.PSObject.Properties.Name | Should -Not -Contain 'RunspaceId'
        $snap.Os.Build | Should -Be 26100
    }
    It 'rejects an unknown schema version' {
        { [pscustomobject]@{ SchemaVersion = 2; ComputerName = 'X' } | ConvertTo-SbSnapshot } | Should -Throw '*schema version*'
    }
}

Describe 'Get-SbSnapshot' {
    It 'fans out with Invoke-Command, sending the collector script' {
        Mock Invoke-Command -ModuleName ServerBaseline {
            foreach ($c in $ComputerName) {
                [pscustomobject]@{ SchemaVersion = 1; ComputerName = $c; PSComputerName = $c; RunspaceId = [guid]::Empty }
            }
        }
        $r = @(Get-SbSnapshot -ComputerName 'CON-A', 'CON-B')
        $r.ComputerName | Should -Be @('CON-A', 'CON-B')
        Should -Invoke Invoke-Command -ModuleName ServerBaseline -Times 1 -Exactly -ParameterFilter {
            $ScriptBlock.ToString() -eq (Get-SbCollectorScript).ToString() -and $ThrottleLimit -eq 32
        }
    }
}

Describe 'Test-SbBaseline: a healthy server' {
    It 'CON-APP01 only gets the informational file-rename note' {
        $f = @(Test-SbBaseline -Snapshot (Get-Fixture 'con-app01') -Baseline $script:Baseline -Now $script:Now)
        $f.Count | Should -Be 1
        $f[0].Check | Should -Be 'PendingFileRename'
        $f[0].Severity | Should -Be 'Info'
    }
}

Describe 'Test-SbBaseline: individual checks' {
    It 'flags a build below the baseline' {
        $s = Get-Fixture 'con-app01'; $s.Os.Build = 20348
        (Get-Check $s 'OsBuild')[0].Severity | Should -Be 'High'
    }
    It 'flags a patch level (UBR) below the minimum' {
        $s = Get-Fixture 'con-app01'
        $b = $script:Baseline | ConvertTo-Json -Depth 5 | ConvertFrom-Json; $b.MinimumUbr = 40000
        @(Test-SbBaseline -Snapshot $s -Baseline $b -Now $script:Now | Where-Object Check -eq 'OsPatchLevel').Count | Should -Be 1
    }
    It 'notes the evaluation edition' {
        (Get-Check (Get-Fixture 'con-dc01') 'EvaluationEdition')[0].Severity | Should -Be 'Info'
    }
    It 'prefers Server Core when the baseline says so' {
        (Get-Check (Get-Fixture 'con-fs01') 'InstallationType')[0].Severity | Should -Be 'Low'
        Get-Check (Get-Fixture 'con-app01') 'InstallationType' | Should -BeNullOrEmpty
    }
    It 'flags uptime over the limit, with the day count' {
        (Get-Check (Get-Fixture 'con-fs01') 'Uptime')[0].Detail | Should -Match 'Up for 110 days'
    }
    It 'treats a Windows Update reboot as High' {
        (Get-Check (Get-Fixture 'con-fs01') 'PendingReboot')[0].Detail | Should -Be 'Reboot pending: Windows Update.'
    }
    It 'treats a pending computer rename as a pending reboot' {
        $s = Get-Fixture 'con-app01'; $s.PendingReboot.ComputerRename = $true
        (Get-Check $s 'PendingReboot')[0].Detail | Should -Match 'computer rename'
    }
    It 'does not double-report PendingFileRename when a real reboot is pending' {
        Get-Check (Get-Fixture 'con-fs01') 'PendingFileRename' | Should -BeNullOrEmpty
    }
    It 'flags the last update being too old' {
        (Get-Check (Get-Fixture 'con-fs01') 'Updates')[0].Detail | Should -Match '128 days ago \(2026-07-15\)'
    }
    It 'ignores undated hotfix entries but warns when nothing is dated' {
        $s = Get-Fixture 'con-app01'
        $s.Hotfixes = @([pscustomobject]@{ Id = 'KB1'; Description = 'Update'; InstalledOn = $null })
        (Get-Check $s 'Updates')[0].Detail | Should -Match 'Get-HotFix only lists CBS updates'
    }
    It 'grades disk space: <Free> GB free of 100 is <Expected>' -ForEach @(
        @{ Free = 25; Expected = $null }, @{ Free = 15; Expected = 'Medium' }, @{ Free = 5; Expected = 'High' }
    ) {
        $s = Get-Fixture 'con-app01'
        $s.Disks = @([pscustomobject]@{ Drive = 'E:'; SizeGB = 100; FreeGB = $Free })
        $r = Get-Check $s 'DiskSpace'
        if ($Expected) { $r[0].Severity | Should -Be $Expected } else { $r | Should -BeNullOrEmpty }
    }
    It 'reports stopped automatic services unless they match the ignore list (wildcards)' {
        $s = Get-Fixture 'con-fs01'
        (Get-Check $s 'Service').Count | Should -Be 1
        $b = $script:Baseline | ConvertTo-Json -Depth 5 | ConvertFrom-Json
        $b.IgnoreStoppedServices = @('Contoso*')
        @(Test-SbBaseline -Snapshot $s -Baseline $b -Now $script:Now | Where-Object Check -eq 'Service').Count | Should -Be 0
    }
    It 'flags SMB1 as a forbidden feature' {
        (Get-Check (Get-Fixture 'con-fs01') 'ForbiddenFeature')[0].Detail | Should -Match 'FS-SMB1'
    }
    It 'checks required features by server name pattern' {
        $s = Get-Fixture 'con-dc01'
        $s.InstalledFeatures = @($s.InstalledFeatures | Where-Object { $_ -ne 'DNS' })
        (Get-Check $s 'MissingFeature')[0].Detail | Should -Match "'DNS'.*CON-DC\*"
    }
    It 'flags a domain controller running on its own CMOS clock' {
        (Get-Check (Get-Fixture 'con-dc01') 'TimeSource')[0].Severity | Should -Be 'High'
    }
    It 'flags each firewall profile that is off' {
        $r = Get-Check (Get-Fixture 'con-fs01') 'Firewall'
        $r.Count | Should -Be 1
        $r[0].Detail | Should -Match "'Public'"
    }
    It 'allows RDP only on servers in RdpAllowed' {
        Get-Check (Get-Fixture 'con-fs01') 'Rdp' | Should -HaveCount 1
        $s = Get-Fixture 'con-fs01'; $s.ComputerName = 'CON-JUMP01'
        Get-Check $s 'Rdp' | Should -BeNullOrEmpty
    }
    It 'flags unexpected local admins, matching DOMAIN\name and plain names' {
        $r = Get-Check (Get-Fixture 'con-fs01') 'LocalAdministrators'
        $r.Count | Should -Be 1
        $r[0].Detail | Should -Match 'alex\.demo'
    }
    It 'skips local admins on a domain controller with an Info note' {
        (Get-Check (Get-Fixture 'con-dc01') 'LocalAdministrators')[0].Severity | Should -Be 'Info'
    }
}

Describe 'Report' {
    BeforeAll {
        $script:All = @('con-dc01', 'con-fs01', 'con-app01') | ForEach-Object {
            Test-SbBaseline -Snapshot (Get-Fixture $_) -Baseline $script:Baseline -Now $script:Now
        }
    }
    It 'orders High first' {
        $sorted = @($script:All | Format-SbFindingOrder)
        $sorted[0].Severity | Should -Be 'High'
        $sorted[-1].Severity | Should -Be 'Info'
    }
    It 'writes one summary row per server with the right counts' {
        $md = ConvertTo-SbMarkdown -Finding $script:All -Server 'CON-DC01', 'CON-FS01', 'CON-APP01' -Now $script:Now
        $md | Should -Match '\| CON-FS01 \| 5 \| 3 \| 2 \| 0 \|'
        $md | Should -Match '\| CON-DC01 \| 1 \| 0 \| 0 \| 2 \|'
    }
    It 'keeps an unreachable server in the report as High' {
        $f = New-SbUnreachableFinding -Server 'CON-OLD01' -Reason 'WinRM cannot complete the operation.'
        $md = ConvertTo-SbMarkdown -Finding @($f) -Server 'CON-OLD01' -Now $script:Now
        $md | Should -Match '\| High \| CON-OLD01 \| Unreachable \|'
    }
}

Describe 'Invoke-ServerBaseline.ps1 (offline, end to end)' {
    It 'writes the report and exits 1 with -FailOnHigh' {
        $out = Join-Path ([IO.Path]::GetTempPath()) "sb-report-$([guid]::NewGuid()).md"
        $script = Join-Path $PSScriptRoot '../src/Invoke-ServerBaseline.ps1'
        $fixtures = Join-Path $PSScriptRoot 'fixtures/*.json'
        # -Command, not -File: on Linux a native call would let the shell-style globbing expand *.json first.
        & pwsh -NoProfile -Command "& '$script' -FromSnapshot '$fixtures' -Now 2026-11-20T09:00:00Z -OutFile '$out' -FailOnHigh" | Out-Null
        $LASTEXITCODE | Should -Be 1
        Get-Content -Raw $out | Should -Match '3 server\(s\)'
        Remove-Item $out
    }
}
