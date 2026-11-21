#Requires -Version 7.2
<#
    TeamsGovernance: Teams governance as code, driven by one policy file (governance.json).

      * Naming   - Resolve-TeamName / Test-TeamsBlockedWord / Test-TeamNameCompliance mirror the Entra ID
                   group naming policy (prefix-suffix with user attributes, blocked words, 63 characters).
      * Create   - New-TeamsCreateRequest + New-GovernedTeam: private by default, minimum owners, POST /teams,
                   wait for the async operation.
      * Audit    - Get-TeamsInventory + Get-TeamsGovernanceFinding: owners, guests, naming, inactivity.
      * Tenant   - Set-TeamsDirectoryPolicy: pushes the same naming policy and the group creation restriction to
                   the Group.Unified directory setting, so the service enforces what the script previews.

    Only Invoke-TeamsGraph* and the three "talk to Graph" functions call Microsoft Graph (Invoke-MgGraphRequest).
#>

Set-StrictMode -Version Latest

$script:GroupUnifiedTemplateId = '62375ab9-6b52-47ed-826b-58e47e0e304b'
$script:NamingAttributes = 'Department', 'Company', 'Office', 'StateOrProvince', 'CountryOrRegion', 'Title'
$script:MaxNameLength = 63    # prefix + group name + suffix, per the Entra ID naming policy

#region Helpers ---------------------------------------------------------------------------------------------------

function Get-TGProp {
    param([object]$Object, [string]$Name, [object]$Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { $Default } else { $p.Value }
}

function ConvertTo-TGDate {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value -or "$Value" -eq '') { return $null }
    if ($Value -is [datetimeoffset]) { return $Value.ToUniversalTime() }
    if ($Value -is [datetime]) { return ([datetimeoffset][datetime]::SpecifyKind($Value, 'Utc')) }
    $styles = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
    [datetimeoffset]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture, $styles)
}

#endregion

#region Policy and naming (pure) ----------------------------------------------------------------------------------

function Get-TeamsGovernancePolicy {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $p = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $pattern = $p.naming.prefixSuffix
    $count = ([regex]::Matches($pattern, '\[GroupName\]')).Count
    if ($count -ne 1) { throw "naming.prefixSuffix must contain [GroupName] exactly once (found $count)." }
    if ([int]$p.owners.minimum -lt 1) { throw 'owners.minimum must be at least 1.' }
    if ($p.visibility.default -notin 'private', 'public') { throw 'visibility.default must be private or public.' }
    $p
}

function Test-TeamsBlockedWord {
    <#
    .SYNOPSIS  Blocked words that appear in a name. Case-insensitive, whole words only: like the service, no
               substring search, so "Class" is fine even when "lass" is blocked.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyString()][string]$Name,
        [AllowEmptyCollection()][string[]]$BlockedWords = @()
    )
    foreach ($w in $BlockedWords) {
        if ([string]::IsNullOrWhiteSpace($w)) { continue }
        $rx = '(?<![\p{L}\p{N}])' + [regex]::Escape($w.Trim()) + '(?![\p{L}\p{N}])'
        if ([regex]::IsMatch($Name, $rx, 'IgnoreCase')) { $w.Trim() }
    }
}

function Resolve-TeamName {
    <#
    .SYNOPSIS  Applies the prefix-suffix convention for a creator and validates the result.
    .OUTPUTS   DisplayName, MailNickname, Errors (empty when the name is valid).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$RequestedName,
        [Parameter(Mandatory)][object]$Creator,     # user attributes: Department, Company, Office, ...
        [Parameter(Mandatory)][object]$Policy
    )
    $errors = [System.Collections.Generic.List[string]]::new()
    $name = $Policy.naming.prefixSuffix
    foreach ($attr in $script:NamingAttributes) {
        $token = "[$attr]"
        if (-not $name.Contains($token)) { continue }
        $value = [string](Get-TGProp $Creator $attr '')
        if ([string]::IsNullOrWhiteSpace($value)) { $errors.Add("MissingAttribute:$attr") }
        $name = $name.Replace($token, $value.Trim())
    }
    # Unsupported tokens such as [postalCode] stay as fixed text, like the service does.
    $name = $name.Replace('[GroupName]', $RequestedName.Trim())

    foreach ($w in Test-TeamsBlockedWord -Name $RequestedName -BlockedWords @($Policy.naming.blockedWords)) { $errors.Add("BlockedWord:$w") }
    if ($name.Length -gt $script:MaxNameLength) { $errors.Add("TooLong:$($name.Length)") }

    [pscustomobject]@{
        DisplayName  = $name
        MailNickname = ($name -replace '[^A-Za-z0-9._-]', '')
        Errors       = @($errors)
    }
}

function Test-TeamNameCompliance {
    <# True when an existing name matches the convention (any attribute value, any group name). #>
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][object]$Policy)
    $rx = [regex]::Escape($Policy.naming.prefixSuffix)
    foreach ($attr in $script:NamingAttributes + 'GroupName') { $rx = $rx.Replace([regex]::Escape("[$attr]"), '.+') }
    [regex]::IsMatch($Name, "^$rx$", 'IgnoreCase')
}

function New-TeamsCreateRequest {
    <# Body for POST /teams (standard template). Private unless the caller says otherwise: the API default is Public. #>
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Builds a request body only')]
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$DisplayName,
        [string]$Description = '',
        [ValidateSet('private', 'public')][string]$Visibility,
        [Parameter(Mandatory)][string[]]$OwnerIds,
        [Parameter(Mandatory)][object]$Policy
    )
    $owners = @($OwnerIds | Where-Object { $_ } | Select-Object -Unique)
    $min = [int]$Policy.owners.minimum
    if ($owners.Count -lt $min) { throw "Policy requires at least $min owners; got $($owners.Count)." }
    if (-not $Visibility) { $Visibility = $Policy.visibility.default }
    [ordered]@{
        'template@odata.bind' = "https://graph.microsoft.com/v1.0/teamsTemplates('standard')"
        displayName           = $DisplayName
        description           = $Description
        visibility            = $Visibility
        members               = @(foreach ($id in $owners) {
                [ordered]@{
                    '@odata.type'     = '#microsoft.graph.aadUserConversationMember'
                    roles             = @('owner')
                    'user@odata.bind' = "https://graph.microsoft.com/v1.0/users('$id')"
                }
            })
    }
}

function Resolve-TeamsOperationUri {
    <# The Location header of POST /teams is relative ("/teams('..')/operations('..')"); make it callable. #>
    param([Parameter(Mandatory)][string]$Location)
    if ($Location -match '^https?://') { return $Location }
    '/v1.0/' + $Location.TrimStart('/')
}

function Merge-GroupSettingValue {
    <# Overlay desired name/value pairs on the current ones (or on template defaults), keeping everything else. #>
    param(
        [AllowEmptyCollection()][object[]]$Current = @(),
        [Parameter(Mandatory)][System.Collections.IDictionary]$Desired
    )
    $result = [ordered]@{}
    foreach ($v in $Current) {
        $n = Get-TGProp $v 'name'
        $result[$n] = if ($null -ne (Get-TGProp $v 'value')) { [string](Get-TGProp $v 'value') } else { [string](Get-TGProp $v 'defaultValue' '') }
    }
    foreach ($k in $Desired.Keys) { $result[$k] = [string]$Desired[$k] }
    @(foreach ($k in $result.Keys) { [ordered]@{ name = $k; value = $result[$k] } })
}

function Get-TeamsDirectoryPolicyValue {
    <# The Group.Unified values that implement governance.json. #>
    param([Parameter(Mandatory)][object]$Policy)
    $v = [ordered]@{
        PrefixSuffixNamingRequirement = $Policy.naming.prefixSuffix
        CustomBlockedWordsList        = (@($Policy.naming.blockedWords) -join ',')
    }
    if ($Policy.creation.restrict) {
        $v.EnableGroupCreation = 'false'
        $v.GroupCreationAllowedGroupId = $Policy.creation.allowedGroupId
    }
    else {
        $v.EnableGroupCreation = 'true'
        $v.GroupCreationAllowedGroupId = ''
    }
    $v
}

function Get-TeamsGovernanceFinding {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Inventory,
        [Parameter(Mandatory)][object]$Policy
    )
    $min = [int]$Policy.owners.minimum
    $inactiveDays = [int]$Policy.lifecycle.inactiveDays
    $joined = @($Inventory | Where-Object { $_.ActivityKnown })
    if ($Inventory.Count -and $joined.Count -eq 0) {
        [pscustomobject]@{ Team = '(all)'; Severity = 'Info'; Rule = 'ActivityUnavailable'; Detail = 'No activity rows matched team IDs: report concealed or not collected; inactivity not evaluated.' }
    }
    foreach ($t in $Inventory) {
        $f = { param($sev, $rule, $detail) [pscustomobject]@{ Team = $t.DisplayName; Severity = $sev; Rule = $rule; Detail = $detail } }
        if ($t.Owners -eq 0)          { & $f 'High' 'Ownerless' 'No owners: nobody can manage members or settings.' }
        elseif ($t.Owners -lt $min)   { & $f 'Medium' 'TooFewOwners' "$($t.Owners) owner(s); policy minimum is $min." }
        if ($t.Visibility -eq 'public' -and $t.Guests -gt 0 -and -not $Policy.guests.allowInPublicTeams) {
            & $f 'High' 'GuestsInPublicTeam' "$($t.Guests) guest(s) in a public team."
        }
        if (-not (Test-TeamNameCompliance -Name $t.DisplayName -Policy $Policy)) {
            & $f 'Low' 'NamingConvention' "Does not match $($Policy.naming.prefixSuffix)."
        }
        if ($joined.Count -and $t.ActivityKnown) {
            if ($null -eq $t.DaysInactive -or $t.DaysInactive -ge $inactiveDays) {
                $d = if ($null -eq $t.DaysInactive) { 'No activity in the report period.' } else { "Inactive for $($t.DaysInactive) days." }
                & $f 'Low' 'Inactive' "$d Review or archive."
            }
        }
    }
}

function Join-TeamsActivity {
    <# Adds LastActivity / DaysInactive from the getTeamsTeamActivityDetail rows (joined on Team Id). #>
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Teams,
        [AllowEmptyCollection()][object[]]$ActivityRows = @()
    )
    $byId = @{}
    foreach ($r in $ActivityRows) { $id = Get-TGProp $r 'Team Id'; if ($id) { $byId[$id.ToLowerInvariant()] = $r } }
    foreach ($t in $Teams) {
        $row = $byId[[string]$t.TeamId.ToLowerInvariant()]
        $last = if ($row) { ConvertTo-TGDate (Get-TGProp $row 'Last Activity Date') } else { $null }
        $asOf = if ($row) { ConvertTo-TGDate (Get-TGProp $row 'Report Refresh Date') } else { $null }
        $t | Add-Member -NotePropertyName ActivityKnown -NotePropertyValue ([bool]$row) -Force
        $t | Add-Member -NotePropertyName LastActivity -NotePropertyValue $last -Force
        $t | Add-Member -NotePropertyName DaysInactive -NotePropertyValue $(if ($last -and $asOf) { [int][math]::Floor(($asOf - $last).TotalDays) } else { $null }) -Force
        $t
    }
}

#endregion

#region Talks to Graph ---------------------------------------------------------------------------------------------

function Invoke-TeamsGraphGet {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Uri, [int]$MaxPages = 200)
    $next = $Uri; $page = 0
    while ($next) {
        if (++$page -gt $MaxPages) { throw "Stopped after $MaxPages pages of $Uri" }
        $resp = Invoke-MgGraphRequest -Method GET -Uri $next -OutputType PSObject -ErrorAction Stop
        if ($null -eq $resp.PSObject.Properties['value']) { return $resp }
        foreach ($i in $resp.value) { $i }
        $next = Get-TGProp $resp '@odata.nextLink'
    }
}

function Get-TeamsActivityReport {
    [CmdletBinding()]
    param([ValidateSet('D7', 'D30', 'D90', 'D180')][string]$Period = 'D180')
    $tmp = [IO.Path]::GetTempFileName()
    try {
        Invoke-MgGraphRequest -Method GET -Uri "/v1.0/reports/getTeamsTeamActivityDetail(period='$Period')" -OutputFilePath $tmp -ErrorAction Stop
        Import-Csv -LiteralPath $tmp
    }
    finally { Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue }
}

function Get-TeamsInventory {
    <# Every team with owner, member and guest counts (roles on conversationMember) plus last activity. #>
    [CmdletBinding()]
    param([ValidateSet('D7', 'D30', 'D90', 'D180')][string]$Period = 'D180', [switch]$SkipActivity)
    $teams = foreach ($team in Invoke-TeamsGraphGet '/v1.0/teams?$select=id,displayName,visibility') {
        $members = @(Invoke-TeamsGraphGet "/v1.0/teams/$($team.id)/members")
        [pscustomobject]@{
            TeamId      = $team.id
            DisplayName = $team.displayName
            Visibility  = ([string](Get-TGProp $team 'visibility' '')).ToLowerInvariant()
            Members     = $members.Count
            Owners      = @($members | Where-Object { @(Get-TGProp $_ 'roles' @()) -contains 'owner' }).Count
            Guests      = @($members | Where-Object { @(Get-TGProp $_ 'roles' @()) -contains 'guest' }).Count
        }
    }
    $rows = @()
    if (-not $SkipActivity) {
        try { $rows = @(Get-TeamsActivityReport -Period $Period) }
        catch { Write-Warning "Activity report not collected: $($_.Exception.Message)" }
    }
    Join-TeamsActivity -Teams @($teams) -ActivityRows $rows
}

function New-GovernedTeam {
    <#
    .SYNOPSIS  Create a team that follows the policy, or explain why it can't be created.
    .EXAMPLE   New-GovernedTeam -RequestedName 'Project Falcon' -Creator @{ Department = 'Finance' } -OwnerIds $a,$b -Policy $p -WhatIf
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$RequestedName,
        [Parameter(Mandatory)][object]$Creator,
        [Parameter(Mandatory)][string[]]$OwnerIds,
        [Parameter(Mandatory)][object]$Policy,
        [string]$Description = '',
        [ValidateSet('private', 'public')][string]$Visibility,
        [int]$TimeoutSeconds = 300,
        [int]$PollSeconds = 10
    )
    $name = Resolve-TeamName -RequestedName $RequestedName -Creator $Creator -Policy $Policy
    if ($name.Errors.Count) { throw "Name '$($name.DisplayName)' rejected: $($name.Errors -join ', ')" }
    $splat = @{ DisplayName = $name.DisplayName; Description = $Description; OwnerIds = $OwnerIds; Policy = $Policy }
    if ($Visibility) { $splat.Visibility = $Visibility }
    $body = New-TeamsCreateRequest @splat

    if (-not $PSCmdlet.ShouldProcess($name.DisplayName, "Create $($body.visibility) team with $($body.members.Count) owners")) {
        return [pscustomobject]@{ DisplayName = $name.DisplayName; Status = 'WhatIf'; TeamId = $null; Body = $body }
    }

    # 202 Accepted with an empty body: the only useful output is the Location header, so ask for the raw response.
    $resp = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/teams' -Body ($body | ConvertTo-Json -Depth 6) `
        -ContentType 'application/json' -OutputType HttpResponseMessage -ErrorAction Stop
    if (-not $resp.IsSuccessStatusCode) {
        throw "POST /teams failed: $([int]$resp.StatusCode) $($resp.Content.ReadAsStringAsync().GetAwaiter().GetResult())"
    }
    if ($null -eq $resp.Headers.Location) { throw 'POST /teams returned no Location header.' }
    $opUri = Resolve-TeamsOperationUri $resp.Headers.Location.OriginalString

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $op = Invoke-MgGraphRequest -Method GET -Uri $opUri -OutputType PSObject -ErrorAction Stop
        $status = Get-TGProp $op 'status'
        if ($status -in 'succeeded', 'failed') { break }
        Start-Sleep -Seconds $PollSeconds
    } while ([datetime]::UtcNow -lt $deadline)

    if ($status -eq 'failed') { throw "Team creation failed: $((Get-TGProp $op 'error') | ConvertTo-Json -Compress)" }
    [pscustomobject]@{
        DisplayName = $name.DisplayName
        Status      = if ($status -eq 'succeeded') { 'Created' } else { "Pending ($status)" }
        TeamId      = Get-TGProp $op 'targetResourceId'
        Body        = $body
    }
}

function Set-TeamsDirectoryPolicy {
    <#
    .SYNOPSIS  Writes naming policy, blocked words and the group creation restriction to the tenant's
               Group.Unified setting (creates it from the template defaults if it doesn't exist yet).
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)][object]$Policy)

    $desired = Get-TeamsDirectoryPolicyValue -Policy $Policy
    $existing = @(Invoke-TeamsGraphGet '/v1.0/groupSettings') | Where-Object { (Get-TGProp $_ 'templateId') -eq $script:GroupUnifiedTemplateId } | Select-Object -First 1

    if ($existing) {
        $values = Merge-GroupSettingValue -Current @($existing.values) -Desired $desired
        if ($PSCmdlet.ShouldProcess('Group.Unified', 'Update directory setting')) {
            Invoke-MgGraphRequest -Method PATCH -Uri "/v1.0/groupSettings/$($existing.id)" -Body (@{ values = $values } | ConvertTo-Json -Depth 5) -ContentType 'application/json' -ErrorAction Stop | Out-Null
        }
    }
    else {
        $template = Invoke-TeamsGraphGet "/v1.0/groupSettingTemplates/$script:GroupUnifiedTemplateId"
        $values = Merge-GroupSettingValue -Current @($template.values) -Desired $desired
        if ($PSCmdlet.ShouldProcess('Group.Unified', 'Create directory setting from template')) {
            Invoke-MgGraphRequest -Method POST -Uri '/v1.0/groupSettings' -Body (@{ templateId = $script:GroupUnifiedTemplateId; values = $values } | ConvertTo-Json -Depth 5) -ContentType 'application/json' -ErrorAction Stop | Out-Null
        }
    }
    @($values | Where-Object { $desired.Contains($_.name) } | ForEach-Object { [pscustomobject]$_ })
}

#endregion

Export-ModuleMember -Function @(
    'Get-TeamsGovernancePolicy', 'Test-TeamsBlockedWord', 'Resolve-TeamName', 'Test-TeamNameCompliance',
    'New-TeamsCreateRequest', 'Resolve-TeamsOperationUri', 'Merge-GroupSettingValue', 'Get-TeamsDirectoryPolicyValue',
    'Get-TeamsGovernanceFinding', 'Join-TeamsActivity',
    'Invoke-TeamsGraphGet', 'Get-TeamsActivityReport', 'Get-TeamsInventory', 'New-GovernedTeam', 'Set-TeamsDirectoryPolicy'
)
