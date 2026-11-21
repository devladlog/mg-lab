# Grants the function's user-assigned managed identity exactly what OnboardingSync needs:
#   - Microsoft Graph application roles: SynchronizationData-User.Upload, User.Read.All, Lists.SelectedOperations.Selected
#   - a 'write' permission on the two onboarding lists only (POST /sites/{site}/lists/{list}/permissions)
# Managed identities have no "API permissions" page, so app roles are assigned through Graph (as Learn's
# inbound-provisioning grant-access page does). Uses Invoke-MgGraphRequest from Microsoft.Graph.Authentication.

$script:GraphAppId = '00000003-0000-0000-c000-000000000000'
$script:RequiredGraphRoles = @('SynchronizationData-User.Upload', 'User.Read.All', 'Lists.SelectedOperations.Selected')

function Get-OnbRequiredGraphRoles { $script:RequiredGraphRoles }

function Invoke-OnbAdminGraph {
    [CmdletBinding()]
    param([ValidateSet('GET', 'POST')] [string] $Method = 'GET', [Parameter(Mandatory)] [string] $Uri, $Body)
    $params = @{ Method = $Method; Uri = $Uri; OutputType = 'PSObject' }
    if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json -Depth 10 -Compress); $params.ContentType = 'application/json' }
    Invoke-MgGraphRequest @params
}

function Get-OnbServicePrincipal {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Filter)
    $r = Invoke-OnbAdminGraph -Uri ("https://graph.microsoft.com/v1.0/servicePrincipals?`$filter=" + [uri]::EscapeDataString($Filter))
    $sp = @($r.value)
    if ($sp.Count -ne 1) { throw "Expected one service principal for [$Filter], found $($sp.Count)." }
    return $sp[0]
}

function Grant-OnbGraphAppRoles {
    <# Assigns each missing Graph app role to the managed identity. Returns one object per role: Added / Exists. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [string] $IdentityClientId, [string[]] $Roles = $script:RequiredGraphRoles)

    $graph = Get-OnbServicePrincipal -Filter "appId eq '$script:GraphAppId'"
    $mi = Get-OnbServicePrincipal -Filter "appId eq '$IdentityClientId'"
    $assigned = @((Invoke-OnbAdminGraph -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$($mi.id)/appRoleAssignments").value)
    foreach ($roleName in $Roles) {
        $role = @($graph.appRoles | Where-Object { $_.value -eq $roleName -and $_.allowedMemberTypes -contains 'Application' })
        if ($role.Count -ne 1) { throw "Microsoft Graph has no application role '$roleName'." }
        if ($assigned | Where-Object { $_.resourceId -eq $graph.id -and $_.appRoleId -eq $role[0].id }) {
            [pscustomobject]@{ Grant = $roleName; Result = 'Exists' }
            continue
        }
        if ($PSCmdlet.ShouldProcess($mi.displayName, "Assign Graph app role $roleName")) {
            Invoke-OnbAdminGraph -Method POST -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$($mi.id)/appRoleAssignments" `
                -Body @{ principalId = $mi.id; resourceId = $graph.id; appRoleId = $role[0].id } | Out-Null
            [pscustomobject]@{ Grant = $roleName; Result = 'Added' }
        }
    }
}

function Resolve-OnbListIds {
    <# Site and list IDs for the app settings (Onboarding__SiteId, __RequestsListId, __TasksListId). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $HostName, [Parameter(Mandatory)] [string] $SitePath, [Parameter(Mandatory)] [string[]] $ListTitles)

    $site = Invoke-OnbAdminGraph -Uri "https://graph.microsoft.com/v1.0/sites/$HostName`:$SitePath"
    $ids = [ordered]@{ SiteId = $site.id }
    foreach ($title in $ListTitles) {
        $filter = [uri]::EscapeDataString("displayName eq '$($title.Replace("'", "''"))'")
        $lists = @((Invoke-OnbAdminGraph -Uri "https://graph.microsoft.com/v1.0/sites/$($site.id)/lists?`$filter=$filter&`$select=id,displayName").value)
        if ($lists.Count -ne 1) { throw "List '$title' not found on $SitePath (run New-OnboardingLists.ps1 first)." }
        $ids[$title] = $lists[0].id
    }
    return $ids
}

function Grant-OnbListAccess {
    <# Gives the identity 'write' on one list (Lists.SelectedOperations.Selected). Idempotent. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [string] $SiteId, [Parameter(Mandatory)] [string] $ListId,
          [Parameter(Mandatory)] [string] $IdentityClientId, [Parameter(Mandatory)] [string] $DisplayName,
          [ValidateSet('read', 'write')] [string] $Role = 'write')

    $base = "https://graph.microsoft.com/v1.0/sites/$SiteId/lists/$ListId/permissions"
    $current = @((Invoke-OnbAdminGraph -Uri $base).value)
    $mine = $current | Where-Object {
        $_.PSObject.Properties['grantedToV2'] -and $_.grantedToV2.PSObject.Properties['application'] -and $_.grantedToV2.application.id -eq $IdentityClientId
    }
    if ($mine -and @($mine.roles) -contains $Role) { return [pscustomobject]@{ Grant = "$Role on list $ListId"; Result = 'Exists' } }
    if ($PSCmdlet.ShouldProcess("list $ListId", "Grant $Role to $DisplayName")) {
        Invoke-OnbAdminGraph -Method POST -Uri $base -Body @{
            roles       = @($Role)
            grantedToV2 = @{ application = @{ id = $IdentityClientId; displayName = $DisplayName } }
        } | Out-Null
        return [pscustomobject]@{ Grant = "$Role on list $ListId"; Result = 'Added' }
    }
}

Export-ModuleMember -Function Get-OnbRequiredGraphRoles, Invoke-OnbAdminGraph, Get-OnbServicePrincipal, Grant-OnbGraphAppRoles,
    Resolve-OnbListIds, Grant-OnbListAccess
