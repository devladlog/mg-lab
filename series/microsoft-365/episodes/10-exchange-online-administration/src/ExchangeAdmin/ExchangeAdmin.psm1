Set-StrictMode -Version Latest

# ExchangeAdmin: Exchange Online administration with the Exchange Online PowerShell module (EXO V3).
# The Exchange cmdlets (Get-EXOMailbox, Set-Mailbox, ...) only exist after Connect-ExchangeOnline; the module never connects by itself.
# Reading is always safe. Writing is limited to: removing mailbox-level external forwarding (rollback file) and a declared list of shared mailboxes.

$script:SeverityOrder = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
$script:KnownFixRules = @('MailboxForwardingExternal')

#region helpers

function Get-EAProp {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $null } }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    return $null
}

function ConvertTo-EAStringList {
    # Any value (null, string, collection, recipient objects) to a clean array of non-empty strings.
    param($Value)
    $out = New-Object System.Collections.Generic.List[string]
    if ($null -ne $Value) {
        foreach ($v in @($Value)) {
            if ($null -eq $v) { continue }
            $s = "$v".Trim()
            if ($s) { $out.Add($s) }
        }
    }
    return $out.ToArray()
}

function ConvertTo-EAAddress {
    # Pulls SMTP addresses out of the strings Exchange returns for recipients: 'alex@example.com', 'smtp:alex@example.com',
    # '"Alex Ext" [SMTP:alex@example.com]'. A value that holds no address (a plain recipient name) yields nothing.
    param($Value)
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($v in @($Value)) {
        if ($null -eq $v) { continue }
        foreach ($m in [regex]::Matches("$v", '[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+')) { $out.Add($m.Value.ToLowerInvariant()) }
    }
    return $out.ToArray()
}

function ConvertTo-EAByteCount {
    # Exchange sizes come back as '1.2 GB (1,288,490,188 bytes)', as ByteQuantifiedSize objects, as numbers or as 'Unlimited'.
    param($Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [int] -or $Value -is [long] -or $Value -is [double] -or $Value -is [uint64] -or $Value -is [decimal]) { return [long]$Value }
    if ($Value.PSObject.Methods['ToBytes']) { return [long]$Value.ToBytes() }
    $s = "$Value".Trim()
    if (-not $s -or $s -match 'Unlimited') { return $null }
    if ($s -match '\(([\d,\.\s]+)\s*bytes\)') { return [long]($Matches[1] -replace '[,\.\s]', '') }
    if ($s -match '^\d+$') { return [long]$s }
    $units = @{ B = 1L; KB = 1KB; MB = 1MB; GB = 1GB; TB = 1TB }
    if ($s -match '^([\d\.]+)\s*(B|KB|MB|GB|TB)$') { return [long]([double]::Parse($Matches[1], [cultureinfo]::InvariantCulture) * $units[$Matches[2].ToUpperInvariant()]) }
    return $null
}

function Test-EAExternalAddress {
    # External = the domain is not one of the tenant's accepted domains of type Authoritative or InternalRelay, and not allowed in the config.
    # An ExternalRelay domain is accepted but delivered to another mail system, so it counts as external.
    param([string]$Address, $Inventory, $Config)
    $domain = ($Address -split '@')[-1].ToLowerInvariant()
    foreach ($a in @($Config.forwarding.allowedExternalDomains)) { if ("$a".ToLowerInvariant() -eq $domain) { return $false } }
    foreach ($d in @(Get-EAProp $Inventory 'acceptedDomains')) {
        $type = "$(Get-EAProp $d 'type')"
        if ($type -eq 'ExternalRelay') { continue }
        $name = "$(Get-EAProp $d 'name')".ToLowerInvariant()
        if ($name -eq $domain) { return $false }
        if ($name.StartsWith('*.') -and $domain.EndsWith($name.Substring(1))) { return $false }
    }
    return $true
}

function Get-EAFindingRecord {
    param([string]$Rule, [string]$Severity, [string]$Target, [string]$Detail, [string]$Hint = '', [bool]$Fixable = $false, $Data = $null)
    [pscustomobject]@{ Rule = $Rule; Severity = $Severity; Target = $Target; Detail = $Detail; Hint = $Hint; Fixable = $Fixable; Data = $Data }
}

function Invoke-EARetry {
    param([scriptblock]$Script, [int]$Count = 1, [int]$DelaySeconds = 0)
    $tries = [Math]::Max(1, $Count)
    for ($i = 1; $i -le $tries; $i++) {
        try { return (& $Script) }
        catch {
            if ($i -ge $tries) { throw }
            if ($DelaySeconds -gt 0) { Start-Sleep -Seconds $DelaySeconds }
        }
    }
}

#endregion

#region configuration

function Get-EAConfig {
    [CmdletBinding()]
    param([string]$Path = (Join-Path (Split-Path $PSScriptRoot -Parent) 'exchange.json'))
    if (-not (Test-Path -LiteralPath $Path)) { throw "Config file not found: $Path" }
    $c = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($section in 'forwarding', 'transportRules', 'outboundSpam', 'sharedMailbox', 'fullAccess', 'quota', 'trace', 'provision', 'fix') {
        if ($null -eq (Get-EAProp $c $section)) { throw "Config is missing the '$section' section ($Path)." }
    }
    foreach ($n in 'warnPercent') {
        foreach ($s in 'sharedMailbox', 'quota') {
            $v = Get-EAProp (Get-EAProp $c $s) $n
            if ($null -eq $v -or $v -lt 1 -or $v -gt 100) { throw "$s.$n must be between 1 and 100." }
        }
    }
    if ((Get-EAProp $c.sharedMailbox 'limitGb') -lt 1) { throw 'sharedMailbox.limitGb must be at least 1.' }
    if ((Get-EAProp $c.fullAccess 'maxDelegatesPerMailbox') -lt 1) { throw 'fullAccess.maxDelegatesPerMailbox must be at least 1.' }
    if ($c.trace.maxDays -lt 1 -or $c.trace.maxDays -gt 10) { throw 'trace.maxDays must be 1 to 10: Get-MessageTraceV2 returns at most 10 days per query.' }
    foreach ($r in @($c.fix.allowedRules)) {
        if ($script:KnownFixRules -notcontains $r) { throw "fix.allowedRules: '$r' is not a rule this module can fix. Known: $($script:KnownFixRules -join ', ')." }
    }
    # Normalise the arrays so a one-item JSON array or an empty one behaves the same everywhere.
    $c.forwarding.allowedExternalDomains = @(ConvertTo-EAStringList $c.forwarding.allowedExternalDomains)
    $c.forwarding.ignoreMailboxes = @(ConvertTo-EAStringList $c.forwarding.ignoreMailboxes)
    $c.outboundSpam.flagModes = @(ConvertTo-EAStringList $c.outboundSpam.flagModes)
    $c.fix.allowedRules = @(ConvertTo-EAStringList $c.fix.allowedRules)
    $c
}

#endregion

#region collection (needs a Connect-ExchangeOnline session)

function Get-EAInventory {
    [CmdletBinding()]
    param([switch]$SkipInboxRules, [int]$MaxMailboxes = 0)
    $errors = New-Object System.Collections.Generic.List[string]

    $domains = @(Get-AcceptedDomain | ForEach-Object { [pscustomobject]@{ name = "$($_.DomainName)"; type = "$($_.DomainType)" } })

    $props = 'Alias', 'DisplayName', 'UserPrincipalName', 'RecipientTypeDetails', 'ForwardingSmtpAddress', 'ForwardingAddress', 'DeliverToMailboxAndForward', 'ProhibitSendReceiveQuota'
    $raw = @(Get-EXOMailbox -RecipientTypeDetails UserMailbox, SharedMailbox -ResultSize Unlimited -Properties $props)
    if ($MaxMailboxes -gt 0) { $raw = @($raw | Select-Object -First $MaxMailboxes) }

    # Sign-in state of the account behind each mailbox. If Get-User is not allowed, the answer stays unknown (null), never "enabled".
    $disabled = @{}
    try { foreach ($u in @(Get-User -ResultSize Unlimited)) { $disabled["$($u.UserPrincipalName)".ToLowerInvariant()] = [bool]$u.AccountDisabled } }
    catch { $errors.Add("Get-User failed, sign-in state unknown: $($_.Exception.Message)") }

    $mailboxes = foreach ($m in $raw) {
        $upn = "$($m.UserPrincipalName)"
        $type = "$($m.RecipientTypeDetails)"
        $total = $null
        try { $total = ConvertTo-EAByteCount (Get-EXOMailboxStatistics -Identity $upn -ErrorAction Stop).TotalItemSize }
        catch { $errors.Add("Statistics for ${upn}: $($_.Exception.Message)") }

        $rules = @()
        if (-not $SkipInboxRules) {
            try {
                $rules = @(Get-InboxRule -Mailbox $upn -ErrorAction Stop | ForEach-Object {
                        [pscustomobject]@{
                            name                  = "$($_.Name)"
                            enabled               = [bool]$_.Enabled
                            forwardTo             = @(ConvertTo-EAStringList $_.ForwardTo)
                            forwardAsAttachmentTo = @(ConvertTo-EAStringList $_.ForwardAsAttachmentTo)
                            redirectTo            = @(ConvertTo-EAStringList $_.RedirectTo)
                        } })
            }
            catch { $errors.Add("Inbox rules for ${upn}: $($_.Exception.Message)") }
        }

        $fullAccess = @(); $sendAs = @()
        if ($type -eq 'SharedMailbox') {
            try {
                $fullAccess = @(Get-EXOMailboxPermission -Identity $upn -ResultSize Unlimited -ErrorAction Stop |
                        Where-Object { "$($_.User)" -ne 'NT AUTHORITY\SELF' -and -not $_.IsInherited -and -not $_.Deny -and (@($_.AccessRights) -contains 'FullAccess') } |
                        ForEach-Object { "$($_.User)".ToLowerInvariant() })
                $sendAs = @(Get-EXORecipientPermission -Identity $upn -ResultSize Unlimited -ErrorAction Stop |
                        Where-Object { "$($_.Trustee)" -ne 'NT AUTHORITY\SELF' -and (@($_.AccessRights) -contains 'SendAs') } |
                        ForEach-Object { "$($_.Trustee)".ToLowerInvariant() })
            }
            catch { $errors.Add("Permissions for ${upn}: $($_.Exception.Message)") }
        }

        $accountDisabled = $null
        if ($disabled.ContainsKey($upn.ToLowerInvariant())) { $accountDisabled = $disabled[$upn.ToLowerInvariant()] }

        [pscustomobject]@{
            upn                        = $upn
            alias                      = "$($m.Alias)"
            displayName                = "$($m.DisplayName)"
            type                       = $type
            forwardingSmtpAddress      = $(if ($m.ForwardingSmtpAddress) { "$($m.ForwardingSmtpAddress)" } else { $null })
            forwardingAddress          = $(if ($m.ForwardingAddress) { "$($m.ForwardingAddress)" } else { $null })
            deliverToMailboxAndForward = [bool]$m.DeliverToMailboxAndForward
            totalBytes                 = $total
            quotaBytes                 = ConvertTo-EAByteCount $m.ProhibitSendReceiveQuota
            accountDisabled            = $accountDisabled
            inboxRules                 = $rules
            fullAccess                 = $fullAccess
            sendAs                     = $sendAs
        }
    }

    $transport = @(Get-TransportRule -ResultSize Unlimited | ForEach-Object {
            [pscustomobject]@{
                name            = "$($_.Name)"
                state           = "$($_.State)"
                mode            = "$($_.Mode)"
                priority        = $_.Priority
                comments        = $(if ($_.Comments) { "$($_.Comments)" } else { $null })
                redirectMessageTo = @(ConvertTo-EAStringList $_.RedirectMessageTo)
                blindCopyTo     = @(ConvertTo-EAStringList $_.BlindCopyTo)
                copyTo          = @(ConvertTo-EAStringList $_.CopyTo)
            } })

    $spam = @(Get-HostedOutboundSpamFilterPolicy | ForEach-Object {
            [pscustomobject]@{ name = "$($_.Name)"; isDefault = [bool]$_.IsDefault; autoForwardingMode = "$($_.AutoForwardingMode)" } })

    [pscustomobject]@{
        collectedAt          = (Get-Date).ToUniversalTime().ToString('o')
        acceptedDomains      = $domains
        mailboxes            = @($mailboxes)
        transportRules       = $transport
        outboundSpamPolicies = $spam
        errors               = $errors.ToArray()
    }
}

#endregion

#region analysis (pure: no Exchange calls)

function Get-EAFinding {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Inventory, [Parameter(Mandatory)]$Config)
    $f = New-Object System.Collections.Generic.List[object]
    $ignore = @($Config.forwarding.ignoreMailboxes | ForEach-Object { "$_".ToLowerInvariant() })
    $mailboxes = @(Get-EAProp $Inventory 'mailboxes')

    foreach ($m in $mailboxes) {
        $upn = "$(Get-EAProp $m 'upn')"
        if ($ignore -contains $upn.ToLowerInvariant()) { continue }
        $type = "$(Get-EAProp $m 'type')"
        $isShared = $type -eq 'SharedMailbox'

        # 1. Mailbox-level forwarding (set by an admin)
        $smtp = Get-EAProp $m 'forwardingSmtpAddress'
        foreach ($a in @(ConvertTo-EAAddress $smtp)) {
            if (Test-EAExternalAddress -Address $a -Inventory $Inventory -Config $Config) {
                $keep = [bool](Get-EAProp $m 'deliverToMailboxAndForward')
                $f.Add((Get-EAFindingRecord 'MailboxForwardingExternal' 'High' $upn "Forwards all mail to $a ($(if ($keep) { 'and keeps a copy' } else { 'without keeping a copy' }))." `
                        'Remove it, or allow the domain in forwarding.allowedExternalDomains if it is intended.' $true @{ address = $a }))
            }
        }
        $fwdRecipient = Get-EAProp $m 'forwardingAddress'
        if ($fwdRecipient) {
            $f.Add((Get-EAFindingRecord 'MailboxForwardingRecipient' 'Low' $upn "Forwards all mail to the recipient '$fwdRecipient' (ForwardingAddress). Check that it is internal: a mail contact can point outside." `
                    'Get-Recipient on that name shows whether it is a mail contact or mail user with an external address.'))
        }

        # 2. Inbox rules that forward, redirect or send as attachment
        foreach ($r in @(Get-EAProp $m 'inboxRules')) {
            $targets = @(@(ConvertTo-EAStringList (Get-EAProp $r 'forwardTo')) + @(ConvertTo-EAStringList (Get-EAProp $r 'forwardAsAttachmentTo')) + @(ConvertTo-EAStringList (Get-EAProp $r 'redirectTo')))
            $ext = @(foreach ($a in @(ConvertTo-EAAddress $targets)) { if (Test-EAExternalAddress -Address $a -Inventory $Inventory -Config $Config) { $a } })
            if ($ext.Count -gt 0) {
                $on = [bool](Get-EAProp $r 'enabled')
                $f.Add((Get-EAFindingRecord 'InboxRuleForwardingExternal' $(if ($on) { 'High' } else { 'Low' }) $upn `
                        "Inbox rule '$(Get-EAProp $r 'name')' ($(if ($on) { 'enabled' } else { 'disabled' })) sends mail to $($ext -join ', ')." `
                        'Users create these rules themselves (or an attacker does after a takeover). The outbound spam policy is the control that blocks them.'))
            }
        }

        # 3. Shared mailbox checks
        if ($isShared) {
            $disabled = Get-EAProp $m 'accountDisabled'
            if ($Config.sharedMailbox.requireSignInBlocked) {
                if ($null -eq $disabled) {
                    $f.Add((Get-EAFindingRecord 'SharedMailboxSignInUnknown' 'Info' $upn 'Could not read whether the account behind this shared mailbox can sign in (Get-User unavailable or no result).' 'Check Active users in the Microsoft 365 admin center.'))
                }
                elseif (-not $disabled) {
                    $f.Add((Get-EAFindingRecord 'SharedMailboxSignInEnabled' 'Medium' $upn 'The account behind this shared mailbox can sign in. Learn: always block sign-in for it and keep it blocked.' `
                            'Microsoft 365 admin center > Users > Active users > the shared mailbox > Block sign-in.'))
                }
            }
            $limit = [long]$Config.sharedMailbox.limitGb * 1GB
            $total = Get-EAProp $m 'totalBytes'
            if ($null -ne $total) {
                $pct = [Math]::Round(100.0 * $total / $limit, 1)
                if ($total -ge $limit) {
                    $f.Add((Get-EAFindingRecord 'SharedMailboxOverLimit' 'High' $upn "Holds $([Math]::Round($total / 1GB, 1)) GB, over the $($Config.sharedMailbox.limitGb) GB limit of an unlicensed shared mailbox." `
                            'Learn: a shared mailbox over 50 GB needs an Exchange Online Plan 2 licence (or less data). Over the limit it stops sending, then receiving.'))
                }
                elseif ($pct -ge $Config.sharedMailbox.warnPercent) {
                    $f.Add((Get-EAFindingRecord 'SharedMailboxNearLimit' 'Medium' $upn "Holds $([Math]::Round($total / 1GB, 1)) GB, $pct% of the $($Config.sharedMailbox.limitGb) GB limit of an unlicensed shared mailbox." `
                            'Plan the Exchange Online Plan 2 licence, or clean up, before it stops sending.'))
                }
            }
            $fa = @(ConvertTo-EAStringList (Get-EAProp $m 'fullAccess'))
            $sa = @(ConvertTo-EAStringList (Get-EAProp $m 'sendAs'))
            if ($fa.Count -eq 0 -and $sa.Count -eq 0) {
                $f.Add((Get-EAFindingRecord 'SharedMailboxNoDelegates' 'Low' $upn 'Nobody has Full Access or Send As on this shared mailbox.' 'Either it is unused (remove it) or access is granted another way.'))
            }
            if ($fa.Count -gt $Config.fullAccess.maxDelegatesPerMailbox) {
                $f.Add((Get-EAFindingRecord 'FullAccessSprawl' 'Low' $upn "$($fa.Count) people have Full Access (limit in config: $($Config.fullAccess.maxDelegatesPerMailbox))." 'Use a security group as the delegate, and review who still needs it.'))
            }
        }
        else {
            # 4. Ordinary mailbox close to its quota
            $total = Get-EAProp $m 'totalBytes'; $quota = Get-EAProp $m 'quotaBytes'
            if ($null -ne $total -and $null -ne $quota -and $quota -gt 0) {
                $pct = [Math]::Round(100.0 * $total / $quota, 1)
                if ($pct -ge $Config.quota.warnPercent) {
                    $f.Add((Get-EAFindingRecord 'MailboxNearQuota' 'Low' $upn "Uses $pct% of its send/receive quota ($([Math]::Round($total / 1GB, 1)) of $([Math]::Round($quota / 1GB, 1)) GB)." 'Archive, clean up, or enable the archive mailbox.'))
                }
            }
        }
    }

    # 5. Transport rules (mail flow rules)
    foreach ($t in @(Get-EAProp $Inventory 'transportRules')) {
        $name = "$(Get-EAProp $t 'name')"
        $targets = @(@(ConvertTo-EAStringList (Get-EAProp $t 'redirectMessageTo')) + @(ConvertTo-EAStringList (Get-EAProp $t 'blindCopyTo')) + @(ConvertTo-EAStringList (Get-EAProp $t 'copyTo')))
        $ext = @(foreach ($a in @(ConvertTo-EAAddress $targets)) { if (Test-EAExternalAddress -Address $a -Inventory $Inventory -Config $Config) { $a } })
        if ($ext.Count -gt 0) {
            $state = "$(Get-EAProp $t 'state')"; $mode = "$(Get-EAProp $t 'mode')"
            $live = ($state -eq 'Enabled' -and $mode -eq 'Enforce')
            $f.Add((Get-EAFindingRecord 'TransportRuleExternalCopy' $(if ($live) { 'High' } else { 'Medium' }) $name `
                    "Mail flow rule sends or copies mail to $($ext -join ', ') (state $state, mode $mode)." `
                    $(if ($live) { 'This rule is live: every matching message leaves the organization.' } else { 'Not enforcing now (disabled or test mode), but one click turns it on.' })))
        }
        if ($Config.transportRules.requireComment -and -not (Get-EAProp $t 'comments')) {
            $f.Add((Get-EAFindingRecord 'TransportRuleNoComment' 'Low' $name 'The rule has no comment, so nobody can tell later why it exists.' 'Set-TransportRule -Comments "owner, date, reason".'))
        }
    }

    # 6. Outbound spam policy: automatic external forwarding
    foreach ($p in @(Get-EAProp $Inventory 'outboundSpamPolicies')) {
        $mode = "$(Get-EAProp $p 'autoForwardingMode')"
        if (@($Config.outboundSpam.flagModes) -contains $mode) {
            $sev = $(if ($mode -eq 'On') { 'High' } else { 'Medium' })
            $detail = $(if ($mode -eq 'On') { 'Automatic external forwarding is allowed (On).' } else { 'Automatic external forwarding is system-controlled (Automatic): it is Off in new tenants since 2021 but can still behave as On in older ones.' })
            $f.Add((Get-EAFindingRecord 'OutboundAutoForwarding' $sev "$(Get-EAProp $p 'name')" $detail 'Learn recommends Off (set it explicitly): Set-HostedOutboundSpamFilterPolicy -AutoForwardingMode Off.'))
        }
    }

    foreach ($e in @(Get-EAProp $Inventory 'errors')) {
        if ($e) { $f.Add((Get-EAFindingRecord 'CollectionError' 'Info' 'collection' "$e" 'The audit is incomplete for this item: fix the permission or retry.')) }
    }

    @($f.ToArray() | Sort-Object @{ Expression = { $script:SeverityOrder[$_.Severity] } }, Rule, Target)
}

function Get-EASummary {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings)
    $count = { param($s) @($Findings | Where-Object { $_.Severity -eq $s }).Count }
    [pscustomobject]@{
        Total   = @($Findings).Count
        High    = & $count 'High'
        Medium  = & $count 'Medium'
        Low     = & $count 'Low'
        Info    = & $count 'Info'
        Fixable = @($Findings | Where-Object { $_.Fixable }).Count
    }
}

#endregion

#region forwarding fix (the only write on existing mailboxes)

function Get-EAFixPlan {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings, [Parameter(Mandatory)]$Config, [Parameter(Mandatory)]$Inventory)
    $allowed = @($Config.fix.allowedRules)
    if ($allowed.Count -eq 0) { return @() }
    $plan = foreach ($x in $Findings) {
        if (-not $x.Fixable -or $allowed -notcontains $x.Rule) { continue }
        $m = @(Get-EAProp $Inventory 'mailboxes') | Where-Object { "$(Get-EAProp $_ 'upn')" -eq $x.Target } | Select-Object -First 1
        if (-not $m) { continue }
        [pscustomobject]@{
            Rule                       = $x.Rule
            Mailbox                    = $x.Target
            ForwardingSmtpAddress      = "$(Get-EAProp $m 'forwardingSmtpAddress')"
            DeliverToMailboxAndForward = [bool](Get-EAProp $m 'deliverToMailboxAndForward')
        }
    }
    @($plan)
}

function Invoke-EAForwardingFix {
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Plan, [Parameter(Mandatory)][string]$RollbackFile)
    if (Test-Path -LiteralPath $RollbackFile) { throw "Rollback file '$RollbackFile' already exists. Restore or move it first: it holds an earlier run." }
    $rollback = New-Object System.Collections.Generic.List[object]
    $results = New-Object System.Collections.Generic.List[object]
    foreach ($p in $Plan) {
        $result = { param($s, $msg) [pscustomobject]@{ Mailbox = $p.Mailbox; Status = $s; Message = $msg } }
        # Re-read: only touch it if it still forwards to what the audit saw.
        try { $now = Get-EXOMailbox -Identity $p.Mailbox -Properties ForwardingSmtpAddress, ForwardingAddress, DeliverToMailboxAndForward -ErrorAction Stop }
        catch { $results.Add((& $result 'Failed' "Could not re-read the mailbox: $($_.Exception.Message)")); break }
        $nowAddr = @(ConvertTo-EAAddress $now.ForwardingSmtpAddress)
        $planAddr = @(ConvertTo-EAAddress $p.ForwardingSmtpAddress)
        if ($nowAddr.Count -ne $planAddr.Count -or ($planAddr.Count -gt 0 -and $nowAddr[0] -ne $planAddr[0])) {
            $results.Add((& $result 'Skipped' 'Forwarding changed since the audit; run the audit again.')); continue
        }
        if (-not $PSCmdlet.ShouldProcess($p.Mailbox, "Remove forwarding to $($planAddr -join ', ')")) {
            $results.Add((& $result 'Skipped' 'WhatIf or declined.')); continue
        }
        try {
            Set-Mailbox -Identity $p.Mailbox -ForwardingSmtpAddress $null -ErrorAction Stop
            $rollback.Add([pscustomobject]@{
                    mailbox                    = $p.Mailbox
                    forwardingSmtpAddress      = $p.ForwardingSmtpAddress
                    deliverToMailboxAndForward = $p.DeliverToMailboxAndForward
                    removedAt                  = (Get-Date).ToUniversalTime().ToString('o')
                })
            # Written after every success: a failure later in the list still leaves a way back for what already changed.
            ConvertTo-Json -InputObject @($rollback.ToArray()) -Depth 5 | Set-Content -LiteralPath $RollbackFile -Encoding utf8
            $results.Add((& $result 'Removed' "Stopped forwarding to $($planAddr -join ', ')."))
        }
        catch { $results.Add((& $result 'Failed' $_.Exception.Message)); break }
    }
    $results.ToArray()
}

function Restore-EAForwarding {
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string]$RollbackFile)
    if (-not (Test-Path -LiteralPath $RollbackFile)) { throw "Rollback file not found: $RollbackFile" }
    $entries = @(Get-Content -LiteralPath $RollbackFile -Raw | ConvertFrom-Json)
    foreach ($e in $entries) {
        $now = Get-EXOMailbox -Identity $e.mailbox -Properties ForwardingSmtpAddress -ErrorAction Stop
        if ($now.ForwardingSmtpAddress) {
            [pscustomobject]@{ Mailbox = $e.mailbox; Status = 'Skipped'; Message = 'It forwards somewhere now; not overwritten.' }; continue
        }
        if ($PSCmdlet.ShouldProcess($e.mailbox, "Put forwarding to $($e.forwardingSmtpAddress) back")) {
            Set-Mailbox -Identity $e.mailbox -ForwardingSmtpAddress $e.forwardingSmtpAddress -DeliverToMailboxAndForward ([bool]$e.deliverToMailboxAndForward) -ErrorAction Stop
            [pscustomobject]@{ Mailbox = $e.mailbox; Status = 'Restored'; Message = "Forwarding to $($e.forwardingSmtpAddress) is back." }
        }
        else { [pscustomobject]@{ Mailbox = $e.mailbox; Status = 'Skipped'; Message = 'WhatIf or declined.' } }
    }
}

#endregion

#region declarative shared mailboxes

function Get-EASharedMailboxPlan {
    # Desired state -> list of actions. Pure: compares the desired file with an inventory. Running it again after the actions gives an empty plan.
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Desired, [Parameter(Mandatory)]$Inventory, [switch]$RemoveExtra)
    $actions = New-Object System.Collections.Generic.List[object]
    $mailboxes = @(Get-EAProp $Inventory 'mailboxes')
    $seen = @{}
    $newAction = { param($a, $mb, $user, $note) [pscustomobject]@{ Action = $a; Mailbox = $mb; User = $user; Note = $note } }
    foreach ($d in @(Get-EAProp $Desired 'mailboxes')) {
        $alias = "$(Get-EAProp $d 'alias')".Trim()
        if (-not $alias) { throw "A mailbox in the desired file has no alias." }
        if ($seen.ContainsKey($alias.ToLowerInvariant())) { throw "Alias '$alias' appears twice in the desired file." }
        $seen[$alias.ToLowerInvariant()] = $true
        $display = "$(Get-EAProp $d 'displayName')"; if (-not $display) { $display = $alias }
        $primary = "$(Get-EAProp $d 'primarySmtpAddress')"
        $wantFull = @(ConvertTo-EAStringList (Get-EAProp $d 'fullAccess') | ForEach-Object { $_.ToLowerInvariant() } | Select-Object -Unique)
        $wantSend = @(ConvertTo-EAStringList (Get-EAProp $d 'sendAs') | ForEach-Object { $_.ToLowerInvariant() } | Select-Object -Unique)

        $existing = $mailboxes | Where-Object {
            "$(Get-EAProp $_ 'alias')".ToLowerInvariant() -eq $alias.ToLowerInvariant() -or
            ($primary -and "$(Get-EAProp $_ 'upn')".ToLowerInvariant() -eq $primary.ToLowerInvariant())
        } | Select-Object -First 1

        if (-not $existing) {
            $actions.Add((& $newAction 'CreateMailbox' $alias $null "$display$(if ($primary) { " <$primary>" })"))
            foreach ($u in $wantFull) { $actions.Add((& $newAction 'AddFullAccess' $alias $u $null)) }
            foreach ($u in $wantSend) { $actions.Add((& $newAction 'AddSendAs' $alias $u $null)) }
            continue
        }
        if ("$(Get-EAProp $existing 'type')" -ne 'SharedMailbox') {
            $actions.Add((& $newAction 'Conflict' $alias $null "A $(Get-EAProp $existing 'type') with this alias already exists; it is not converted or changed.")); continue
        }
        $haveFull = @(ConvertTo-EAStringList (Get-EAProp $existing 'fullAccess') | ForEach-Object { $_.ToLowerInvariant() })
        $haveSend = @(ConvertTo-EAStringList (Get-EAProp $existing 'sendAs') | ForEach-Object { $_.ToLowerInvariant() })
        foreach ($u in $wantFull) { if ($haveFull -notcontains $u) { $actions.Add((& $newAction 'AddFullAccess' $alias $u $null)) } }
        foreach ($u in $wantSend) { if ($haveSend -notcontains $u) { $actions.Add((& $newAction 'AddSendAs' $alias $u $null)) } }
        if ($RemoveExtra) {
            foreach ($u in $haveFull) { if ($wantFull -notcontains $u) { $actions.Add((& $newAction 'RemoveFullAccess' $alias $u $null)) } }
            foreach ($u in $haveSend) { if ($wantSend -notcontains $u) { $actions.Add((& $newAction 'RemoveSendAs' $alias $u $null)) } }
        }
    }
    $actions.ToArray()
}

function Invoke-EASharedMailboxPlan {
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Plan, $Desired, [int]$RetryCount = 3, [int]$RetrySeconds = 5)
    $created = @{}; $failedCreate = @{}
    foreach ($a in $Plan) {
        $res = { param($s, $msg) [pscustomobject]@{ Action = $a.Action; Mailbox = $a.Mailbox; User = $a.User; Status = $s; Message = $msg } }
        if ($a.Action -eq 'Conflict') { & $res 'Skipped' $a.Note; continue }
        if ($failedCreate.ContainsKey($a.Mailbox)) { & $res 'Skipped' 'The mailbox could not be created.'; continue }
        $what = switch ($a.Action) {
            'CreateMailbox' { "Create shared mailbox $($a.Note)" }
            'AddFullAccess' { "Grant Full Access to $($a.User)" }
            'AddSendAs' { "Grant Send As to $($a.User)" }
            'RemoveFullAccess' { "Remove Full Access from $($a.User)" }
            'RemoveSendAs' { "Remove Send As from $($a.User)" }
            default { throw "Unknown action '$($a.Action)'" }
        }
        if (-not $PSCmdlet.ShouldProcess($a.Mailbox, $what)) { & $res 'Skipped' 'WhatIf or declined.'; continue }
        # A mailbox created a moment ago may not be visible to the permission cmdlets yet: retry only for those.
        $tries = $(if ($created.ContainsKey($a.Mailbox)) { $RetryCount } else { 1 })
        try {
            switch ($a.Action) {
                'CreateMailbox' {
                    $d = @(Get-EAProp $Desired 'mailboxes') | Where-Object { "$(Get-EAProp $_ 'alias')".ToLowerInvariant() -eq $a.Mailbox.ToLowerInvariant() } | Select-Object -First 1
                    $display = "$(Get-EAProp $d 'displayName')"; if (-not $display) { $display = $a.Mailbox }
                    $p = @{ Shared = $true; Name = $display; DisplayName = $display; Alias = $a.Mailbox; ErrorAction = 'Stop' }
                    $primary = "$(Get-EAProp $d 'primarySmtpAddress')"; if ($primary) { $p.PrimarySmtpAddress = $primary }
                    New-Mailbox @p | Out-Null
                    $created[$a.Mailbox] = $true
                }
                'AddFullAccess' { Invoke-EARetry -Count $tries -DelaySeconds $RetrySeconds -Script { Add-MailboxPermission -Identity $a.Mailbox -User $a.User -AccessRights FullAccess -InheritanceType All -AutoMapping $true -ErrorAction Stop | Out-Null } }
                'AddSendAs' { Invoke-EARetry -Count $tries -DelaySeconds $RetrySeconds -Script { Add-RecipientPermission -Identity $a.Mailbox -Trustee $a.User -AccessRights SendAs -Confirm:$false -ErrorAction Stop | Out-Null } }
                'RemoveFullAccess' { Remove-MailboxPermission -Identity $a.Mailbox -User $a.User -AccessRights FullAccess -InheritanceType All -Confirm:$false -ErrorAction Stop }
                'RemoveSendAs' { Remove-RecipientPermission -Identity $a.Mailbox -Trustee $a.User -AccessRights SendAs -Confirm:$false -ErrorAction Stop }
            }
            & $res 'Done' $null
        }
        catch {
            if ($a.Action -eq 'CreateMailbox') { $failedCreate[$a.Mailbox] = $true }
            & $res 'Failed' $_.Exception.Message
        }
    }
}

#endregion

#region message trace

function Get-EAMessageTrace {
    [CmdletBinding()]
    param(
        [string]$SenderAddress, [string]$RecipientAddress, [string]$Subject,
        [ValidateSet('Delivered', 'Expanded', 'Failed', 'FilteredAsSpam', 'GettingStatus', 'Pending', 'Quarantined')][string[]]$Status,
        [int]$Hours = 0, [datetime]$Start, [datetime]$End, [int]$Top = 100,
        $Config, [datetime]$Now = (Get-Date).ToUniversalTime()
    )
    $maxDays = $(if ($Config) { $Config.trace.maxDays } else { 10 })
    $defaultHours = $(if ($Config) { $Config.trace.defaultHours } else { 48 })
    if ($Top -lt 1 -or $Top -gt 5000) { throw 'Top must be 1 to 5000 (the ResultSize range of Get-MessageTraceV2).' }
    $haveStart = $PSBoundParameters.ContainsKey('Start'); $haveEnd = $PSBoundParameters.ContainsKey('End')
    if (-not $haveEnd) { $End = $Now }
    if (-not $haveStart) { $Start = $End.AddHours( - $(if ($Hours -gt 0) { $Hours } else { $defaultHours })) }
    if ($End -le $Start) { throw 'End must be after Start.' }
    if (($End - $Start).TotalDays -gt $maxDays) { throw "The window is $([Math]::Round(($End - $Start).TotalDays, 1)) days. Get-MessageTraceV2 returns at most $maxDays days per query (Learn): run it in several windows." }
    if (($Now - $Start).TotalDays -gt 90) { throw 'Get-MessageTraceV2 only looks back 90 days (Learn). For older mail use a historical search in the Exchange admin center.' }

    $p = @{ StartDate = $Start; EndDate = $End; ResultSize = $Top }
    if ($SenderAddress) { $p.SenderAddress = $SenderAddress }
    if ($RecipientAddress) { $p.RecipientAddress = $RecipientAddress }
    if ($Subject) { $p.Subject = $Subject; $p.SubjectFilterType = 'StartsWith' }
    if ($Status) { $p.Status = $Status }
    $rows = @(Get-MessageTraceV2 @p)
    if ($rows.Count -ge $Top) { Write-Warning "Got $Top rows, the limit you asked for: the list may be cut off. Narrow the window or the filters (the cmdlet has no paging)." }
    $rows | Sort-Object Received | ForEach-Object {
        [pscustomobject]@{
            Received  = $_.Received
            Sender    = "$($_.SenderAddress)"
            Recipient = "$($_.RecipientAddress)"
            Subject   = "$($_.Subject)"
            Status    = "$($_.Status)"
            Size      = $_.Size
            TraceId   = "$($_.MessageTraceId)"
        }
    }
}

#endregion

#region report

function ConvertTo-EAMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Inventory, [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings, [object[]]$FixPlan = @())
    $s = Get-EASummary -Findings $Findings
    $mb = @(Get-EAProp $Inventory 'mailboxes')
    $shared = @($mb | Where-Object { (Get-EAProp $_ 'type') -eq 'SharedMailbox' }).Count
    $cell = { param($t) ("$t" -replace '\|', '\|' -replace '\r?\n', ' ') }
    $o = New-Object System.Collections.Generic.List[string]
    $o.Add('# Exchange Online audit'); $o.Add('')
    $at = Get-EAProp $Inventory 'collectedAt'
    if ($at -is [datetime]) { $at = $at.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss') + 'Z' }
    $o.Add("Collected: $at (UTC). $($mb.Count) mailboxes ($shared shared), $(@(Get-EAProp $Inventory 'transportRules').Count) mail flow rules, $(@(Get-EAProp $Inventory 'outboundSpamPolicies').Count) outbound spam policies, $(@(Get-EAProp $Inventory 'acceptedDomains').Count) accepted domains.")
    $o.Add(''); $o.Add("**$($s.Total) findings:** $($s.High) high, $($s.Medium) medium, $($s.Low) low, $($s.Info) info. $($s.Fixable) can be fixed by this tool (and only if the rule is in ``fix.allowedRules``).")
    $o.Add('')
    if ($s.Total -gt 0) {
        $o.Add('| Severity | Rule | Target | What was found |'); $o.Add('|---|---|---|---|')
        foreach ($x in $Findings) { $o.Add("| $($x.Severity) | $($x.Rule) | $(& $cell $x.Target) | $(& $cell $x.Detail) |") }
        $o.Add(''); $o.Add('### What to do about each rule'); $o.Add('')
        foreach ($g in ($Findings | Group-Object Rule)) { $o.Add("- **$($g.Name)**: $(& $cell ($g.Group | Select-Object -First 1).Hint)") }
    }
    else { $o.Add('Nothing to report with the current config.') }
    $o.Add('')
    if (@($FixPlan).Count -gt 0) {
        $o.Add("### Fix plan ($(@($FixPlan).Count) forwarding removals)"); $o.Add('')
        foreach ($p in $FixPlan) { $o.Add("- $($p.Mailbox): stop forwarding to $($p.ForwardingSmtpAddress)") }
    }
    else { $o.Add('### Fix plan'); $o.Add(''); $o.Add('Empty. Nothing is fixed unless a rule is listed in `fix.allowedRules`.') }
    $o.Add('')
    $o -join "`n"
}

#endregion

Export-ModuleMember -Function Get-EAConfig, Get-EAInventory, Get-EAFinding, Get-EASummary, ConvertTo-EAMarkdown, Get-EAFixPlan, Invoke-EAForwardingFix, Restore-EAForwarding, Get-EASharedMailboxPlan, Invoke-EASharedMailboxPlan, Get-EAMessageTrace
