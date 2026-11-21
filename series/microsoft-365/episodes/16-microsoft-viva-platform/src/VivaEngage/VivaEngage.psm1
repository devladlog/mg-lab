<#
.SYNOPSIS
    Viva Engage communities and roles as code (Microsoft Graph v1.0) - DEVLADLOG Microsoft 365 #16.

.DESCRIPTION
    Pure functions (no network, unit-tested): Get-VivaCommunityConfig, ConvertTo-VivaCommunityBody, ConvertTo-VivaGroupRefBody,
    Get-VivaHeaderValue, Get-VivaCommunityDiff, Get-VivaFinding, ConvertTo-VivaMarkdown.
    Only Invoke-VivaRequest, Wait-VivaOperation, New-VivaCommunity, Get-VivaInventory and Set-VivaCommunity call
    Microsoft Graph (Invoke-MgGraphRequest).

    Facts from Microsoft Learn this module is built on:
    - /employeeExperience/communities works only for Viva Engage networks in native mode.
    - Create community answers 202 Accepted and an engagementAsyncOperation; poll it, waiting more than 30 seconds between checks.
    - Owners and members are managed through the community's connected Microsoft 365 group (groupId).
    - Throttling: 10 requests per user per app per 30 seconds, then 429.
    - Nothing here deletes: deleting a community deletes its group, notebook and plans.
#>

Set-StrictMode -Version Latest

$script:Limits = @{ DisplayName = 255; Description = 1024; Owners = 100 }
$script:GraphRoot = 'https://graph.microsoft.com/v1.0'

#region Helpers ---------------------------------------------------------------------------------------------------

function Get-VVProp {
    param([object]$Object, [string]$Name, [object]$Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { $Default } else { $p.Value }
}

function Get-VVHttpStatus {
    param([Parameter(Mandatory)][System.Management.Automation.ErrorRecord]$ErrorRecord)
    $e = $ErrorRecord.Exception
    $r = Get-VVProp $e 'Response'
    if ($r -and (Get-VVProp $r 'StatusCode')) { return [int](Get-VVProp $r 'StatusCode') }
    if ($e.Message -match '\b(400|403|404|409|412|429)\b') { return [int]$Matches[1] }
    $null
}

function Get-VVRetryAfter {
    <# Seconds from a Retry-After header of a failed call; 30 when the header is not available. #>
    param([Parameter(Mandatory)][System.Management.Automation.ErrorRecord]$ErrorRecord)
    # Not through Get-VVProp: a function that returns the header collection would enumerate it.
    $resp = $ErrorRecord.Exception.PSObject.Properties['Response']
    if ($resp -and $resp.Value -and $resp.Value.PSObject.Properties['Headers']) {
        $delta = $resp.Value.Headers.RetryAfter.Delta
        if ($delta) { return [int][math]::Ceiling($delta.TotalSeconds) }
    }
    30
}

function Start-VVSleep {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Only waits')]
    param([int]$Seconds)
    Start-Sleep -Seconds $Seconds
}

#endregion

#region Config (pure) ---------------------------------------------------------------------------------------------

function Get-VivaCommunityConfig {
    <# Reads communities.json and validates it against the documented limits. Throws one error listing every problem. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $raw = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $errors = [System.Collections.Generic.List[string]]::new()

    $settings = [ordered]@{
        minOwners            = [int](Get-VVProp (Get-VVProp $raw 'settings') 'minOwners' 2)
        maxNetworkAdmins     = [int](Get-VVProp (Get-VVProp $raw 'settings') 'maxNetworkAdmins' 3)
        allowedNetworkAdmins = @((Get-VVProp (Get-VVProp $raw 'settings') 'allowedNetworkAdmins' @()) | ForEach-Object { "$_".ToLowerInvariant() })
    }
    if ($settings.minOwners -lt 1) { $errors.Add('settings.minOwners must be at least 1.') }

    $list = @(Get-VVProp $raw 'communities' @())
    if ($list.Count -eq 0) { $errors.Add('communities: at least one community is required.') }

    $seen = @{}
    $out = foreach ($c in $list) {
        $name = [string](Get-VVProp $c 'displayName' '')
        $label = if ($name) { "'$name'" } else { '(no name)' }
        if (-not $name.Trim()) { $errors.Add('A community has no displayName.') }
        elseif ($name.Length -gt $script:Limits.DisplayName) { $errors.Add("${label}: displayName is longer than $($script:Limits.DisplayName) characters.") }
        if ($seen.ContainsKey($name.ToLowerInvariant())) { $errors.Add("${label}: duplicate displayName (the name is the match key).") }
        $seen[$name.ToLowerInvariant()] = $true

        $desc = [string](Get-VVProp $c 'description' '')
        if ($desc.Length -gt $script:Limits.Description) { $errors.Add("${label}: description is longer than $($script:Limits.Description) characters.") }

        $privacy = ([string](Get-VVProp $c 'privacy' 'private')).ToLowerInvariant()
        if ($privacy -notin 'public', 'private') { $errors.Add("${label}: privacy must be 'public' or 'private', not '$privacy'.") }

        $owners = @((Get-VVProp $c 'owners' @()) | ForEach-Object { "$_".Trim().ToLowerInvariant() } | Where-Object { $_ })
        $members = @((Get-VVProp $c 'members' @()) | ForEach-Object { "$_".Trim().ToLowerInvariant() } | Where-Object { $_ })
        foreach ($u in $owners + $members) { if ($u -notmatch '^[^@\s]+@[^@\s]+$') { $errors.Add("${label}: '$u' is not a user principal name.") } }
        if ($owners.Count -lt $settings.minOwners) { $errors.Add("${label}: $($owners.Count) owner(s) listed but settings.minOwners is $($settings.minOwners).") }
        if ($owners.Count -gt $script:Limits.Owners) { $errors.Add("${label}: more than $($script:Limits.Owners) owners (the owners relationship is limited to $($script:Limits.Owners)).") }
        if (@($owners | Select-Object -Unique).Count -ne $owners.Count) { $errors.Add("${label}: an owner is listed twice.") }

        [pscustomobject]@{
            displayName = $name.Trim(); description = $desc; privacy = $privacy
            owners = $owners; members = @($members | Where-Object { $_ -notin $owners })
        }
    }
    if ($errors.Count) { throw ("communities.json is not valid:`n - " + ($errors -join "`n - ")) }
    [pscustomobject]@{ settings = [pscustomobject]$settings; communities = @($out) }
}

#endregion

#region Request bodies and headers (pure) -------------------------------------------------------------------------

function ConvertTo-VivaCommunityBody {
    <#
        Body of POST /employeeExperience/communities. With delegated permissions the caller becomes the owner; with
        application permissions Learn says owners must be supplied: pass -OwnerIds and -AsApplication.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Community,
        [string[]]$OwnerIds = @(),
        [switch]$AsApplication
    )
    $body = [ordered]@{
        displayName = $Community.displayName
        description = $Community.description
        privacy     = $Community.privacy
    }
    if ($AsApplication) {
        if ($OwnerIds.Count -eq 0) { throw 'Application permissions: at least one owner id is required (owners@odata.bind).' }
        $body['owners@odata.bind'] = @($OwnerIds | ForEach-Object { "$script:GraphRoot/users/$_" })
    }
    $body
}

function ConvertTo-VivaGroupRefBody {
    <# Body of POST /groups/{id}/members/$ref and /owners/$ref. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$UserId)
    [ordered]@{ '@odata.id' = "$script:GraphRoot/directoryObjects/$UserId" }
}

function Get-VivaHeaderValue {
    <# Case-insensitive lookup in the response headers of Invoke-MgGraphRequest (values are string arrays). #>
    [CmdletBinding()]
    param([AllowNull()][object]$Headers, [Parameter(Mandatory)][string[]]$Name)
    if ($null -eq $Headers) { return $null }
    foreach ($wanted in $Name) {
        foreach ($k in @($Headers.Keys)) {
            if ("$k" -ieq $wanted) {
                $v = $Headers[$k]
                if ($v -is [System.Collections.IEnumerable] -and $v -isnot [string]) { $v = @($v)[0] }
                if ($v) { return [string]$v }
            }
        }
    }
    $null
}

#endregion

#region Diff (pure) -----------------------------------------------------------------------------------------------

function Get-VivaCommunityDiff {
    <#
        Config against an inventory. Returns one row per action:
        Create, Update (description/privacy drift), AddOwner, AddMember, Unmanaged (info), InSync.
        It never returns a delete: this module only adds.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Config, [Parameter(Mandatory)][object]$Inventory)

    $existing = @{}
    foreach ($c in @(Get-VVProp $Inventory 'communities' @())) { $existing[([string]$c.displayName).ToLowerInvariant()] = $c }
    $wantedNames = @{}

    $rows = [System.Collections.Generic.List[object]]::new()
    $add = { param($a, $n, $d, $f) $rows.Add([pscustomobject]@{ Action = $a; Community = $n; Detail = $d; Field = $f }) }

    foreach ($c in $Config.communities) {
        $key = $c.displayName.ToLowerInvariant()
        $wantedNames[$key] = $true
        $have = $existing[$key]
        $haveOwners = @(); $haveMembers = @()
        if ($null -eq $have) {
            & $add 'Create' $c.displayName "privacy $($c.privacy)" 'create'
        }
        else {
            $haveOwners = @(@(Get-VVProp $have 'owners' @()) | ForEach-Object { "$_".ToLowerInvariant() })
            $haveMembers = @(@(Get-VVProp $have 'members' @()) | ForEach-Object { "$_".ToLowerInvariant() })
            if (([string](Get-VVProp $have 'privacy' '')).ToLowerInvariant() -ne $c.privacy) {
                & $add 'Update' $c.displayName "privacy is $(Get-VVProp $have 'privacy'), config says $($c.privacy)" 'privacy'
            }
            if ([string](Get-VVProp $have 'description' '') -ne $c.description) {
                & $add 'Update' $c.displayName 'description differs from the config' 'description'
            }
        }
        $before = $rows.Count
        foreach ($u in $c.owners) { if ($u -notin $haveOwners) { & $add 'AddOwner' $c.displayName $u 'owner' } }
        foreach ($u in ($c.owners + $c.members)) { if ($u -notin $haveMembers) { & $add 'AddMember' $c.displayName $u 'member' } }
        if ($null -ne $have -and $rows.Count -eq $before -and -not (@($rows | Where-Object { $_.Community -eq $c.displayName -and $_.Action -eq 'Update' }).Count)) {
            & $add 'InSync' $c.displayName 'nothing to do' ''
        }
    }
    foreach ($k in $existing.Keys) {
        if (-not $wantedNames.ContainsKey($k)) { & $add 'Unmanaged' $existing[$k].displayName 'in the tenant, not in the config (left alone)' '' }
    }
    $rows.ToArray()
}

#endregion

#region Audit (pure) ----------------------------------------------------------------------------------------------

function Get-VivaFinding {
    <#
        Findings over an inventory (communities + role members) and the config settings.
        Severity High/Medium/Low/Info; rule names are stable so a pipeline can filter on them.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Inventory, [Parameter(Mandatory)][object]$Config)

    $out = [System.Collections.Generic.List[object]]::new()
    $f = { param($s, $sub, $rule, $d) $out.Add([pscustomobject]@{ Severity = $s; Subject = $sub; Rule = $rule; Detail = $d }) }
    $communities = @(Get-VVProp $Inventory 'communities' @())
    $configured = @{}
    foreach ($c in $Config.communities) { $configured[$c.displayName.ToLowerInvariant()] = $c }

    $names = @{}
    foreach ($c in $communities) {
        $name = [string]$c.displayName
        $names[$name.ToLowerInvariant()] = 1 + [int]($names[$name.ToLowerInvariant()])
        $owners = @(@(Get-VVProp $c 'owners' @()) | Where-Object { $_ })
        $members = @(@(Get-VVProp $c 'members' @()) | Where-Object { $_ })
        if ($owners.Count -eq 0) {
            & $f 'High' $name 'NoOwner' 'No owner. Nobody can manage this community, and requests for help have nowhere to go.'
        }
        elseif ($owners.Count -lt $Config.settings.minOwners) {
            & $f 'Medium' $name 'FewOwners' "$($owners.Count) owner(s), policy asks for $($Config.settings.minOwners)."
        }
        if ($owners.Count -gt 0 -and @($members | Where-Object { $_ -notin $owners }).Count -eq 0) {
            & $f 'Low' $name 'NoMembers' 'Only owners are members.'
        }
        $cfg = $configured[$name.ToLowerInvariant()]
        if ($null -eq $cfg) {
            & $f 'Info' $name 'NotInConfig' 'Not described in communities.json. The script leaves it alone.'
        }
        elseif (([string]$c.privacy).ToLowerInvariant() -ne $cfg.privacy) {
            & $f 'Medium' $name 'PrivacyDrift' "Privacy is $($c.privacy), config says $($cfg.privacy)."
        }
    }
    foreach ($k in $names.Keys) {
        if ($names[$k] -gt 1) { & $f 'Low' $k 'DuplicateName' "$($names[$k]) communities share this name; the script cannot match them safely." }
    }
    foreach ($k in $configured.Keys) {
        if (-not $names.ContainsKey($k)) { & $f 'Medium' $configured[$k].displayName 'MissingCommunity' 'In the config, not in the tenant. Run -Apply.' }
    }

    $admins = @()
    foreach ($r in @(Get-VVProp $Inventory 'roles' @())) {
        if (([string]$r.name) -match 'Network Admin') { $admins += @(@(Get-VVProp $r 'members' @()) | ForEach-Object { [string](Get-VVProp $_ 'upn' (Get-VVProp $_ 'userId' '')) }) }
    }
    $admins = @($admins | Where-Object { $_ } | Select-Object -Unique)
    if ($admins.Count -gt $Config.settings.maxNetworkAdmins) {
        & $f 'Medium' 'Network Administrator' 'TooManyNetworkAdmins' "$($admins.Count) Network Administrators, policy allows $($Config.settings.maxNetworkAdmins)."
    }
    $allowed = @($Config.settings.allowedNetworkAdmins)
    if ($allowed.Count -gt 0) {
        foreach ($a in $admins) {
            if ($a.ToLowerInvariant() -notin $allowed) { & $f 'High' $a 'UnexpectedNetworkAdmin' 'Network Administrator who is not in settings.allowedNetworkAdmins.' }
        }
    }
    $rank = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
    @($out | Sort-Object { $rank[$_.Severity] }, Subject, Rule)
}

function ConvertTo-VivaMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Finding, [Parameter(Mandatory)][object]$Inventory, [string]$Title = 'Viva Engage audit')
    $nl = "`n"
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.Append("# $Title$nl$nl")
    $communities = @(Get-VVProp $Inventory 'communities' @())
    $null = $sb.Append("Generated: $(Get-VVProp $Inventory 'generatedAt' 'n/a') | communities: $($communities.Count)$nl$nl")
    $counts = @('High', 'Medium', 'Low', 'Info') | ForEach-Object { $s = $_; "$s $(@($Finding | Where-Object { $_.Severity -eq $s }).Count)" }
    $null = $sb.Append("**Findings:** $($counts -join ' | ')$nl$nl")
    if ($Finding.Count -eq 0) { $null = $sb.Append("No findings.$nl$nl") }
    else {
        $null = $sb.Append("| Severity | Subject | Rule | Detail |$nl|---|---|---|---|$nl")
        foreach ($x in $Finding) { $null = $sb.Append("| $($x.Severity) | $($x.Subject) | $($x.Rule) | $(([string]$x.Detail) -replace '\|', '/') |$nl") }
        $null = $sb.Append($nl)
    }
    $null = $sb.Append("## Communities$nl$nl| Name | Privacy | Owners | Members |$nl|---|---|---|---|$nl")
    foreach ($c in $communities) {
        $null = $sb.Append("| $($c.displayName) | $($c.privacy) | $(@(Get-VVProp $c 'owners' @()).Count) | $(@(Get-VVProp $c 'members' @()).Count) |$nl")
    }
    $roles = @(Get-VVProp $Inventory 'roles' @())
    if ($roles.Count) {
        $null = $sb.Append("$nl## Viva Engage roles$nl$nl| Role | Members |$nl|---|---|$nl")
        foreach ($r in $roles) { $null = $sb.Append("| $($r.name) | $(@(Get-VVProp $r 'members' @()).Count) |$nl") }
    }
    $sb.ToString()
}

#endregion

#region Graph callers ---------------------------------------------------------------------------------------------

function Invoke-VivaRequest {
    <#
        One Graph call with 429 handling: wait for Retry-After (30 s when the header is missing) and try again.
        Learn: 10 requests per user per app per 30 seconds for Viva Engage. With -WithHeaders returns
        @{ Body; Headers } so the caller can read Operation-Location.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [object]$Body,
        [hashtable]$Headers,
        [switch]$WithHeaders,
        [int]$MaxRetries = 3
    )
    $attempt = 0
    while ($true) {
        $rh = $null
        $splat = @{ Method = $Method; Uri = $Uri; OutputType = 'PSObject'; ErrorAction = 'Stop' }
        if ($PSBoundParameters.ContainsKey('Body')) { $splat.Body = ($Body | ConvertTo-Json -Depth 8); $splat.ContentType = 'application/json' }
        if ($Headers) { $splat.Headers = $Headers }
        if ($WithHeaders) { $splat.ResponseHeadersVariable = 'rh' }
        try {
            $result = Invoke-MgGraphRequest @splat
            if ($WithHeaders) { return [pscustomobject]@{ Body = $result; Headers = $rh } }
            return $result
        }
        catch {
            $code = Get-VVHttpStatus $_
            if ($code -eq 429 -and $attempt -lt $MaxRetries) {
                $attempt++
                $wait = Get-VVRetryAfter $_
                Write-Verbose "429 on $Method $Uri. Waiting $wait s (retry $attempt of $MaxRetries)."
                Start-VVSleep -Seconds $wait
                continue
            }
            throw
        }
    }
}

function Invoke-VivaGet {
    <# GET with @odata.nextLink paging; returns the items. A collection is recognised by its value property. #>
    param([Parameter(Mandatory)][string]$Uri)
    $items = [System.Collections.Generic.List[object]]::new()
    $next = $Uri
    while ($next) {
        $r = Invoke-VivaRequest -Method GET -Uri $next
        $isCollection = if ($r -is [System.Collections.IDictionary]) { $r.Contains('value') } else { $null -ne $r.PSObject.Properties['value'] }
        if ($isCollection) { foreach ($v in @(Get-VVProp $r 'value')) { $items.Add($v) } } else { $items.Add($r) }
        $next = Get-VVProp $r '@odata.nextLink'
    }
    $items.ToArray()
}

function Wait-VivaOperation {
    <#
        Polls an engagementAsyncOperation until status is succeeded or failed. Learn: wait more than 30 seconds between checks.
        Returns the operation (resourceId = the new community id).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$OperationUri,
        [ValidateRange(31, 600)][int]$IntervalSeconds = 31,
        [int]$MaxChecks = 20
    )
    for ($i = 1; $i -le $MaxChecks; $i++) {
        $op = Invoke-VivaRequest -Method GET -Uri $OperationUri
        $status = [string](Get-VVProp $op 'status' '')
        switch ($status) {
            'succeeded' { return $op }
            'failed' { throw "Viva Engage operation failed: $(Get-VVProp $op 'statusDetail' '(no detail)')" }
        }
        Write-Verbose "Operation is '$status' (check $i of $MaxChecks)."
        Start-VVSleep -Seconds $IntervalSeconds
    }
    throw "Viva Engage operation still not finished after $MaxChecks checks ($OperationUri)."
}

function New-VivaCommunity {
    <# POST the community, follow the async operation, return the community (with groupId). Delegated: the caller becomes owner. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][object]$Community, [int]$IntervalSeconds = 31)
    if (-not $PSCmdlet.ShouldProcess($Community.displayName, 'Create Viva Engage community')) { return $null }
    $resp = Invoke-VivaRequest -Method POST -Uri '/v1.0/employeeExperience/communities' -Body (ConvertTo-VivaCommunityBody -Community $Community) -WithHeaders
    # Learn's text says Operation-Location, its example shows Location: accept both.
    $loc = Get-VivaHeaderValue -Headers $resp.Headers -Name 'Operation-Location', 'Location'
    if (-not $loc) { throw 'Create community: 202 without Operation-Location or Location header, cannot follow the operation.' }
    $op = Wait-VivaOperation -OperationUri $loc -IntervalSeconds $IntervalSeconds
    $id = [string](Get-VVProp $op 'resourceId' '')
    if (-not $id) { throw 'The operation succeeded but has no resourceId.' }
    Invoke-VivaRequest -Method GET -Uri "/v1.0/employeeExperience/communities/${id}?`$select=id,displayName,description,privacy,groupId"
}

function Get-VVGroupUser {
    param([string]$GroupId, [ValidateSet('owners', 'members')][string]$Kind)
    $u = @(Invoke-VivaGet "/v1.0/groups/$GroupId/${Kind}?`$select=id,userPrincipalName&`$top=999")
    @($u | Where-Object { Get-VVProp $_ 'userPrincipalName' } | ForEach-Object { ([string]$_.userPrincipalName).ToLowerInvariant() })
}

function Get-VivaInventory {
    <# Communities (with owners/members from the connected group) and the Viva Engage role members. Read-only. #>
    [CmdletBinding()]
    param([switch]$SkipRoles, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    $list = @(Invoke-VivaGet '/v1.0/employeeExperience/communities?$select=id,displayName,description,privacy,groupId&$top=20')
    $communities = foreach ($c in $list) {
        $owners = @(); $members = @()
        if ($c.groupId) { $owners = @(Get-VVGroupUser $c.groupId 'owners'); $members = @(Get-VVGroupUser $c.groupId 'members') }
        [ordered]@{
            id = $c.id; displayName = $c.displayName; description = Get-VVProp $c 'description' ''; privacy = $c.privacy
            groupId = Get-VVProp $c 'groupId'; owners = $owners; members = $members
        }
    }
    $roles = @()
    if (-not $SkipRoles) {
        $cache = @{}
        $roles = foreach ($r in @(Invoke-VivaGet '/v1.0/employeeExperience/roles?$select=id,displayName')) {
            $members = foreach ($m in @(Invoke-VivaGet "/v1.0/employeeExperience/roles/$($r.id)/members")) {
                $uid = [string](Get-VVProp $m 'userId' '')
                if ($uid -and -not $cache.ContainsKey($uid)) {
                    $u = Invoke-VivaRequest -Method GET -Uri "/v1.0/users/${uid}?`$select=id,userPrincipalName"
                    $cache[$uid] = ([string]$u.userPrincipalName).ToLowerInvariant()
                }
                [ordered]@{ userId = $uid; upn = $cache[$uid] }
            }
            [ordered]@{ id = $r.id; name = $r.displayName; members = @($members) }
        }
    }
    [ordered]@{ generatedAt = $Now.UtcDateTime.ToString('yyyy-MM-dd HH:mm') + ' UTC'; communities = @($communities); roles = @($roles) }
}

function Set-VivaCommunity {
    <#
        Applies the config: creates missing communities, adds missing owners and members, and (only with -FixDrift) patches
        description/privacy. Never removes anything. Honours -WhatIf. Returns one row per step.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][object]$Config, [switch]$FixDrift, [int]$IntervalSeconds = 31)

    $inventory = Get-VivaInventory -SkipRoles
    $plan = @(Get-VivaCommunityDiff -Config $Config -Inventory $inventory)
    $byName = @{}; foreach ($c in $inventory.communities) { $byName[([string]$c.displayName).ToLowerInvariant()] = $c }
    $cfgByName = @{}; foreach ($c in $Config.communities) { $cfgByName[$c.displayName.ToLowerInvariant()] = $c }
    $userIds = @{}
    $groupUsers = @{}   # groupId -> @{ owners; members } as known now (refreshed after create)
    $result = [System.Collections.Generic.List[object]]::new()
    $row = { param($s, $t, $r) $result.Add([pscustomobject]@{ Step = $s; Target = $t; Result = $r }) }

    foreach ($step in $plan) {
        $key = $step.Community.ToLowerInvariant()
        switch ($step.Action) {
            'InSync' { & $row 'InSync' $step.Community 'nothing to do' }
            'Unmanaged' { & $row 'Unmanaged' $step.Community 'left alone' }
            'Create' {
                if (-not $PSCmdlet.ShouldProcess($step.Community, 'Create Viva Engage community')) { & $row 'CreateCommunity' $step.Community 'WhatIf'; continue }
                $made = New-VivaCommunity -Community $cfgByName[$key] -IntervalSeconds $IntervalSeconds -Confirm:$false
                $byName[$key] = [ordered]@{ id = $made.id; groupId = $made.groupId }
                $groupUsers[$made.groupId] = @{ owners = @(Get-VVGroupUser $made.groupId 'owners'); members = @(Get-VVGroupUser $made.groupId 'members') }
                & $row 'CreateCommunity' $step.Community "Created ($($made.id))"
            }
            'Update' {
                if (-not $FixDrift) { & $row "Drift:$($step.Field)" $step.Community "$($step.Detail) (report only, use -FixDrift)"; continue }
                $c = $byName[$key]
                if ($PSCmdlet.ShouldProcess($step.Community, "Update $($step.Field)")) {
                    $patch = @{ $step.Field = $cfgByName[$key].($step.Field) }
                    $null = Invoke-VivaRequest -Method PATCH -Uri "/v1.0/employeeExperience/communities/$($c.id)" -Body $patch
                    & $row "Update:$($step.Field)" $step.Community 'Updated'
                }
                else { & $row "Update:$($step.Field)" $step.Community 'WhatIf' }
            }
            { $_ -in 'AddOwner', 'AddMember' } {
                $kind = if ($step.Action -eq 'AddOwner') { 'owners' } else { 'members' }
                $label = "$($step.Community): $($step.Detail)"
                $c = $byName[$key]
                $gid = Get-VVProp $c 'groupId'
                if (-not $gid) {
                    if ($WhatIfPreference) { & $row $step.Action $label 'WhatIf (community is created first)'; continue }
                    throw "No groupId for '$($step.Community)'."
                }
                if (-not $groupUsers.ContainsKey($gid)) { $groupUsers[$gid] = @{ owners = @(Get-VVProp $c 'owners' @()); members = @(Get-VVProp $c 'members' @()) } }
                if ($step.Detail -in $groupUsers[$gid][$kind]) { & $row $step.Action $label 'Already there (the creator is owner)'; continue }
                if (-not $PSCmdlet.ShouldProcess($label, "Add to group $kind")) { & $row $step.Action $label 'WhatIf'; continue }
                if (-not $userIds.ContainsKey($step.Detail)) {
                    $u = Invoke-VivaRequest -Method GET -Uri "/v1.0/users/$([uri]::EscapeDataString($step.Detail))?`$select=id"
                    $userIds[$step.Detail] = $u.id
                }
                $null = Invoke-VivaRequest -Method POST -Uri "/v1.0/groups/$gid/$kind/`$ref" -Body (ConvertTo-VivaGroupRefBody -UserId $userIds[$step.Detail])
                $groupUsers[$gid][$kind] = @($groupUsers[$gid][$kind]) + $step.Detail
                & $row $step.Action $label 'Added'
            }
        }
    }
    $result.ToArray()
}

#endregion

Export-ModuleMember -Function Get-VivaCommunityConfig, ConvertTo-VivaCommunityBody, ConvertTo-VivaGroupRefBody, Get-VivaHeaderValue,
Get-VivaCommunityDiff, Get-VivaFinding, ConvertTo-VivaMarkdown, Invoke-VivaRequest, Wait-VivaOperation, New-VivaCommunity,
Get-VivaInventory, Set-VivaCommunity
