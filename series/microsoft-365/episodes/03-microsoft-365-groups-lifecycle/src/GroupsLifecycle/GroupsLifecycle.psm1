#Requires -Version 7.2
<#
    GroupsLifecycle: the life of a Microsoft 365 group, from expiration policy to restore, driven by lifecycle.json.

      * Policy   - Get-GroupsLifecycleConfig / ConvertTo-GroupLifecyclePolicyBody / Compare-GroupLifecyclePolicy and
                   Set-GroupsExpirationPolicy: the tenant's single groupLifecyclePolicy (lifetime, All/Selected/None,
                   alternate notification emails) plus addGroup for a Selected rollout.
      * Preview  - Get-ExpirationRolloutImpact: which groups are older than the lifetime and so start with 35 days.
      * Audit    - Get-GroupsLifecycleInventory + Get-GroupsLifecycleFinding: expiring soon, ownerless (nobody gets
                   the renewal mail), not covered, deleted groups close to permanent deletion.
      * Act      - Invoke-GroupRenewal (POST /groups/{id}/renew), Restore-DeletedM365Group
                   (POST /directory/deletedItems/{id}/restore), Invoke-TeamArchive (POST /teams/{id}/archive).

    Only Invoke-GLGraphGet and the Set/Invoke/Restore/Get-*Inventory functions call Microsoft Graph (Invoke-MgGraphRequest).
#>

Set-StrictMode -Version Latest

$script:MinLifetimeDays = 30        # Entra admin center: "It should be 30 days or more."
$script:MaxSelectedGroups = 500     # addGroup: up to 500 groups when managedGroupTypes is Selected
$script:RestoreWindowDays = 30      # deleted groups are kept 30 days, not customizable
$script:FirstRolloutDays = 35       # groups older than the lifetime get 35 days when expiration is first set up

#region Helpers ---------------------------------------------------------------------------------------------------

function Get-GLProp {
    param([object]$Object, [string]$Name, [object]$Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { $Default } else { $p.Value }
}

function ConvertTo-GLDate {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value -or "$Value" -eq '') { return $null }
    if ($Value -is [datetimeoffset]) { return $Value.ToUniversalTime() }
    if ($Value -is [datetime]) { return ([datetimeoffset][datetime]::SpecifyKind($Value, 'Utc')) }
    $styles = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
    [datetimeoffset]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture, $styles)
}

function Split-GLEmail {
    # alternateNotificationEmails is ONE string, semicolon-separated. Normalise for comparison.
    param([AllowNull()][object]$Value)
    @("$(@($Value) -join ';')" -split ';' | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ } | Sort-Object -Unique)
}

function Resolve-GLOperationUri {
    <# teamsAsyncOperation Location headers are relative ("/teams({id})/operations({opId})"); make them callable. #>
    param([Parameter(Mandatory)][string]$Location)
    if ($Location -match '^https?://') { return $Location }
    '/v1.0/' + $Location.TrimStart('/')
}

#endregion

#region Policy (pure) ---------------------------------------------------------------------------------------------

function Get-GroupsLifecycleConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $c = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $e = $c.expiration
    if ($e.managedGroupTypes -cnotin 'All', 'Selected', 'None') { throw "expiration.managedGroupTypes must be All, Selected or None (got '$($e.managedGroupTypes)')." }
    if ([int]$e.groupLifetimeInDays -lt $script:MinLifetimeDays) { throw "expiration.groupLifetimeInDays must be $($script:MinLifetimeDays) or more (got $($e.groupLifetimeInDays))." }
    foreach ($m in @($e.alternateNotificationEmails)) {
        if ($m -and $m -notmatch '^[^@\s;]+@[^@\s;]+\.[^@\s;]+$') { throw "Not an email address: '$m'." }
    }
    $ids = @(Get-GLProp $e 'selectedGroupIds' @())
    if ($e.managedGroupTypes -eq 'Selected') {
        if ($ids.Count -eq 0) { throw 'managedGroupTypes is Selected but selectedGroupIds is empty.' }
        if ($ids.Count -gt $script:MaxSelectedGroups) { throw "Selected supports up to $($script:MaxSelectedGroups) groups (got $($ids.Count)); use All instead." }
    }
    $c
}

function ConvertTo-GroupLifecyclePolicyBody {
    <# The groupLifecyclePolicy body. alternateNotificationEmails is a single semicolon-separated string. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Config)
    [ordered]@{
        groupLifetimeInDays         = [int]$Config.expiration.groupLifetimeInDays
        managedGroupTypes           = [string]$Config.expiration.managedGroupTypes
        alternateNotificationEmails = (@($Config.expiration.alternateNotificationEmails) | Where-Object { $_ }) -join ';'
    }
}

function Compare-GroupLifecyclePolicy {
    <# Names of the properties that differ between the tenant policy and the desired body (emails compared as a set). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Current, [Parameter(Mandatory)][System.Collections.IDictionary]$Desired)
    if ([int](Get-GLProp $Current 'groupLifetimeInDays' 0) -ne $Desired.groupLifetimeInDays) { 'groupLifetimeInDays' }
    if ([string](Get-GLProp $Current 'managedGroupTypes' '') -ne $Desired.managedGroupTypes) { 'managedGroupTypes' }
    $a = (Split-GLEmail (Get-GLProp $Current 'alternateNotificationEmails')) -join ';'
    $b = (Split-GLEmail $Desired.alternateNotificationEmails) -join ';'
    if ($a -ne $b) { 'alternateNotificationEmails' }
}

function Get-ExpirationRolloutImpact {
    <#
    .SYNOPSIS  Before switching expiration on: which groups (not yet under the policy) are older than the lifetime?
               Microsoft documents that those are set to 35 days until expiration (unless renewed or auto-renewed).
               For younger groups we only say "within lifetime": the exact date isn't documented, so we don't guess.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Groups,
        [Parameter(Mandatory)][int]$LifetimeDays,
        [Parameter(Mandatory)][datetimeoffset]$Now,
        [string[]]$OnlyGroupIds
    )
    foreach ($g in $Groups) {
        if ($OnlyGroupIds -and (Get-GLProp $g 'id') -notin $OnlyGroupIds) { continue }
        if ($null -ne (ConvertTo-GLDate (Get-GLProp $g 'expirationDateTime'))) { continue }   # already under the policy
        $created = ConvertTo-GLDate (Get-GLProp $g 'createdDateTime')
        if ($null -eq $created) { continue }
        $age = [int][math]::Floor(($Now - $created).TotalDays)
        $old = $age -ge $LifetimeDays
        [pscustomobject]@{
            Group         = Get-GLProp $g 'displayName'
            GroupId       = Get-GLProp $g 'id'
            AgeDays       = $age
            Outcome       = if ($old) { 'SetTo35Days' } else { 'WithinLifetime' }
            ExpiresAround = if ($old) { $Now.AddDays($script:FirstRolloutDays).ToString('yyyy-MM-dd') } else { $null }
        }
    }
}

function Get-GroupPurgeDate {
    <# A deleted Microsoft 365 group can be restored for 30 days; after that it's permanently deleted. #>
    param([Parameter(Mandatory)][object]$DeletedDateTime)
    (ConvertTo-GLDate $DeletedDateTime).AddDays($script:RestoreWindowDays)
}

#endregion

#region Findings (pure) -------------------------------------------------------------------------------------------

function ConvertTo-GLFinding([string]$Severity, [string]$Target, [string]$Rule, [string]$Detail) {
    [pscustomobject]@{ Severity = $Severity; Target = $Target; Rule = $Rule; Detail = $Detail }
}

function Get-GroupsLifecycleFinding {
    <#
    .SYNOPSIS  Judge an inventory (policy, groups, deleted groups) against lifecycle.json.
    .OUTPUTS   Severity (High/Medium/Low/Info), Target, Rule, Detail.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Inventory,
        [Parameter(Mandatory)][object]$Config,
        [Parameter(Mandatory)][datetimeoffset]$Now
    )
    $desired = ConvertTo-GroupLifecyclePolicyBody $Config
    $policy = Get-GLProp $Inventory 'policy'
    $mode = if ($policy) { [string](Get-GLProp $policy 'managedGroupTypes') } else { 'None' }
    $alt = @(Split-GLEmail (Get-GLProp $policy 'alternateNotificationEmails'))
    $selected = @(Get-GLProp $Config.expiration 'selectedGroupIds' @())
    $soon = [int]$Config.review.expiringWithinDays

    # Tenant policy
    if (-not $policy) {
        if ($desired.managedGroupTypes -ne 'None') { ConvertTo-GLFinding High 'Tenant' 'NoExpirationPolicy' 'No groupLifecyclePolicy: groups never expire and are never reviewed.' }
    }
    else {
        $diff = @(Compare-GroupLifecyclePolicy -Current $policy -Desired $desired)
        if ($diff.Count) { ConvertTo-GLFinding Medium 'Tenant' 'PolicyDrift' "Tenant policy differs from lifecycle.json: $($diff -join ', ')." }
        if ($mode -eq 'None') { ConvertTo-GLFinding Info 'Tenant' 'ExpirationDisabled' 'managedGroupTypes is None: no group expires.' }
    }

    foreach ($g in @(Get-GLProp $Inventory 'groups' @())) {
        $name = Get-GLProp $g 'displayName'
        $owners = [int](Get-GLProp $g 'ownerCount' 0)
        $exp = ConvertTo-GLDate (Get-GLProp $g 'expirationDateTime')
        $inScope = ($mode -eq 'All') -or ($mode -eq 'Selected' -and (Get-GLProp $g 'id') -in $selected)

        if ($null -eq $exp) {
            if ($inScope) { ConvertTo-GLFinding Medium $name 'NotCoveredByPolicy' 'In scope of the policy but has no expirationDateTime (addGroup not applied?).' }
            continue
        }
        $days = [int][math]::Floor(($exp - $Now).TotalDays)
        $when = $exp.ToString('yyyy-MM-dd')

        if ($owners -eq 0) {
            $to = if ($alt.Count) { "only to $($alt -join ', ')" } else { 'to nobody: no alternate notification email is set' }
            $team = if (Get-GLProp $g 'isTeam' $false) { ' The team also cannot be archived until it has an owner.' } else { '' }
            ConvertTo-GLFinding High $name 'OwnerlessExpiring' "No owners. Renewal mails for $when go $to.$team"
        }
        if ($days -lt 0) {
            ConvertTo-GLFinding High $name 'Expired' "Expired on $when; it is deleted one day after expiration (restorable for 30 days)."
        }
        elseif ($days -le $soon) {
            ConvertTo-GLFinding Medium $name 'ExpiringSoon' "Expires in $days days ($when) and wasn't auto-renewed (activity renews around 35 days before expiry): owners are being asked to renew."
        }
        if ($owners -eq 1) { ConvertTo-GLFinding Low $name 'SingleOwner' 'Renewal depends on one person.' }
    }

    foreach ($d in @(Get-GLProp $Inventory 'deletedGroups' @())) {
        $types = @(Get-GLProp $d 'groupTypes' @('Unified'))
        if ('Unified' -notin $types) { continue }
        $purge = Get-GroupPurgeDate (Get-GLProp $d 'deletedDateTime')
        $left = [int][math]::Floor(($purge - $Now).TotalDays)
        if ($left -lt 0) { continue }
        $name = Get-GLProp $d 'displayName'
        if ($left -le [int]$Config.review.purgeWithinDays) {
            ConvertTo-GLFinding High $name 'PurgeSoon' "Deleted; permanently deleted on $($purge.ToString('yyyy-MM-dd')) ($left days left). Restore now if it's still needed."
        }
        else {
            ConvertTo-GLFinding Info $name 'Restorable' "Deleted; restorable until $($purge.ToString('yyyy-MM-dd')) ($left days)."
        }
    }
}

function Get-GLSortedFinding {
    param([AllowEmptyCollection()][object[]]$Findings)
    $rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
    @($Findings | Sort-Object { $rank[$_.Severity] }, Target, Rule)
}

function ConvertTo-GroupsLifecycleMarkdown {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Inventory,
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings,
        [Parameter(Mandatory)][datetimeoffset]$Now
    )
    $p = Get-GLProp $Inventory 'policy'
    $md = [System.Collections.Generic.List[string]]::new()
    $md.Add('# Microsoft 365 groups lifecycle audit'); $md.Add('')
    $pol = if ($p) { "$($p.groupLifetimeInDays) days, $($p.managedGroupTypes), alternate: $(if ($p.alternateNotificationEmails) { $p.alternateNotificationEmails } else { '(none)' })" } else { 'none' }
    $groups = @(Get-GLProp $Inventory 'groups' @()); $deleted = @(Get-GLProp $Inventory 'deletedGroups' @())
    $md.Add("As of $($Now.ToString('yyyy-MM-dd HH:mm')) UTC. Tenant expiration policy: $pol. $($groups.Count) groups, $($deleted.Count) deleted, $($Findings.Count) findings."); $md.Add('')
    $md.Add('| Severity | Target | Rule | Detail |'); $md.Add('|---|---|---|---|')
    foreach ($f in (Get-GLSortedFinding $Findings)) { $md.Add("| $($f.Severity) | $($f.Target) | $($f.Rule) | $($f.Detail) |") }
    $md.Add(''); $md.Add('| Group | Team | Owners | Expires | Last renewed |'); $md.Add('|---|---|---|---|---|')
    foreach ($g in $groups) {
        $e = ConvertTo-GLDate (Get-GLProp $g 'expirationDateTime'); $r = ConvertTo-GLDate (Get-GLProp $g 'renewedDateTime')
        $md.Add("| $($g.displayName) | $(if (Get-GLProp $g 'isTeam' $false) { 'yes' } else { 'no' }) | $($g.ownerCount) | $(if ($e) { $e.ToString('yyyy-MM-dd') } else { '-' }) | $(if ($r) { $r.ToString('yyyy-MM-dd') } else { '-' }) |")
    }
    $md
}

#endregion

#region Microsoft Graph -------------------------------------------------------------------------------------------

function Invoke-GLGraphGet {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Uri, [int]$MaxPages = 200)
    $next = $Uri; $page = 0
    while ($next) {
        if (++$page -gt $MaxPages) { throw "Stopped after $MaxPages pages of $Uri" }
        $resp = Invoke-MgGraphRequest -Method GET -Uri $next -OutputType PSObject -ErrorAction Stop
        if ($null -eq $resp.PSObject.Properties['value']) { return $resp }
        foreach ($i in $resp.value) { $i }
        $next = Get-GLProp $resp '@odata.nextLink'
    }
}

function Get-GroupsLifecycleInventory {
    <#
    .SYNOPSIS  Tenant policy, every Microsoft 365 group (with owner count) and the deleted Microsoft 365 groups.
               Scopes: Directory.Read.All (policy), Group.Read.All (groups, deleted items), GroupMember.Read.All (owners).
    #>
    [CmdletBinding()]
    param()
    $policies = @(Invoke-GLGraphGet '/v1.0/groupLifecyclePolicies')
    $groups = foreach ($g in Invoke-GLGraphGet "/v1.0/groups?`$filter=groupTypes/any(c:c+eq+'Unified')&`$select=id,displayName,createdDateTime,expirationDateTime,renewedDateTime,resourceProvisioningOptions&`$top=999") {
        # No query options on /owners: the docs say they need advanced query parameters (except $expand).
        $owners = @(Invoke-GLGraphGet "/v1.0/groups/$($g.id)/owners")
        [pscustomobject]@{
            id                 = $g.id
            displayName        = $g.displayName
            createdDateTime    = Get-GLProp $g 'createdDateTime'
            expirationDateTime = Get-GLProp $g 'expirationDateTime'
            renewedDateTime    = Get-GLProp $g 'renewedDateTime'
            isTeam             = 'Team' -in @(Get-GLProp $g 'resourceProvisioningOptions' @())
            ownerCount         = $owners.Count
        }
    }
    $deleted = foreach ($d in Invoke-GLGraphGet "/v1.0/directory/deletedItems/microsoft.graph.group?`$select=id,displayName,deletedDateTime,groupTypes&`$top=999") {
        if ('Unified' -notin @(Get-GLProp $d 'groupTypes' @())) { continue }
        [pscustomobject]@{ id = $d.id; displayName = $d.displayName; deletedDateTime = Get-GLProp $d 'deletedDateTime'; groupTypes = @($d.groupTypes) }
    }
    $p = $policies | Select-Object -First 1
    [pscustomobject]@{
        collectedAt   = [datetimeoffset]::UtcNow.ToString('o')
        policy        = if ($p) { [pscustomobject]@{ id = $p.id; groupLifetimeInDays = $p.groupLifetimeInDays; managedGroupTypes = $p.managedGroupTypes; alternateNotificationEmails = $p.alternateNotificationEmails } } else { $null }
        groups        = @($groups)
        deletedGroups = @($deleted)
    }
}

function Set-GroupsExpirationPolicy {
    <#
    .SYNOPSIS  Make the tenant's single groupLifecyclePolicy match lifecycle.json: create it, or PATCH only what
               differs, then addGroup each selected group (Selected mode). Scope: Directory.ReadWrite.All.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)][object]$Config)
    $desired = ConvertTo-GroupLifecyclePolicyBody $Config
    $existing = @(Invoke-GLGraphGet '/v1.0/groupLifecyclePolicies')
    if ($existing.Count -gt 1) { throw "Expected at most one groupLifecyclePolicy, found $($existing.Count)." }

    $policyId = $null
    if ($existing.Count -eq 0) {
        $what = "Create: $($desired.groupLifetimeInDays) days, $($desired.managedGroupTypes), alternate '$($desired.alternateNotificationEmails)'"
        if ($PSCmdlet.ShouldProcess('groupLifecyclePolicies', $what)) {
            $created = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/groupLifecyclePolicies' -Body ($desired | ConvertTo-Json) `
                -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop
            $policyId = $created.id
            [pscustomobject]@{ Step = 'Policy'; Target = $policyId; Result = 'Created' }
        }
        else { [pscustomobject]@{ Step = 'Policy'; Target = 'groupLifecyclePolicies'; Result = 'WhatIf: create' } }
    }
    else {
        $policyId = $existing[0].id
        $diff = @(Compare-GroupLifecyclePolicy -Current $existing[0] -Desired $desired)
        if ($diff.Count -eq 0) { [pscustomobject]@{ Step = 'Policy'; Target = $policyId; Result = 'Unchanged' } }
        else {
            $patch = [ordered]@{}; foreach ($k in $diff) { $patch[$k] = $desired[$k] }
            if ($PSCmdlet.ShouldProcess($policyId, "Update $($diff -join ', ')")) {
                Invoke-MgGraphRequest -Method PATCH -Uri "/v1.0/groupLifecyclePolicies/$policyId" -Body ($patch | ConvertTo-Json) `
                    -ContentType 'application/json' -ErrorAction Stop | Out-Null
                [pscustomobject]@{ Step = 'Policy'; Target = $policyId; Result = "Updated: $($diff -join ', ')" }
            }
            else { [pscustomobject]@{ Step = 'Policy'; Target = $policyId; Result = "WhatIf: update $($diff -join ', ')" } }
        }
    }

    if ($desired.managedGroupTypes -ne 'Selected') { return }
    foreach ($gid in @($Config.expiration.selectedGroupIds)) {
        if (-not $policyId -or -not $PSCmdlet.ShouldProcess($gid, 'Add group to the expiration policy')) {
            [pscustomobject]@{ Step = 'AddGroup'; Target = $gid; Result = 'WhatIf' }; continue
        }
        # One group per request. 200 OK with true when added (expirationDateTime is then set), false otherwise.
        $r = Invoke-MgGraphRequest -Method POST -Uri "/v1.0/groupLifecyclePolicies/$policyId/addGroup" -Body (@{ groupId = $gid } | ConvertTo-Json) `
            -ContentType 'application/json' -OutputType PSObject -ErrorAction Stop
        $added = if ($r -is [bool]) { $r } else { [bool](Get-GLProp $r 'value' $false) }
        [pscustomobject]@{ Step = 'AddGroup'; Target = $gid; Result = if ($added) { 'Added' } else { 'NotAdded (false)' } }
    }
}

function Invoke-GroupRenewal {
    <# Renew one group (204 No Content), then read back its new dates. Scope: Group.ReadWrite.All. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string]$GroupId)
    if (-not $PSCmdlet.ShouldProcess($GroupId, 'Renew group expiration')) { return }
    Invoke-MgGraphRequest -Method POST -Uri "/v1.0/groups/$GroupId/renew" -ErrorAction Stop | Out-Null
    $g = Invoke-MgGraphRequest -Method GET -Uri "/v1.0/groups/$($GroupId)?`$select=id,displayName,expirationDateTime,renewedDateTime" -OutputType PSObject -ErrorAction Stop
    [pscustomobject]@{
        GroupId            = $GroupId
        DisplayName        = Get-GLProp $g 'displayName'
        RenewedDateTime    = Get-GLProp $g 'renewedDateTime'
        ExpirationDateTime = Get-GLProp $g 'expirationDateTime'
    }
}

function Restore-DeletedM365Group {
    <#
    .SYNOPSIS  Restore a soft-deleted Microsoft 365 group, after checking it's still inside the 30-day window.
               Scope: Group.ReadWrite.All. Contents (site, mailbox) can take up to 24 hours to come back.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string]$GroupId, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    $d = Invoke-MgGraphRequest -Method GET -Uri "/v1.0/directory/deletedItems/$GroupId" -OutputType PSObject -ErrorAction Stop
    if ((Get-GLProp $d '@odata.type') -ne '#microsoft.graph.group') { throw "$GroupId is not a deleted group ($(Get-GLProp $d '@odata.type'))." }
    if ('Unified' -notin @(Get-GLProp $d 'groupTypes' @())) { throw "$($d.displayName) is not a Microsoft 365 group." }
    $purge = Get-GroupPurgeDate (Get-GLProp $d 'deletedDateTime')
    if ($purge -le $Now) { throw "$($d.displayName) was deleted more than $($script:RestoreWindowDays) days ago." }
    if (-not $PSCmdlet.ShouldProcess($d.displayName, "Restore deleted group (permanent deletion on $($purge.ToString('yyyy-MM-dd')))")) { return }
    $r = Invoke-MgGraphRequest -Method POST -Uri "/v1.0/directory/deletedItems/$GroupId/restore" -OutputType PSObject -ErrorAction Stop
    [pscustomobject]@{ GroupId = $GroupId; DisplayName = Get-GLProp $r 'displayName'; Status = 'Restored' }
}

function Invoke-TeamArchive {
    <#
    .SYNOPSIS  End of life without deletion: archive a team (read-only), optionally making the SharePoint site
               read-only for members. The team and group must have an owner. Scope: TeamSettings.ReadWrite.All
               (+ GroupMember.Read.All for the owner check).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$TeamId,
        [switch]$SetSpoSiteReadOnlyForMembers,
        [int]$TimeoutSeconds = 300,
        [int]$PollSeconds = 10
    )
    $owners = @(Invoke-GLGraphGet "/v1.0/groups/$TeamId/owners")
    if ($owners.Count -eq 0) { throw "Team $TeamId has no owner. Archiving requires the team and group to have an owner: assign one first." }
    if (-not $PSCmdlet.ShouldProcess($TeamId, "Archive team (SharePoint read-only for members: $([bool]$SetSpoSiteReadOnlyForMembers))")) { return }

    $body = @{ shouldSetSpoSiteReadOnlyForMembers = [bool]$SetSpoSiteReadOnlyForMembers } | ConvertTo-Json
    $resp = Invoke-MgGraphRequest -Method POST -Uri "/v1.0/teams/$TeamId/archive" -Body $body -ContentType 'application/json' `
        -OutputType HttpResponseMessage -ErrorAction Stop
    if (-not $resp.IsSuccessStatusCode) { throw "Archive failed: $([int]$resp.StatusCode) $($resp.Content.ReadAsStringAsync().GetAwaiter().GetResult())" }
    if ($null -eq $resp.Headers.Location) { throw 'Archive returned no Location header.' }
    $opUri = Resolve-GLOperationUri $resp.Headers.Location.OriginalString

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $op = Invoke-MgGraphRequest -Method GET -Uri $opUri -OutputType PSObject -ErrorAction Stop
        $status = Get-GLProp $op 'status'
        if ($status -in 'succeeded', 'failed') { break }
        Start-Sleep -Seconds $PollSeconds
    } while ([datetime]::UtcNow -lt $deadline)
    if ($status -eq 'failed') { throw "Archive failed: $((Get-GLProp $op 'error') | ConvertTo-Json -Compress)" }
    [pscustomobject]@{ TeamId = $TeamId; Status = if ($status -eq 'succeeded') { 'Archived' } else { "Pending ($status)" } }
}

#endregion
