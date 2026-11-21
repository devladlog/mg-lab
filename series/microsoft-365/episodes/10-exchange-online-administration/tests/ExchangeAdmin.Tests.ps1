BeforeAll {
    # The Exchange cmdlets only exist after Connect-ExchangeOnline (most of them are created by implicit remoting), so the tests define stubs
    # with the documented parameter names. Pester mocks them with a small fake tenant held in a global. If the real ExchangeOnlineManagement module is
    # on PSModulePath, one test checks the Get-EXO* parameters we pass against it.
    $plain = @{
        'Get-AcceptedDomain' = @('Identity'); 'Get-EXOMailbox' = @('Identity', 'RecipientTypeDetails', 'ResultSize', 'Properties')
        'Get-EXOMailboxStatistics' = @('Identity'); 'Get-EXOMailboxPermission' = @('Identity', 'ResultSize'); 'Get-EXORecipientPermission' = @('Identity', 'ResultSize')
        'Get-InboxRule' = @('Mailbox'); 'Get-TransportRule' = @('ResultSize'); 'Get-HostedOutboundSpamFilterPolicy' = @('Identity'); 'Get-User' = @('ResultSize')
        'Get-MessageTraceV2' = @('StartDate', 'EndDate', 'SenderAddress', 'RecipientAddress', 'Subject', 'SubjectFilterType', 'Status', 'ResultSize')
    }
    $changing = @{
        'Set-Mailbox' = @('Identity', 'ForwardingSmtpAddress', 'DeliverToMailboxAndForward'); 'New-Mailbox' = @('Shared', 'Name', 'DisplayName', 'Alias', 'PrimarySmtpAddress')
        'Add-MailboxPermission' = @('Identity', 'User', 'AccessRights', 'InheritanceType', 'AutoMapping'); 'Remove-MailboxPermission' = @('Identity', 'User', 'AccessRights', 'InheritanceType')
        'Add-RecipientPermission' = @('Identity', 'Trustee', 'AccessRights'); 'Remove-RecipientPermission' = @('Identity', 'Trustee', 'AccessRights')
    }
    foreach ($kind in @(@{ t = $plain; b = '[CmdletBinding()]' }, @{ t = $changing; b = '[CmdletBinding(SupportsShouldProcess)]' })) {
        foreach ($n in $kind.t.Keys) {
            if (Get-Command $n -ErrorAction SilentlyContinue) { continue }
            $plist = ($kind.t[$n] | ForEach-Object { "`$$_" }) -join ', '
            Set-Item -Path "function:global:$n" -Value ([scriptblock]::Create("$($kind.b) param($plist) throw 'stub: not connected'"))
        }
    }
    Import-Module "$PSScriptRoot/../src/ExchangeAdmin/ExchangeAdmin.psd1" -Force
    $script:fx = "$PSScriptRoot/fixtures"
    $script:cfgPath = "$fx/exchange.test.json"
    $script:config = Get-EAConfig -Path $cfgPath
    $script:shipped = Get-EAConfig
    $script:inventory = Get-Content "$fx/inventory.json" -Raw | ConvertFrom-Json
    $script:desired = Get-Content "$fx/desired.json" -Raw | ConvertFrom-Json
    $script:GB = 1GB

    function script:Clone($o) { $o | ConvertTo-Json -Depth 12 | ConvertFrom-Json -Depth 12 }
    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json -Depth 10; & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 10 | Set-Content $p; Get-EAConfig -Path $p
    }
    function script:Find($Inv = $inventory, $Cfg = $config) { @(Get-EAFinding -Inventory $Inv -Config $Cfg) }
    function script:Rule([string]$Name, [object[]]$F = (Find)) { @($F | Where-Object Rule -EQ $Name) }

    # --- fake tenant, built from the fixture inventory so that collecting it again must give the same findings ---
    function script:Reset-Tenant {
        $mb = foreach ($m in @($inventory.mailboxes)) {
            $full = @(@{ User = 'NT AUTHORITY\SELF'; AccessRights = @('FullAccess'); IsInherited = $false; Deny = $false },
                @{ User = 'Domain Admins'; AccessRights = @('FullAccess'); IsInherited = $true; Deny = $false },
                @{ User = 'blocked.user@contoso.com'; AccessRights = @('FullAccess'); IsInherited = $false; Deny = $true },
                @{ User = 'alex.demo@contoso.com'; AccessRights = @('ReadPermission'); IsInherited = $false; Deny = $false })
            foreach ($u in @($m.fullAccess)) { $full += @{ User = $u; AccessRights = @('FullAccess'); IsInherited = $false; Deny = $false } }
            $send = @(@{ Trustee = 'NT AUTHORITY\SELF'; AccessRights = @('SendAs') })
            foreach ($u in @($m.sendAs)) { $send += @{ Trustee = $u; AccessRights = @('SendAs') } }
            @{
                upn = $m.upn; alias = $m.alias; display = $m.displayName; type = $m.type; fwd = $m.forwardingSmtpAddress; fwdAddr = $m.forwardingAddress
                dtmf = [bool]$m.deliverToMailboxAndForward; size = ('{0:N1} GB ({1:N0} bytes)' -f ($m.totalBytes / 1GB), $m.totalBytes); quota = ('{0:N0} GB ({1:N0} bytes)' -f ($m.quotaBytes / 1GB), $m.quotaBytes)
                disabled = $m.accountDisabled; rules = @($m.inboxRules); full = $full; send = $send
            }
        }
        $global:T10 = @{
            Calls = [System.Collections.Generic.List[string]]::new(); Mailboxes = [System.Collections.Generic.List[object]]::new(@($mb))
            Domains = @($inventory.acceptedDomains); Transport = @($inventory.transportRules); Spam = @($inventory.outboundSpamPolicies)
            FailGetUser = $false; FailRulesFor = @(); FailSetFor = @(); FailNew = @(); AddPermFailures = 0; Trace = @(); TraceArgs = $null
        }
    }
    function script:Register-FakeExchange {
        Mock Get-AcceptedDomain -ModuleName ExchangeAdmin { $global:T10.Calls.Add('Get-AcceptedDomain'); $global:T10.Domains | ForEach-Object { [pscustomobject]@{ DomainName = $_.name; DomainType = $_.type } } }
        Mock Get-EXOMailbox -ModuleName ExchangeAdmin {
            $global:T10.Calls.Add("Get-EXOMailbox $Identity")
            $list = @($global:T10.Mailboxes)
            if ($Identity) { $list = @($list | Where-Object { $_.upn -eq $Identity -or $_.alias -eq $Identity }); if ($list.Count -eq 0) { throw "The operation couldn't be performed because object '$Identity' couldn't be found." } }
            elseif ($RecipientTypeDetails) { $list = @($list | Where-Object { $RecipientTypeDetails -contains $_.type }) }
            foreach ($m in $list) {
                [pscustomobject]@{ UserPrincipalName = $m.upn; Alias = $m.alias; DisplayName = $m.display; RecipientTypeDetails = $m.type; ForwardingSmtpAddress = $m.fwd
                    ForwardingAddress = $m.fwdAddr; DeliverToMailboxAndForward = $m.dtmf; ProhibitSendReceiveQuota = $m.quota }
            }
        }
        Mock Get-EXOMailboxStatistics -ModuleName ExchangeAdmin { $global:T10.Calls.Add("Get-EXOMailboxStatistics $Identity"); $m = $global:T10.Mailboxes | Where-Object { $_.upn -eq $Identity }; [pscustomobject]@{ TotalItemSize = $m.size } }
        Mock Get-EXOMailboxPermission -ModuleName ExchangeAdmin { $global:T10.Calls.Add("Get-EXOMailboxPermission $Identity"); $m = $global:T10.Mailboxes | Where-Object { $_.upn -eq $Identity -or $_.alias -eq $Identity }; $m.full | ForEach-Object { [pscustomobject]$_ } }
        Mock Get-EXORecipientPermission -ModuleName ExchangeAdmin { $global:T10.Calls.Add("Get-EXORecipientPermission $Identity"); $m = $global:T10.Mailboxes | Where-Object { $_.upn -eq $Identity -or $_.alias -eq $Identity }; $m.send | ForEach-Object { [pscustomobject]$_ } }
        Mock Get-InboxRule -ModuleName ExchangeAdmin {
            $global:T10.Calls.Add("Get-InboxRule $Mailbox")
            if ($global:T10.FailRulesFor -contains $Mailbox) { throw 'The user does not have permission to read Inbox rules.' }
            $m = $global:T10.Mailboxes | Where-Object { $_.upn -eq $Mailbox }
            foreach ($r in @($m.rules)) { [pscustomobject]@{ Name = $r.name; Enabled = $r.enabled; ForwardTo = $r.forwardTo; ForwardAsAttachmentTo = $r.forwardAsAttachmentTo; RedirectTo = $r.redirectTo } }
        }
        Mock Get-TransportRule -ModuleName ExchangeAdmin {
            $global:T10.Calls.Add('Get-TransportRule')
            foreach ($t in $global:T10.Transport) { [pscustomobject]@{ Name = $t.name; State = $t.state; Mode = $t.mode; Priority = $t.priority; Comments = $t.comments; RedirectMessageTo = $t.redirectMessageTo; BlindCopyTo = $t.blindCopyTo; CopyTo = $t.copyTo } }
        }
        Mock Get-HostedOutboundSpamFilterPolicy -ModuleName ExchangeAdmin { $global:T10.Calls.Add('Get-HostedOutboundSpamFilterPolicy'); foreach ($p in $global:T10.Spam) { [pscustomobject]@{ Name = $p.name; IsDefault = $p.isDefault; AutoForwardingMode = $p.autoForwardingMode } } }
        Mock Get-User -ModuleName ExchangeAdmin {
            $global:T10.Calls.Add('Get-User')
            if ($global:T10.FailGetUser) { throw 'The term Get-User is not recognized (role not assigned).' }
            foreach ($m in $global:T10.Mailboxes) { if ($null -ne $m.disabled) { [pscustomobject]@{ UserPrincipalName = $m.upn; AccountDisabled = $m.disabled } } }
        }
        Mock Set-Mailbox -ModuleName ExchangeAdmin {
            $global:T10.Calls.Add("Set-Mailbox $Identity fwd=$ForwardingSmtpAddress")
            if ($global:T10.FailSetFor -contains $Identity) { throw "Set-Mailbox failed for $Identity" }
            $m = $global:T10.Mailboxes | Where-Object { $_.upn -eq $Identity }
            $m.fwd = $ForwardingSmtpAddress
            if ($null -ne $DeliverToMailboxAndForward) { $m.dtmf = [bool]$DeliverToMailboxAndForward }
        }
        Mock New-Mailbox -ModuleName ExchangeAdmin {
            $global:T10.Calls.Add("New-Mailbox Shared=$Shared Alias=$Alias Name=$Name")
            if ($global:T10.FailNew -contains $Alias) { throw 'The proxy address is already in use.' }
            $global:T10.Mailboxes.Add(@{ upn = "$Alias@contoso.com"; alias = $Alias; display = $DisplayName; type = $(if ($Shared) { 'SharedMailbox' } else { 'UserMailbox' }); fwd = $null; fwdAddr = $null; dtmf = $false
                    size = '0 B (0 bytes)'; quota = '50 GB (53,687,091,200 bytes)'; disabled = $false; rules = @(); full = @(@{ User = 'NT AUTHORITY\SELF'; AccessRights = @('FullAccess'); IsInherited = $false; Deny = $false }); send = @() })
        }
        Mock Add-MailboxPermission -ModuleName ExchangeAdmin {
            $global:T10.Calls.Add("Add-MailboxPermission $Identity $User $AccessRights")
            if ($global:T10.AddPermFailures -gt 0) { $global:T10.AddPermFailures--; throw "Couldn't find object '$Identity'." }
            $m = $global:T10.Mailboxes | Where-Object { $_.alias -eq $Identity -or $_.upn -eq $Identity }
            $m.full += @{ User = $User; AccessRights = @('FullAccess'); IsInherited = $false; Deny = $false }
        }
        Mock Add-RecipientPermission -ModuleName ExchangeAdmin {
            $global:T10.Calls.Add("Add-RecipientPermission $Identity $Trustee $AccessRights")
            $m = $global:T10.Mailboxes | Where-Object { $_.alias -eq $Identity -or $_.upn -eq $Identity }
            $m.send += @{ Trustee = $Trustee; AccessRights = @('SendAs') }
        }
        Mock Remove-MailboxPermission -ModuleName ExchangeAdmin {
            $global:T10.Calls.Add("Remove-MailboxPermission $Identity $User")
            $m = $global:T10.Mailboxes | Where-Object { $_.alias -eq $Identity -or $_.upn -eq $Identity }
            $m.full = @($m.full | Where-Object { $_.User -ne $User })
        }
        Mock Remove-RecipientPermission -ModuleName ExchangeAdmin {
            $global:T10.Calls.Add("Remove-RecipientPermission $Identity $Trustee")
            $m = $global:T10.Mailboxes | Where-Object { $_.alias -eq $Identity -or $_.upn -eq $Identity }
            $m.send = @($m.send | Where-Object { $_.Trustee -ne $Trustee })
        }
        Mock Get-MessageTraceV2 -ModuleName ExchangeAdmin {
            $global:T10.TraceArgs = @{ StartDate = $StartDate; EndDate = $EndDate; SenderAddress = $SenderAddress; RecipientAddress = $RecipientAddress; Subject = $Subject
                SubjectFilterType = $SubjectFilterType; Status = $Status; ResultSize = $ResultSize }
            $global:T10.Trace | ForEach-Object { [pscustomobject]$_ }
        }
    }
    function script:Writes { @($global:T10.Calls | Where-Object { $_ -match '^(Set|New|Add|Remove)-' }) }
    function script:Mbx([string]$Name) { $global:T10.Mailboxes | Where-Object { $_.upn -like "$Name@*" -or $_.alias -eq $Name } }
}

Describe 'Helpers' {
    It 'finds addresses in the strings Exchange returns' {
        InModuleScope ExchangeAdmin {
            @(ConvertTo-EAAddress 'smtp:Alex@Example.com') | Should -Be @('alex@example.com')
            @(ConvertTo-EAAddress '"Riley Home" [SMTP:riley.home@example.net]') | Should -Be @('riley.home@example.net')
            @(ConvertTo-EAAddress @('a@x.org', 'b@y.org')) | Should -Be @('a@x.org', 'b@y.org')
            @(ConvertTo-EAAddress 'Casey Contractor').Count | Should -Be 0
            @(ConvertTo-EAAddress $null).Count | Should -Be 0
        }
    }
    It 'reads sizes from text, numbers and objects, and treats Unlimited as no number' {
        InModuleScope ExchangeAdmin {
            ConvertTo-EAByteCount '1.2 GB (1,288,490,188 bytes)' | Should -Be 1288490188
            ConvertTo-EAByteCount '99 GB (106.300.440.576 bytes)' | Should -Be 106300440576
            ConvertTo-EAByteCount 5000 | Should -Be 5000
            ConvertTo-EAByteCount '2 GB' | Should -Be 2147483648
            ConvertTo-EAByteCount 'Unlimited' | Should -BeNullOrEmpty
            ConvertTo-EAByteCount $null | Should -BeNullOrEmpty
            $obj = [pscustomobject]@{}; Add-Member -InputObject $obj -MemberType ScriptMethod -Name ToBytes -Value { 4096 }
            ConvertTo-EAByteCount $obj | Should -Be 4096
        }
    }
    It 'treats accepted Authoritative and InternalRelay domains as internal, ExternalRelay and everything else as external' {
        $t = { param($a, $cfg = $config) InModuleScope ExchangeAdmin -Parameters @{ a = $a; cfg = $cfg; inv = $inventory } { Test-EAExternalAddress -Address $a -Inventory $inv -Config $cfg } }
        & $t 'x@contoso.com' | Should -BeFalse
        & $t 'x@contoso.onmicrosoft.com' | Should -BeFalse
        & $t 'x@partner-relay.example' | Should -BeTrue
        & $t 'x@example.com' | Should -BeTrue
        & $t 'X@CONTOSO.COM' | Should -BeFalse
    }
    It 'honours wildcard accepted domains and the allowed external domains from the config' {
        $inv = Clone $inventory; $inv.acceptedDomains += [pscustomobject]@{ name = '*.fabrikam.example'; type = 'InternalRelay' }
        $cfg = New-Config { param($c) $c.forwarding.allowedExternalDomains = @('Example.ORG') }
        InModuleScope ExchangeAdmin -Parameters @{ inv = $inv; cfg = $cfg } {
            Test-EAExternalAddress -Address 'a@eu.fabrikam.example' -Inventory $inv -Config $cfg | Should -BeFalse
            Test-EAExternalAddress -Address 'a@example.org' -Inventory $inv -Config $cfg | Should -BeFalse
            Test-EAExternalAddress -Address 'a@example.net' -Inventory $inv -Config $cfg | Should -BeTrue
        }
    }
}

Describe 'Get-EAConfig' {
    It 'loads the shipped config: nothing is fixed by default, limits match Learn' {
        $shipped.fix.allowedRules.Count | Should -Be 0
        $shipped.forwarding.allowedExternalDomains.Count | Should -Be 0
        $shipped.sharedMailbox.limitGb | Should -Be 50
        $shipped.trace.maxDays | Should -Be 10
        $shipped.outboundSpam.flagModes | Should -Contain 'Automatic'
    }
    It 'turns a single string or an empty list into an array' {
        $c = New-Config { param($c) $c.forwarding.allowedExternalDomains = 'example.org'; $c.forwarding.ignoreMailboxes = @() }
        , $c.forwarding.allowedExternalDomains | Should -BeOfType [object[]]
        $c.forwarding.allowedExternalDomains | Should -Be @('example.org')
        $c.forwarding.ignoreMailboxes.Count | Should -Be 0
    }
    It 'rejects a rule it cannot fix, a window over 10 days, a bad percentage and a missing section' {
        { New-Config { param($c) $c.fix.allowedRules = @('InboxRuleForwardingExternal') } } | Should -Throw '*not a rule this module can fix*'
        { New-Config { param($c) $c.trace.maxDays = 11 } } | Should -Throw '*at most 10 days*'
        { New-Config { param($c) $c.quota.warnPercent = 0 } } | Should -Throw '*between 1 and 100*'
        { New-Config { param($c) $c.PSObject.Properties.Remove('provision') } } | Should -Throw "*missing the 'provision' section*"
        { Get-EAConfig -Path "$TestDrive/nope.json" } | Should -Throw '*not found*'
    }
}

Describe 'Get-EAFinding: what the audit reports' {
    It 'flags admin-set forwarding to an outside address, and says whether a copy is kept' {
        $r = Rule 'MailboxForwardingExternal'
        ($r | Where-Object Target -Like 'sam.demo@*').Severity | Should -Be 'High'
        ($r | Where-Object Target -Like 'sam.demo@*').Detail | Should -BeLike '*sam.private@example.com*without keeping a copy*'
        ($r | Where-Object Target -Like 'taylor.demo@*').Detail | Should -BeLike '*and keeps a copy*'
        ($r | Where-Object Target -Like 'sam.demo@*').Fixable | Should -BeTrue
    }
    It 'does not flag forwarding to an address inside the organization' {
        (Find | Where-Object { $_.Target -like 'jordan.demo@*' -and $_.Rule -eq 'MailboxForwardingExternal' }) | Should -BeNullOrEmpty
    }
    It 'counts an ExternalRelay accepted domain as outside' {
        (Rule 'MailboxForwardingExternal' | Where-Object Target -Like 'taylor.demo@*') | Should -Not -BeNullOrEmpty
    }
    It 'raises a forwarding recipient name for review instead of guessing whether it is internal' {
        $r = Rule 'MailboxForwardingRecipient'
        $r.Count | Should -Be 1; $r.Severity | Should -Be 'Low'; $r.Detail | Should -BeLike "*Casey Contractor*"; $r.Fixable | Should -BeFalse
    }
    It 'flags an enabled Inbox rule that forwards outside as High and a disabled one as Low; an internal target is fine' {
        $r = Rule 'InboxRuleForwardingExternal' | Where-Object Target -Like 'riley.demo@*'
        $r.Count | Should -Be 2
        ($r | Where-Object Detail -Like "*'Forward to home'*").Severity | Should -Be 'High'
        ($r | Where-Object Detail -Like "*'Old rule'*").Severity | Should -Be 'Low'
        ($r | Where-Object Detail -Like "*'To manager'*") | Should -BeNullOrEmpty
        ($r | Where-Object Detail -Like "*'Forward to home'*").Fixable | Should -BeFalse
    }
    It 'rates a mail flow rule by whether it is live: enabled and enforcing is High, disabled or test mode is Medium' {
        $r = Rule 'TransportRuleExternalCopy'
        ($r | Where-Object Target -EQ 'Copy HR to outside counsel').Severity | Should -Be 'High'
        ($r | Where-Object Target -EQ 'Test redirect').Severity | Should -Be 'Medium'
        ($r | Where-Object Target -EQ 'Compliance copy') | Should -BeNullOrEmpty
    }
    It 'asks for a comment on every mail flow rule (switchable)' {
        @(Rule 'TransportRuleNoComment').Target | Should -Be @('Footer', 'Test redirect')
        $c = New-Config { param($c) $c.transportRules.requireComment = $false }
        Rule 'TransportRuleNoComment' (Find -Cfg $c) | Should -BeNullOrEmpty
    }
    It 'flags outbound spam policies that allow automatic forwarding: On is High, Automatic is Medium, Off is fine' {
        $r = Rule 'OutboundAutoForwarding'
        ($r | Where-Object Target -EQ 'Open').Severity | Should -Be 'High'
        ($r | Where-Object Target -EQ 'Default').Severity | Should -Be 'Medium'
        ($r | Where-Object Target -EQ 'Default').Detail | Should -BeLike '*2021*'
        ($r | Where-Object Target -EQ 'Strict') | Should -BeNullOrEmpty
    }
    It 'knows when a shared mailbox account can sign in, cannot tell, or is blocked' {
        (Rule 'SharedMailboxSignInEnabled').Target | Should -Be @('support@contoso.com')
        (Rule 'SharedMailboxSignInUnknown').Target | Should -Be @('archive-old@contoso.com')
        (Rule 'SharedMailboxSignInUnknown').Severity | Should -Be 'Info'
        $c = New-Config { param($c) $c.sharedMailbox.requireSignInBlocked = $false }
        Rule 'SharedMailboxSignInEnabled' (Find -Cfg $c) | Should -BeNullOrEmpty
    }
    It 'warns before the 50 GB shared mailbox limit and is loud after it' {
        (Rule 'SharedMailboxNearLimit').Target | Should -Be @('support@contoso.com')
        (Rule 'SharedMailboxNearLimit').Detail | Should -BeLike '*92%*'
        (Rule 'SharedMailboxOverLimit').Target | Should -Be @('finance@contoso.com')
        (Rule 'SharedMailboxOverLimit').Hint | Should -BeLike '*Plan 2*'
    }
    It 'reports shared mailboxes nobody can use, and Full Access sprawl' {
        (Rule 'SharedMailboxNoDelegates').Target | Should -Be @('archive-old@contoso.com')
        (Rule 'FullAccessSprawl').Target | Should -Be @('finance@contoso.com')
        (Rule 'FullAccessSprawl').Detail | Should -BeLike '*12 people*'
    }
    It 'warns about an ordinary mailbox near its quota but never about shared ones' {
        (Rule 'MailboxNearQuota').Target | Should -Be @('riley.demo@contoso.com')
    }
    It 'skips the mailboxes listed in forwarding.ignoreMailboxes, and reports them with the shipped config' {
        Find | Where-Object Target -Like 'emergency.access@*' | Should -BeNullOrEmpty
        (Find -Cfg $shipped | Where-Object Target -Like 'emergency.access@*').Rule | Should -Contain 'MailboxForwardingExternal'
    }
    It 'stops flagging a domain once it is in forwarding.allowedExternalDomains' {
        $c = New-Config { param($c) $c.forwarding.allowedExternalDomains = @('example.com', 'example.net', 'example.org') }
        $f = Find -Cfg $c
        (Rule 'MailboxForwardingExternal' $f).Target | Should -Be @('taylor.demo@contoso.com')
        Rule 'InboxRuleForwardingExternal' $f | Should -BeNullOrEmpty
        Rule 'TransportRuleExternalCopy' $f | Should -BeNullOrEmpty
    }
    It 'turns a collection error into an Info finding so a half-finished audit is visible' {
        $inv = Clone $inventory; $inv.errors = @('Inbox rules for jordan.demo@contoso.com: access denied')
        $e = Rule 'CollectionError' (Find $inv)
        $e.Count | Should -Be 1; $e.Severity | Should -Be 'Info'; $e.Detail | Should -BeLike '*access denied*'
    }
    It 'lists High before Medium before Low before Info' {
        $order = @(Find | ForEach-Object Severity)
        $rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
        for ($i = 1; $i -lt $order.Count; $i++) { $rank[$order[$i]] | Should -BeGreaterOrEqual $rank[$order[$i - 1]] }
    }
    It 'gives the same answer for an empty tenant: no findings, no errors' {
        $inv = [pscustomobject]@{ collectedAt = 'x'; acceptedDomains = @(); mailboxes = @(); transportRules = @(); outboundSpamPolicies = @(); errors = @() }
        @(Find $inv).Count | Should -Be 0
    }
    It 'counts findings per severity' {
        $s = Get-EASummary -Findings (Find)
        $s.Total | Should -Be 18; $s.High | Should -Be 6; $s.Medium | Should -Be 4; $s.Low | Should -Be 7; $s.Info | Should -Be 1; $s.Fixable | Should -Be 2
        (Get-EASummary -Findings @()).Total | Should -Be 0
    }
}

Describe 'Get-EAFixPlan: what may be fixed' {
    It 'plans nothing when no rule is allowed (the shipped default), even with findings' {
        @(Get-EAFixPlan -Findings (Find -Cfg $shipped) -Config $shipped -Inventory $inventory).Count | Should -Be 0
    }
    It 'plans only mailbox forwarding to an outside address, never Inbox rules, transport rules or policies' {
        $p = @(Get-EAFixPlan -Findings (Find) -Config $config -Inventory $inventory)
        $p.Mailbox | Should -Be @('sam.demo@contoso.com', 'taylor.demo@contoso.com')
        ($p | Where-Object Mailbox -Like 'taylor*').DeliverToMailboxAndForward | Should -BeTrue
        ($p | Where-Object Mailbox -Like 'sam*').ForwardingSmtpAddress | Should -Be 'smtp:sam.private@example.com'
    }
    It 'never plans an ignored mailbox' {
        (Get-EAFixPlan -Findings (Find -Cfg $shipped | Where-Object Rule -EQ 'MailboxForwardingExternal') -Config (New-Config { param($c) $c.forwarding.ignoreMailboxes = @() }) -Inventory $inventory).Mailbox | Should -Contain 'emergency.access@contoso.com'
        (Get-EAFixPlan -Findings (Find) -Config $config -Inventory $inventory).Mailbox | Should -Not -Contain 'emergency.access@contoso.com'
    }
}

Describe 'Get-EAInventory (fake tenant)' {
    BeforeEach { Register-FakeExchange; Reset-Tenant }
    It 'collects with read cmdlets only' {
        $null = Get-EAInventory
        Writes | Should -BeNullOrEmpty
        $global:T10.Calls | Should -Contain 'Get-TransportRule'
    }
    It 'gives the same findings as the fixture it was built from' {
        $live = Get-EAInventory
        $a = @(Find $live | ForEach-Object { "$($_.Severity)|$($_.Rule)|$($_.Target)" })
        $b = @(Find | ForEach-Object { "$($_.Severity)|$($_.Rule)|$($_.Target)" })
        $a | Should -Be $b
    }
    It 'keeps only real, direct, allowed Full Access and Send As entries (no SELF, inherited, deny or other rights)' {
        $inv = Get-EAInventory
        ($inv.mailboxes | Where-Object upn -EQ 'support@contoso.com').fullAccess | Should -Be @('alex.demo@contoso.com', 'sam.demo@contoso.com')
        ($inv.mailboxes | Where-Object upn -EQ 'support@contoso.com').sendAs | Should -Be @('alex.demo@contoso.com')
    }
    It 'asks for permissions only on shared mailboxes' {
        $null = Get-EAInventory
        @($global:T10.Calls | Where-Object { $_ -like 'Get-EXOMailboxPermission*' }).Count | Should -Be 3
    }
    It 'reads sizes into bytes and an unknown sign-in state as null, not as enabled' {
        $inv = Get-EAInventory
        ($inv.mailboxes | Where-Object upn -EQ 'finance@contoso.com').totalBytes | Should -Be (51 * 1GB)
        ($inv.mailboxes | Where-Object upn -EQ 'archive-old@contoso.com').accountDisabled | Should -BeNullOrEmpty
        ($inv.mailboxes | Where-Object upn -EQ 'support@contoso.com').accountDisabled | Should -BeFalse
    }
    It 'survives Get-User being refused: sign-in state stays unknown and the error is recorded' {
        $global:T10.FailGetUser = $true
        $inv = Get-EAInventory
        $inv.errors | Should -Contain ($inv.errors | Where-Object { $_ -like 'Get-User failed*' } | Select-Object -First 1)
        @($inv.mailboxes | Where-Object { $null -ne $_.accountDisabled }).Count | Should -Be 0
        (Rule 'SharedMailboxSignInUnknown' (Find $inv)).Count | Should -Be 3
    }
    It 'records an Inbox-rule failure for one mailbox and carries on with the others' {
        $global:T10.FailRulesFor = @('jordan.demo@contoso.com')
        $inv = Get-EAInventory
        @($inv.errors | Where-Object { $_ -like 'Inbox rules for jordan.demo@contoso.com*' }).Count | Should -Be 1
        (Rule 'InboxRuleForwardingExternal' (Find $inv) | Where-Object Target -Like 'riley*').Count | Should -Be 2
    }
    It '-SkipInboxRules never calls Get-InboxRule; -MaxMailboxes limits the walk' {
        $null = Get-EAInventory -SkipInboxRules
        @($global:T10.Calls | Where-Object { $_ -like 'Get-InboxRule*' }).Count | Should -Be 0
        (Get-EAInventory -MaxMailboxes 2).mailboxes.Count | Should -Be 2
    }
}

Describe 'Invoke-EAForwardingFix and Restore-EAForwarding (fake tenant)' {
    BeforeEach {
        Register-FakeExchange; Reset-Tenant
        $script:rb = Join-Path $TestDrive ("rollback-{0}.json" -f [guid]::NewGuid())
        $script:plan = @(Get-EAFixPlan -Findings (Find) -Config $config -Inventory $inventory)
    }
    It '-WhatIf sends no write and creates no rollback file' {
        Invoke-EAForwardingFix -Plan $plan -RollbackFile $rb -WhatIf | ForEach-Object Status | Should -Be @('Skipped', 'Skipped')
        Writes | Should -BeNullOrEmpty
        Test-Path $rb | Should -BeFalse
    }
    It 'removes only the forwarding address, records it, and leaves DeliverToMailboxAndForward alone' {
        $res = @(Invoke-EAForwardingFix -Plan $plan -RollbackFile $rb -Confirm:$false)
        $res.Status | Should -Be @('Removed', 'Removed')
        (Mbx 'sam.demo').fwd | Should -BeNullOrEmpty
        (Mbx 'taylor.demo').dtmf | Should -BeTrue
        Writes | Should -Be @('Set-Mailbox sam.demo@contoso.com fwd=', 'Set-Mailbox taylor.demo@contoso.com fwd=')
        $saved = @(Get-Content $rb -Raw | ConvertFrom-Json)
        $saved.Count | Should -Be 2
        $saved[0].mailbox | Should -Be 'sam.demo@contoso.com'; $saved[0].forwardingSmtpAddress | Should -Be 'smtp:sam.private@example.com'
        $saved[1].deliverToMailboxAndForward | Should -BeTrue
    }
    It 'refuses to overwrite an earlier rollback file' {
        Set-Content $rb '[]'
        { Invoke-EAForwardingFix -Plan $plan -RollbackFile $rb -Confirm:$false } | Should -Throw '*already exists*'
        Writes | Should -BeNullOrEmpty
    }
    It 'skips a mailbox whose forwarding changed after the audit' {
        (Mbx 'sam.demo').fwd = 'smtp:someone.else@example.com'
        $res = @(Invoke-EAForwardingFix -Plan $plan -RollbackFile $rb -Confirm:$false)
        ($res | Where-Object Mailbox -Like 'sam*').Status | Should -Be 'Skipped'
        ($res | Where-Object Mailbox -Like 'sam*').Message | Should -BeLike '*changed since the audit*'
        (Mbx 'sam.demo').fwd | Should -Be 'smtp:someone.else@example.com'
        ($res | Where-Object Mailbox -Like 'taylor*').Status | Should -Be 'Removed'
    }
    It 'stops at a failure and the rollback file holds exactly what was removed before it' {
        $global:T10.FailSetFor = @('taylor.demo@contoso.com')
        $res = @(Invoke-EAForwardingFix -Plan $plan -RollbackFile $rb -Confirm:$false)
        $res.Status | Should -Be @('Removed', 'Failed')
        @(Get-Content $rb -Raw | ConvertFrom-Json).mailbox | Should -Be @('sam.demo@contoso.com')
    }
    It 'Restore puts the forwarding back, with the copy setting, and does not overwrite a new one' {
        $null = Invoke-EAForwardingFix -Plan $plan -RollbackFile $rb -Confirm:$false
        (Mbx 'taylor.demo').fwd = 'smtp:new.target@example.com'
        $res = @(Restore-EAForwarding -RollbackFile $rb)
        ($res | Where-Object Mailbox -Like 'sam*').Status | Should -Be 'Restored'
        (Mbx 'sam.demo').fwd | Should -Be 'smtp:sam.private@example.com'
        ($res | Where-Object Mailbox -Like 'taylor*').Status | Should -Be 'Skipped'
        (Mbx 'taylor.demo').fwd | Should -Be 'smtp:new.target@example.com'
    }
    It 'Restore -WhatIf writes nothing, and a missing file is an error' {
        $null = Invoke-EAForwardingFix -Plan $plan -RollbackFile $rb -Confirm:$false
        $before = @(Writes).Count
        (Restore-EAForwarding -RollbackFile $rb -WhatIf).Status | Should -Be @('Skipped', 'Skipped')
        @(Writes).Count | Should -Be $before
        { Restore-EAForwarding -RollbackFile "$TestDrive/none.json" } | Should -Throw '*not found*'
    }
    It 'the whole circle: audit, fix, audit again shows the finding gone' {
        $null = Invoke-EAForwardingFix -Plan $plan -RollbackFile $rb -Confirm:$false
        $after = Find (Get-EAInventory)
        Rule 'MailboxForwardingExternal' $after | Should -BeNullOrEmpty
        Rule 'InboxRuleForwardingExternal' $after | Should -Not -BeNullOrEmpty
    }
}

Describe 'Shared mailboxes from a file (fake tenant)' {
    BeforeEach { Register-FakeExchange; Reset-Tenant }
    It 'plans a missing mailbox as create plus its grants, and only the missing grants for an existing one' {
        $plan = @(Get-EASharedMailboxPlan -Desired $desired -Inventory (Get-EAInventory))
        ($plan | ForEach-Object { "$($_.Action) $($_.Mailbox) $($_.User)".Trim() }) | Should -Be @(
            'AddFullAccess support jordan.demo@contoso.com', 'CreateMailbox helpdesk', 'AddFullAccess helpdesk alex.demo@contoso.com',
            'AddFullAccess helpdesk sam.demo@contoso.com', 'AddSendAs helpdesk alex.demo@contoso.com')
    }
    It 'applies the plan, and a second run has nothing left to do (idempotent)' {
        $plan = @(Get-EASharedMailboxPlan -Desired $desired -Inventory (Get-EAInventory))
        $res = @(Invoke-EASharedMailboxPlan -Plan $plan -Desired $desired -RetrySeconds 0)
        $res.Status | Should -Be (@('Done') * 5)
        (Writes) | Should -Contain 'New-Mailbox Shared=True Alias=helpdesk Name=Help Desk'
        @(Get-EASharedMailboxPlan -Desired $desired -Inventory (Get-EAInventory)).Count | Should -Be 0
        (Get-EAInventory).mailboxes | Where-Object upn -EQ 'helpdesk@contoso.com' | ForEach-Object { $_.type | Should -Be 'SharedMailbox'; $_.fullAccess | Should -Be @('alex.demo@contoso.com', 'sam.demo@contoso.com') }
    }
    It '-WhatIf sends no write' {
        $plan = @(Get-EASharedMailboxPlan -Desired $desired -Inventory (Get-EAInventory))
        $res = @(Invoke-EASharedMailboxPlan -Plan $plan -Desired $desired -WhatIf)
        $res.Status | Should -Not -Contain 'Done'
        Writes | Should -BeNullOrEmpty
    }
    It 'never converts or changes an existing user mailbox that has the wanted alias' {
        $d = [pscustomobject]@{ mailboxes = @([pscustomobject]@{ alias = 'sam.demo'; fullAccess = @('alex.demo@contoso.com') }) }
        $plan = @(Get-EASharedMailboxPlan -Desired $d -Inventory (Get-EAInventory))
        $plan.Count | Should -Be 1; $plan[0].Action | Should -Be 'Conflict'
        (Invoke-EASharedMailboxPlan -Plan $plan -Desired $d).Status | Should -Be 'Skipped'
        Writes | Should -BeNullOrEmpty
    }
    It 'adds only unless -RemoveExtra is given; then it removes what is not declared' {
        $d = [pscustomobject]@{ mailboxes = @([pscustomobject]@{ alias = 'support'; fullAccess = @('alex.demo@contoso.com'); sendAs = @() }) }
        $inv = Get-EAInventory
        @(Get-EASharedMailboxPlan -Desired $d -Inventory $inv).Count | Should -Be 0
        $plan = @(Get-EASharedMailboxPlan -Desired $d -Inventory $inv -RemoveExtra)
        ($plan | ForEach-Object { "$($_.Action) $($_.User)" }) | Should -Be @('RemoveFullAccess sam.demo@contoso.com', 'RemoveSendAs alex.demo@contoso.com')
        $null = Invoke-EASharedMailboxPlan -Plan $plan -Desired $d
        (Mbx 'support').full.User | Should -Not -Contain 'sam.demo@contoso.com'
        (Mbx 'support').full.User | Should -Contain 'alex.demo@contoso.com'
    }
    It 'matches aliases and addresses without caring about case, and rejects a missing or repeated alias' {
        $d = [pscustomobject]@{ mailboxes = @([pscustomobject]@{ alias = 'SUPPORT'; fullAccess = @('ALEX.DEMO@contoso.com', 'sam.demo@contoso.com') }) }
        @(Get-EASharedMailboxPlan -Desired $d -Inventory (Get-EAInventory)).Count | Should -Be 0
        { Get-EASharedMailboxPlan -Desired ([pscustomobject]@{ mailboxes = @([pscustomobject]@{ displayName = 'x' }) }) -Inventory $inventory } | Should -Throw '*no alias*'
        { Get-EASharedMailboxPlan -Desired ([pscustomobject]@{ mailboxes = @([pscustomobject]@{ alias = 'a' }, [pscustomobject]@{ alias = 'A' }) }) -Inventory $inventory } | Should -Throw '*twice*'
    }
    It 'retries the grants of a mailbox it just created (the new object may not be visible yet), and only those' {
        $global:T10.AddPermFailures = 2
        $d = [pscustomobject]@{ mailboxes = @([pscustomobject]@{ alias = 'helpdesk'; fullAccess = @('alex.demo@contoso.com') }) }
        $res = @(Invoke-EASharedMailboxPlan -Plan @(Get-EASharedMailboxPlan -Desired $d -Inventory (Get-EAInventory)) -Desired $d -RetryCount 3 -RetrySeconds 0)
        $res.Status | Should -Be @('Done', 'Done')
        @($global:T10.Calls | Where-Object { $_ -like 'Add-MailboxPermission*' }).Count | Should -Be 3
        # an existing mailbox gets one try: a real failure is reported at once
        $global:T10.AddPermFailures = 1
        $d2 = [pscustomobject]@{ mailboxes = @([pscustomobject]@{ alias = 'support'; fullAccess = @('alex.demo@contoso.com', 'sam.demo@contoso.com', 'jordan.demo@contoso.com') }) }
        $r2 = @(Invoke-EASharedMailboxPlan -Plan @(Get-EASharedMailboxPlan -Desired $d2 -Inventory (Get-EAInventory)) -Desired $d2 -RetryCount 3 -RetrySeconds 0)
        $r2[0].Status | Should -Be 'Failed'; $r2[0].Message | Should -BeLike "*Couldn't find*"
    }
    It 'when the mailbox cannot be created it reports that and skips its grants' {
        $global:T10.FailNew = @('helpdesk')
        $res = @(Invoke-EASharedMailboxPlan -Plan @(Get-EASharedMailboxPlan -Desired $desired -Inventory (Get-EAInventory)) -Desired $desired -RetrySeconds 0)
        ($res | Where-Object { $_.Action -eq 'CreateMailbox' }).Status | Should -Be 'Failed'
        ($res | Where-Object { $_.Mailbox -eq 'helpdesk' -and $_.Action -ne 'CreateMailbox' }).Status | Should -Be @('Skipped', 'Skipped', 'Skipped')
        ($res | Where-Object { $_.Mailbox -eq 'support' }).Status | Should -Be 'Done'
    }
    It 'sends the primary address when the file declares one' {
        $d = [pscustomobject]@{ mailboxes = @([pscustomobject]@{ alias = 'billing'; displayName = 'Billing'; primarySmtpAddress = 'billing@contoso.com' }) }
        $null = Invoke-EASharedMailboxPlan -Plan @(Get-EASharedMailboxPlan -Desired $d -Inventory (Get-EAInventory)) -Desired $d
        Should -Invoke New-Mailbox -ModuleName ExchangeAdmin -Times 1 -Exactly -ParameterFilter { $PrimarySmtpAddress -eq 'billing@contoso.com' -and $Shared }
    }
}

Describe 'Get-EAMessageTrace' {
    BeforeEach {
        Register-FakeExchange; Reset-Tenant
        $script:now = [datetime]::SpecifyKind([datetime]'2026-11-21T12:00:00', 'Utc')
        $global:T10.Trace = @(
            @{ Received = [datetime]'2026-11-21T10:05:00'; SenderAddress = 'alex.demo@contoso.com'; RecipientAddress = 'sam.demo@contoso.com'; Subject = 'Hello'; Status = 'Delivered'; Size = 2048; MessageTraceId = '00000000-0000-0000-0000-000000000001' },
            @{ Received = [datetime]'2026-11-21T09:00:00'; SenderAddress = 'alex.demo@contoso.com'; RecipientAddress = 'friend@example.com'; Subject = 'Hello'; Status = 'Failed'; Size = 1024; MessageTraceId = '00000000-0000-0000-0000-000000000002' })
    }
    It 'defaults to the last 48 hours and passes the filters through' {
        $rows = @(Get-EAMessageTrace -SenderAddress 'alex.demo@contoso.com' -Subject 'Hello' -Status Failed, Delivered -Config $config -Now $now)
        $a = $global:T10.TraceArgs
        $a.EndDate | Should -Be $now
        $a.StartDate | Should -Be $now.AddHours(-48)
        $a.SenderAddress | Should -Be 'alex.demo@contoso.com'
        $a.Subject | Should -Be 'Hello'; $a.SubjectFilterType | Should -Be 'StartsWith'
        $a.Status | Should -Be @('Failed', 'Delivered')
        $a.ResultSize | Should -Be 100
        $rows.Count | Should -Be 2
    }
    It 'returns the oldest message first with readable column names' {
        $rows = @(Get-EAMessageTrace -Config $config -Now $now)
        $rows[0].Status | Should -Be 'Failed'; $rows[0].Recipient | Should -Be 'friend@example.com'
        $rows[1].TraceId | Should -Be '00000000-0000-0000-0000-000000000001'
    }
    It 'uses -Hours, and an explicit Start and End' {
        $null = Get-EAMessageTrace -Hours 6 -Config $config -Now $now
        $global:T10.TraceArgs.StartDate | Should -Be $now.AddHours(-6)
        $null = Get-EAMessageTrace -Start ([datetime]'2026-11-15') -End ([datetime]'2026-11-16') -Config $config -Now $now
        $global:T10.TraceArgs.StartDate | Should -Be ([datetime]'2026-11-15')
    }
    It 'refuses a window over 10 days or older than 90 days, before calling the service' {
        { Get-EAMessageTrace -Start ([datetime]'2026-11-01') -End ([datetime]'2026-11-20') -Config $config -Now $now } | Should -Throw '*at most 10 days*'
        { Get-EAMessageTrace -Start ([datetime]'2026-06-01') -End ([datetime]'2026-06-02') -Config $config -Now $now } | Should -Throw '*90 days*'
        { Get-EAMessageTrace -Start ([datetime]'2026-11-20') -End ([datetime]'2026-11-19') -Config $config -Now $now } | Should -Throw '*after Start*'
        { Get-EAMessageTrace -Top 6000 -Config $config -Now $now } | Should -Throw '*1 to 5000*'
        Should -Invoke Get-MessageTraceV2 -ModuleName ExchangeAdmin -Times 0 -Exactly
    }
    It 'warns when the result hits the limit, because the cmdlet has no paging' {
        $w = $null
        $null = Get-EAMessageTrace -Top 2 -Config $config -Now $now -WarningVariable w -WarningAction SilentlyContinue
        "$w" | Should -BeLike '*cut off*'
    }
}

Describe 'ConvertTo-EAMarkdown' {
    It 'writes the summary, one row per finding, the hint per rule and an empty fix plan note' {
        $f = Find
        $md = ConvertTo-EAMarkdown -Inventory $inventory -Findings $f
        $md | Should -BeLike '*# Exchange Online audit*'
        $md | Should -BeLike '*18 findings:** 6 high, 4 medium, 7 low, 1 info*'
        @($md -split "`n" | Where-Object { $_ -like '| High |*' }).Count | Should -Be 6
        $md.Contains('Empty. Nothing is fixed unless a rule is listed in `fix.allowedRules`.') | Should -BeTrue
    }
    It 'lists the fix plan when there is one, and escapes pipes in table cells' {
        $inv = Clone $inventory; $inv.transportRules[0].name = 'Copy | to counsel'
        $plan = @(Get-EAFixPlan -Findings (Find) -Config $config -Inventory $inventory)
        $md = ConvertTo-EAMarkdown -Inventory $inv -Findings (Find $inv) -FixPlan $plan
        $md | Should -BeLike '*Fix plan (2 forwarding removals)*'
        $md | Should -BeLike '*Copy \| to counsel*'
    }
    It 'says so when nothing was found' {
        $inv = [pscustomobject]@{ collectedAt = 'x'; acceptedDomains = @(); mailboxes = @(); transportRules = @(); outboundSpamPolicies = @(); errors = @() }
        ConvertTo-EAMarkdown -Inventory $inv -Findings @() | Should -BeLike '*Nothing to report*'
    }
}

Describe 'Runner' {
    It 'audits a snapshot offline and writes the report' {
        $out = Join-Path $TestDrive 'audit.md'
        $text = (& "$PSScriptRoot/../src/Invoke-ExchangeAdmin.ps1" -Snapshot "$fx/inventory.json" -ConfigFile $cfgPath -OutFile $out) -join "`n"
        $text | Should -BeLike '*Findings: 18 (6 high, 4 medium, 7 low, 1 info). Fixable here: 2. Fix plan: 2 removal(s).*'
        Test-Path $out | Should -BeTrue
    }
    It 'refuses to fix or sync from a snapshot, and a fix without a rollback file' {
        { & "$PSScriptRoot/../src/Invoke-ExchangeAdmin.ps1" -Mode Fix -Snapshot "$fx/inventory.json" -RollbackFile "$TestDrive/r.json" } | Should -Throw '*needs the live tenant*'
        { & "$PSScriptRoot/../src/Invoke-ExchangeAdmin.ps1" -Mode Fix } | Should -Throw '*needs -RollbackFile*'
        { & "$PSScriptRoot/../src/Invoke-ExchangeAdmin.ps1" -Mode Restore } | Should -Throw '*needs -RollbackFile*'
    }
    It 'the shipped shared-mailboxes file declares nothing' {
        (Get-Content "$PSScriptRoot/../src/shared-mailboxes.json" -Raw | ConvertFrom-Json).mailboxes.Count | Should -Be 0
    }
}

Describe 'Real modules' {
    It 'Connect-ExchangeOnline and the Get-EXO* cmdlets take the parameters we pass' -Skip:(-not (Get-Module -ListAvailable ExchangeOnlineManagement)) {
        Import-Module ExchangeOnlineManagement -ErrorAction Stop
        $c = (Get-Command Connect-ExchangeOnline).Parameters.Keys
        $c | Should -Contain 'ShowBanner'; $c | Should -Contain 'UserPrincipalName'
        $m = (Get-Command Get-EXOMailbox).Parameters.Keys
        foreach ($n in 'RecipientTypeDetails', 'ResultSize', 'Properties', 'Identity') { $m | Should -Contain $n }
        (Get-Command Get-EXOMailboxStatistics).Parameters.Keys | Should -Contain 'Identity'
        foreach ($cmd in 'Get-EXOMailboxPermission', 'Get-EXORecipientPermission') {
            $p = (Get-Command $cmd).Parameters.Keys; $p | Should -Contain 'Identity'; $p | Should -Contain 'ResultSize'
        }
    }
}
