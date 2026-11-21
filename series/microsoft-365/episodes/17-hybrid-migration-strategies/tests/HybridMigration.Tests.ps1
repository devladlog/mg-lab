BeforeAll {
    # Active Directory and Exchange Online cmdlets only exist on a domain controller / after Connect-ExchangeOnline: stubs with the documented
    # parameter names, mocked per test against a small fake directory. Nothing here talks to a real service.
    $stubs = @{
        'Get-ADUser' = @('Identity', 'Filter', 'Properties', 'SearchBase', 'Server'); 'Set-ADUser' = @('Identity', 'UserPrincipalName', 'Server')
        'Get-User' = @('ResultSize'); 'Get-EXOMailbox' = @('RecipientTypeDetails', 'ResultSize', 'Properties')
        'Get-EXOMailboxStatistics' = @('Identity'); 'Get-EXOMailboxPermission' = @('Identity')
    }
    foreach ($n in $stubs.Keys) {
        if (Get-Command $n -ErrorAction SilentlyContinue) { continue }
        $plist = ($stubs[$n] | ForEach-Object { "`$$_" }) -join ', '
        $attr = if ($n -like 'Set-*') { '[CmdletBinding(SupportsShouldProcess)]' } else { '[CmdletBinding()]' }
        Set-Item -Path "function:global:$n" -Value ([scriptblock]::Create("$attr param($plist) throw 'stub: not connected'"))
    }
    Import-Module "$PSScriptRoot/../src/HybridMigration/HybridMigration.psd1" -Force
    $script:fx = "$PSScriptRoot/fixtures"
    $script:cfg = Get-HMConfig -Path "$fx/migration.test.json"
    $script:users = @(Get-Content "$fx/users.json" -Raw | ConvertFrom-Json)
    $script:boxes = @(Get-Content "$fx/mailboxes.json" -Raw | ConvertFrom-Json)
    $script:verified = @('contoso.com', 'contoso.onmicrosoft.com')
    function script:Find($U = $users) { @(Get-HMDirectoryFinding -Users $U -VerifiedDomains $verified -Config $cfg) }
    function script:Rule([string]$R, $F = (Find)) { @($F | Where-Object Rule -EQ $R) }
    function script:One($o) { $o | ConvertTo-Json -Depth 8 | ConvertFrom-Json }
}

Describe 'Get-HMConfig' {
    It 'loads the shipped config' { (Get-HMConfig).waves.maxMailboxesPerWave | Should -BeGreaterThan 0 }
    It 'refuses a config without a number' {
        $p = Join-Path $TestDrive 'bad.json'; '{"directory":{},"waves":{"maxMailboxesPerWave":0,"maxGBPerWave":1,"largeMailboxGB":1},"batch":{}}' | Set-Content $p
        { Get-HMConfig -Path $p } | Should -Throw '*maxMailboxesPerWave*'
    }
    It 'refuses a config without a section' {
        $p = Join-Path $TestDrive 'bad2.json'; '{"directory":{}}' | Set-Content $p
        { Get-HMConfig -Path $p } | Should -Throw "*no 'waves'*"
    }
}

Describe 'Get-HMStrategy (the Learn decision table)' {
    It 'IMAP for a non-Exchange system, and says it moves only email' {
        $s = Get-HMStrategy -Source NonExchange -Mailboxes 500
        $s.Strategy | Should -Be 'IMAP'; ($s.Warnings -join ' ') | Should -Match 'only email'
    }
    It 'IMAP for Exchange 2000 or earlier' { (Get-HMStrategy -Source ExchangeLegacy -Mailboxes 10).Strategy | Should -Be 'IMAP' }
    It 'cutover for Exchange 2010+ under 150 mailboxes, all at once' { (Get-HMStrategy -Source Exchange2010OrLater -Mailboxes 149).Strategy | Should -Be 'Cutover' }
    It 'hybrid for Exchange 2010+ at exactly 150 mailboxes' { (Get-HMStrategy -Source Exchange2010OrLater -Mailboxes 150).Strategy | Should -Be 'Hybrid' }
    It 'hybrid for a gradual move even when small' { (Get-HMStrategy -Source Exchange2010OrLater -Mailboxes 40 -Pace Gradual).Strategy | Should -Be 'Hybrid' }
    It 'hybrid when users stay managed on-premises' { (Get-HMStrategy -Source Exchange2010OrLater -Mailboxes 40 -ManageUsersOnPremises).Strategy | Should -Be 'Hybrid' }
    It 'never staged for Exchange 2010+, and warns about it' {
        $s = Get-HMStrategy -Source Exchange2010OrLater -Mailboxes 5000
        $s.Strategy | Should -Not -Be 'Staged'; ($s.Warnings -join ' ') | Should -Match 'staged migration cannot'
    }
    It 'cutover for Exchange 2007 under 150 all at once' { (Get-HMStrategy -Source Exchange2007 -Mailboxes 100).Strategy | Should -Be 'Cutover' }
    It 'staged for Exchange 2007 above 150, with the 2,000 row note and the dir-sync warning' {
        $s = Get-HMStrategy -Source Exchange2007 -Mailboxes 800
        $s.Strategy | Should -Be 'Staged'; ($s.Warnings -join ' ') | Should -Match '2,000 rows'; ($s.Warnings -join ' ') | Should -Match 'directory synchronization'
    }
    It 'staged for Exchange 2003 when you want a few users at a time' { (Get-HMStrategy -Source Exchange2003 -Mailboxes 60 -Pace Gradual).Strategy | Should -Be 'Staged' }
    It 'notes that Exchange 2003 and 2007 are out of support' { ((Get-HMStrategy -Source Exchange2003 -Mailboxes 60).Warnings -join ' ') | Should -Match 'out of support' }
    It 'warns that hybrid is complex below 2,000 mailboxes' { ((Get-HMStrategy -Source Exchange2010OrLater -Mailboxes 300).Warnings -join ' ') | Should -Match 'complexity' }
    It 'rejects zero mailboxes' { { Get-HMStrategy -Source NonExchange -Mailboxes 0 } | Should -Throw }
}

Describe 'Get-HMDirectoryFinding' {
    It 'a clean account has no findings' { Find @($users[0]) | Should -BeNullOrEmpty }
    It 'flags a non-routable UPN suffix as fixable and quotes the suffix' {
        $f = Rule UpnNonRoutable
        $f.Account | Should -Be 'sam.demo'; $f[0].Fixable | Should -BeTrue; $f[0].Detail | Should -Match 'contoso\.local'
    }
    It 'accepts the onmicrosoft.com initial domain as verified' { (Rule UpnNonRoutable | Where-Object Account -EQ 'alex.demo') | Should -BeNullOrEmpty }
    It 'flags a space in the UPN' { (Rule UpnInvalidChars | Where-Object Account -EQ 'jordan.demo') | Should -Not -BeNullOrEmpty }
    It 'flags a diacritic in the UPN' { (Rule UpnInvalidChars | Where-Object Account -EQ 'jose.demo').Detail | Should -Match 'diacritical' }
    It 'flags a user name that ends with a period' { (Rule UpnFormat | Where-Object Account -EQ 'pat.demo') | Should -Not -BeNullOrEmpty }
    It 'flags a UPN that is too long (113 / 64 / 48)' {
        $x = One $users[0]; $x.Upn = ('a' * 65) + '@contoso.com'
        (Rule UpnTooLong (Find @($x))).Detail | Should -Match 'user name part is 77|user name part is 65'
        $y = One $users[0]; $y.Upn = 'a@' + ('d' * 50) + '.com'
        (Rule UpnTooLong (Find @($y))).Detail | Should -Match 'domain part'
        # 64 + 1 + 48 is exactly 113, so the total limit cannot be exceeded without breaking the 64 or 48 limit first
        $z = One $users[0]; $z.Upn = ('a' * 64) + '@' + ('d' * 44) + '.com'
        Rule UpnTooLong (Find @($z)) | Should -BeNullOrEmpty
    }
    It 'flags a missing @' { $x = One $users[0]; $x.Upn = 'nobody'; (Find @($x)).Rule | Should -Contain 'UpnFormat' }
    It 'flags duplicate UPNs on both accounts and names the other one' {
        $d = Rule UpnDuplicate; $d.Account | Should -Contain 'lee.demo'; $d.Account | Should -Contain 'lee.old'
        ($d | Where-Object Account -EQ 'lee.demo').Detail | Should -Match 'lee\.old'
    }
    It 'flags duplicate mail and proxy addresses, ignoring case and the SMTP/smtp prefix' {
        (Rule MailDuplicate).Account | Should -Contain 'riley.demo'; (Rule MailDuplicate).Account | Should -Contain 'taylor.demo'
        (Rule ProxyDuplicate).Account | Should -Contain 'taylor.demo'
    }
    It 'flags a space inside a proxy address' { (Rule ProxyInvalidChars | Where-Object Account -EQ 'quinn.demo').Detail | Should -Match 'quinn \(old\)' }
    It 'flags a long sAMAccountName as Medium' { (Rule SamTooLong).Severity | Should -Be 'Medium' }
    It 'flags a mailNickname that starts with a period' { (Rule MailNicknameLeadingDot).Account | Should -Be 'casey.demo' }
    It 'flags an empty displayName as Low' { (Rule DisplayNameMissing).Severity | Should -Be 'Low' }
    It 'notes when the UPN differs from the primary SMTP address' {
        $x = One $users[0]; $x.ProxyAddresses = @('SMTP:alex@contoso.com'); (Rule UpnMailMismatch (Find @($x))).Severity | Should -Be 'Low'
    }
    It 'flags two primary SMTP addresses' { $x = One $users[0]; $x.ProxyAddresses = @('SMTP:a@contoso.com', 'SMTP:b@contoso.com'); (Rule MultiplePrimarySmtp (Find @($x))) | Should -Not -BeNullOrEmpty }
    It 'ignores the accounts named in the config (krbtgt)' { (Find).Account | Should -Not -Contain 'krbtgt' }
    It 'sorts High before Medium before Low' {
        $sev = (Find).Severity; $rank = @{ High = 0; Medium = 1; Low = 2 }
        $r = $sev | ForEach-Object { $rank[$_] }; ($r | Select-Object) | Should -Be ($r | Sort-Object)
    }
    It 'accepts an empty directory' { Find @() | Should -BeNullOrEmpty }
    It 'summarizes and says not ready while there are High findings' {
        $s = Get-HMSummary -Findings (Find); $s.High | Should -BeGreaterThan 0; $s.ReadyForSync | Should -BeFalse; $s.Fixable | Should -Be 1
        (Get-HMSummary -Findings @()).ReadyForSync | Should -BeTrue
    }
}

Describe 'New-HMWavePlan' {
    BeforeAll { $script:plan = New-HMWavePlan -Mailboxes $boxes -Config $cfg }
    It 'places every mailbox exactly once' {
        $all = $plan.Waves | ForEach-Object { $_.Mailboxes.Email }
        @($all).Count | Should -Be $boxes.Count; @($all | Sort-Object -Unique).Count | Should -Be $boxes.Count
    }
    It 'puts the pilot mailboxes alone in the first wave' {
        $plan.Waves[0].Kind | Should -Be 'Pilot'; ($plan.Waves[0].Mailboxes.Email | Sort-Object) | Should -Be @('alex.demo@contoso.com', 'sam.demo@contoso.com')
        @($plan.Waves | Where-Object Kind -EQ 'Pilot').Count | Should -Be 1
    }
    It 'respects the caps in every wave' {
        foreach ($w in $plan.Waves | Where-Object Kind -NE 'Large') { $w.Count | Should -BeLessOrEqual 3; $w.TotalGB | Should -BeLessOrEqual 20 }
    }
    It 'keeps a shared mailbox in the same wave as the mailbox it moves with' {
        $wave = { param($e) ($plan.Waves | Where-Object { $_.Mailboxes.Email -contains $e }).Name }
        (& $wave 'finance-ap@contoso.com') | Should -Be (& $wave 'lee.demo@contoso.com')
        (& $wave 'sales-info@contoso.com') | Should -Be (& $wave 'riley.demo@contoso.com')
    }
    It 'moves the group with a large mailbox in a wave of its own, last' {
        $last = $plan.Waves[-1]; $last.Kind | Should -Be 'Large'; $last.Mailboxes.Email | Should -Contain 'riley.demo@contoso.com'; $last.Count | Should -Be 2
    }
    It 'numbers waves and names them wave-NN' { $plan.Waves.Name | Should -Be (1..$plan.Waves.Count | ForEach-Object { 'wave-{0:00}' -f $_ }) }
    It 'reports totals' { $plan.TotalMailboxes | Should -Be 10; $plan.TotalGB | Should -Be 80.1 }
    It 'follows a chain of MoveWith links into one group' {
        $b = @(@{ Email = 'a@x.com'; SizeGB = 1; Type = 'User'; Department = 'D'; MoveWith = 'b@x.com' }, @{ Email = 'b@x.com'; SizeGB = 1; Type = 'User'; Department = 'D'; MoveWith = 'c@x.com' },
            @{ Email = 'c@x.com'; SizeGB = 1; Type = 'User'; Department = 'D' }, @{ Email = 'd@x.com'; SizeGB = 1; Type = 'User'; Department = 'D' }) | ForEach-Object { [pscustomobject]$_ }
        $c = One $cfg; $c.waves.maxMailboxesPerWave = 3
        $p = New-HMWavePlan -Mailboxes $b -Config $c
        ($p.Waves | Where-Object { $_.Mailboxes.Email -contains 'a@x.com' }).Mailboxes.Email | Should -Contain 'c@x.com'
    }
    It 'gives a group above the caps its own wave and warns' {
        $c = One $cfg; $c.waves.maxMailboxesPerWave = 1
        $p = New-HMWavePlan -Mailboxes @($boxes | Where-Object { $_.Email -in 'lee.demo@contoso.com', 'finance-ap@contoso.com' }) -Config $c
        $p.Waves.Count | Should -Be 1; $p.Warnings | Should -Not -BeNullOrEmpty
    }
    It 'warns about a MoveWith target that is not in the input' {
        $b = @([pscustomobject]@{ Email = 'a@x.com'; SizeGB = 1; Type = 'Shared'; Department = ''; MoveWith = 'ghost@x.com'; Pilot = $false })
        (New-HMWavePlan -Mailboxes $b -Config $cfg).Warnings | Should -Match 'ghost@x.com'
    }
    It 'rejects duplicate mailboxes and mailboxes without an address' {
        { New-HMWavePlan -Mailboxes @($boxes[0], $boxes[0]) -Config $cfg } | Should -Throw '*Duplicate*'
        { New-HMWavePlan -Mailboxes @([pscustomobject]@{ Email = ''; SizeGB = 1 }) -Config $cfg } | Should -Throw '*without an Email*'
    }
    It 'is deterministic' { (New-HMWavePlan -Mailboxes $boxes -Config $cfg | ConvertTo-Json -Depth 6) | Should -Be ($plan | ConvertTo-Json -Depth 6) }
}

Describe 'Export-HMWaveCsv and Get-HMBatchCommand' {
    It 'writes one CSV per wave with the batch columns' {
        $plan = New-HMWavePlan -Mailboxes $boxes -Config $cfg
        $files = Export-HMWaveCsv -Plan $plan -Directory (Join-Path $TestDrive 'w') -Config $cfg
        @($files).Count | Should -Be $plan.Waves.Count
        $rows = Import-Csv (Join-Path $TestDrive 'w/wave-01.csv'); $rows.Count | Should -Be 2
        $rows[0].PSObject.Properties.Name | Should -Be @('EmailAddress', 'BadItemLimit', 'LargeItemLimit')
        $rows.EmailAddress | Should -Contain 'alex.demo@contoso.com'
    }
    It 'writes nothing under -WhatIf' {
        $plan = New-HMWavePlan -Mailboxes $boxes -Config $cfg
        Export-HMWaveCsv -Plan $plan -Directory (Join-Path $TestDrive 'nope') -Config $cfg -WhatIf | Out-Null
        Test-Path (Join-Path $TestDrive 'nope') | Should -BeFalse
    }
    It 'builds the New-MigrationBatch and Start-MigrationBatch text for a wave' {
        $plan = New-HMWavePlan -Mailboxes $boxes -Config $cfg
        $t = Get-HMBatchCommand -Wave $plan.Waves[0] -Config $cfg -CsvPath './wave-01.csv'
        $t | Should -Match "New-MigrationBatch -Name 'wave-01' -SourceEndpoint"; $t | Should -Match 'TargetDeliveryDomain'; $t | Should -Match "Start-MigrationBatch -Identity 'wave-01'"
        $t | Should -Match "ReadAllBytes\('\./wave-01\.csv'\)"
    }
    It 'the generated text parses as PowerShell' {
        $plan = New-HMWavePlan -Mailboxes $boxes -Config $cfg
        $t = Get-HMBatchCommand -Wave $plan.Waves[0] -Config $cfg
        { [scriptblock]::Create($t) } | Should -Not -Throw
    }
}

Describe 'Get-HMMailboxInventory (fake Exchange Online)' {
    BeforeAll {
        Mock Get-User { @([pscustomobject]@{ UserPrincipalName = 'a@contoso.com'; Department = 'IT' }, [pscustomobject]@{ UserPrincipalName = 'sh@contoso.com'; Department = '' }) } -ModuleName HybridMigration
        Mock Get-EXOMailbox {
            @([pscustomobject]@{ PrimarySmtpAddress = 'a@contoso.com'; RecipientTypeDetails = 'UserMailbox'; UserPrincipalName = 'a@contoso.com' },
                [pscustomobject]@{ PrimarySmtpAddress = 'sh@contoso.com'; RecipientTypeDetails = 'SharedMailbox'; UserPrincipalName = 'sh@contoso.com' })
        } -ModuleName HybridMigration
        Mock Get-EXOMailboxStatistics { [pscustomobject]@{ TotalItemSize = '2 GB (2,147,483,648 bytes)' } } -ModuleName HybridMigration
        Mock Get-EXOMailboxPermission { @([pscustomobject]@{ User = 'a@contoso.com'; AccessRights = @('FullAccess'); IsInherited = $false; Deny = $false }, [pscustomobject]@{ User = 'NT AUTHORITY\SELF'; AccessRights = @('FullAccess'); IsInherited = $false; Deny = $false }) } -ModuleName HybridMigration
    }
    It 'returns size, type, department and ties the shared mailbox to its Full Access user' {
        $inv = @(Get-HMMailboxInventory -PilotUsers 'a@contoso.com')
        $inv.Count | Should -Be 2
        $a = $inv | Where-Object Email -EQ 'a@contoso.com'; $a.SizeGB | Should -Be 2; $a.Department | Should -Be 'IT'; $a.Pilot | Should -BeTrue; $a.Type | Should -Be 'User'
        ($inv | Where-Object Email -EQ 'sh@contoso.com').MoveWith | Should -Be 'a@contoso.com'
        ($inv | Where-Object Email -EQ 'sh@contoso.com').Type | Should -Be 'Shared'
    }
    It 'fails loudly on a size it cannot read' {
        Mock Get-EXOMailboxStatistics { [pscustomobject]@{ TotalItemSize = 'unknown' } } -ModuleName HybridMigration
        { Get-HMMailboxInventory } | Should -Throw '*Cannot read the size*'
    }
}

Describe 'UPN fix with rollback (fake Active Directory)' {
    BeforeEach {
        $global:fakeAd = @{}; foreach ($u in $users) { $global:fakeAd[$u.Dn] = $u.Upn }
        $global:setCalls = [System.Collections.Generic.List[string]]::new()
        Mock Get-ADUser { [pscustomobject]@{ DistinguishedName = $Identity; UserPrincipalName = $global:fakeAd[$Identity] } } -ModuleName HybridMigration
        Mock Set-ADUser { $global:fakeAd[$Identity] = $UserPrincipalName; $global:setCalls.Add("$Identity=$UserPrincipalName") } -ModuleName HybridMigration
        $script:findings = Find
        $script:plan = Get-HMUpnFixPlan -Users $users -Findings $findings -VerifiedDomains $verified -Config $cfg
        $script:rb = Join-Path $TestDrive ("rb-{0}.json" -f [guid]::NewGuid())
    }
    AfterAll { Remove-Variable fakeAd, setCalls -Scope Global -ErrorAction SilentlyContinue }
    It 'plans only the non-routable account, keeping the local part' {
        @($plan).Count | Should -Be 1; $plan[0].OldUpn | Should -Be 'sam.demo@contoso.local'; $plan[0].NewUpn | Should -Be 'sam.demo@contoso.onmicrosoft.com'
    }
    It 'plans nothing when the rule is not allowed (the default)' {
        $c = One $cfg; $c.directory.upnFix.allowedRules = @()
        @(Get-HMUpnFixPlan -Users $users -Findings $findings -VerifiedDomains $verified -Config $c).Count | Should -Be 0
    }
    It 'refuses a target suffix that is not verified' {
        $c = One $cfg; $c.directory.upnFix.targetSuffix = 'example.net'
        { Get-HMUpnFixPlan -Users $users -Findings $findings -VerifiedDomains $verified -Config $c } | Should -Throw '*not a verified domain*'
    }
    It 'skips a change that would create a duplicate UPN' {
        $u2 = @($users) + @([pscustomobject]@{ Dn = 'CN=x,DC=a'; Sam = 'x'; Upn = 'sam.demo@contoso.onmicrosoft.com'; Mail = ''; MailNickname = 'x'; DisplayName = 'X'; GivenName = ''; Surname = ''; TargetAddress = ''; ProxyAddresses = @(); Enabled = $true })
        $p = @(Get-HMUpnFixPlan -Users $u2 -Findings (Find $u2) -VerifiedDomains $verified -Config $cfg)
        $p[0].Skip | Should -Match 'already used'
    }
    It 'under -WhatIf changes nothing and writes no rollback file' {
        Invoke-HMUpnFix -Plan $plan -RollbackFile $rb -WhatIf | Out-Null
        $setCalls.Count | Should -Be 0; Test-Path $rb | Should -BeFalse
    }
    It 'changes the UPN, writes the rollback file, and the finding is gone afterwards' {
        $r = @(Invoke-HMUpnFix -Plan $plan -RollbackFile $rb -Confirm:$false)
        $r[0].Result | Should -Be 'Changed'; $fakeAd[$plan[0].Dn] | Should -Be 'sam.demo@contoso.onmicrosoft.com'
        (Get-Content $rb -Raw | ConvertFrom-Json).OldUpn | Should -Be 'sam.demo@contoso.local'
        $after = $users | ForEach-Object { $c = One $_; $c.Upn = $fakeAd[$c.Dn]; $c }
        Rule UpnNonRoutable (Find $after) | Should -BeNullOrEmpty
    }
    It 'never overwrites an existing rollback file' {
        'x' | Set-Content $rb
        { Invoke-HMUpnFix -Plan $plan -RollbackFile $rb -Confirm:$false } | Should -Throw '*already exists*'
        $setCalls.Count | Should -Be 0
    }
    It 'skips an account whose UPN changed since the audit' {
        $fakeAd[$plan[0].Dn] = 'someone.else@contoso.com'
        (@(Invoke-HMUpnFix -Plan $plan -RollbackFile $rb -Confirm:$false))[0].Result | Should -Be 'Skipped'; $setCalls.Count | Should -Be 0
    }
    It 'restores the old UPN from the rollback file, and only if nobody changed it since' {
        Invoke-HMUpnFix -Plan $plan -RollbackFile $rb -Confirm:$false | Out-Null
        $r = @(Restore-HMUpn -RollbackFile $rb -Confirm:$false); $r[0].Result | Should -Be 'Restored'; $fakeAd[$plan[0].Dn] | Should -Be 'sam.demo@contoso.local'
        $r2 = @(Restore-HMUpn -RollbackFile $rb -Confirm:$false); $r2[0].Result | Should -Be 'Skipped'
    }
    It 'skips a plan row that already carries a Skip reason' {
        $p = @([pscustomobject]@{ Dn = 'd'; Account = 'a'; OldUpn = 'o'; NewUpn = 'n'; Skip = 'because' })
        (@(Invoke-HMUpnFix -Plan $p -RollbackFile $rb -Confirm:$false))[0].Result | Should -Be 'Skipped'
    }
}

Describe 'Reports and the runner' {
    It 'renders strategy, findings and waves as markdown' {
        $md = ConvertTo-HMMarkdown -Strategy (Get-HMStrategy -Source Exchange2007 -Mailboxes 800) -Findings (Find) -Plan (New-HMWavePlan -Mailboxes $boxes -Config $cfg)
        $md | Should -Match '\*\*Staged\*\*'; $md | Should -Match '\| High \| UpnNonRoutable \|'; $md | Should -Match '\| wave-01 \| Pilot \|'; $md | Should -Match 'fix the high findings first'
    }
    It 'the runner works offline: Strategy' {
        $o = & "$PSScriptRoot/../src/Invoke-HybridMigration.ps1" -Mode Strategy -Source Exchange2010OrLater -Mailboxes 400 -ConfigFile "$fx/migration.test.json" -OutFile (Join-Path $TestDrive 's.md')
        $o.Strategy | Should -Be 'Hybrid'; (Get-Content (Join-Path $TestDrive 's.md') -Raw) | Should -Match 'Hybrid'
    }
    It 'the runner works offline: Directory from a users file' {
        & "$PSScriptRoot/../src/Invoke-HybridMigration.ps1" -Mode Directory -UsersFile "$fx/users.json" -VerifiedDomain contoso.com, contoso.onmicrosoft.com -ConfigFile "$fx/migration.test.json" -OutFile (Join-Path $TestDrive 'd.md') *> $null
        (Get-Content (Join-Path $TestDrive 'd.md') -Raw) | Should -Match 'UpnNonRoutable'
    }
    It 'the runner works offline: Waves from a mailboxes file' {
        Push-Location $TestDrive
        try { & "$PSScriptRoot/../src/Invoke-HybridMigration.ps1" -Mode Waves -MailboxesFile "$fx/mailboxes.json" -ConfigFile "$fx/migration.test.json" -WaveDirectory (Join-Path $TestDrive 'rw') *> $null } finally { Pop-Location }
        Test-Path (Join-Path $TestDrive 'rw/wave-01.csv') | Should -BeTrue
    }
    It 'the runner refuses FixUpn without a SearchBase and a rollback file' {
        { & "$PSScriptRoot/../src/Invoke-HybridMigration.ps1" -Mode FixUpn -ConfigFile "$fx/migration.test.json" } | Should -Throw '*SearchBase*'
        { & "$PSScriptRoot/../src/Invoke-HybridMigration.ps1" -Mode FixUpn -SearchBase 'OU=x' -ConfigFile "$fx/migration.test.json" } | Should -Throw '*RollbackFile*'
    }
}
