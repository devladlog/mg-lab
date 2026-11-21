#Requires -Version 7.2
<#
.SYNOPSIS
    Microsoft Intune as code (DEVLADLOG Microsoft 365 #7): one JSON file drives a Windows compliance policy; the module
    audits the managed devices and can trigger a device sync. Microsoft Graph only (Invoke-MgGraphRequest).

    Graph v1.0 resources used (Microsoft Learn, "Microsoft Graph API for Intune"; needs an active Intune licence):
      windows10CompliancePolicy, deviceComplianceScheduledActionForRule + deviceComplianceActionItem, assign,
      scheduleActionsForRules, managedDevice (list, syncDevice).
    Delegated scopes: DeviceManagementConfiguration.ReadWrite.All (policy), DeviceManagementManagedDevices.Read.All
    (audit), DeviceManagementManagedDevices.PrivilegedOperations.All (syncDevice).
#>
Set-StrictMode -Version Latest

$script:PolicyType = '#microsoft.graph.windows10CompliancePolicy'
$script:RuleType = '#microsoft.graph.deviceComplianceScheduledActionForRule'
$script:ActionType = '#microsoft.graph.deviceComplianceActionItem'
$script:RuleName = 'PasswordRequired'   # Learn: scheduled actions are per policy; ruleName is always PasswordRequired
$script:ZeroGuid = '00000000-0000-0000-0000-000000000000'
$script:GraphRoot = '/v1.0/deviceManagement'

# Writable settings of windows10CompliancePolicy (Learn, resource type) and their JSON types.
$script:SettingTypes = [ordered]@{
    passwordRequired                      = 'bool'
    passwordBlockSimple                   = 'bool'
    passwordRequiredToUnlockFromIdle      = 'bool'
    passwordMinutesOfInactivityBeforeLock = 'int'
    passwordExpirationDays                = 'int'
    passwordMinimumLength                 = 'int'
    passwordMinimumCharacterSetCount      = 'int'
    passwordRequiredType                  = 'enum:deviceDefault,alphanumeric,numeric'
    passwordPreviousPasswordBlockCount    = 'int'
    requireHealthyDeviceReport            = 'bool'
    osMinimumVersion                      = 'version'
    osMaximumVersion                      = 'version'
    earlyLaunchAntiMalwareDriverEnabled   = 'bool'
    bitLockerEnabled                      = 'bool'
    secureBootEnabled                     = 'bool'
    codeIntegrityEnabled                  = 'bool'
    storageRequireEncryption              = 'bool'
}
# Learn, deviceComplianceActionType: noAction, notification, block, retire, wipe, removeResourceAccessProfiles, pushNotification.
# We only offer the ones that make sense for a Windows policy and never a wipe.
$script:AllowedActions = @('block', 'notification', 'retire', 'pushNotification')

function Get-IDProp {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $null } }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { $p.Value } else { $null }
}

function Test-IDGuid {
    param($Value)
    $g = [guid]::Empty
    [guid]::TryParse("$Value", [ref]$g)
}

function ConvertTo-IDDate {
    param($Value)
    if ($null -eq $Value -or "$Value" -eq '') { return $null }
    if ($Value -is [datetimeoffset]) { return $Value }
    if ($Value -is [datetime]) { return [datetimeoffset]::new($Value.ToUniversalTime()) }
    $out = [datetimeoffset]::MinValue
    if ([datetimeoffset]::TryParse("$Value", [cultureinfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AssumeUniversal, [ref]$out)) { return $out }
    $null
}

# ---------------------------------------------------------------- configuration

function Get-IntuneConfig {
    <#
    .SYNOPSIS Reads and validates intune.json. Refuses anything Graph or Learn says is invalid, before a single call.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $cfg = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $cp = Get-IDProp $cfg 'compliancePolicy'
    if (-not $cp) { throw "Config: 'compliancePolicy' is missing." }
    if ([string]::IsNullOrWhiteSpace((Get-IDProp $cp 'displayName'))) { throw 'Config: compliancePolicy.displayName is required.' }

    $assign = Get-IDProp $cp 'assignTo'
    $gid = Get-IDProp $assign 'groupId'
    $all = Get-IDProp $assign 'allLicensedUsers'
    if (-not $assign -or ([bool]$gid -eq [bool]$all)) { throw 'Config: assignTo needs exactly one of groupId or allLicensedUsers.' }
    if ($gid -and -not (Test-IDGuid $gid)) { throw "Config: assignTo.groupId '$gid' is not a GUID (use the Entra group object id)." }

    $settings = Get-IDProp $cp 'settings'
    if (-not $settings -or @($settings.PSObject.Properties).Count -eq 0) { throw 'Config: compliancePolicy.settings is empty.' }
    foreach ($p in $settings.PSObject.Properties) {
        if (-not $script:SettingTypes.Contains($p.Name)) { throw "Config: '$($p.Name)' is not a windows10CompliancePolicy setting we manage." }
        $type = $script:SettingTypes[$p.Name]; $v = $p.Value
        switch -Wildcard ($type) {
            'bool' { if ($v -isnot [bool]) { throw "Config: $($p.Name) must be true or false." } }
            'int' { if ($v -isnot [int] -and $v -isnot [long] -or $v -lt 0) { throw "Config: $($p.Name) must be a whole number >= 0." } }
            'version' { if ("$v" -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw "Config: $($p.Name) '$v' must be major.minor.build.revision (Learn: the value `ver` prints, for example 10.0.26100.1742)." } }
            'enum:*' { if ("$v" -cnotin ($type.Substring(5) -split ',')) { throw "Config: $($p.Name) '$v' must be one of $($type.Substring(5))." } }
        }
    }

    $actions = @(Get-IDProp $cp 'actions')
    if (-not $actions) { throw 'Config: compliancePolicy.actions needs one block action (Learn: a compliance policy must have one and only one block scheduled action).' }
    foreach ($a in $actions) {
        $t = Get-IDProp $a 'type'
        if ($t -cnotin $script:AllowedActions) { throw "Config: action type '$t' is not allowed (use $($script:AllowedActions -join ', '))." }
        $h = Get-IDProp $a 'gracePeriodHours'
        if (($h -isnot [int] -and $h -isnot [long]) -or $h -lt 0 -or $h -gt 8760) { throw "Config: gracePeriodHours must be a whole number from 0 to 8760 (Learn), got '$h'." }
        if ($t -eq 'notification') {
            $tpl = Get-IDProp $a 'notificationTemplateId'
            if (-not $tpl -or -not (Test-IDGuid $tpl) -or "$tpl" -eq $script:ZeroGuid) { throw 'Config: a notification action needs notificationTemplateId (the id of an existing notification message template).' }
        }
    }
    if (@($actions | Where-Object { (Get-IDProp $_ 'type') -eq 'block' }).Count -ne 1) { throw 'Config: exactly one block action is required (Learn).' }

    $audit = Get-IDProp $cfg 'audit'
    $days = Get-IDProp $audit 'staleDays'
    if ($audit -and $null -ne $days -and (($days -isnot [int] -and $days -isnot [long]) -or $days -lt 1 -or $days -gt 270)) { throw "Config: audit.staleDays must be 1 to 270, got '$days'." }
    $cfg
}

function ConvertTo-IDActionItem {
    param($Action)
    $item = [ordered]@{
        '@odata.type'    = $script:ActionType
        gracePeriodHours = [int](Get-IDProp $Action 'gracePeriodHours')
        actionType       = [string](Get-IDProp $Action 'type')
    }
    if ($item.actionType -eq 'notification') { $item.notificationTemplateId = [string](Get-IDProp $Action 'notificationTemplateId') }
    $item
}

function ConvertTo-IDCompliancePolicyBody {
    <#
    .SYNOPSIS The windows10CompliancePolicy request body for POST /deviceManagement/deviceCompliancePolicies.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Config)
    $cp = $Config.compliancePolicy
    $body = [ordered]@{
        '@odata.type' = $script:PolicyType
        displayName   = [string]$cp.displayName
        description   = [string](Get-IDProp $cp 'description')
    }
    foreach ($name in $script:SettingTypes.Keys) {
        $v = Get-IDProp $cp.settings $name
        if ($null -ne $v) { $body[$name] = $v }
    }
    $body['scheduledActionsForRule'] = @([ordered]@{
            '@odata.type'                 = $script:RuleType
            ruleName                      = $script:RuleName
            scheduledActionConfigurations = @($cp.actions | ForEach-Object { ConvertTo-IDActionItem $_ })
        })
    $body
}

function ConvertTo-IDAssignmentBody {
    <#
    .SYNOPSIS The body for POST .../deviceCompliancePolicies/{id}/assign (replaces the policy's assignment list).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Config)
    $a = $Config.compliancePolicy.assignTo
    $target = if (Get-IDProp $a 'groupId') { [ordered]@{ '@odata.type' = '#microsoft.graph.groupAssignmentTarget'; groupId = [string]$a.groupId } }
    else { [ordered]@{ '@odata.type' = '#microsoft.graph.allLicensedUsersAssignmentTarget' } }
    [ordered]@{ assignments = @([ordered]@{ '@odata.type' = '#microsoft.graph.deviceCompliancePolicyAssignment'; target = $target }) }
}

# ---------------------------------------------------------------- normalised views (for comparing desired vs actual)

function ConvertTo-IDActionKey {
    param($Item)
    $t = Get-IDProp $Item 'actionType'
    $key = '{0}|{1}h' -f $t, [int](Get-IDProp $Item 'gracePeriodHours')
    if ($t -eq 'notification') { $key += '|' + (Get-IDProp $Item 'notificationTemplateId') }
    $key
}

function ConvertTo-IDTargetKey {
    param($Target)
    $type = "$(Get-IDProp $Target '@odata.type')"
    switch -Regex ($type) {
        'groupAssignmentTarget$' { if ($type -match 'exclusion') { return "exclude:$(Get-IDProp $Target 'groupId')" } else { return "group:$(Get-IDProp $Target 'groupId')" } }
        'allLicensedUsersAssignmentTarget$' { return 'allLicensedUsers' }
        default { return $type }
    }
}

function Get-IntuneCompliancePolicy {
    <#
    .SYNOPSIS Finds our Windows compliance policy by display name and reads its actions and assignments.
    .OUTPUTS $null when it does not exist; otherwise Policy, Id, Actions (normalised keys), Assignments (normalised keys).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$DisplayName)
    $uri = "$script:GraphRoot/deviceCompliancePolicies"
    $found = @()
    while ($uri) {
        $page = Invoke-MgGraphRequest -Method GET -Uri $uri -OutputType PSObject -ErrorAction Stop
        $found += @($page.value | Where-Object { $_.displayName -eq $DisplayName -and (Get-IDProp $_ '@odata.type') -eq $script:PolicyType })
        $uri = Get-IDProp $page '@odata.nextLink'
    }
    if ($found.Count -eq 0) { return $null }
    if ($found.Count -gt 1) { throw "More than one Windows compliance policy is named '$DisplayName' ($($found.id -join ', ')). Rename or delete the duplicates first." }
    $p = $found[0]
    $actions = @()
    $rules = Invoke-MgGraphRequest -Method GET -Uri "$script:GraphRoot/deviceCompliancePolicies/$($p.id)/scheduledActionsForRule" -OutputType PSObject -ErrorAction Stop
    foreach ($r in @($rules.value)) {
        $items = Invoke-MgGraphRequest -Method GET -Uri "$script:GraphRoot/deviceCompliancePolicies/$($p.id)/scheduledActionsForRule/$($r.id)/scheduledActionConfigurations" -OutputType PSObject -ErrorAction Stop
        $actions += @($items.value | ForEach-Object { ConvertTo-IDActionKey $_ })
    }
    $asg = Invoke-MgGraphRequest -Method GET -Uri "$script:GraphRoot/deviceCompliancePolicies/$($p.id)/assignments" -OutputType PSObject -ErrorAction Stop
    [pscustomobject]@{
        Id          = $p.id
        Policy      = $p
        Actions     = @($actions | Sort-Object)
        Assignments = @(@($asg.value) | ForEach-Object { ConvertTo-IDTargetKey $_.target } | Sort-Object)
    }
}

function Compare-IntuneCompliancePolicy {
    <#
    .SYNOPSIS Differences between the desired body/assignment and what the tenant has. Empty = in sync.
    .OUTPUTS Objects with Area (Setting | Actions | Assignment), Name, Desired, Actual.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Existing, [Parameter(Mandatory)]$Config)
    $diff = [System.Collections.Generic.List[object]]::new()
    $body = ConvertTo-IDCompliancePolicyBody -Config $Config
    foreach ($k in @('description') + @($script:SettingTypes.Keys)) {
        if (-not $body.Contains($k)) { continue }
        $actual = Get-IDProp $Existing.Policy $k
        if ("$actual" -ne "$($body[$k])") { $diff.Add([pscustomobject]@{ Area = 'Setting'; Name = $k; Desired = $body[$k]; Actual = $actual }) }
    }
    $want = @($body.scheduledActionsForRule[0].scheduledActionConfigurations | ForEach-Object { ConvertTo-IDActionKey $_ } | Sort-Object)
    if (($want -join ';') -ne ($Existing.Actions -join ';')) { $diff.Add([pscustomobject]@{ Area = 'Actions'; Name = 'actions for noncompliance'; Desired = ($want -join '; '); Actual = ($Existing.Actions -join '; ') }) }
    $wantAsg = ConvertTo-IDTargetKey (ConvertTo-IDAssignmentBody -Config $Config).assignments[0].target
    if (($Existing.Assignments -join ';') -ne $wantAsg) { $diff.Add([pscustomobject]@{ Area = 'Assignment'; Name = 'assignments'; Desired = $wantAsg; Actual = ($Existing.Assignments -join '; ') }) }
    $diff.ToArray()
}

function Set-IntuneCompliancePolicy {
    <#
    .SYNOPSIS
        Makes the tenant match intune.json: create the policy (with its actions) or patch only what differs, then assign.
        Reads always run; every write honours -WhatIf / -Confirm. Needs DeviceManagementConfiguration.ReadWrite.All.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
    param([Parameter(Mandatory)]$Config)
    $assign = $Config.compliancePolicy.assignTo
    if ((Get-IDProp $assign 'groupId') -eq $script:ZeroGuid) {
        throw 'assignTo.groupId is still the zero-GUID placeholder. Put the object id of the Entra group in your own copy of intune.json.'
    }
    $name = [string]$Config.compliancePolicy.displayName
    $existing = Get-IntuneCompliancePolicy -DisplayName $name
    $body = ConvertTo-IDCompliancePolicyBody -Config $Config
    $assignBody = ConvertTo-IDAssignmentBody -Config $Config

    if (-not $existing) {
        if (-not $PSCmdlet.ShouldProcess($name, 'Create Windows compliance policy and assign it')) { return [pscustomobject]@{ Policy = $name; Id = $null; Action = 'WhatIf-Create'; Changes = @() } }
        $created = Invoke-MgGraphRequest -Method POST -Uri "$script:GraphRoot/deviceCompliancePolicies" -Body ($body | ConvertTo-Json -Depth 10) -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop
        $null = Invoke-MgGraphRequest -Method POST -Uri "$script:GraphRoot/deviceCompliancePolicies/$($created.id)/assign" -Body ($assignBody | ConvertTo-Json -Depth 10) -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop
        return [pscustomobject]@{ Policy = $name; Id = $created.id; Action = 'Created'; Changes = @() }
    }

    $changes = @(Compare-IntuneCompliancePolicy -Existing $existing -Config $Config)
    if ($changes.Count -eq 0) { return [pscustomobject]@{ Policy = $name; Id = $existing.Id; Action = 'Unchanged'; Changes = @() } }
    if (-not $PSCmdlet.ShouldProcess($name, "Update: $($changes.Name -join ', ')")) { return [pscustomobject]@{ Policy = $name; Id = $existing.Id; Action = 'WhatIf-Update'; Changes = $changes } }

    $settingChanges = @($changes | Where-Object Area -eq 'Setting')
    if ($settingChanges) {
        $patch = [ordered]@{ '@odata.type' = $script:PolicyType }
        foreach ($c in $settingChanges) { $patch[$c.Name] = $c.Desired }
        $null = Invoke-MgGraphRequest -Method PATCH -Uri "$script:GraphRoot/deviceCompliancePolicies/$($existing.Id)" -Body ($patch | ConvertTo-Json -Depth 10) -ContentType 'application/json' -ErrorAction Stop
    }
    if ($changes | Where-Object Area -eq 'Actions') {
        $rules = [ordered]@{ deviceComplianceScheduledActionForRules = @($body.scheduledActionsForRule) }
        $null = Invoke-MgGraphRequest -Method POST -Uri "$script:GraphRoot/deviceCompliancePolicies/$($existing.Id)/scheduleActionsForRules" -Body ($rules | ConvertTo-Json -Depth 10) -ContentType 'application/json' -ErrorAction Stop
    }
    if ($changes | Where-Object Area -eq 'Assignment') {
        $null = Invoke-MgGraphRequest -Method POST -Uri "$script:GraphRoot/deviceCompliancePolicies/$($existing.Id)/assign" -Body ($assignBody | ConvertTo-Json -Depth 10) -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop
    }
    [pscustomobject]@{ Policy = $name; Id = $existing.Id; Action = 'Updated'; Changes = $changes }
}

# ---------------------------------------------------------------- devices

$script:DeviceSelect = @(
    'id', 'deviceName', 'userId', 'userPrincipalName', 'managedDeviceOwnerType', 'enrolledDateTime', 'lastSyncDateTime', 'operatingSystem',
    'osVersion', 'complianceState', 'complianceGracePeriodExpirationDateTime', 'isEncrypted', 'azureADRegistered', 'deviceEnrollmentType',
    'azureADDeviceId', 'manufacturer', 'model', 'serialNumber'
) -join ','

function Get-IntuneManagedDevice {
    <#
    .SYNOPSIS All managed devices (paged), filtered client-side by operating system.
        $filter support is only documented for some properties (complianceState, lastSyncDateTime...), not operatingSystem.
    #>
    [CmdletBinding()]
    param([string]$OperatingSystem = 'Windows')
    $uri = "$script:GraphRoot/managedDevices?`$select=$script:DeviceSelect&`$top=100"
    $all = [System.Collections.Generic.List[object]]::new()
    while ($uri) {
        $page = Invoke-MgGraphRequest -Method GET -Uri $uri -OutputType PSObject -ErrorAction Stop
        foreach ($d in @($page.value)) { if (-not $OperatingSystem -or $d.operatingSystem -eq $OperatingSystem) { $all.Add($d) } }
        $uri = Get-IDProp $page '@odata.nextLink'
    }
    $all.ToArray()
}

function Get-IntuneComplianceSummary {
    <#
    .SYNOPSIS Devices per complianceState (compliant, noncompliant, inGracePeriod, ...) with percentages.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Devices)
    $total = @($Devices).Count
    $Devices | Group-Object { if ($_.complianceState) { $_.complianceState } else { 'unknown' } } | Sort-Object Count -Descending | ForEach-Object {
        [pscustomobject]@{ State = $_.Name; Devices = $_.Count; Percent = if ($total) { [math]::Round(100 * $_.Count / $total, 0) } else { 0 } }
    }
}

function Get-IntuneDeviceFinding {
    <#
    .SYNOPSIS
        Hygiene findings for a device list. Rules: NonCompliant, InGracePeriod, StaleCheckIn, NeverSynced, NotEncrypted,
        OsBelowMinimum, NoPrimaryUser, PersonalOwned, DuplicateSerial. Thresholds come from the config; -Now makes it testable.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Devices,
        [Parameter(Mandatory)]$Config,
        [datetimeoffset]$Now = [datetimeoffset]::UtcNow
    )
    $audit = Get-IDProp $Config 'audit'
    $staleDays = if ($null -ne (Get-IDProp $audit 'staleDays')) { [int]$audit.staleDays } else { 30 }
    $needEnc = if ($null -ne (Get-IDProp $audit 'requireEncryption')) { [bool]$audit.requireEncryption } else { $true }
    $flagPersonal = if ($null -ne (Get-IDProp $audit 'flagPersonalOwned')) { [bool]$audit.flagPersonalOwned } else { $true }
    $minOs = Get-IDProp (Get-IDProp (Get-IDProp $Config 'compliancePolicy') 'settings') 'osMinimumVersion'
    $minVer = $null; if ($minOs) { [void][version]::TryParse("$minOs", [ref]$minVer) }

    $out = [System.Collections.Generic.List[object]]::new()
    function Add-F($sev, $rule, $dev, $msg) { $out.Add([pscustomobject]@{ Severity = $sev; Rule = $rule; Device = $dev.deviceName; User = $dev.userPrincipalName; Message = $msg }) }

    foreach ($d in $Devices) {
        $state = "$($d.complianceState)"
        if ($state -in 'noncompliant', 'error', 'conflict') { Add-F 'High' 'NonCompliant' $d "complianceState is $state. Open Devices > Monitor > Noncompliant devices for the failing setting." }
        if ($state -eq 'inGracePeriod') {
            $exp = ConvertTo-IDDate (Get-IDProp $d 'complianceGracePeriodExpirationDateTime')
            Add-F 'Low' 'InGracePeriod' $d ("in grace period" + $(if ($exp) { ", expires $($exp.ToString('yyyy-MM-dd HH:mm')) UTC" }))
        }
        $sync = ConvertTo-IDDate (Get-IDProp $d 'lastSyncDateTime')
        if (-not $sync) { Add-F 'Medium' 'NeverSynced' $d 'no lastSyncDateTime: enrolled but never completed a sync.' }
        elseif (($Now - $sync).TotalDays -gt $staleDays) { Add-F 'Medium' 'StaleCheckIn' $d ("last sync {0:N0} days ago (limit {1}). A device cleanup rule (30-270 days) only hides the record; it does not wipe or retire." -f ($Now - $sync).TotalDays, $staleDays) }
        if ($needEnc -and $d.operatingSystem -eq 'Windows' -and (Get-IDProp $d 'isEncrypted') -eq $false) { Add-F 'High' 'NotEncrypted' $d 'isEncrypted is false.' }
        if ($minVer -and $d.operatingSystem -eq 'Windows') {
            $v = $null
            if ([version]::TryParse("$($d.osVersion)", [ref]$v)) { if ($v -lt $minVer) { Add-F 'Medium' 'OsBelowMinimum' $d "OS $($d.osVersion) is below the policy minimum $minOs." } }
            else { Add-F 'Low' 'OsVersionUnknown' $d "osVersion '$($d.osVersion)' could not be read." }
        }
        $uid = "$(Get-IDProp $d 'userId')"
        if (-not $uid -or $uid -eq $script:ZeroGuid) { Add-F 'Low' 'NoPrimaryUser' $d 'no primary user (userless device).' }
        if ($flagPersonal -and (Get-IDProp $d 'managedDeviceOwnerType') -eq 'personal') { Add-F 'Low' 'PersonalOwned' $d 'personal (BYOD) device: check the enrollment restrictions you intended.' }
    }
    foreach ($g in ($Devices | Where-Object { $_.serialNumber -and $_.serialNumber -notin 'Defaultstring', 'None' } | Group-Object serialNumber | Where-Object Count -gt 1)) {
        foreach ($d in $g.Group) { Add-F 'Medium' 'DuplicateSerial' $d "serial $($g.Name) appears on $($g.Count) records ($($g.Group.deviceName -join ', ')): re-enrolled device or stale record." }
    }
    $order = @{ High = 0; Medium = 1; Low = 2 }
    $out | Sort-Object { $order[$_.Severity] }, Rule, Device
}

function ConvertTo-IntuneMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Summary, [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings, [int]$DeviceCount = 0, [string]$Title = 'Intune device audit')
    $sb = [System.Text.StringBuilder]::new()
    [void]$sb.AppendLine("# $Title").AppendLine()
    [void]$sb.AppendLine("$DeviceCount Windows device(s).").AppendLine()
    [void]$sb.AppendLine('## Compliance state').AppendLine().AppendLine('| State | Devices | % |').AppendLine('|---|---|---|')
    foreach ($s in $Summary) { [void]$sb.AppendLine("| $($s.State) | $($s.Devices) | $($s.Percent) |") }
    [void]$sb.AppendLine().AppendLine("## Findings ($(@($Findings).Count))").AppendLine()
    if (@($Findings).Count -eq 0) { [void]$sb.AppendLine('None.') }
    else {
        [void]$sb.AppendLine('| Severity | Rule | Device | User | Message |').AppendLine('|---|---|---|---|---|')
        foreach ($f in $Findings) { [void]$sb.AppendLine("| $($f.Severity) | $($f.Rule) | $($f.Device) | $($f.User) | $($f.Message -replace '\|', '/') |") }
    }
    $sb.ToString()
}

function Invoke-IntuneDeviceSync {
    <#
    .SYNOPSIS Asks Intune to send the device a check-in request (POST managedDevices/{id}/syncDevice, 204 No Content).
        Needs DeviceManagementManagedDevices.PrivilegedOperations.All.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory, ValueFromPipelineByPropertyName)][Alias('Id')][string]$DeviceId, [Parameter(ValueFromPipelineByPropertyName)][string]$DeviceName = '')
    process {
        if ($DeviceId -notmatch '^[0-9a-fA-F-]{36}$') { throw "DeviceId '$DeviceId' is not a GUID." }
        if ($PSCmdlet.ShouldProcess("$DeviceName $DeviceId".Trim(), 'syncDevice')) {
            Invoke-MgGraphRequest -Method POST -Uri "$script:GraphRoot/managedDevices/$DeviceId/syncDevice" -ErrorAction Stop | Out-Null
            [pscustomobject]@{ DeviceId = $DeviceId; DeviceName = $DeviceName; Requested = $true }
        }
    }
}

Export-ModuleMember -Function Get-IntuneConfig, ConvertTo-IDCompliancePolicyBody, ConvertTo-IDAssignmentBody, Compare-IntuneCompliancePolicy,
Get-IntuneCompliancePolicy, Set-IntuneCompliancePolicy, Get-IntuneManagedDevice, Get-IntuneDeviceFinding, Get-IntuneComplianceSummary,
ConvertTo-IntuneMarkdown, Invoke-IntuneDeviceSync
