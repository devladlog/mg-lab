#Requires -Version 7.2
<#
    DefenderForOffice: Microsoft Defender for Office 365 as code, driven by defender.json.

      * Presets   - ConvertTo-DOPresetRuleParameter / Set-DefenderPresetPolicy: who gets the Strict and Standard preset
                    security policies (EOP and Defender for Office 365 rules), then turn them on. The rules only exist
                    after a preset was turned on once in the Defender portal: the function says so instead of failing
                    halfway.
      * Coverage  - Test-DORecipientInScope / Get-DOProtectionCoverage: which preset each mailbox really gets, using the
                    documented logic (values of one condition: OR; different condition types: AND; any exception wins).
      * Audit     - Get-DefenderInventory + Get-DefenderFinding: missing or disabled preset rules, combined conditions,
                    mailboxes left on defaults, priority accounts not on Strict, Built-in protection exceptions, and
                    every setting Microsoft's configuration analyzer reports below the Standard baseline.
      * Hunting   - New-DOHuntingQuery / Invoke-DOHuntingQuery / ConvertFrom-DOHuntingResult: KQL on EmailEvents via
                    Microsoft Graph runHuntingQuery (ThreatHunting.Read.All).
      * Training  - Get-DOAttackSimulationReport / Get-DOSimulationSummary: results of an Attack simulation training
                    campaign via Microsoft Graph (AttackSimulation.Read.All).

    Exchange Online PowerShell (Connect-ExchangeOnline) for the policies, Microsoft Graph (Connect-MgGraph) for hunting
    and simulations. Everything else is pure and unit tested.
#>

Set-StrictMode -Version Latest

$script:PresetRuleName = @{ Standard = 'Standard Preset Security Policy'; Strict = 'Strict Preset Security Policy' }
$script:BuiltInRuleName = 'ATP Built-In Protection Rule'
$script:ConditionKeys = @('SentTo', 'SentToMemberOf', 'RecipientDomainIs')
$script:ExceptionKeys = @('ExceptIfSentTo', 'ExceptIfSentToMemberOf', 'ExceptIfRecipientDomainIs')
$script:Rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }

#region Helpers ---------------------------------------------------------------------------------------------------

function Get-DOProp {
    param([object]$Object, [string]$Name, [object]$Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { $Default } else { $p.Value }
}

function Get-DOList {
    <# Non-empty string values of a list-valued property (handles $null, scalars and arrays). #>
    param([object]$Object, [string]$Name)
    @(Get-DOProp $Object $Name @() | Where-Object { $null -ne $_ -and "$_" -ne '' } | ForEach-Object { "$_" })
}

function New-DOFinding {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Pure: builds an object, changes nothing.')]
    param([string]$Severity, [string]$Target, [string]$Rule, [string]$Detail)
    [pscustomobject]@{ Severity = $Severity; Target = $Target; Rule = $Rule; Detail = $Detail }
}

#endregion

#region Config and parameters (pure) ------------------------------------------------------------------------------

function Get-DefenderConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $c = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($name in 'standard', 'strict') {
        $p = Get-DOProp $c.presets $name
        if (-not $p) { throw "presets.$($name): missing." }
        $types = @(foreach ($k in 'sentTo', 'sentToMemberOf', 'recipientDomainIs') { if (@(Get-DOList $p $k).Count) { $k } })
        if (-not $types.Count) {
            throw "presets.$($name): no recipient condition. Empty conditions mean everyone, so say who explicitly (recipientDomainIs for all users)."
        }
        # Different types of conditions use AND logic: users AND groups means 'only users who are also in the groups'.
        if ($types.Count -gt 1 -and -not [bool](Get-DOProp $c 'allowCombinedConditions' $false)) {
            throw "presets.$($name): uses $($types -join ' + '). Different condition types are ANDed (a recipient must match all of them). Use one type, or set allowCombinedConditions to true."
        }
        foreach ($a in @(Get-DOList $p 'sentTo') + @(Get-DOList $p 'sentToMemberOf')) {
            if ($a -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') { throw "presets.$($name): '$a' isn't an email address (use addresses so coverage can be checked)." }
        }
    }
    $max = [int](Get-DOProp $c.attackSimulation 'maxCompromisedPercent' 20)
    if ($max -lt 0 -or $max -gt 100) { throw 'attackSimulation.maxCompromisedPercent must be between 0 and 100.' }
    $days = [int](Get-DOProp $c.hunting 'lookbackDays' 7)
    if ($days -lt 1 -or $days -gt 30) { throw 'hunting.lookbackDays must be between 1 and 30 (runHuntingQuery looks back 30 days by default).' }
    $c
}

function ConvertTo-DOPresetRuleParameter {
    <#
    .SYNOPSIS  Parameters for Set-EOPProtectionPolicyRule / Set-ATPProtectionPolicyRule. Every recipient parameter is
               passed, $null when unused, so the tenant ends up exactly like the file (no leftover conditions).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][ValidateSet('Standard', 'Strict')][string]$Preset, [Parameter(Mandatory)][object]$Config)
    $p = Get-DOProp $Config.presets $Preset.ToLowerInvariant()
    $out = [ordered]@{ Identity = $script:PresetRuleName[$Preset] }
    foreach ($k in $script:ConditionKeys + $script:ExceptionKeys) {
        $jsonKey = $k.Substring(0, 1).ToLowerInvariant() + $k.Substring(1)
        $v = @(Get-DOList $p $jsonKey)
        $out[$k] = if ($v.Count) { $v } else { $null }
    }
    $out
}

#endregion

#region Coverage (pure) -------------------------------------------------------------------------------------------

function Get-DOMemberSet {
    param([object]$Inventory, [string[]]$Groups)
    $set = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($g in $Groups) {
        $grp = @($Inventory.groups | Where-Object { $_.identity -eq $g }) | Select-Object -First 1
        foreach ($m in @(Get-DOList $grp 'members')) { [void]$set.Add($m) }
    }
    , $set
}

function Test-DORecipientInScope {
    <#
    .SYNOPSIS  Does a preset rule apply to this mailbox? Values of the same condition: OR. Different condition types:
               AND. Exceptions: any match excludes. No condition at all: everyone. A disabled rule applies to nobody.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param([Parameter(Mandatory)][object]$Rule, [Parameter(Mandatory)][object]$Mailbox, [Parameter(Mandatory)][object]$Inventory)
    if ("$(Get-DOProp $Rule 'state' 'Enabled')" -ne 'Enabled') { return $false }
    $ids = @($Mailbox.primarySmtpAddress, (Get-DOProp $Mailbox 'alias'), (Get-DOProp $Mailbox 'displayName'), (Get-DOProp $Mailbox 'name')) | Where-Object { $_ }
    $domain = ($Mailbox.primarySmtpAddress -split '@')[-1]
    $inv = $Inventory
    $test = {
        param($Kind, [string[]]$Values)
        switch ($Kind) {
            'SentTo' { return [bool]@($Values | Where-Object { $_ -in $ids }).Count }
            'SentToMemberOf' { return (Get-DOMemberSet -Inventory $inv -Groups $Values).Contains($Mailbox.primarySmtpAddress) }
            'RecipientDomainIs' { return [bool]@($Values | Where-Object { $_ -eq $domain }).Count }
        }
    }
    foreach ($k in $script:ExceptionKeys) {
        $v = @(Get-DOList $Rule ($k.Substring(0, 1).ToLowerInvariant() + $k.Substring(1)))
        if ($v.Count -and (& $test $k.Substring(8) $v)) { return $false }
    }
    foreach ($k in $script:ConditionKeys) {
        $v = @(Get-DOList $Rule ($k.Substring(0, 1).ToLowerInvariant() + $k.Substring(1)))
        if (-not $v.Count) { continue }
        if (-not (& $test $k $v)) { return $false }
    }
    $true   # all used condition types matched (or none was used: everyone)
}

function Get-DOProtectionCoverage {
    <# One row per mailbox: which preset applies for EOP features and for Defender for Office 365 features. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Inventory)
    $rule = { param($Kind, $Preset) @($Inventory.rules | Where-Object { $_.kind -eq $Kind -and $_.preset -eq $Preset }) | Select-Object -First 1 }
    $builtIn = & $rule 'BuiltIn' 'BuiltIn'
    foreach ($m in @($Inventory.mailboxes)) {
        $row = [ordered]@{ Mailbox = $m.primarySmtpAddress }
        foreach ($kind in 'EOP', 'ATP') {
            $level = $null
            foreach ($preset in 'Strict', 'Standard') {   # order of precedence: Strict, then Standard
                $r = & $rule $kind $preset
                if ($r -and (Test-DORecipientInScope -Rule $r -Mailbox $m -Inventory $Inventory)) { $level = $preset; break }
            }
            if (-not $level) {
                if ($kind -eq 'EOP') { $level = 'Default/custom' }
                elseif ($builtIn -and (Test-DORecipientInScope -Rule $builtIn -Mailbox $m -Inventory $Inventory)) { $level = 'Built-in protection' }
                else { $level = 'None' }
            }
            $row[$(if ($kind -eq 'EOP') { 'Eop' } else { 'Defender' })] = $level
        }
        [pscustomobject]$row
    }
}

#endregion

#region Findings and report (pure) --------------------------------------------------------------------------------

function Get-DefenderFinding {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Inventory, [Parameter(Mandatory)][object]$Config)
    $inv = $Inventory
    foreach ($preset in 'Strict', 'Standard') {
        $wanted = ConvertTo-DOPresetRuleParameter -Preset $preset -Config $Config
        foreach ($kind in 'EOP', 'ATP') {
            $target = "$kind rule: $($script:PresetRuleName[$preset])"
            $r = @($inv.rules | Where-Object { $_.kind -eq $kind -and $_.preset -eq $preset }) | Select-Object -First 1
            if (-not $r) {
                New-DOFinding 'High' $target 'PresetRuleMissing' "The rule doesn't exist. Turn on the $preset preset once in the Microsoft Defender portal; PowerShell can't create it."
                continue
            }
            if ("$(Get-DOProp $r 'state' '')" -ne 'Enabled') { New-DOFinding 'High' $target 'PresetDisabled' "State is '$(Get-DOProp $r 'state' '')': nobody gets these protections." }
            $types = @(foreach ($k in $script:ConditionKeys) { if (@(Get-DOList $r ($k.Substring(0, 1).ToLowerInvariant() + $k.Substring(1))).Count) { $k } })
            if ($types.Count -gt 1) {
                $missed = @(foreach ($m in @($inv.mailboxes)) {
                        $anyType = $false
                        foreach ($k in $types) {
                            $single = [pscustomobject]@{ state = 'Enabled' }
                            $single | Add-Member -NotePropertyName ($k.Substring(0, 1).ToLowerInvariant() + $k.Substring(1)) -NotePropertyValue @(Get-DOList $r ($k.Substring(0, 1).ToLowerInvariant() + $k.Substring(1)))
                            if (Test-DORecipientInScope -Rule $single -Mailbox $m -Inventory $inv) { $anyType = $true }
                        }
                        if ($anyType -and -not (Test-DORecipientInScope -Rule $r -Mailbox $m -Inventory $inv)) { $m.primarySmtpAddress }
                    })
                $who = if ($missed.Count) { " Matches one condition but not all: $($missed -join ', ')." } else { '' }
                New-DOFinding 'Medium' $target 'CombinedConditions' "Uses $($types -join ' + '): different condition types are ANDed.$who"
            }
            foreach ($k in $script:ConditionKeys + $script:ExceptionKeys) {
                $jsonKey = $k.Substring(0, 1).ToLowerInvariant() + $k.Substring(1)
                $have = @(Get-DOList $r $jsonKey | Sort-Object); $want = @($wanted[$k] | Where-Object { $_ } | Sort-Object)
                if (($have -join '|') -ne ($want -join '|')) {
                    New-DOFinding 'Low' $target 'Drift' "$k is '$($have -join ', ')' in the tenant, '$($want -join ', ')' in defender.json. -ApplyPresets fixes it."
                }
            }
        }
    }

    $coverage = @(Get-DOProtectionCoverage -Inventory $inv)
    $priority = Get-DOMemberSet -Inventory $inv -Groups @(Get-DOList $Config.presets.strict 'sentToMemberOf')
    foreach ($a in @(Get-DOList $Config.presets.strict 'sentTo')) { [void]$priority.Add($a) }
    foreach ($row in $coverage) {
        if ($priority.Contains($row.Mailbox) -and ($row.Eop -ne 'Strict' -or $row.Defender -ne 'Strict')) {
            New-DOFinding 'High' "Mailbox: $($row.Mailbox)" 'PriorityNotStrict' "Priority account, but gets EOP: $($row.Eop), Defender: $($row.Defender)."
        }
        elseif ($row.Eop -eq 'Default/custom' -or $row.Defender -in 'Built-in protection', 'None') {
            New-DOFinding 'Medium' "Mailbox: $($row.Mailbox)" 'NotOnPreset' "Not covered by Standard or Strict (EOP: $($row.Eop), Defender: $($row.Defender))."
        }
        if ($row.Defender -eq 'None') {
            New-DOFinding 'High' "Mailbox: $($row.Mailbox)" 'NoSafeLinksOrAttachments' 'Excluded from Built-in protection and not in a preset: no Safe Links or Safe Attachments from presets.'
        }
    }

    $builtIn = @($inv.rules | Where-Object kind -EQ 'BuiltIn') | Select-Object -First 1
    if ($builtIn) {
        $allowed = @(Get-DOList $Config.audit 'builtInProtectionExceptionsAllowed')
        $exceptions = @(@(foreach ($k in $script:ExceptionKeys) { Get-DOList $builtIn ($k.Substring(0, 1).ToLowerInvariant() + $k.Substring(1)) }) | Where-Object { $_ -notin $allowed })
        if ($exceptions.Count) {
            New-DOFinding 'Medium' "Rule: $($script:BuiltInRuleName)" 'BuiltInProtectionExcluded' "Exceptions: $($exceptions -join ', '). Microsoft: exceptions are typically only for users without Defender for Office 365 licences."
        }
    }

    foreach ($x in @($inv.configAnalyzer)) {
        New-DOFinding 'Medium' "$($x.policyGroup): $($x.policy)" 'BelowStandard' "$($x.settingName) is '$($x.currentConfiguration)', Standard recommends '$($x.recommendation)'."
    }
}

function ConvertTo-DefenderMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Inventory, [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings)
    $md = [System.Collections.Generic.List[string]]::new()
    $md.Add('# Defender for Office 365 audit'); $md.Add('')
    $when = $Inventory.collectedAt
    if ($when -is [datetime]) { $when = $when.ToUniversalTime().ToString('yyyy-MM-dd HH:mm') + ' UTC' }
    $md.Add("Collected $when. $(@($Inventory.mailboxes).Count) mailboxes, $(@($Inventory.rules).Count) preset rules, $(@($Inventory.configAnalyzer).Count) settings below the Standard baseline, $($Findings.Count) findings."); $md.Add('')
    $md.Add('## Coverage'); $md.Add(''); $md.Add('| Mailbox | EOP features | Defender for Office 365 |'); $md.Add('|---|---|---|')
    foreach ($c in @(Get-DOProtectionCoverage -Inventory $Inventory)) { $md.Add("| $($c.Mailbox) | $($c.Eop) | $($c.Defender) |") }
    $md.Add(''); $md.Add('## Findings'); $md.Add(''); $md.Add('| Severity | Target | Rule | Detail |'); $md.Add('|---|---|---|---|')
    foreach ($f in @($Findings | Sort-Object { $script:Rank[$_.Severity] }, Target, Rule)) { $md.Add("| $($f.Severity) | $($f.Target) | $($f.Rule) | $($f.Detail) |") }
    $md
}

#endregion

#region Hunting and attack simulation (pure parts) ----------------------------------------------------------------

function New-DOHuntingQuery {
    <# KQL on the EmailEvents table (columns from the Defender XDR advanced hunting schema). #>
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Pure: returns a string.')]
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)][ValidateSet('ThreatSummary', 'Recipient')][string]$Kind,
        [ValidateRange(1, 30)][int]$Days = 7,
        [string]$Recipient
    )
    switch ($Kind) {
        'ThreatSummary' {
            @"
EmailEvents
| where Timestamp > ago($($Days)d)
| where isnotempty(ThreatTypes)
| summarize Messages = count(), Recipients = dcount(RecipientEmailAddress) by ThreatTypes, DeliveryAction, DeliveryLocation
| order by Messages desc
"@
        }
        'Recipient' {
            # The address goes into a KQL string literal: allow only a plain address (no quotes, backslashes, spaces).
            if ($Recipient -notmatch '^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$') { throw "Recipient '$Recipient' isn't a plain email address." }
            @"
EmailEvents
| where Timestamp > ago($($Days)d)
| where RecipientEmailAddress =~ "$Recipient"
| project Timestamp, SenderFromAddress, Subject, EmailDirection, ThreatTypes, DetectionMethods, DeliveryAction, DeliveryLocation
| order by Timestamp desc
| take 20
"@
        }
    }
}

function ConvertFrom-DOHuntingResult {
    <# huntingQueryResults (schema + results) -> objects with properties in schema order. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Response)
    $cols = @(Get-DOProp $Response 'schema' @() | ForEach-Object { $_.name })
    foreach ($row in @(Get-DOProp $Response 'results' @())) {
        $o = [ordered]@{}
        foreach ($c in $cols) {
            # Learn's second example returns lowercase keys; match the schema name case-insensitively.
            $v = Get-DOProp $row $c
            if ($null -eq $v -and $row -isnot [System.Collections.IDictionary]) {
                $p = @($row.PSObject.Properties | Where-Object { $_.Name -ieq $c }) | Select-Object -First 1
                if ($p) { $v = $p.Value }
            }
            $o[$c] = $v
        }
        [pscustomobject]$o
    }
}

function Get-DOSimulationSummary {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Report, [Parameter(Mandatory)][object]$Config)
    $users = @($Report.users)
    $rows = foreach ($u in $users) {
        $su = Get-DOProp $u 'simulationUser'
        [pscustomobject]@{
            User        = "$(Get-DOProp $su 'displayName' '?') <$(Get-DOProp $su 'email' '?')>"
            Compromised = [bool](Get-DOProp $u 'isCompromised' $false)
            Reported    = [bool](Get-DOProp $u 'reportedPhishDateTime')
            Training    = "{0}/{1}" -f [int](Get-DOProp $u 'completedTrainingsCount' 0), [int](Get-DOProp $u 'assignedTrainingsCount' 0)
        }
    }
    $rows = @($rows)
    $n = $rows.Count
    $comp = @($rows | Where-Object Compromised).Count
    $rep = @($rows | Where-Object Reported).Count
    $pct = { param($x) if ($n) { [math]::Round(100.0 * $x / $n, 1) } else { 0 } }
    $findings = @()
    $max = [int](Get-DOProp $Config.attackSimulation 'maxCompromisedPercent' 20)
    if ($n -and (& $pct $comp) -gt $max) { $findings += New-DOFinding 'Medium' "Simulation: $($Report.simulation.displayName)" 'CompromiseRateHigh' "$comp of $n users compromised ($(& $pct $comp)%), above the $max% target." }
    foreach ($u in $users) {
        if ([bool](Get-DOProp $u 'isCompromised' $false) -and [int](Get-DOProp $u 'assignedTrainingsCount' 0) -eq 0) {
            $findings += New-DOFinding 'Low' "User: $(Get-DOProp (Get-DOProp $u 'simulationUser') 'email' '?')" 'CompromisedNoTraining' 'Compromised in the simulation, but no training assigned.'
        }
    }
    [pscustomobject]@{
        Simulation       = "$($Report.simulation.displayName)"
        Status           = "$(Get-DOProp $Report.simulation 'status' '')"
        Targeted         = $n
        Compromised      = $comp
        CompromisedPct   = & $pct $comp
        Reported         = $rep
        ReportedPct      = & $pct $rep
        Users            = $rows
        Findings         = $findings
    }
}

#endregion

#region Exchange Online PowerShell and Microsoft Graph ------------------------------------------------------------

function ConvertTo-DORuleRecord {
    param([object]$Rule, [string]$Kind, [string]$Preset)
    $o = [ordered]@{ kind = $Kind; preset = $Preset; state = "$(Get-DOProp $Rule 'State' '')" }
    foreach ($k in $script:ConditionKeys + $script:ExceptionKeys) { $o[$k.Substring(0, 1).ToLowerInvariant() + $k.Substring(1)] = @(Get-DOList $Rule $k) }
    [pscustomobject]$o
}

function Get-DefenderInventory {
    <# Read-only snapshot. Needs Connect-ExchangeOnline (Security Reader or Global Reader is enough for the Get- cmdlets). #>
    [CmdletBinding()]
    param()
    $rules = @()
    foreach ($preset in 'Standard', 'Strict') {
        $n = $script:PresetRuleName[$preset]
        $e = Get-EOPProtectionPolicyRule -Identity $n -ErrorAction SilentlyContinue
        if ($e) { $rules += ConvertTo-DORuleRecord $e 'EOP' $preset }
        $a = Get-ATPProtectionPolicyRule -Identity $n -ErrorAction SilentlyContinue
        if ($a) { $rules += ConvertTo-DORuleRecord $a 'ATP' $preset }
    }
    $b = Get-ATPBuiltInProtectionRule -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($b) { $rules += ConvertTo-DORuleRecord $b 'BuiltIn' 'BuiltIn' }

    $mailboxes = foreach ($m in @(Get-EXOMailbox -RecipientTypeDetails UserMailbox -ResultSize Unlimited -ErrorAction Stop)) {
        [pscustomobject]@{ primarySmtpAddress = "$($m.PrimarySmtpAddress)"; alias = Get-DOProp $m 'Alias'; displayName = Get-DOProp $m 'DisplayName'; name = Get-DOProp $m 'Name' }
    }
    $groupIds = @($rules | ForEach-Object { @($_.sentToMemberOf) + @($_.exceptIfSentToMemberOf) } | Where-Object { $_ } | Sort-Object -Unique)
    $groups = foreach ($g in $groupIds) {
        # Distribution groups and mail-enabled security groups. (Microsoft 365 Groups would need Get-UnifiedGroupLinks.)
        $members = @(Get-DistributionGroupMember -Identity $g -ResultSize Unlimited -ErrorAction SilentlyContinue | ForEach-Object { "$($_.PrimarySmtpAddress)" })
        [pscustomobject]@{ identity = $g; members = $members }
    }
    $analyzer = foreach ($x in @(Get-ConfigAnalyzerPolicyRecommendation -RecommendedPolicyType Standard -ErrorAction Stop)) {
        [pscustomobject]@{
            policyGroup = "$(Get-DOProp $x 'PolicyGroup' '')"; settingName = "$(Get-DOProp $x 'SettingName' '')"; policy = "$(Get-DOProp $x 'Policy' '')"
            currentConfiguration = "$(Get-DOProp $x 'CurrentConfiguration' '')"; recommendation = "$(Get-DOProp $x 'Recommendation' '')"
        }
    }
    [pscustomobject]@{
        collectedAt = [datetimeoffset]::UtcNow.ToString('o')
        rules = $rules; mailboxes = @($mailboxes); groups = @($groups); configAnalyzer = @($analyzer)
    }
}

function Set-DefenderPresetPolicy {
    <#
    .SYNOPSIS  Make the Strict and Standard preset rules (EOP and Defender for Office 365) match defender.json, then
               turn them on. Refuses up front if a rule doesn't exist yet (turn the preset on once in the portal).
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)][object]$Config)
    $cmd = @{
        EOP = @{ Get = 'Get-EOPProtectionPolicyRule'; Set = 'Set-EOPProtectionPolicyRule'; Enable = 'Enable-EOPProtectionPolicyRule' }
        ATP = @{ Get = 'Get-ATPProtectionPolicyRule'; Set = 'Set-ATPProtectionPolicyRule'; Enable = 'Enable-ATPProtectionPolicyRule' }
    }
    $work = foreach ($preset in 'Strict', 'Standard') {
        foreach ($kind in 'EOP', 'ATP') {
            $existing = & $cmd[$kind].Get -Identity $script:PresetRuleName[$preset] -ErrorAction SilentlyContinue
            [pscustomobject]@{ Preset = $preset; Kind = $kind; Rule = $existing }
        }
    }
    $missing = @($work | Where-Object { -not $_.Rule })
    if ($missing.Count) {
        throw "Missing preset rules: $(($missing | ForEach-Object { "$($_.Kind) $($_.Preset)" }) -join ', '). These rules are created the first time you turn on the preset in the Microsoft Defender portal (Email & collaboration > Policies & rules > Threat policies > Preset security policies). Turn it on once, then run this again."
    }
    foreach ($w in $work) {
        $params = ConvertTo-DOPresetRuleParameter -Preset $w.Preset -Config $Config
        $who = (@($script:ConditionKeys | Where-Object { $params[$_] } | ForEach-Object { "$_ $($params[$_] -join ',')" }) -join '; ')
        if (-not $PSCmdlet.ShouldProcess("$($w.Kind) $($params.Identity)", "Apply to: $who; enable")) {
            [pscustomobject]@{ Preset = $w.Preset; Kind = $w.Kind; Result = 'WhatIf'; AppliesTo = $who }; continue
        }
        & $cmd[$w.Kind].Set @params -ErrorAction Stop | Out-Null
        if ("$(Get-DOProp $w.Rule 'State' '')" -ne 'Enabled') { & $cmd[$w.Kind].Enable -Identity $params.Identity -ErrorAction Stop | Out-Null }
        [pscustomobject]@{ Preset = $w.Preset; Kind = $w.Kind; Result = 'Applied'; AppliesTo = $who }
    }
}

function Invoke-DOHuntingQuery {
    <# POST /security/runHuntingQuery (Microsoft Graph v1.0). Scope: ThreatHunting.Read.All. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Query, [ValidateRange(1, 30)][int]$Days = 7)
    $body = @{ Query = $Query; Timespan = "P$($Days)D" } | ConvertTo-Json
    $r = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/security/runHuntingQuery' -Body $body -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop
    ConvertFrom-DOHuntingResult -Response $r
}

function Invoke-DOGraphGet {
    param([Parameter(Mandatory)][string]$Uri, [int]$MaxPages = 50)
    $next = $Uri; $page = 0
    while ($next) {
        if (++$page -gt $MaxPages) { throw "Stopped after $MaxPages pages of $Uri" }
        $resp = Invoke-MgGraphRequest -Method GET -Uri $next -OutputType PSObject -ErrorAction Stop
        if ($null -eq $resp.PSObject.Properties['value']) { return $resp }
        foreach ($i in $resp.value) { $i }
        $next = Get-DOProp $resp '@odata.nextLink'
    }
}

function Get-DOAttackSimulationReport {
    <# A simulation (by id, or the most recently launched) and its users. Scope: AttackSimulation.Read.All. #>
    [CmdletBinding()]
    param([string]$SimulationId)
    if ($SimulationId) { $sim = Invoke-MgGraphRequest -Method GET -Uri "/v1.0/security/attackSimulation/simulations/$SimulationId" -OutputType PSObject -ErrorAction Stop }
    else {
        $sim = @(Invoke-DOGraphGet "/v1.0/security/attackSimulation/simulations?`$orderby=launchDateTime desc&`$top=1" -MaxPages 1) | Select-Object -First 1
        if (-not $sim) { throw 'No attack simulations found. Launch one in the Defender portal (Attack simulation training).' }
    }
    $users = @(Invoke-DOGraphGet "/v1.0/security/attackSimulation/simulations/$($sim.id)/report/simulationUsers")
    [pscustomobject]@{ simulation = $sim; users = $users }
}

#endregion
