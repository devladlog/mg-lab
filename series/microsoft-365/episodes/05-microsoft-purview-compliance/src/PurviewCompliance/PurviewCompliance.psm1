#Requires -Version 7.2
<#
    PurviewCompliance: Microsoft Purview as code, driven by compliance.json.

      * Config    - Get-PurviewConfig: loads compliance.json and refuses what Microsoft Learn says won't work or
                    can't be undone (label condition + Teams location, tip text > 256 chars, record labels and
                    Preservation Lock unless explicitly allowed, rules without a condition or an action).
      * Params    - ConvertTo-PV*Params: pure builders of the splatted parameters for New-Label, New-LabelPolicy,
                    New-DlpCompliancePolicy, New-DlpComplianceRule, New-ComplianceTag,
                    New-RetentionCompliancePolicy and New-RetentionComplianceRule.
      * Plan      - Get-PurviewPlan: compares the file with a tenant inventory -> Create / Exists / Drift / Wait.
      * Deploy    - Invoke-PurviewPlan: runs the Create steps in dependency order. -WhatIf is implemented HERE,
                    because the WhatIf switch doesn't work in Security & Compliance PowerShell.
      * Promote   - Set-PurviewDlpMode: moves a DLP policy from simulation to Enable after review.
      * Audit     - Get-PurviewInventory + Get-PurviewFinding: distribution errors, simulations past 15 days,
                    unpublished labels, label conditions in policies that include Teams, record labels, locks.
      * Test data - New-DlpTestContent: synthetic Luhn-valid card numbers with a keyword, because the Credit Card
                    Number type doesn't flag reserved test card numbers.

    Only Get-PurviewInventory, Invoke-PurviewPlan and Set-PurviewDlpMode call Security & Compliance PowerShell
    (Connect-IPPSSession first). Everything else is pure and unit tested.
#>

Set-StrictMode -Version Latest

$script:DlpModes = @('Enable', 'Disable', 'TestWithNotifications', 'TestWithoutNotifications')
$script:DlpLocations = [ordered]@{ Exchange = 'ExchangeLocation'; SharePoint = 'SharePointLocation'; OneDrive = 'OneDriveLocation'; Teams = 'TeamsLocation' }
$script:RetentionLocations = [ordered]@{ Exchange = 'ExchangeLocation'; SharePoint = 'SharePointLocation'; OneDrive = 'OneDriveLocation' }
$script:NotifyUserValues = @('Owner', 'SiteAdmin', 'LastModifier')
$script:OverrideValues = @('FalsePositive', 'WithAcknowledgement', 'WithoutJustification', 'WithJustification')
$script:Severities = @('None', 'Low', 'Medium', 'High')
$script:RetentionActions = @('Delete', 'Keep', 'KeepAndDelete')
$script:RetentionTypes = @('CreationAgeInDays', 'EventAgeInDays', 'ModificationAgeInDays', 'TaggedAgeInDays')
$script:PolicyTipMax = 256      # NotifyPolicyTipCustomText: maximum length is 256 characters
$script:NameMax = 64            # New-Label / New-LabelPolicy: Name maximum length is 64 characters

#region Helpers ---------------------------------------------------------------------------------------------------

function Get-PVProp {
    param([object]$Object, [string]$Name, [object]$Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { $Default } else { $p.Value }
}

function ConvertTo-PVDate {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value -or "$Value" -eq '') { return $null }
    if ($Value -is [datetimeoffset]) { return $Value.ToUniversalTime() }
    if ($Value -is [datetime]) { return ([datetimeoffset][datetime]::SpecifyKind($Value, 'Utc')) }
    $styles = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
    [datetimeoffset]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture, $styles)
}

function New-PVFinding {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Pure: builds an object, changes nothing.')]
    param([string]$Severity, [string]$Target, [string]$Rule, [string]$Detail)
    [pscustomobject]@{ Severity = $Severity; Target = $Target; Rule = $Rule; Detail = $Detail }
}

#endregion

#region Config ----------------------------------------------------------------------------------------------------

function Get-PurviewConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $c = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $labelNames = @($c.sensitivityLabels.name)
    foreach ($l in @($c.sensitivityLabels)) {
        if ("$($l.name)".Length -gt $script:NameMax) { throw "sensitivityLabels: name '$($l.name)' is longer than $($script:NameMax) characters." }
    }
    if ("$($c.labelPolicy.name)".Length -gt $script:NameMax) { throw "labelPolicy: name is longer than $($script:NameMax) characters." }
    foreach ($n in @($c.labelPolicy.labels)) { if ($n -notin $labelNames) { throw "labelPolicy: label '$n' is not defined in sensitivityLabels." } }
    if (-not @($c.labelPolicy.publishTo).Count) { throw 'labelPolicy: publishTo needs at least one mailbox (start with a pilot group).' }

    foreach ($p in @($c.dlpPolicies)) {
        if ($p.mode -notin $script:DlpModes) { throw "dlpPolicies '$($p.name)': mode must be one of $($script:DlpModes -join ', ')." }
        foreach ($loc in @($p.locations)) { if ($loc -notin $script:DlpLocations.Keys) { throw "dlpPolicies '$($p.name)': unknown location '$loc'." } }
        foreach ($r in @($p.rules)) {
            $sits = @(Get-PVProp $r 'sensitiveTypes' @()); $labels = @(Get-PVProp $r 'sensitivityLabels' @())
            if (-not ($sits.Count -or $labels.Count)) { throw "rule '$($r.name)': needs a condition (sensitiveTypes or sensitivityLabels)." }
            if ($sits.Count -and $labels.Count) { throw "rule '$($r.name)': use one rule per condition kind (sensitiveTypes or sensitivityLabels)." }
            # DLP policy reference: Teams chat and channel messages can't define content by sensitivity label, and in a
            # multi-location policy a 'no' wins - so a label condition in a policy that includes Teams can't work.
            if ($labels.Count -and 'Teams' -in @($p.locations)) {
                throw "rule '$($r.name)': a sensitivity label condition isn't supported when the policy includes Teams. Put label rules in a policy without Teams."
            }
            foreach ($n in $labels) { if ($n -notin $labelNames) { throw "rule '$($r.name)': label '$n' is not defined in sensitivityLabels." } }
            $hasAction = [bool](Get-PVProp $r 'blockAccess' $false) -or @(Get-PVProp $r 'notifyUser' @()).Count -or @(Get-PVProp $r 'incidentReportTo' @()).Count
            if (-not $hasAction) { throw "rule '$($r.name)': needs an action (blockAccess, notifyUser or incidentReportTo)." }
            foreach ($u in @(Get-PVProp $r 'notifyUser' @())) {
                if ($u -notin $script:NotifyUserValues -and $u -notmatch '^[^@\s]+@[^@\s]+$') { throw "rule '$($r.name)': notifyUser '$u' must be Owner, SiteAdmin, LastModifier or an email address." }
            }
            $ov = Get-PVProp $r 'allowOverride'
            if ($ov -and $ov -notin $script:OverrideValues) { throw "rule '$($r.name)': allowOverride must be one of $($script:OverrideValues -join ', ')." }
            $tip = "$(Get-PVProp $r 'policyTip' '')"
            if ($tip.Length -gt $script:PolicyTipMax) { throw "rule '$($r.name)': policyTip is $($tip.Length) characters; the maximum is $($script:PolicyTipMax)." }
            if ($tip -match '<[^>]+>|%%') { throw "rule '$($r.name)': policyTip can't contain HTML tags or tokens." }
            $sev = Get-PVProp $r 'severity' 'Low'
            if ($sev -notin $script:Severities) { throw "rule '$($r.name)': severity must be one of $($script:Severities -join ', ')." }
        }
    }

    $ret = $c.retention
    foreach ($t in @($ret.labels)) {
        if ($t.action -notin $script:RetentionActions) { throw "retention label '$($t.name)': action must be one of $($script:RetentionActions -join ', ')." }
        if ($t.retentionType -notin $script:RetentionTypes) { throw "retention label '$($t.name)': retentionType must be one of $($script:RetentionTypes -join ', ')." }
        if ("$($t.durationDays)" -ne 'unlimited' -and [int]$t.durationDays -lt 1) { throw "retention label '$($t.name)': durationDays must be a positive number or 'unlimited'." }
        # Once a record label is applied to content, the label can't be removed.
        if ([bool](Get-PVProp $t 'isRecordLabel' $false) -and -not [bool](Get-PVProp $ret 'allowRecordLabels' $false)) {
            throw "retention label '$($t.name)' is a record label (can't be removed from content once applied). Set retention.allowRecordLabels to true if that's intended."
        }
    }
    $lp = $ret.labelPolicy
    if ($lp.label -notin @($ret.labels.name)) { throw "retention.labelPolicy: label '$($lp.label)' is not defined in retention.labels." }
    foreach ($loc in @($lp.locations)) { if ($loc -notin $script:RetentionLocations.Keys) { throw "retention.labelPolicy: unknown location '$loc'." } }
    # Preservation Lock: no one - including an administrator - can turn off the policy or make it less restrictive.
    if ([bool](Get-PVProp $lp 'restrictiveRetention' $false) -and -not [bool](Get-PVProp $ret 'allowPreservationLock' $false)) {
        throw 'retention.labelPolicy: restrictiveRetention (Preservation Lock) is irreversible. Set retention.allowPreservationLock to true if that is really intended.'
    }
    $c
}

#endregion

#region Parameter builders (pure) ---------------------------------------------------------------------------------

function ConvertTo-PVLabelParameter {
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param([Parameter(Mandatory)][object]$Label)
    $p = [ordered]@{ Name = $Label.name; DisplayName = $Label.displayName; Tooltip = $Label.tooltip; ContentType = $Label.contentType }
    $h = Get-PVProp $Label 'header'
    if ($h) {
        $p.ApplyContentMarkingHeaderEnabled = $true
        $p.ApplyContentMarkingHeaderText = $h.text
        if (Get-PVProp $h 'fontSize') { $p.ApplyContentMarkingHeaderFontSize = [int]$h.fontSize }
        if (Get-PVProp $h 'fontColor') { $p.ApplyContentMarkingHeaderFontColor = $h.fontColor }
        if (Get-PVProp $h 'alignment') { $p.ApplyContentMarkingHeaderAlignment = $h.alignment }
    }
    $p
}

function ConvertTo-PVLabelPolicyParameter {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Config)
    $lp = $Config.labelPolicy
    [ordered]@{ Name = $lp.name; Labels = @($lp.labels); ExchangeLocation = @($lp.publishTo); Comment = $lp.comment }
}

function ConvertTo-PVDlpPolicyParameter {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Policy)
    $p = [ordered]@{ Name = $Policy.name; Comment = $Policy.comment; Mode = $Policy.mode }
    foreach ($loc in @($Policy.locations)) { $p[$script:DlpLocations[$loc]] = 'All' }
    $p
}

function ConvertTo-PVSensitiveInfoCondition {
    <# The advanced ContentContainsSensitiveInformation shape from the New-DlpComplianceRule examples (groups). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Rule)
    $group = [ordered]@{ operator = 'Or'; name = 'Default' }
    $labels = @(Get-PVProp $Rule 'sensitivityLabels' @())
    if ($labels.Count) {
        $group.labels = @(foreach ($n in $labels) { [ordered]@{ name = $n; type = 'Sensitivity' } })
    }
    else {
        $group.sensitivetypes = @(foreach ($s in @($Rule.sensitiveTypes)) {
                [ordered]@{ name = $s.name; mincount = [int](Get-PVProp $s 'minCount' 1); maxcount = [int](Get-PVProp $s 'maxCount' -1) }
            })
    }
    [ordered]@{ operator = 'And'; groups = @($group) }
}

function ConvertTo-PVDlpRuleParameter {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Rule, [Parameter(Mandatory)][string]$PolicyName)
    $p = [ordered]@{
        Name                                = $Rule.name
        Policy                              = $PolicyName
        ContentContainsSensitiveInformation = ConvertTo-PVSensitiveInfoCondition -Rule $Rule
    }
    $scope = Get-PVProp $Rule 'accessScope'
    if ($scope) { $p.AccessScope = $scope }
    if ([bool](Get-PVProp $Rule 'blockAccess' $false)) { $p.BlockAccess = $true }
    $notify = @(Get-PVProp $Rule 'notifyUser' @())
    if ($notify.Count) { $p.NotifyUser = $notify }
    $tip = Get-PVProp $Rule 'policyTip'
    if ($tip) { $p.NotifyPolicyTipCustomText = $tip }
    $ov = Get-PVProp $Rule 'allowOverride'
    if ($ov) { $p.NotifyAllowOverride = $ov }
    $report = @(Get-PVProp $Rule 'incidentReportTo' @())
    if ($report.Count) { $p.GenerateIncidentReport = $report; $p.IncidentReportContent = 'All' }
    $p.ReportSeverityLevel = Get-PVProp $Rule 'severity' 'Low'
    $p
}

function ConvertTo-PVRetentionLabelParameter {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Label)
    [ordered]@{
        Name              = $Label.name
        Comment           = $Label.comment
        RetentionAction   = $Label.action
        RetentionDuration = if ("$($Label.durationDays)" -eq 'unlimited') { 'unlimited' } else { [int]$Label.durationDays }
        RetentionType     = $Label.retentionType
        IsRecordLabel     = [bool](Get-PVProp $Label 'isRecordLabel' $false)
    }
}

function ConvertTo-PVRetentionPolicyParameter {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Config)
    $lp = $Config.retention.labelPolicy
    $p = [ordered]@{ Name = $lp.name; Comment = $lp.comment }
    foreach ($loc in @($lp.locations)) { $p[$script:RetentionLocations[$loc]] = 'All' }
    if ([bool](Get-PVProp $lp 'restrictiveRetention' $false)) { $p.RestrictiveRetention = $true }
    $p
}

function ConvertTo-PVRetentionRuleParameter {
    <# A published label is a rule with PublishComplianceTag (no Name, no RetentionDuration in that parameter set). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Config)
    $lp = $Config.retention.labelPolicy
    [ordered]@{ Policy = $lp.name; PublishComplianceTag = $lp.label }
}

#endregion

#region Plan, findings, report (pure) -----------------------------------------------------------------------------

function New-PVStep {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Pure: builds an object, changes nothing.')]
    param([string]$Kind, [string]$Name, [string]$Action, [string]$Cmdlet, $Params, [string]$Detail = '')
    [pscustomobject]@{ Kind = $Kind; Name = $Name; Action = $Action; Cmdlet = $Cmdlet; Params = $Params; Detail = $Detail }
}

function Get-PurviewPlan {
    <# Ordered steps: labels, label policy, retention label/policy/rule, DLP policies and rules. Never deletes. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Config, [Parameter(Mandatory)][object]$Inventory)
    $inv = $Inventory
    foreach ($l in @($Config.sensitivityLabels)) {
        $exists = @($inv.labels | Where-Object { $_.name -eq $l.name }).Count
        New-PVStep 'SensitivityLabel' $l.name ($(if ($exists) { 'Exists' } else { 'Create' })) 'New-Label' (ConvertTo-PVLabelParameter -Label $l)
    }
    $lp = @($inv.labelPolicies | Where-Object { $_.name -eq $Config.labelPolicy.name }) | Select-Object -First 1
    if (-not $lp) { New-PVStep 'LabelPolicy' $Config.labelPolicy.name 'Create' 'New-LabelPolicy' (ConvertTo-PVLabelPolicyParameter -Config $Config) }
    else {
        $missing = @($Config.labelPolicy.labels | Where-Object { $_ -notin @($lp.labels) })
        if ($missing.Count) { New-PVStep 'LabelPolicy' $lp.name 'Drift' '' $null "Tenant policy doesn't publish: $($missing -join ', ')." }
        else { New-PVStep 'LabelPolicy' $lp.name 'Exists' '' $null }
    }

    foreach ($t in @($Config.retention.labels)) {
        $exists = @($inv.retentionLabels | Where-Object { $_.name -eq $t.name }).Count
        New-PVStep 'RetentionLabel' $t.name ($(if ($exists) { 'Exists' } else { 'Create' })) 'New-ComplianceTag' (ConvertTo-PVRetentionLabelParameter -Label $t)
    }
    $rlp = $Config.retention.labelPolicy
    $rp = @($inv.retentionPolicies | Where-Object { $_.name -eq $rlp.name }) | Select-Object -First 1
    if (-not $rp) {
        New-PVStep 'RetentionPolicy' $rlp.name 'Create' 'New-RetentionCompliancePolicy' (ConvertTo-PVRetentionPolicyParameter -Config $Config)
        New-PVStep 'RetentionRule' $rlp.name 'Create' 'New-RetentionComplianceRule' (ConvertTo-PVRetentionRuleParameter -Config $Config)
    }
    else {
        New-PVStep 'RetentionPolicy' $rlp.name 'Exists' '' $null
        $rule = @($inv.retentionRules | Where-Object { $_.policy -eq $rlp.name }).Count
        if ($rule) { New-PVStep 'RetentionRule' $rlp.name 'Exists' '' $null }
        elseif ("$(Get-PVProp $rp 'distributionStatus')" -eq 'Pending') {
            New-PVStep 'RetentionRule' $rlp.name 'Wait' '' $null 'Policy distribution is Pending: wait until it is no longer Pending before changing it.'
        }
        else { New-PVStep 'RetentionRule' $rlp.name 'Create' 'New-RetentionComplianceRule' (ConvertTo-PVRetentionRuleParameter -Config $Config) }
    }

    foreach ($p in @($Config.dlpPolicies)) {
        $live = @($inv.dlpPolicies | Where-Object { $_.name -eq $p.name }) | Select-Object -First 1
        if (-not $live) { New-PVStep 'DlpPolicy' $p.name 'Create' 'New-DlpCompliancePolicy' (ConvertTo-PVDlpPolicyParameter -Policy $p) }
        elseif ($live.mode -ne $p.mode) { New-PVStep 'DlpPolicy' $p.name 'Drift' '' $null "Tenant mode $($live.mode), file mode $($p.mode). Use -Promote to change the mode on purpose." }
        else { New-PVStep 'DlpPolicy' $p.name 'Exists' '' $null }
        foreach ($r in @($p.rules)) {
            $exists = @($inv.dlpRules | Where-Object { $_.name -eq $r.name }).Count
            New-PVStep 'DlpRule' $r.name ($(if ($exists) { 'Exists' } else { 'Create' })) 'New-DlpComplianceRule' (ConvertTo-PVDlpRuleParameter -Rule $r -PolicyName $p.name)
        }
    }
}

function Get-PurviewFinding {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Inventory, [Parameter(Mandatory)][object]$Config, [Parameter(Mandatory)][datetimeoffset]$Now)
    $inv = $Inventory
    $maxSim = [int](Get-PVProp $Config.audit 'simulationMaxDays' 15)

    $distributed = @(
        foreach ($x in @($inv.dlpPolicies)) { [pscustomobject]@{ Kind = 'DLP policy'; Item = $x } }
        foreach ($x in @($inv.retentionPolicies)) { [pscustomobject]@{ Kind = 'Retention policy'; Item = $x } }
        foreach ($x in @($inv.labelPolicies)) { [pscustomobject]@{ Kind = 'Label policy'; Item = $x } }
    )
    foreach ($d in $distributed) {
        $status = "$(Get-PVProp $d.Item 'distributionStatus' '')"
        if ($status -eq '' -or $status -eq 'Success') { continue }
        if ($status -eq 'Pending') { New-PVFinding 'Info' "$($d.Kind): $($d.Item.name)" 'DistributionPending' 'Still distributing. Wait until it is no longer Pending before you change it.' }
        else { New-PVFinding 'High' "$($d.Kind): $($d.Item.name)" 'DistributionError' "DistributionStatus '$status'. Check DistributionResults and fix the errors (warnings can be ignored)." }
    }

    foreach ($p in @($inv.dlpPolicies)) {
        if ($p.mode -like 'Test*') {
            $since = ConvertTo-PVDate (Get-PVProp $p 'whenChangedUtc' (Get-PVProp $p 'whenCreatedUtc'))
            if ($since -and ($Now - $since).TotalDays -gt $maxSim) {
                New-PVFinding 'Medium' "DLP policy: $($p.name)" 'SimulationOverdue' ("In {0} for {1:N0} days. A simulation runs for up to {2} days: review the results, then promote it or re-run the simulation." -f $p.mode, ($Now - $since).TotalDays, $maxSim)
            }
        }
        elseif ($p.mode -eq 'Disable') { New-PVFinding 'Low' "DLP policy: $($p.name)" 'DlpPolicyOff' 'Policy is turned off.' }
        if ('Teams' -in @($p.locations)) {
            foreach ($r in @($inv.dlpRules | Where-Object { $_.policy -eq $p.name })) {
                if ("$(Get-PVProp $r 'conditionJson' '')" -match '"type"\s*:\s*"Sensitivity"') {
                    New-PVFinding 'High' "DLP rule: $($r.name)" 'LabelConditionWithTeams' "Policy '$($p.name)' includes Teams, which can't define content by sensitivity label, so the label condition can't work. Move the rule to a policy without Teams."
                }
            }
        }
    }

    $published = @(foreach ($lp in @($inv.labelPolicies)) { @($lp.labels) })
    foreach ($l in @($inv.labels)) {
        $ids = @($l.name, (Get-PVProp $l 'displayName'), (Get-PVProp $l 'guid')) | Where-Object { $_ }
        if (-not @($published | Where-Object { $_ -in $ids }).Count) {
            New-PVFinding 'Medium' "Sensitivity label: $($l.name)" 'LabelNotPublished' 'Not in any label policy, so nobody can apply it.'
        }
    }
    $publishedTags = @($inv.retentionRules | ForEach-Object { "$(Get-PVProp $_ 'publishComplianceTag' '')" } | Where-Object { $_ })
    foreach ($t in @($inv.retentionLabels)) {
        if (-not @($publishedTags | Where-Object { $_ -like "*$($t.name)*" }).Count) {
            New-PVFinding 'Medium' "Retention label: $($t.name)" 'RetentionLabelNotPublished' 'Not published by any retention label policy (or auto-applied).'
        }
        if ([bool](Get-PVProp $t 'isRecordLabel' $false)) {
            New-PVFinding 'Info' "Retention label: $($t.name)" 'RecordLabel' 'Record label: once applied to content, it cannot be removed.'
        }
    }
    foreach ($rp in @($inv.retentionPolicies)) {
        if ([bool](Get-PVProp $rp 'restrictiveRetention' $false)) {
            New-PVFinding 'Info' "Retention policy: $($rp.name)" 'PreservationLock' 'Preservation Lock is on: no one, including an administrator, can turn it off or make it less restrictive.'
        }
    }
    foreach ($s in @(Get-PurviewPlan -Config $Config -Inventory $Inventory | Where-Object Action -In 'Create', 'Drift')) {
        if ($s.Action -eq 'Create') { New-PVFinding 'Medium' "$($s.Kind): $($s.Name)" 'NotDeployed' 'In compliance.json but not in the tenant.' }
        else { New-PVFinding 'Low' "$($s.Kind): $($s.Name)" 'Drift' $s.Detail }
    }
}

function ConvertTo-PurviewMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Inventory, [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings, [Parameter(Mandatory)][datetimeoffset]$Now)
    $rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
    $md = [System.Collections.Generic.List[string]]::new()
    $md.Add('# Microsoft Purview audit'); $md.Add('')
    $md.Add("As of $($Now.ToString('yyyy-MM-dd HH:mm')) UTC. $(@($Inventory.labels).Count) sensitivity labels, $(@($Inventory.labelPolicies).Count) label policies, $(@($Inventory.dlpPolicies).Count) DLP policies, $(@($Inventory.dlpRules).Count) DLP rules, $(@($Inventory.retentionLabels).Count) retention labels, $($Findings.Count) findings."); $md.Add('')
    $md.Add('| Severity | Target | Rule | Detail |'); $md.Add('|---|---|---|---|')
    foreach ($f in @($Findings | Sort-Object { $rank[$_.Severity] }, Target, Rule)) { $md.Add("| $($f.Severity) | $($f.Target) | $($f.Rule) | $($f.Detail) |") }
    $md
}

#endregion

#region DLP test content (pure) -----------------------------------------------------------------------------------

function Test-PVLuhn {
    [CmdletBinding()]
    [OutputType([bool])]
    param([Parameter(Mandatory)][string]$Number)
    $digits = ($Number -replace '[\s-]', '')
    if ($digits -notmatch '^\d{12,19}$') { return $false }
    $sum = 0; $double = $false
    for ($i = $digits.Length - 1; $i -ge 0; $i--) {
        $d = [int][string]$digits[$i]
        if ($double) { $d *= 2; if ($d -gt 9) { $d -= 9 } }
        $sum += $d; $double = -not $double
    }
    ($sum % 10) -eq 0
}

function New-DlpTestContent {
    <#
    .SYNOPSIS  Synthetic test data for the Credit Card Number type: 16-digit Visa-format numbers that pass the Luhn
               check, each next to the keyword "Visa" (high confidence needs a keyword or an expiry date within 300
               characters). Random numbers on purpose: the type doesn't flag reserved test card numbers.
               No names, no expiry dates, no CVV. Use only inside the lab tenant.
    #>
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Pure: returns strings, writes nothing.')]
    [CmdletBinding()]
    [OutputType([string[]])]
    param([ValidateRange(1, 500)][int]$Count = 12, [int]$Seed = 2026)
    $rng = [System.Random]::new($Seed)
    $out = [System.Collections.Generic.List[string]]::new()
    $out.Add('Contoso - DLP test file (synthetic data, DEVLADLOG Microsoft 365 #5)')
    $seen = @{}
    while ($seen.Count -lt $Count) {
        $body = '4' + (-join (1..14 | ForEach-Object { $rng.Next(0, 10) }))
        $check = 0
        foreach ($c in 0..9) { if (Test-PVLuhn "$body$c") { $check = $c; break } }
        $n = "$body$check"
        if ($seen.ContainsKey($n)) { continue }
        $seen[$n] = $true
        $out.Add(('Customer {0:D3} - Visa card number {1} {2} {3} {4}' -f $seen.Count, $n.Substring(0, 4), $n.Substring(4, 4), $n.Substring(8, 4), $n.Substring(12, 4)))
    }
    $out.ToArray()
}

#endregion

#region Security & Compliance PowerShell ---------------------------------------------------------------------------

function Get-PurviewInventory {
    <# Read-only snapshot. Needs Connect-IPPSSession and a role that can read labels, DLP and retention (e.g. Compliance Administrator). #>
    [CmdletBinding()]
    param()
    $labels = foreach ($l in @(Get-Label -ErrorAction Stop)) {
        [pscustomobject]@{ name = $l.Name; displayName = Get-PVProp $l 'DisplayName'; guid = "$(Get-PVProp $l 'Guid')"; priority = Get-PVProp $l 'Priority' }
    }
    $labelPolicies = foreach ($p in @(Get-LabelPolicy -ErrorAction Stop)) {
        [pscustomobject]@{ name = $p.Name; labels = @(Get-PVProp $p 'Labels' @() | ForEach-Object { "$_" }); distributionStatus = "$(Get-PVProp $p 'DistributionStatus' '')" }
    }
    $dlpPolicies = @(); $dlpRules = @()
    foreach ($p in @(Get-DlpCompliancePolicy -ErrorAction Stop)) {
        $d = Get-DlpCompliancePolicy -Identity $p.Name -DistributionDetail -ErrorAction Stop
        $locs = @(foreach ($k in $script:DlpLocations.Keys) { if (@(Get-PVProp $p $script:DlpLocations[$k] @()).Count) { $k } })
        $dlpPolicies += [pscustomobject]@{
            name = $p.Name; mode = "$($p.Mode)"; distributionStatus = "$(Get-PVProp $d 'DistributionStatus' '')"
            whenCreatedUtc = Get-PVProp $p 'WhenCreatedUTC'; whenChangedUtc = Get-PVProp $p 'WhenChangedUTC'; locations = $locs
        }
        foreach ($r in @(Get-DlpComplianceRule -Policy $p.Name -ErrorAction Stop)) {
            $dlpRules += [pscustomobject]@{
                name = $r.Name; policy = $p.Name; disabled = [bool](Get-PVProp $r 'Disabled' $false)
                conditionJson = (Get-PVProp $r 'ContentContainsSensitiveInformation' @() | ConvertTo-Json -Depth 10 -Compress)
            }
        }
    }
    $retentionLabels = foreach ($t in @(Get-ComplianceTag -ErrorAction Stop)) {
        [pscustomobject]@{ name = $t.Name; retentionAction = "$(Get-PVProp $t 'RetentionAction' '')"; retentionDuration = "$(Get-PVProp $t 'RetentionDuration' '')"; isRecordLabel = [bool](Get-PVProp $t 'IsRecordLabel' $false) }
    }
    $retentionPolicies = @(); $retentionRules = @()
    foreach ($p in @(Get-RetentionCompliancePolicy -ErrorAction Stop)) {
        $d = Get-RetentionCompliancePolicy -Identity $p.Name -DistributionDetail -ErrorAction Stop
        $retentionPolicies += [pscustomobject]@{
            name = $p.Name; distributionStatus = "$(Get-PVProp $d 'DistributionStatus' '')"
            restrictiveRetention = [bool](Get-PVProp $p 'RestrictiveRetention' $false); enabled = [bool](Get-PVProp $p 'Enabled' $true)
        }
        foreach ($r in @(Get-RetentionComplianceRule -Policy $p.Name -ErrorAction Stop)) {
            $retentionRules += [pscustomobject]@{ name = $r.Name; policy = $p.Name; publishComplianceTag = "$(Get-PVProp $r 'PublishComplianceTag' '')" }
        }
    }
    [pscustomobject]@{
        collectedAt = [datetimeoffset]::UtcNow.ToString('o')
        labels = @($labels); labelPolicies = @($labelPolicies)
        dlpPolicies = $dlpPolicies; dlpRules = $dlpRules
        retentionLabels = @($retentionLabels); retentionPolicies = $retentionPolicies; retentionRules = $retentionRules
    }
}

function Invoke-PurviewPlan {
    <#
    .SYNOPSIS  Runs the Create steps of a plan, in order. -WhatIf and -Confirm are handled here, never passed on:
               the WhatIf switch doesn't work in Security & Compliance PowerShell.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Plan)
    foreach ($s in $Plan) {
        if ($s.Action -ne 'Create') { [pscustomobject]@{ Kind = $s.Kind; Name = $s.Name; Result = $s.Action; Detail = $s.Detail }; continue }
        if (-not $PSCmdlet.ShouldProcess("$($s.Kind) '$($s.Name)'", $s.Cmdlet)) {
            [pscustomobject]@{ Kind = $s.Kind; Name = $s.Name; Result = 'WhatIf'; Detail = $s.Cmdlet }; continue
        }
        $params = $s.Params
        try {
            & $s.Cmdlet @params -ErrorAction Stop | Out-Null
            [pscustomobject]@{ Kind = $s.Kind; Name = $s.Name; Result = 'Created'; Detail = $s.Cmdlet }
        }
        catch {
            [pscustomobject]@{ Kind = $s.Kind; Name = $s.Name; Result = 'Failed'; Detail = $_.Exception.Message }
            throw "Stopped at $($s.Kind) '$($s.Name)': $($_.Exception.Message)"
        }
    }
}

function Set-PurviewDlpMode {
    <# Promote (or demote) one DLP policy after reviewing the simulation. Refuses while distribution is Pending. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)][string]$Name, [ValidateSet('Enable', 'Disable', 'TestWithNotifications', 'TestWithoutNotifications')][string]$Mode = 'Enable')
    $p = Get-DlpCompliancePolicy -Identity $Name -DistributionDetail -ErrorAction Stop
    if ("$(Get-PVProp $p 'DistributionStatus' '')" -eq 'Pending') { throw "'$Name' is still distributing (Pending). Try again later." }
    if ("$($p.Mode)" -eq $Mode) { return [pscustomobject]@{ Name = $Name; From = "$($p.Mode)"; To = $Mode; Result = 'NoChange' } }
    if (-not $PSCmdlet.ShouldProcess($Name, "Change DLP mode $($p.Mode) -> $Mode")) { return [pscustomobject]@{ Name = $Name; From = "$($p.Mode)"; To = $Mode; Result = 'WhatIf' } }
    Set-DlpCompliancePolicy -Identity $Name -Mode $Mode -ErrorAction Stop | Out-Null
    [pscustomobject]@{ Name = $Name; From = "$($p.Mode)"; To = $Mode; Result = 'Changed (takes effect in about an hour)' }
}

#endregion
