using namespace System.Management.Automation.Language

BeforeAll {
    $src = Join-Path $PSScriptRoot '../src'
    Import-Module (Join-Path $src 'GpoLab/GpoLab.psd1') -Force
    $script:Definition = Join-Path $src 'gpo-definitions.json'
    $script:Fixture = Join-Path $PSScriptRoot 'fixtures/gpo-snapshot.json'
    function Get-Snapshot { Get-Content -Raw $script:Fixture | ConvertFrom-Json }
    function Get-Check($Snapshot, [string] $Check) { @(Test-GpoLabHygiene -Snapshot $Snapshot | Where-Object Check -eq $Check) }
    function New-TempDefinition([scriptblock] $Change) {
        $d = Get-Content -Raw $script:Definition | ConvertFrom-Json
        & $Change $d
        $path = Join-Path ([IO.Path]::GetTempPath()) "gpo-def-$([guid]::NewGuid()).json"
        $d | ConvertTo-Json -Depth 8 | Set-Content -Path $path
        $path
    }

    # Stubs so Pester can mock cmdlets that only exist where GPMC / RSAT is installed. Mock copies the stub's
    # parameters, so the stub declares every parameter the module passes (otherwise -ParameterFilter sees nothing).
    $stub = {
        [CmdletBinding()]
        param($Domain, $Server, $Name, $Comment, $Key, $ValueName, $Type, $Value, $Target, $LinkEnabled, $Enforced, $Order,
            [switch] $All, $TargetName, $TargetType, $PermissionLevel, [switch] $Replace, $Guid, $ReportType, $Filter, $Path)
    }
    foreach ($c in 'Get-GPO', 'New-GPO', 'Get-GPRegistryValue', 'Set-GPRegistryValue', 'Get-GPInheritance', 'New-GPLink',
        'Set-GPLink', 'Get-GPPermission', 'Set-GPPermission', 'Get-GPOReport', 'Backup-GPO', 'Get-ADDomain', 'Get-ADOrganizationalUnit') {
        if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { New-Item -Path "function:global:$c" -Value $stub | Out-Null }
    }
    $script:Ids = @{ 'CON-Servers-Baseline' = '00000000-0000-0000-0000-000000000003'; 'CON-Finance-ScreenLock' = '00000000-0000-0000-0000-000000000004' }
}

Describe 'Scope helpers' {
    It '<Key> is a <Half> setting' -ForEach @(
        @{ Key = 'HKLM\Software\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging'; Half = 'Computer' }
        @{ Key = 'HKEY_CURRENT_USER\Software\Policies\Microsoft\Windows\Control Panel\Desktop'; Half = 'User' }
    ) { Get-GpoLabScope -Key $Key | Should -Be $Half }
    It 'refuses other hives' { { Get-GpoLabScope -Key 'HKCR\foo' } | Should -Throw '*HKLM or HKCU*' }
    It 'knows which half a GpoStatus disables' {
        Test-GpoLabHalfEnabled -Status 'UserSettingsDisabled' -Half User | Should -BeFalse
        Test-GpoLabHalfEnabled -Status 'UserSettingsDisabled' -Half Computer | Should -BeTrue
        Test-GpoLabHalfEnabled -Status 'AllSettingsDisabled' -Half Computer | Should -BeFalse
    }
}

Describe 'Read-GpoLabDefinition' {
    It 'accepts the lab definition' {
        $d = Read-GpoLabDefinition -Path $script:Definition
        @($d.Gpos).Count | Should -Be 2
    }
    It 'rejects a setting in a half the status disables' {
        $p = New-TempDefinition { param($d) $d.Gpos[0].Status = 'ComputerSettingsDisabled' }
        { Read-GpoLabDefinition -Path $p } | Should -Throw '*Computer setting but Status*'
        Remove-Item $p
    }
    It 'rejects security filtering without a computer Read group (MS16-072)' {
        $p = New-TempDefinition { param($d) $d.Gpos[1].PSObject.Properties.Remove('ComputerRead') }
        { Read-GpoLabDefinition -Path $p } | Should -Throw '*needs ComputerRead*'
        Remove-Item $p
    }
    It 'rejects links outside the domain and duplicate names' {
        $p = New-TempDefinition { param($d) $d.Gpos[1].Links[0].Target = 'OU=Users,DC=fabrikam,DC=com'; $d.Gpos[1].Name = $d.Gpos[0].Name }
        { Read-GpoLabDefinition -Path $p } | Should -Throw '*Duplicate GPO name*'
        { Read-GpoLabDefinition -Path $p } | Should -Throw '*not in DC=lab,DC=contoso,DC=com*'
        Remove-Item $p
    }
}

Describe 'Hygiene checks (fictional snapshot)' {
    It 'flags user settings that computers cannot read (MS16-072) as High' {
        $f = Get-Check (Get-Snapshot) 'UserGpoNoComputerRead'
        $f.Count | Should -Be 1
        $f[0].Target | Should -Be 'CON-Finance-ScreenLock'
        $f[0].Severity | Should -Be 'High'
    }
    It 'is satisfied by Read for Authenticated Users or Domain Computers' {
        $s = Get-Snapshot
        $g = $s.Gpos | Where-Object Name -eq 'CON-Finance-ScreenLock'
        $g.Permissions += [pscustomobject]@{ Trustee = 'Domain Computers'; Sid = 'S-1-5-21-0-0-0-515'; Permission = 'GpoRead'; Denied = $false }
        (Get-Check $s 'UserGpoNoComputerRead').Count | Should -Be 0
    }
    It 'flags settings in a disabled half as High' {
        $f = Get-Check (Get-Snapshot) 'DisabledHalfHasSettings'
        $f.Target | Should -Be 'CON-Legacy-Drives'
        $f.Detail | Should -Match 'User settings exist'
    }
    It 'flags AD/SYSVOL version mismatch' {
        (Get-Check (Get-Snapshot) 'VersionMismatch').Detail | Should -Match 'AD 5 vs SYSVOL 4'
    }
    It 'finds unlinked, empty, all-links-disabled and nobody-can-apply GPOs' {
        $s = Get-Snapshot
        (Get-Check $s 'UnlinkedGpo').Target | Should -Be 'CON-Test-Empty'
        (Get-Check $s 'EmptyGpo').Target | Should -Be 'CON-Test-Empty'
        (Get-Check $s 'AllLinksDisabled').Target | Should -Be 'CON-Old-Kiosk'
        (Get-Check $s 'NobodyCanApply').Target | Should -Be 'CON-HR-Printers'
    }
    It 'reports enforced links and blocked inheritance as Info' {
        $s = Get-Snapshot
        (Get-Check $s 'EnforcedLink').Target | Should -Be 'CON-Sec-Enforced'
        (Get-Check $s 'BlockedInheritance').Target | Should -Match '^OU=Operations'
    }
    It 'says nothing about the GPOs that are fine' {
        $targets = @(Test-GpoLabHygiene -Snapshot (Get-Snapshot)).Target
        $targets | Should -Not -Contain 'CON-Servers-Baseline'
        $targets | Should -Not -Contain 'Default Domain Policy'
    }
    It 'sorts worst first: 2 High, 2 Medium, 3 Low, 2 Info' {
        $all = @(Test-GpoLabHygiene -Snapshot (Get-Snapshot))
        $all.Count | Should -Be 9
        $all[0].Severity | Should -Be 'High'
        $all[-1].Severity | Should -Be 'Info'
        @($all | Where-Object Severity -eq 'Medium').Count | Should -Be 2
        @($all | Where-Object Severity -eq 'Low').Count | Should -Be 3
    }
}

Describe 'Invoke-GpoLabDeployment (GroupPolicy cmdlets mocked)' {
    Context 'empty domain' {
        BeforeEach {
            Mock Get-GPO -ModuleName GpoLab { $null }
            Mock New-GPO -ModuleName GpoLab { [pscustomobject]@{ DisplayName = $Name; Id = [guid]$script:Ids[$Name]; GpoStatus = 'AllSettingsEnabled' } }
            Mock Get-GPRegistryValue -ModuleName GpoLab { $null }
            Mock Set-GPRegistryValue -ModuleName GpoLab { }
            Mock Get-GPInheritance -ModuleName GpoLab { [pscustomobject]@{ GpoLinks = @() } }
            Mock New-GPLink -ModuleName GpoLab { }
            Mock Set-GPLink -ModuleName GpoLab { }
            Mock Get-GPPermission -ModuleName GpoLab { @([pscustomobject]@{ Trustee = [pscustomobject]@{ Name = 'Authenticated Users' }; Permission = 'GpoApply' }) }
            Mock Set-GPPermission -ModuleName GpoLab { }
        }
        It 'creates both GPOs, four settings, two links and sets the unused half to disabled' {
            $log = @(Invoke-GpoLabDeployment -DefinitionPath $script:Definition)
            Should -Invoke New-GPO -ModuleName GpoLab -Times 2 -Exactly
            Should -Invoke Set-GPRegistryValue -ModuleName GpoLab -Times 4 -Exactly
            Should -Invoke Set-GPRegistryValue -ModuleName GpoLab -Times 1 -Exactly -ParameterFilter {
                $ValueName -eq 'EnableScriptBlockLogging' -and $Type -eq 'DWord' -and $Value -eq 1 -and $Key -like 'HKLM\*'
            }
            Should -Invoke New-GPLink -ModuleName GpoLab -Times 1 -Exactly -ParameterFilter {
                $Name -eq 'CON-Servers-Baseline' -and $Target -like 'OU=Servers,*' -and $Order -eq 1 -and $LinkEnabled -eq 'Yes' -and $Enforced -eq 'No'
            }
            @($log | Where-Object { $_.Action -eq 'SetStatus' -and $_.Result -eq 'Done' }).Count | Should -Be 2
        }
        It 'filters to the Finance group and keeps Read (not Apply) for Authenticated Users' {
            Invoke-GpoLabDeployment -DefinitionPath $script:Definition | Out-Null
            Should -Invoke Set-GPPermission -ModuleName GpoLab -Times 2 -Exactly
            Should -Invoke Set-GPPermission -ModuleName GpoLab -Times 1 -Exactly -ParameterFilter { $TargetName -eq 'GG-Dept-Finance' -and $PermissionLevel -eq 'GpoApply' }
            Should -Invoke Set-GPPermission -ModuleName GpoLab -Times 1 -Exactly -ParameterFilter {
                $TargetName -eq 'Authenticated Users' -and $PermissionLevel -eq 'GpoRead' -and $Replace
            }
        }
        It 'changes nothing with -WhatIf' {
            $log = @(Invoke-GpoLabDeployment -DefinitionPath $script:Definition -WhatIf)
            Should -Invoke New-GPO -ModuleName GpoLab -Times 0 -Exactly
            Should -Invoke Set-GPRegistryValue -ModuleName GpoLab -Times 0 -Exactly
            Should -Invoke New-GPLink -ModuleName GpoLab -Times 0 -Exactly
            Should -Invoke Set-GPPermission -ModuleName GpoLab -Times 0 -Exactly
            @($log | Where-Object Result -ne 'WhatIf').Count | Should -Be 0
        }
    }

    Context 'domain already matches' {
        BeforeEach {
            $script:Def = Get-Content -Raw $script:Definition | ConvertFrom-Json
            Mock Get-GPO -ModuleName GpoLab {
                $g = $script:Def.Gpos | Where-Object Name -eq $Name
                [pscustomobject]@{ DisplayName = $Name; Id = [guid]$script:Ids[$Name]; GpoStatus = $g.Status }
            }
            Mock Get-GPRegistryValue -ModuleName GpoLab {
                $r = $script:Def.Gpos.Registry | Where-Object { $_.ValueName -eq $ValueName }
                [pscustomobject]@{ ValueName = $ValueName; Type = $r.Type; Value = $r.Value }
            }
            Mock Get-GPInheritance -ModuleName GpoLab {
                $owner = if ($Target -like 'OU=Servers,*') { 'CON-Servers-Baseline' } else { 'CON-Finance-ScreenLock' }
                [pscustomobject]@{ GpoLinks = @([pscustomobject]@{ GpoId = [guid]$script:Ids[$owner]; Enabled = $true; Enforced = $false; Order = 1 }) }
            }
            Mock Get-GPPermission -ModuleName GpoLab {
                @([pscustomobject]@{ Trustee = [pscustomobject]@{ Name = 'GG-Dept-Finance' }; Permission = 'GpoApply' },
                    [pscustomobject]@{ Trustee = [pscustomobject]@{ Name = 'Authenticated Users' }; Permission = 'GpoRead' })
            }
            foreach ($c in 'New-GPO', 'Set-GPRegistryValue', 'New-GPLink', 'Set-GPLink', 'Set-GPPermission') { Mock $c -ModuleName GpoLab { } }
        }
        It 'reports NoChange for everything on a second run' {
            $log = @(Invoke-GpoLabDeployment -DefinitionPath $script:Definition)
            @($log | Where-Object Result -ne 'NoChange').Count | Should -Be 0
            $log.Count | Should -Be 12
            foreach ($c in 'New-GPO', 'Set-GPRegistryValue', 'New-GPLink', 'Set-GPLink', 'Set-GPPermission') {
                Should -Invoke $c -ModuleName GpoLab -Times 0 -Exactly
            }
        }
        It 'repairs drift: a disabled link, a changed value, Authenticated Users removed by hand' {
            Mock Get-GPInheritance -ModuleName GpoLab {
                $owner = if ($Target -like 'OU=Servers,*') { 'CON-Servers-Baseline' } else { 'CON-Finance-ScreenLock' }
                [pscustomobject]@{ GpoLinks = @([pscustomobject]@{ GpoId = [guid]$script:Ids[$owner]; Enabled = ($owner -ne 'CON-Servers-Baseline'); Enforced = $false; Order = 1 }) }
            }
            Mock Get-GPRegistryValue -ModuleName GpoLab -ParameterFilter { $ValueName -eq 'ScreenSaveTimeOut' } {
                [pscustomobject]@{ ValueName = $ValueName; Type = 'String'; Value = '3600' }
            }
            Mock Get-GPPermission -ModuleName GpoLab { @([pscustomobject]@{ Trustee = [pscustomobject]@{ Name = 'GG-Dept-Finance' }; Permission = 'GpoApply' }) }
            $log = @(Invoke-GpoLabDeployment -DefinitionPath $script:Definition)
            Should -Invoke Set-GPLink -ModuleName GpoLab -Times 1 -Exactly -ParameterFilter { $LinkEnabled -eq 'Yes' -and $Target -like 'OU=Servers,*' }
            Should -Invoke Set-GPRegistryValue -ModuleName GpoLab -Times 1 -Exactly -ParameterFilter { $ValueName -eq 'ScreenSaveTimeOut' -and $Value -eq '900' }
            Should -Invoke Set-GPPermission -ModuleName GpoLab -Times 1 -Exactly -ParameterFilter { $TargetName -eq 'Authenticated Users' -and $PermissionLevel -eq 'GpoRead' }
            @($log | Where-Object Result -in 'Done', 'Updated').Count | Should -Be 3
        }
    }
}

Describe 'Export-GpoLabSnapshot (cmdlets mocked)' {
    BeforeAll {
        $script:ReportXml = Get-Content -Raw (Join-Path $PSScriptRoot 'fixtures/gporeport-baseline.xml')
        Mock Get-ADDomain -ModuleName GpoLab { [pscustomobject]@{ DNSRoot = 'lab.contoso.com'; DistinguishedName = 'DC=lab,DC=contoso,DC=com'; DomainSID = 'S-1-5-21-0-0-0' } }
        Mock Get-ADOrganizationalUnit -ModuleName GpoLab { @([pscustomobject]@{ DistinguishedName = 'OU=Servers,OU=Contoso,DC=lab,DC=contoso,DC=com' }, [pscustomobject]@{ DistinguishedName = 'OU=Empty,DC=lab,DC=contoso,DC=com' }) }
        Mock Get-GPO -ModuleName GpoLab {
            @([pscustomobject]@{
                    DisplayName = 'CON-Servers-Baseline'; Id = [guid]'00000000-0000-0000-0000-000000000003'; GpoStatus = 'UserSettingsDisabled'; Description = ''
                    ModificationTime = [datetime]'2026-11-18T10:00:00Z'; WmiFilter = $null
                    Computer = [pscustomobject]@{ DSVersion = 2; SysvolVersion = 2 }; User = [pscustomobject]@{ DSVersion = 0; SysvolVersion = 0 }
                })
        }
        Mock Get-GPOReport -ModuleName GpoLab { $script:ReportXml }
        Mock Get-GPPermission -ModuleName GpoLab { @([pscustomobject]@{ Trustee = [pscustomobject]@{ Name = 'Authenticated Users'; Sid = 'S-1-5-11' }; Permission = 'GpoApply'; Denied = $false }) }
        Mock Get-GPInheritance -ModuleName GpoLab {
            if ($Target -like 'OU=Servers,*') {
                [pscustomobject]@{ GpoInheritanceBlocked = 'No'; GpoLinks = @([pscustomobject]@{ GpoId = [guid]'00000000-0000-0000-0000-000000000003'; DisplayName = 'CON-Servers-Baseline'; Enabled = $true; Enforced = $false; Order = 1 }) }
            }
            else { [pscustomobject]@{ GpoInheritanceBlocked = 'No'; GpoLinks = @() } }
        }
    }
    It 'writes a snapshot the checks can read, settings presence taken from the GPO report XML' {
        $path = Join-Path ([IO.Path]::GetTempPath()) "gpo-snap-$([guid]::NewGuid()).json"
        $s = Export-GpoLabSnapshot -Path $path
        $s.Gpos[0].Computer.HasSettings | Should -BeTrue
        $s.Gpos[0].User.HasSettings | Should -BeFalse
        @($s.Soms).Count | Should -Be 1
        $s.Soms[0].Links[0].GpoId | Should -Be '00000000-0000-0000-0000-000000000003'
        $reloaded = Get-Content -Raw $path | ConvertFrom-Json
        @(Test-GpoLabHygiene -Snapshot $reloaded).Count | Should -Be 0
        Remove-Item $path
    }
}

Describe 'Backup-GpoLab (cmdlets mocked)' {
    It 'backs up all GPOs into a timestamped folder and writes links.json next to them' {
        Mock Backup-GPO -ModuleName GpoLab { @([pscustomobject]@{ Id = 'b1' }, [pscustomobject]@{ Id = 'b2' }) }
        Mock Export-GpoLabSnapshot -ModuleName GpoLab { Get-Content -Raw $script:Fixture | ConvertFrom-Json }
        $root = Join-Path ([IO.Path]::GetTempPath()) "gpo-bak-$([guid]::NewGuid())"
        $r = Backup-GpoLab -Path $root -Now ([datetime]'2026-11-20T09:00:00')
        $r.Path | Should -Be (Join-Path $root '20261120-090000')
        $r.GpoCount | Should -Be 2
        Should -Invoke Backup-GPO -ModuleName GpoLab -Times 1 -Exactly -ParameterFilter { $All -and $Path -eq $r.Path }
        (Get-Content -Raw $r.LinkFile | ConvertFrom-Json).Count | Should -Be 7
        Remove-Item $root -Recurse
    }
}

Describe 'Invoke-GpoHygieneReport.ps1 (offline, end to end)' {
    It 'writes the markdown report and exits 1 with -FailOnHigh' {
        $out = Join-Path ([IO.Path]::GetTempPath()) "gpo-report-$([guid]::NewGuid()).md"
        $script = Join-Path $PSScriptRoot '../src/Invoke-GpoHygieneReport.ps1'
        & pwsh -NoProfile -Command "& '$script' -FromSnapshot '$script:Fixture' -OutFile '$out' -FailOnHigh" | Out-Null
        $LASTEXITCODE | Should -Be 1
        $md = Get-Content -Raw $out
        $md | Should -Match 'Group Policy hygiene report: lab.contoso.com'
        $md | Should -Match 'High 2 / Medium 2 / Low 3 / Info 2'
        Remove-Item $out
    }
}

Describe 'Windows PowerShell 5.1 compatibility' {
    It '<File> has no PowerShell 7-only syntax' -ForEach @(
        @{ File = 'GpoLab/GpoLab.psm1' }, @{ File = 'Invoke-GpoHygieneReport.ps1' }
    ) {
        $ast = [Parser]::ParseFile((Join-Path $PSScriptRoot "../src/$File"), [ref]$null, [ref]$null)
        $bad = $ast.FindAll({
                param($n)
                $n -is [TernaryExpressionAst] -or $n -is [PipelineChainAst] -or
                ($n -is [BinaryExpressionAst] -and "$($n.Operator)" -eq 'QuestionQuestion') -or
                ($n -is [AssignmentStatementAst] -and "$($n.Operator)" -eq 'QuestionQuestionEquals') -or
                ($n -is [MemberExpressionAst] -and $n.NullConditional) -or ($n -is [IndexExpressionAst] -and $n.NullConditional)
            }, $true)
        @($bad).Count | Should -Be 0
    }
    It 'the manifest asks for 5.1, not 7' {
        (Import-PowerShellDataFile (Join-Path $PSScriptRoot '../src/GpoLab/GpoLab.psd1')).PowerShellVersion | Should -Be '5.1'
    }
}
