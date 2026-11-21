#requires -Version 7.2
Set-StrictMode -Version Latest

# Contoso Zero Trust helpers (DEVLADLOG Deep Dive #9).
# Everything talks to Microsoft Graph through Invoke-MgGraphRequest (module Microsoft.Graph.Authentication).
# Connect first, with the least scopes the step needs:
#   Connect-MgGraph -Scopes Policy.ReadWrite.ConditionalAccess, Policy.Read.All, Group.ReadWrite.All,
#                           DeviceManagementConfiguration.ReadWrite.All, AuditLog.Read.All, Directory.Read.All

# Values Learn documents for these enums (Graph v1.0 conditionalAccessGrantControl, conditionalAccessClientApp,
# conditionalAccessPolicyState). The linter rejects anything else so a typo fails here, not in the tenant.
$script:GrantControls = 'block', 'mfa', 'compliantDevice', 'domainJoinedDevice', 'approvedApplication', 'compliantApplication', 'passwordChange'
$script:ClientAppTypes = 'all', 'browser', 'mobileAppsAndDesktopClients', 'exchangeActiveSync', 'easSupported', 'other'
$script:PolicyStates = 'enabled', 'disabled', 'enabledForReportingButNotEnforced'

function Expand-CaTemplate {
    <#
    .SYNOPSIS Replaces {{name}} tokens in a policy template. Throws on a token without a value, so a policy with a
    half-filled placeholder never reaches Graph.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Template,
        [Parameter(Mandatory)][hashtable]$Values
    )
    $out = [regex]::Replace($Template, '\{\{\s*(\w+)\s*\}\}', {
            param($m)
            $key = $m.Groups[1].Value
            if (-not $Values.ContainsKey($key) -or [string]::IsNullOrWhiteSpace([string]$Values[$key])) {
                throw "No value for template token '$key'."
            }
            [string]$Values[$key]
        })
    $out
}

function Test-CaPolicy {
    <#
    .SYNOPSIS Returns a list of problems in one Conditional Access policy object (empty list = fine).
    Rules: report-only unless -AllowEnforced; the break-glass group is excluded; no empty targeting; documented
    enum values only; mfa and an authentication strength never together (Learn: not supported in one policy);
    a block policy never targets everyone without an exclusion.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Policy,
        [switch]$AllowEnforced
    )
    Set-StrictMode -Off   # a policy with a missing section is a finding, not an exception
    $issues = [System.Collections.Generic.List[string]]::new()

    if (-not $Policy.displayName) { $issues.Add('displayName is missing') }
    if ($Policy.state -notin $script:PolicyStates) { $issues.Add("state '$($Policy.state)' is not one of $($script:PolicyStates -join ', ')") }
    elseif ($Policy.state -ne 'enabledForReportingButNotEnforced' -and -not $AllowEnforced) {
        $issues.Add("state is '$($Policy.state)': new policies start in report-only")
    }

    $users = $Policy.conditions.users
    $apps = $Policy.conditions.applications
    if (-not $users) { $issues.Add('conditions.users is missing') }
    if (-not $apps -or -not $apps.includeApplications) { $issues.Add('conditions.applications.includeApplications is missing') }

    if ($users) {
        $props = $users.PSObject.Properties.Name
        $targets = @('includeUsers', 'includeGroups', 'includeRoles') | Where-Object { $_ -in $props -and @($users.$_).Count -gt 0 }
        if (-not $targets) { $issues.Add('the policy targets nobody (no includeUsers, includeGroups or includeRoles)') }
        $excludeGroups = if ('excludeGroups' -in $props) { @($users.excludeGroups) } else { @() }
        if ('{{breakGlassGroupId}}' -notin $excludeGroups -and -not ($excludeGroups | Where-Object { $_ -match '^[0-9a-f-]{36}$' })) {
            $issues.Add('the break-glass group is not in excludeGroups')
        }
    }

    foreach ($c in @($Policy.conditions.clientAppTypes)) {
        if ($c -notin $script:ClientAppTypes) { $issues.Add("clientAppTypes value '$c' is not documented") }
    }
    if (-not $Policy.conditions.clientAppTypes) { $issues.Add('conditions.clientAppTypes is missing') }

    $grant = $Policy.grantControls
    if (-not $grant) { $issues.Add('grantControls is missing') }
    else {
        $gp = $grant.PSObject.Properties.Name
        $controls = if ('builtInControls' -in $gp) { @($grant.builtInControls) } else { @() }
        $hasStrength = ('authenticationStrength' -in $gp) -and $grant.authenticationStrength
        foreach ($c in $controls) { if ($c -notin $script:GrantControls) { $issues.Add("builtInControls value '$c' is not documented") } }
        if (-not $controls -and -not $hasStrength) { $issues.Add('grantControls has no control') }
        if ('mfa' -in $controls -and $hasStrength) { $issues.Add("'mfa' and authenticationStrength cannot be combined in one policy") }
        if ('block' -in $controls -and $controls.Count -gt 1) { $issues.Add("'block' is combined with other controls") }
        if ($grant.operator -notin 'AND', 'OR') { $issues.Add("grantControls.operator '$($grant.operator)' must be AND or OR") }
    }
    [string[]]$issues
}

function Resolve-AuthStrengthId {
    <# Looks up a BUILT-IN authentication strength by display name (e.g. 'Phishing-resistant MFA'). #>
    [CmdletBinding()]
    param([string]$Like = '*hishing*')
    $r = Invoke-MgGraphRequest -Method GET -Uri '/v1.0/policies/authenticationStrengthPolicies'
    $hit = @($r.value | Where-Object { $_.policyType -eq 'builtIn' -and $_.displayName -like $Like })
    if ($hit.Count -ne 1) { throw "Expected exactly one built-in authentication strength matching '$Like', found $($hit.Count)." }
    $hit[0].id
}

function Initialize-LabGroup {
    <# Creates (or finds) an assigned security group by name and returns its object id. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string]$DisplayName, [string]$Description = 'Zero Trust lab (episode 9)')
    $safe = $DisplayName.Replace("'", "''")
    $filter = [uri]::EscapeDataString("displayName eq '$safe'")
    $r = Invoke-MgGraphRequest -Method GET -Uri ('/v1.0/groups?$filter=' + $filter + '&$select=id,displayName')
    if (@($r.value).Count -gt 0) { return $r.value[0].id }
    if ($PSCmdlet.ShouldProcess($DisplayName, 'Create security group')) {
        $body = @{
            displayName     = $DisplayName
            description     = $Description
            mailEnabled     = $false
            mailNickname    = ($DisplayName -replace '[^A-Za-z0-9]', '')
            securityEnabled = $true
        }
        (Invoke-MgGraphRequest -Method POST -Uri '/v1.0/groups' -Body ($body | ConvertTo-Json) -ContentType 'application/json').id
    }
}

function Publish-CaPolicy {
    <#
    .SYNOPSIS Creates or updates one Conditional Access policy, matched by displayName.
    The state in the template is sent as is: this function never promotes a policy to 'enabled' on its own
    unless -Enforce is given. -WhatIf makes no write call.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$TemplatePath,
        [Parameter(Mandatory)][hashtable]$Values,
        [switch]$Enforce
    )
    $json = Expand-CaTemplate -Template (Get-Content -LiteralPath $TemplatePath -Raw) -Values $Values
    $policy = $json | ConvertFrom-Json -Depth 20
    $issues = @(Test-CaPolicy -Policy $policy -AllowEnforced:$Enforce)
    if ($issues.Count -gt 0) { throw "Policy '$($policy.displayName)' is not safe to publish: $($issues -join '; ')" }
    if ($Enforce) { $policy.state = 'enabled'; $json = $policy | ConvertTo-Json -Depth 20 }

    $all = Invoke-MgGraphRequest -Method GET -Uri '/v1.0/identity/conditionalAccess/policies'
    $existing = @($all.value | Where-Object { $_.displayName -eq $policy.displayName })
    if ($existing.Count -gt 1) { throw "More than one policy is named '$($policy.displayName)'." }

    if ($existing.Count -eq 1) {
        if ($PSCmdlet.ShouldProcess($policy.displayName, "Update policy $($existing[0].id)")) {
            Invoke-MgGraphRequest -Method PATCH -Uri "/v1.0/identity/conditionalAccess/policies/$($existing[0].id)" -Body $json -ContentType 'application/json' | Out-Null
            [pscustomobject]@{ Policy = $policy.displayName; Action = 'updated'; State = $policy.state }
        }
    }
    elseif ($PSCmdlet.ShouldProcess($policy.displayName, 'Create policy')) {
        $created = Invoke-MgGraphRequest -Method POST -Uri '/v1.0/identity/conditionalAccess/policies' -Body $json -ContentType 'application/json'
        [pscustomobject]@{ Policy = $policy.displayName; Action = 'created'; State = $created.state }
    }
}

function Publish-CompliancePolicy {
    <# Creates the Intune Windows compliance policy (or reuses it by name) and assigns it to one group. #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$GroupId
    )
    $body = Get-Content -LiteralPath $Path -Raw
    $policy = $body | ConvertFrom-Json -Depth 20
    $list = Invoke-MgGraphRequest -Method GET -Uri '/v1.0/deviceManagement/deviceCompliancePolicies?$select=id,displayName'
    $existing = @($list.value | Where-Object { $_.displayName -eq $policy.displayName })
    if ($existing.Count -gt 0) { $id = $existing[0].id; $action = 'reused' }
    elseif ($PSCmdlet.ShouldProcess($policy.displayName, 'Create compliance policy')) {
        $id = (Invoke-MgGraphRequest -Method POST -Uri '/v1.0/deviceManagement/deviceCompliancePolicies' -Body $body -ContentType 'application/json').id
        $action = 'created'
    }
    else { return }

    if ($PSCmdlet.ShouldProcess("$($policy.displayName) -> group $GroupId", 'Assign')) {
        $assign = @{ assignments = @(@{ target = @{ '@odata.type' = '#microsoft.graph.groupAssignmentTarget'; groupId = $GroupId } }) }
        Invoke-MgGraphRequest -Method POST -Uri "/v1.0/deviceManagement/deviceCompliancePolicies/$id/assign" -Body ($assign | ConvertTo-Json -Depth 6) -ContentType 'application/json' | Out-Null
        [pscustomobject]@{ Policy = $policy.displayName; Id = $id; Action = $action; AssignedTo = $GroupId }
    }
}

function Get-CaReportOnlyImpact {
    <#
    .SYNOPSIS What would the report-only policies have done in the last N hours? Reads the sign-in log
    (appliedConditionalAccessPolicies) and counts, per policy, the documented report-only results.
    Needs AuditLog.Read.All and a role that may read Conditional Access data (Learn: Security Reader and others).
    #>
    [CmdletBinding()]
    param(
        [int]$Hours = 24,
        [string]$NamePrefix = 'CT0',
        [datetime]$Now = (Get-Date).ToUniversalTime()
    )
    $since = $Now.AddHours(-$Hours).ToString('yyyy-MM-ddTHH:mm:ssZ')
    $uri = '/v1.0/auditLogs/signIns?$filter=createdDateTime ge ' + $since + '&$top=200'
    $counts = @{}
    $signIns = 0
    while ($uri) {
        $page = Invoke-MgGraphRequest -Method GET -Uri $uri
        foreach ($s in $page.value) {
            $signIns++
            foreach ($p in @($s.appliedConditionalAccessPolicies)) {
                if ($p.displayName -notlike "$NamePrefix*") { continue }
                if (-not $counts.ContainsKey($p.displayName)) {
                    $counts[$p.displayName] = [ordered]@{ Policy = $p.displayName; WouldPass = 0; WouldFail = 0; UserActionNeeded = 0; NotApplied = 0 }
                }
                switch ($p.result) {
                    'reportOnlySuccess' { $counts[$p.displayName].WouldPass++ }
                    'reportOnlyFailure' { $counts[$p.displayName].WouldFail++ }
                    'reportOnlyInterrupted' { $counts[$p.displayName].UserActionNeeded++ }
                    'reportOnlyNotApplied' { $counts[$p.displayName].NotApplied++ }
                }
            }
        }
        $uri = $page['@odata.nextLink']   # Invoke-MgGraphRequest returns hashtables
    }
    Write-Verbose "$signIns sign-ins read"
    $counts.Values | Sort-Object { $_.Policy } | ForEach-Object { [pscustomobject]$_ }
}

Export-ModuleMember -Function Expand-CaTemplate, Test-CaPolicy, Resolve-AuthStrengthId, Initialize-LabGroup, Publish-CaPolicy, Publish-CompliancePolicy, Get-CaReportOnlyImpact
