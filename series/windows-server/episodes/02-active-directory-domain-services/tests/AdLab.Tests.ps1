using namespace System.Management.Automation.Language

BeforeAll {
    $src = Join-Path $PSScriptRoot '../src'
    Import-Module (Join-Path $src 'AdLab/AdLab.psd1') -Force
    $script:Policy = Get-Content -Raw (Join-Path $src 'policy.json') | ConvertFrom-Json
    $script:Now = [datetime]::new(2026, 11, 20, 9, 0, 0, [DateTimeKind]::Utc)
    $script:Csv = Join-Path $src 'users.csv'
    $script:DomainDn = 'DC=lab,DC=contoso,DC=com'

    function Get-Snapshot { Get-Content -Raw (Join-Path $PSScriptRoot 'fixtures/lab-snapshot.json') | ConvertFrom-Json }
    function Get-Check($Snapshot, [string] $Check) {
        @(Test-AdLabHygiene -Snapshot $Snapshot -Policy $script:Policy -Now $script:Now | Where-Object Check -eq $Check)
    }
}

Describe 'Logon names' {
    It '<Given> <Surname> -> <Expected>' -ForEach @(
        @{ Given = 'Alex'; Surname = 'Demo'; Expected = 'ademo' }
        @{ Given = 'João'; Surname = 'Gonçalves'; Expected = 'jgoncalves' }
        @{ Given = 'Inês'; Surname = 'Ferreira'; Expected = 'iferreira' }
        @{ Given = 'Ana Maria'; Surname = 'Silva Costa'; Expected = 'acosta' }
        @{ Given = "Seán"; Surname = "O'Brien"; Expected = 'sobrien' }
    ) {
        ConvertTo-AdLabSamAccountName $Given $Surname | Should -Be $Expected
    }
    It 'never exceeds 20 characters (sAMAccountName limit)' {
        $sam = ConvertTo-AdLabSamAccountName 'Bartholomew' 'Featherstonehaugh-Smythe'
        $sam | Should -Be 'bfeatherstonehaughsm'
        $sam.Length | Should -Be 20
    }
    It 'adds a number on collision and stays within 20 characters' {
        $taken = [Collections.Generic.HashSet[string]]::new([string[]]@('jgoncalves', 'jgoncalves2', 'bfeatherstonehaughsm'), [StringComparer]::OrdinalIgnoreCase)
        Get-AdLabUniqueSamAccountName -Base 'jgoncalves' -Taken $taken | Should -Be 'jgoncalves3'
        $long = Get-AdLabUniqueSamAccountName -Base 'bfeatherstonehaughsm' -Taken $taken
        $long | Should -Be 'bfeatherstonehaughs2'
        $long.Length | Should -Be 20
    }
    It 'refuses names that reduce to nothing' {
        { ConvertTo-AdLabSamAccountName '---' 'Demo' } | Should -Throw '*Cannot build a logon name*'
    }
}

Describe 'OU plan' {
    It 'lists parents before children, one OU per department' {
        $plan = @(Get-AdLabOuPlan -DomainDn $script:DomainDn -Department 'Sales', 'IT', 'Sales')
        $plan[0].DistinguishedName | Should -Be 'OU=Contoso,DC=lab,DC=contoso,DC=com'
        $plan.DistinguishedName | Should -Contain 'OU=IT,OU=Users,OU=Contoso,DC=lab,DC=contoso,DC=com'
        @($plan | Where-Object Name -eq 'Sales').Count | Should -Be 1
        $plan.Count | Should -Be 6
    }
}

Describe 'User plan' {
    BeforeAll { $script:Rows = Import-Csv $script:Csv }
    It 'creates everyone on an empty domain, with unique names' {
        $plan = @(New-AdLabUserPlan -User $script:Rows -DomainDn $script:DomainDn -UpnSuffix 'lab.contoso.com')
        $plan.Count | Should -Be 8
        @($plan | Where-Object Action -eq 'Create').Count | Should -Be 8
        ($plan | Where-Object EmployeeId -eq '1005').SamAccountName | Should -Be 'jgoncalves2'
        ($plan.SamAccountName | Sort-Object -Unique).Count | Should -Be 8
    }
    It 'builds UPN, OU path and department group' {
        $u = New-AdLabUserPlan -User $script:Rows -DomainDn $script:DomainDn -UpnSuffix 'lab.contoso.com' | Where-Object EmployeeId -eq '1002'
        $u.UserPrincipalName | Should -Be 'jgoncalves@lab.contoso.com'
        $u.Path | Should -Be 'OU=Finance,OU=Users,OU=Contoso,DC=lab,DC=contoso,DC=com'
        $u.Group | Should -Be 'GG-Dept-Finance'
        $u.DisplayName | Should -Be 'João Gonçalves'
    }
    It 'is idempotent: existing EmployeeIds keep their logon name, even after a rename' {
        $existing = @([pscustomobject]@{ EmployeeId = '1002'; SamAccountName = 'jgoncalves.old' })
        $u = New-AdLabUserPlan -User $script:Rows -DomainDn $script:DomainDn -UpnSuffix 'lab.contoso.com' -Existing $existing |
            Where-Object EmployeeId -eq '1002'
        $u.Action | Should -Be 'Exists'
        $u.SamAccountName | Should -Be 'jgoncalves.old'
    }
    It 'treats every logon name in the domain as taken' {
        $existing = @([pscustomobject]@{ EmployeeId = $null; SamAccountName = 'ademo' })
        (New-AdLabUserPlan -User $script:Rows -DomainDn $script:DomainDn -UpnSuffix 'x' -Existing $existing |
            Where-Object EmployeeId -eq '1001').SamAccountName | Should -Be 'ademo2'
    }
    It 'rejects duplicate EmployeeIds in the CSV' {
        $dup = @($script:Rows[0], $script:Rows[0])
        { New-AdLabUserPlan -User $dup -DomainDn $script:DomainDn -UpnSuffix 'x' } | Should -Throw '*appears twice*'
    }
}

Describe 'FILETIME conversion' {
    It 'converts a lastLogonTimestamp value' {
        $ft = [datetime]::new(2026, 11, 18, 8, 12, 0, [DateTimeKind]::Utc).ToFileTimeUtc()
        ConvertFrom-AdLabFileTime $ft | Should -Be ([datetime]::new(2026, 11, 18, 8, 12, 0, [DateTimeKind]::Utc))
    }
    It 'returns null for <Value> (never)' -ForEach @(@{ Value = 0 }, @{ Value = [long]::MaxValue }, @{ Value = $null }) {
        ConvertFrom-AdLabFileTime $Value | Should -BeNullOrEmpty
    }
}

Describe 'Hygiene checks' {
    It 'flags a stale privileged account as High and a stale normal account as Medium' {
        $r = Get-Check (Get-Snapshot) 'StaleUser'
        ($r | Where-Object Object -eq 'adm-alex').Severity | Should -Be 'High'
        ($r | Where-Object Object -eq 'mlopes').Severity | Should -Be 'Medium'
        $r.Count | Should -Be 2
    }
    It 'mentions the replication lag of lastLogonTimestamp' {
        (Get-Check (Get-Snapshot) 'StaleUser')[0].Detail | Should -Match 'lag by up to 14 days'
    }
    It 'does not flag disabled accounts or brand-new accounts that never signed in' {
        $objects = (Test-AdLabHygiene -Snapshot (Get-Snapshot) -Policy $script:Policy -Now $script:Now).Object
        $objects | Should -Not -Contain 'dold'
        $objects | Should -Not -Contain 'tnew'
    }
    It 'flags old accounts that never signed in' {
        (Get-Check (Get-Snapshot) 'NeverUsed').Object | Should -Be 'rold'
    }
    It 'treats a never-expiring password on an admin as High' {
        (Get-Check (Get-Snapshot) 'PasswordNeverExpires' | Where-Object Object -eq 'adm-alex').Severity | Should -Be 'High'
    }
    It 'suggests a gMSA for a user account with an SPN' {
        (Get-Check (Get-Snapshot) 'ServiceAccount').Object | Should -Be 'svc-backup'
        Get-Check (Get-Snapshot) 'PasswordNeverExpires' | Where-Object Object -eq 'svc-backup' | Should -BeNullOrEmpty
    }
    It 'flags PASSWD_NOTREQD' {
        (Get-Check (Get-Snapshot) 'PasswordNotRequired').Object | Should -Be 'scanner01'
    }
    It 'finds orphaned adminCount but not current members of protected groups' {
        $r = Get-Check (Get-Snapshot) 'OrphanedAdminCount'
        $r.Object | Should -Be 'pformer'
    }
    It 'counts Tier 0 members besides the built-in Administrator' {
        $r = Get-Check (Get-Snapshot) 'PrivilegedGroup'
        $r.Object | Should -Contain 'Domain Admins'
        $r.Object | Should -Not -Contain 'Enterprise Admins'
        $r.Object | Should -Not -Contain 'Backup Operators'
    }
    It 'flags stale enabled computers only' {
        $r = Get-Check (Get-Snapshot) 'StaleComputer'
        $r.Object | Should -Be 'CON-OLD01'
    }
    It 'flags an old krbtgt password with the reset-twice advice' {
        (Get-Check (Get-Snapshot) 'KrbtgtPassword')[0].Detail | Should -Match '311 days old.*twice, at least 10 hours apart'
    }
    It 'flags the Recycle Bin when it is off, and not when it is on' {
        $s = Get-Snapshot
        Get-Check $s 'RecycleBin' | Should -HaveCount 1
        $s.Domain.RecycleBinEnabled = $true
        Get-Check $s 'RecycleBin' | Should -BeNullOrEmpty
    }
    It 'flags an enabled Guest account' {
        $s = Get-Snapshot; $s.Domain.GuestEnabled = $true
        (Get-Check $s 'GuestEnabled')[0].Severity | Should -Be 'High'
    }
    It 'checks password length and lockout against the policy' {
        Get-Check (Get-Snapshot) 'PasswordPolicy' | Should -HaveCount 1
        Get-Check (Get-Snapshot) 'LockoutPolicy' | Should -HaveCount 1
    }
    It 'reports functional levels below the target as Info' {
        $r = Get-Check (Get-Snapshot) 'FunctionalLevel'
        $r.Count | Should -Be 2
        $r[0].Severity | Should -Be 'Info'
    }
    It 'returns findings worst first' {
        $all = @(Test-AdLabHygiene -Snapshot (Get-Snapshot) -Policy $script:Policy -Now $script:Now)
        $all[0].Severity | Should -Be 'High'
        $all[-1].Severity | Should -Be 'Info'
        $all.Count | Should -Be 16
    }
}

Describe 'Invoke-AdLabProvisioning (ActiveDirectory cmdlets mocked)' {
    BeforeAll {
        # Stubs so Pester can mock cmdlets that only exist where RSAT is installed. Mock copies the stub's parameters,
        # so the stub declares every parameter the module passes (otherwise -ParameterFilter sees nothing).
        $stub = {
            param($Filter, $Identity, $Properties, $Server, $Name, $Path, $ProtectedFromAccidentalDeletion, $SamAccountName,
                $GroupScope, $GroupCategory, $Description, $GivenName, $Surname, $DisplayName, $UserPrincipalName, $EmployeeID,
                $Department, $Title, $AccountPassword, $ChangePasswordAtLogon, $Enabled, $Members)
        }
        foreach ($c in 'Get-ADDomain', 'Get-ADOrganizationalUnit', 'New-ADOrganizationalUnit', 'Get-ADGroup', 'New-ADGroup',
            'Get-ADUser', 'New-ADUser', 'Add-ADGroupMember') {
            if (-not (Get-Command $c -ErrorAction SilentlyContinue)) {
                New-Item -Path "function:global:$c" -Value $stub | Out-Null
            }
        }
        $script:Pwd = ConvertTo-SecureString 'Lab-Only-Pa55word!' -AsPlainText -Force
    }

    Context 'empty domain' {
        BeforeEach {
            Mock Get-ADOrganizationalUnit -ModuleName AdLab { $null }
            Mock Get-ADGroup -ModuleName AdLab { $null }
            Mock Get-ADUser -ModuleName AdLab { @() }
            Mock New-ADOrganizationalUnit -ModuleName AdLab { }
            Mock New-ADGroup -ModuleName AdLab { }
            Mock New-ADUser -ModuleName AdLab { }
            Mock Add-ADGroupMember -ModuleName AdLab { }
        }
        It 'creates 9 OUs, 5 groups and 8 users, OUs protected from accidental deletion' {
            $log = Invoke-AdLabProvisioning -CsvPath $script:Csv -DomainDn $script:DomainDn -UpnSuffix 'lab.contoso.com' -InitialPassword $script:Pwd
            @($log | Where-Object { $_.Action -eq 'Created' -and $_.Type -eq 'User' }).Count | Should -Be 8
            Should -Invoke New-ADOrganizationalUnit -ModuleName AdLab -Times 9 -Exactly -ParameterFilter { $ProtectedFromAccidentalDeletion -eq $true }
            Should -Invoke New-ADGroup -ModuleName AdLab -Times 5 -Exactly -ParameterFilter { $GroupScope -eq 'Global' -and $GroupCategory -eq 'Security' }
            Should -Invoke New-ADUser -ModuleName AdLab -Times 8 -Exactly -ParameterFilter { $ChangePasswordAtLogon -eq $true -and $Enabled -eq $true }
            Should -Invoke Add-ADGroupMember -ModuleName AdLab -Times 8 -Exactly
        }
        It 'creates the user in the department OU with EmployeeID set' {
            Invoke-AdLabProvisioning -CsvPath $script:Csv -DomainDn $script:DomainDn -UpnSuffix 'lab.contoso.com' -InitialPassword $script:Pwd | Out-Null
            Should -Invoke New-ADUser -ModuleName AdLab -Times 1 -Exactly -ParameterFilter {
                $SamAccountName -eq 'jgoncalves2' -and $EmployeeID -eq '1005' -and $Path -eq 'OU=Sales,OU=Users,OU=Contoso,DC=lab,DC=contoso,DC=com'
            }
        }
        It 'changes nothing with -WhatIf' {
            Invoke-AdLabProvisioning -CsvPath $script:Csv -DomainDn $script:DomainDn -UpnSuffix 'lab.contoso.com' -InitialPassword $script:Pwd -WhatIf | Out-Null
            Should -Invoke New-ADOrganizationalUnit -ModuleName AdLab -Times 0 -Exactly
            Should -Invoke New-ADUser -ModuleName AdLab -Times 0 -Exactly
            Should -Invoke Add-ADGroupMember -ModuleName AdLab -Times 0 -Exactly
        }
    }

    Context 'second run' {
        BeforeEach {
            Mock Get-ADOrganizationalUnit -ModuleName AdLab { [pscustomobject]@{ DistinguishedName = 'existing' } }
            Mock Get-ADGroup -ModuleName AdLab { [pscustomobject]@{ SamAccountName = 'existing' } }
            Mock Get-ADUser -ModuleName AdLab {
                Import-Csv $script:Csv | ForEach-Object {
                    [pscustomobject]@{ EmployeeID = $_.EmployeeId; SamAccountName = "user$($_.EmployeeId)" }
                }
            }
            Mock New-ADOrganizationalUnit -ModuleName AdLab { }
            Mock New-ADGroup -ModuleName AdLab { }
            Mock New-ADUser -ModuleName AdLab { }
            Mock Add-ADGroupMember -ModuleName AdLab { }
        }
        It 'creates nothing when everything already exists' {
            $log = Invoke-AdLabProvisioning -CsvPath $script:Csv -DomainDn $script:DomainDn -UpnSuffix 'lab.contoso.com' -InitialPassword $script:Pwd
            @($log | Where-Object Action -eq 'Created').Count | Should -Be 0
            @($log | Where-Object Action -eq 'Exists').Count | Should -Be 22
            Should -Invoke New-ADUser -ModuleName AdLab -Times 0 -Exactly
            Should -Invoke New-ADOrganizationalUnit -ModuleName AdLab -Times 0 -Exactly
        }
    }
}

Describe 'Invoke-AdHygieneReport.ps1 (offline, end to end)' {
    It 'writes the markdown report and exits 1 with -FailOnHigh' {
        $out = Join-Path ([IO.Path]::GetTempPath()) "ad-report-$([guid]::NewGuid()).md"
        $script = Join-Path $PSScriptRoot '../src/Invoke-AdHygieneReport.ps1'
        $fixture = Join-Path $PSScriptRoot 'fixtures/lab-snapshot.json'
        & pwsh -NoProfile -Command "& '$script' -FromSnapshot '$fixture' -Now 2026-11-20T09:00:00Z -OutFile '$out' -FailOnHigh" | Out-Null
        $LASTEXITCODE | Should -Be 1
        $md = Get-Content -Raw $out
        $md | Should -Match 'AD hygiene report: lab.contoso.com'
        $md | Should -Match 'High 3 / Medium 8 / Low 3 / Info 2'
        Remove-Item $out
    }
}

Describe 'Setup script' {
    It 'New-LabForest.ps1 parses without errors' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '../setup/New-LabForest.ps1'), [ref]$null, [ref]$errors) | Out-Null
        $errors | Should -BeNullOrEmpty
    }
    It 'stays Windows PowerShell 5.1-safe (written for powershell.exe on the new DC)' {
        $ast = [Parser]::ParseFile((Join-Path $PSScriptRoot '../setup/New-LabForest.ps1'), [ref]$null, [ref]$null)
        $bad = $ast.FindAll({
                param($n)
                $n -is [TernaryExpressionAst] -or $n -is [PipelineChainAst] -or
                ($n -is [BinaryExpressionAst] -and "$($n.Operator)" -eq 'QuestionQuestion') -or
                ($n -is [AssignmentStatementAst] -and "$($n.Operator)" -eq 'QuestionQuestionEquals')
            }, $true)
        $bad.Count | Should -Be 0
    }
    It 'checks prerequisites and supports -WhatIf' {
        $text = Get-Content -Raw (Join-Path $PSScriptRoot '../setup/New-LabForest.ps1')
        $text | Should -Match 'Test-ADDSForestInstallation'
        $text | Should -Match 'SupportsShouldProcess'
        $text | Should -Match "GetEnumNames\(\)"
    }
}
