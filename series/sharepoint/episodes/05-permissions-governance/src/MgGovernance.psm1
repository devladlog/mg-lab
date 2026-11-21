#Requires -Version 7.2
<#
.SYNOPSIS
    Permissions and sharing governance as code for one SharePoint site: a JSON policy (sharing, default link,
    sensitivity label, owners, who may hold Full Control, which lists may break inheritance), a snapshot of what the
    site really has (site sharing settings, admins, groups and members, role assignments on the web, lists and items,
    sharing links), rules that compare the two, and a remediation plan that fixes what can be fixed safely.

    Pure functions (no SharePoint needed): Import-MgJson, Test-MgGovernancePolicy, Test-MgPermissionSnapshot,
    Get-MgRemediationPlan, Get-MgScopeSummary, Compare-MgSharingCapability.
    Tenant functions (PnP.PowerShell, after Connect-PnPOnline): Get-MgPermissionSnapshot, Invoke-MgRemediation.
#>

Set-StrictMode -Version Latest

# ---- What Learn documents (see README "References") -------------------------------------------------------------
#   Site sharing options, most to least restrictive: Only people in your organization (Disabled), Existing guests
#   (ExistingExternalUserSharingOnly), New and existing guests (ExternalUserSharingOnly), Anyone
#   (ExternalUserAndGuestSharing). The available site settings depend on the organization-level setting.
#   Default sharing link type: None (same as organization), Direct (specific people), Internal (people in your
#   organization), AnonymousAccess (anyone). Default link permission: None, View, Edit.
#   Unique permissions per list or library: 50,000 supported, 5,000 recommended general limit.
#   Limited Access is assigned by SharePoint for fine-grained access and can't be edited: it's not a grant to audit.
#   Guests have #EXT# in their user principal name.
#   "Everyone except external users" and "Everyone" make content visible to the whole organization.
$script:SharingOrder = @('Disabled', 'ExistingExternalUserSharingOnly', 'ExternalUserSharingOnly', 'ExternalUserAndGuestSharing')
$script:SharingLabel = @{
    Disabled                        = 'Only people in your organization'
    ExistingExternalUserSharingOnly = 'Existing guests'
    ExternalUserSharingOnly         = 'New and existing guests'
    ExternalUserAndGuestSharing     = 'Anyone'
}
$script:LinkTypes = @('None', 'Direct', 'Internal', 'AnonymousAccess')
$script:LinkPermissions = @('None', 'View', 'Edit')
$script:LinkScopes = @('Anonymous', 'Organization', 'Users')
$script:SupportedScopesPerList = 50000
$script:RecommendedScopesPerList = 5000
$script:IgnoredRoles = @('Limited Access', 'Web-Only Limited Access')

function Import-MgJson {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json -Depth 30
}

function Get-MgProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    if ($Object.PSObject.Properties[$Name]) { $Object.$Name } else { $Default }
}

function New-MgFinding([string]$Rule, [string]$Severity, [string]$Target, [string]$Message, $Fix = $null) {
    [pscustomobject]@{ Rule = $Rule; Severity = $Severity; Target = $Target; Message = $Message; Fix = $Fix }
}

function New-MgFix([string]$Action, [System.Collections.IDictionary]$Data) {
    $o = [ordered]@{ Action = $Action }
    foreach ($k in $Data.Keys) { $o[$k] = $Data[$k] }
    [pscustomobject]$o
}

function Compare-MgSharingCapability {
    <#
    .SYNOPSIS  -1 / 0 / 1 when $A is more restrictive than / the same as / more permissive than $B.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$A, [Parameter(Mandatory)][string]$B)
    $ia = [array]::IndexOf($script:SharingOrder, $A); $ib = [array]::IndexOf($script:SharingOrder, $B)
    if ($ia -lt 0 -or $ib -lt 0) { throw "Unknown sharing capability '$(if ($ia -lt 0) { $A } else { $B })'." }
    [math]::Sign($ia - $ib)
}

function Get-MgSharingLabel([string]$Capability) { $script:SharingLabel[$Capability] }

# ---- Policy lint ---------------------------------------------------------------------------------------------------

function Test-MgGovernancePolicy {
    <#
    .SYNOPSIS  Checks the policy itself (GP001-GP007) before it's compared with a site.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Policy)
    $sharing = Get-MgProp $Policy 'sharing'
    $cap = Get-MgProp $sharing 'capability'
    $org = Get-MgProp $Policy 'organizationSharingCapability'
    foreach ($pair in @(@('sharing.capability', $cap), @('organizationSharingCapability', $org))) {
        if ($pair[1] -and $pair[1] -notin $script:SharingOrder) {
            New-MgFinding 'GP001' 'Error' $pair[0] "'$($pair[1])' isn't a sharing capability: $($script:SharingOrder -join ', ')."
        }
    }
    $linkType = Get-MgProp $sharing 'defaultLinkType'
    if ($linkType -and $linkType -notin $script:LinkTypes) {
        New-MgFinding 'GP001' 'Error' 'sharing.defaultLinkType' "'$linkType' isn't a link type: $($script:LinkTypes -join ', ')."
    }
    $linkPerm = Get-MgProp $sharing 'defaultLinkPermission'
    if ($linkPerm -and $linkPerm -notin $script:LinkPermissions) {
        New-MgFinding 'GP001' 'Error' 'sharing.defaultLinkPermission' "'$linkPerm' isn't a link permission: $($script:LinkPermissions -join ', ')."
    }
    foreach ($s in @(Get-MgProp (Get-MgProp $Policy 'sharingLinks') 'forbiddenScopes' @()) + @(Get-MgProp (Get-MgProp $Policy 'sharingLinks') 'warnScopes' @())) {
        if ($s -notin $script:LinkScopes) { New-MgFinding 'GP001' 'Error' 'sharingLinks' "'$s' isn't a link scope: $($script:LinkScopes -join ', ')." }
    }
    if ($cap -in $script:SharingOrder -and $org -in $script:SharingOrder -and (Compare-MgSharingCapability $cap $org) -gt 0) {
        New-MgFinding 'GP002' 'Error' 'sharing.capability' ("The site can't be more permissive than the organization: '{0}' is more than '{1}'." -f (Get-MgSharingLabel $cap), (Get-MgSharingLabel $org))
    }
    if ($linkType -eq 'AnonymousAccess' -and $cap -in $script:SharingOrder -and $cap -ne 'ExternalUserAndGuestSharing') {
        New-MgFinding 'GP003' 'Error' 'sharing.defaultLinkType' "Default link 'Anyone' but the site sharing is '$(Get-MgSharingLabel $cap)': Anyone links can't be created there."
    }
    $owners = Get-MgProp $Policy 'owners'
    if ((Get-MgProp $owners 'min' 0) -lt 2) {
        New-MgFinding 'GP004' 'Warning' 'owners.min' 'Require at least two owners: a site with one owner has no owner when that person leaves.'
    }
    $max = Get-MgProp (Get-MgProp $Policy 'uniquePermissions') 'maxItemScopesPerList'
    if ($null -ne $max) {
        if ($max -gt $script:SupportedScopesPerList) {
            New-MgFinding 'GP005' 'Error' 'uniquePermissions.maxItemScopesPerList' "$max is above the supported 50,000 unique permissions per list or library."
        }
        elseif ($max -gt $script:RecommendedScopesPerList) {
            New-MgFinding 'GP005' 'Warning' 'uniquePermissions.maxItemScopesPerList' "$max is above the recommended general limit of 5,000."
        }
    }
    $label = Get-MgProp $Policy 'sensitivityLabel'
    if ($label -and -not (Get-MgProp $label 'id')) {
        New-MgFinding 'GP006' 'Warning' 'sensitivityLabel' "Label '$(Get-MgProp $label 'name')' has no id: pass -SensitivityLabelId so the audit can compare and fix it."
    }
    $roles = @('Owners', 'Members', 'Visitors')
    foreach ($l in @(Get-MgProp (Get-MgProp $Policy 'uniquePermissions') 'allowedLists' @())) {
        foreach ($g in @((Get-MgProp $l 'access' ([pscustomobject]@{})).PSObject.Properties | ForEach-Object Name)) {
            if ($g.StartsWith('@') -and $g.Substring(1) -notin $roles) {
                New-MgFinding 'GP007' 'Error' "uniquePermissions.allowedLists['$($l.title)']" "'$g' isn't a role: use @Owners, @Members, @Visitors or a group name."
            }
        }
    }
}

# ---- Snapshot audit ------------------------------------------------------------------------------------------------

function Resolve-MgRoleName([string]$Name, $Snapshot) {
    if ($Name.StartsWith('@')) { return (Get-MgProp (Get-MgProp $Snapshot 'associatedGroups') $Name.Substring(1) $Name) }
    $Name
}

function Test-MgIsGuest($Principal) { ((Get-MgProp $Principal 'loginName' '') -match '#ext#') }

function Get-MgGrants($Scope) {
    foreach ($a in @(Get-MgProp $Scope 'assignments' @())) {
        $roles = @($a.roles | Where-Object { $_ -notin $script:IgnoredRoles })
        if ($roles.Count) { [pscustomobject]@{ Principal = $a; Roles = $roles } }
    }
}

function Get-MgScopeTarget($Scope) {
    switch ($Scope.kind) {
        'Web' { 'site' }
        'List' { "list '$($Scope.title)'" }
        default { "item '$($Scope.path)'" }
    }
}

function New-MgRemoveGrantFix($Scope, $Principal, [string]$Role) {
    $data = [ordered]@{ Kind = $Scope.kind; Role = $Role; PrincipalType = $Principal.principalType }
    if ($Principal.principalType -eq 'SharePointGroup') { $data.Group = $Principal.title } else { $data.User = $Principal.loginName }
    if ($Scope.kind -eq 'List') { $data.List = $Scope.title }
    if ($Scope.kind -eq 'Item') { $data.List = $Scope.list; $data.ItemId = $Scope.id }
    New-MgFix 'RemoveGrant' $data
}

function Test-MgPermissionSnapshot {
    <#
    .SYNOPSIS  Compares a permission snapshot with the policy (GV001-GV015). Each finding may carry a Fix.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Snapshot, [Parameter(Mandatory)]$Policy, [string]$SensitivityLabelId)
    $sharing = Get-MgProp $Policy 'sharing'
    $site = $Snapshot.url

    # GV001-GV003: site sharing settings
    $want = Get-MgProp $sharing 'capability'
    if ($want -and (Compare-MgSharingCapability $Snapshot.sharingCapability $want) -gt 0) {
        New-MgFinding 'GV001' 'Error' 'site' ("External sharing is '{0}', the policy allows '{1}'." -f (Get-MgSharingLabel $Snapshot.sharingCapability), (Get-MgSharingLabel $want)) (New-MgFix 'SetSite' @{ SharingCapability = $want })
    }
    $wantLink = Get-MgProp $sharing 'defaultLinkType'
    if ($wantLink -and $Snapshot.defaultSharingLinkType -ne $wantLink) {
        New-MgFinding 'GV002' 'Warning' 'site' "Default sharing link is '$($Snapshot.defaultSharingLinkType)', the policy wants '$wantLink'." (New-MgFix 'SetSite' @{ DefaultSharingLinkType = $wantLink })
    }
    $wantPerm = Get-MgProp $sharing 'defaultLinkPermission'
    if ($wantPerm -and $Snapshot.defaultLinkPermission -ne $wantPerm) {
        New-MgFinding 'GV003' 'Warning' 'site' "Default link permission is '$($Snapshot.defaultLinkPermission)', the policy wants '$wantPerm'." (New-MgFix 'SetSite' @{ DefaultLinkPermission = $wantPerm })
    }

    # GV004: sensitivity label
    $label = Get-MgProp $Policy 'sensitivityLabel'
    if ($label) {
        $id = if ($SensitivityLabelId) { $SensitivityLabelId } else { Get-MgProp $label 'id' }
        $have = Get-MgProp $Snapshot 'sensitivityLabel'
        $fix = if ($id) { New-MgFix 'SetSite' @{ SensitivityLabel = "$id" } } else { $null }
        if (-not $have) {
            New-MgFinding 'GV004' 'Error' 'site' "No sensitivity label: the policy wants '$($label.name)'." $fix
        }
        elseif ($id -and $have -ne "$id") {
            New-MgFinding 'GV004' 'Error' 'site' "Sensitivity label is $have, the policy wants '$($label.name)' ($id)." $fix
        }
    }

    # GV005-GV006: owners and admins
    $ownersGroup = Get-MgProp (Get-MgProp $Snapshot 'associatedGroups') 'Owners'
    $group = @($Snapshot.groups | Where-Object title -eq $ownersGroup) | Select-Object -First 1
    $people = @(if ($group) { $group.members | Where-Object principalType -eq 'User' })
    $owners = Get-MgProp $Policy 'owners'
    if ($owners) {
        if ($people.Count -lt (Get-MgProp $owners 'min' 0)) {
            New-MgFinding 'GV005' 'Warning' "group '$ownersGroup'" "$($people.Count) owner(s), the policy wants at least $($owners.min)."
        }
        if ((Get-MgProp $owners 'max') -and $people.Count -gt $owners.max) {
            New-MgFinding 'GV005' 'Warning' "group '$ownersGroup'" "$($people.Count) owners, the policy allows at most $($owners.max)."
        }
    }
    $maxAdmins = Get-MgProp (Get-MgProp $Policy 'siteAdmins') 'max'
    if ($maxAdmins -and @($Snapshot.siteAdmins).Count -gt $maxAdmins) {
        New-MgFinding 'GV006' 'Warning' 'site' "$(@($Snapshot.siteAdmins).Count) site admins, the policy allows at most $maxAdmins."
    }

    # GV007: forbidden principals, as group members or as direct grants
    $forbidden = @(Get-MgProp $Policy 'forbiddenPrincipals' @())
    foreach ($g in @($Snapshot.groups)) {
        foreach ($m in @($g.members | Where-Object { $_.title -in $forbidden })) {
            New-MgFinding 'GV007' 'Error' "group '$($g.title)'" "'$($m.title)' is a member: everything the group can open is open to the whole organization." (New-MgFix 'RemoveGroupMember' @{ Group = $g.title; LoginName = $m.loginName })
        }
    }
    $adminLogins = @($Snapshot.siteAdmins | ForEach-Object loginName)
    $fullControlOk = @(@(Get-MgProp $Policy 'fullControlOnlyFor' @('@Owners')) | ForEach-Object { Resolve-MgRoleName $_ $Snapshot })
    $allowedLists = @(Get-MgProp (Get-MgProp $Policy 'uniquePermissions') 'allowedLists' @())
    foreach ($scope in @($Snapshot.scopes | Where-Object unique)) {
        $target = Get-MgScopeTarget $scope
        foreach ($g in @(Get-MgGrants $scope)) {
            $p = $g.Principal
            if ($p.title -in $forbidden) {
                foreach ($r in $g.Roles) {
                    New-MgFinding 'GV007' 'Error' $target "'$($p.title)' has $r." (New-MgRemoveGrantFix $scope $p $r)
                }
                continue
            }
            # GV009: Full Control outside the owners group (site admins aren't role assignments, but be safe)
            if ('Full Control' -in $g.Roles -and $p.title -notin $fullControlOk -and $p.loginName -notin $adminLogins) {
                New-MgFinding 'GV009' 'Error' $target "'$($p.title)' has Full Control: only $($fullControlOk -join ', ') may." (New-MgRemoveGrantFix $scope $p 'Full Control')
            }
            # GV008: people granted directly instead of through a group
            if ($p.principalType -eq 'User' -and $scope.kind -ne 'Item') {
                foreach ($r in @($g.Roles | Where-Object { $_ -ne 'Full Control' -or $p.title -in $fullControlOk })) {
                    New-MgFinding 'GV008' 'Warning' $target "'$($p.title)' is granted $r directly: grant a group instead." (New-MgRemoveGrantFix $scope $p $r)
                }
            }
            # GV015: guests when the policy allows no external sharing
            if ((Test-MgIsGuest $p) -and $want -eq 'Disabled') {
                New-MgFinding 'GV015' 'Error' $target "Guest '$($p.title)' has $($g.Roles -join ', ') on a site that allows no external sharing."
            }
        }
        if ($scope.kind -eq 'List') {
            $allowed = @($allowedLists | Where-Object title -eq $scope.title) | Select-Object -First 1
            if (-not $allowed) {
                # GV010: list breaks inheritance without a reason in the policy
                New-MgFinding 'GV010' 'Warning' $target 'Unique permissions on a list the policy doesn''t list: it should inherit from the site.' (New-MgFix 'ResetListInheritance' @{ List = $scope.title })
            }
            else {
                # GV011: grants on an allowed list that the policy doesn't declare
                $declared = @{}
                foreach ($prop in @((Get-MgProp $allowed 'access' ([pscustomobject]@{})).PSObject.Properties)) { $declared[(Resolve-MgRoleName $prop.Name $Snapshot)] = $prop.Value }
                foreach ($g in @(Get-MgGrants $scope)) {
                    # forbidden principals (GV007) and people granted directly (GV008/GV009) are reported above
                    if ($g.Principal.title -in $forbidden -or $g.Principal.principalType -eq 'User') { continue }
                    foreach ($r in $g.Roles) {
                        if ($declared[$g.Principal.title] -ne $r) {
                            New-MgFinding 'GV011' 'Warning' $target "'$($g.Principal.title)' has $r; the policy declares $(if ($declared.Contains($g.Principal.title)) { $declared[$g.Principal.title] } else { 'no access' }) for it." (New-MgRemoveGrantFix $scope $g.Principal $r)
                        }
                    }
                }
            }
        }
    }

    # GV012-GV013: items with unique permissions
    $maxItems = Get-MgProp (Get-MgProp $Policy 'uniquePermissions') 'maxItemScopesPerList'
    foreach ($byList in @($Snapshot.scopes | Where-Object { $_.kind -eq 'Item' -and $_.unique } | Group-Object list)) {
        $allowed = @($allowedLists | Where-Object title -eq $byList.Name) | Select-Object -First 1
        if (-not $allowed -or -not (Get-MgProp $allowed 'allowItemScopes' $false)) {
            foreach ($i in $byList.Group) {
                New-MgFinding 'GV012' 'Warning' (Get-MgScopeTarget $i) 'Item breaks inheritance: someone shared it on its own.' (New-MgFix 'ResetItemInheritance' @{ List = $i.list; ItemId = $i.id })
            }
        }
        $n = $byList.Count
        if ($n -gt $script:SupportedScopesPerList) {
            New-MgFinding 'GV013' 'Error' "list '$($byList.Name)'" "$n items with unique permissions: above the supported 50,000."
        }
        elseif ($n -gt $script:RecommendedScopesPerList) {
            New-MgFinding 'GV013' 'Warning' "list '$($byList.Name)'" "$n items with unique permissions: above the recommended 5,000."
        }
        elseif ($null -ne $maxItems -and $n -gt $maxItems) {
            New-MgFinding 'GV013' 'Warning' "list '$($byList.Name)'" "$n items with unique permissions, the policy allows $maxItems."
        }
    }

    # GV014: sharing links
    $links = Get-MgProp $Policy 'sharingLinks'
    foreach ($l in @(Get-MgProp $Snapshot 'sharingLinks' @())) {
        $sev = if ($l.scope -in @(Get-MgProp $links 'forbiddenScopes' @())) { 'Error' } elseif ($l.scope -in @(Get-MgProp $links 'warnScopes' @())) { 'Warning' } else { $null }
        if ($sev) {
            New-MgFinding 'GV014' $sev "item '$($l.path)'" "$($l.scope) link ($($l.type))$(if (-not $l.expires) { ', no expiry' })." (New-MgFix 'RemoveSharingLink' @{ FileUrl = $l.fileUrl; LinkId = $l.id })
        }
    }

    # GV015: guests in groups
    if ($want -eq 'Disabled') {
        foreach ($g in @($Snapshot.groups)) {
            foreach ($m in @($g.members | Where-Object { Test-MgIsGuest $_ })) {
                New-MgFinding 'GV015' 'Error' "group '$($g.title)'" "Guest '$($m.title)' is a member on a site that allows no external sharing."
            }
        }
    }
}

function Get-MgScopeSummary {
    <#
    .SYNOPSIS  Counts of what the snapshot holds (for the report header).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Snapshot)
    $unique = @($Snapshot.scopes | Where-Object unique)
    [pscustomobject]@{
        Site         = $Snapshot.url
        Sharing      = Get-MgSharingLabel $Snapshot.sharingCapability
        DefaultLink  = "$($Snapshot.defaultSharingLinkType) / $($Snapshot.defaultLinkPermission)"
        Label        = if (Get-MgProp $Snapshot 'sensitivityLabel') { $Snapshot.sensitivityLabel } else { '(none)' }
        Groups       = @($Snapshot.groups).Count
        UniqueLists  = @($unique | Where-Object kind -eq 'List').Count
        UniqueItems  = @($unique | Where-Object kind -eq 'Item').Count
        SharingLinks = @(Get-MgProp $Snapshot 'sharingLinks' @()).Count
    }
}

function Get-MgRemediationPlan {
    <#
    .SYNOPSIS  Turns findings into an ordered, de-duplicated list of fixes. Site settings are merged into one call.
               Item resets come before list resets (a list reset clears item scopes anyway, see -ClearSubscopes).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings)
    $site = [ordered]@{}
    $rest = [System.Collections.Generic.List[object]]::new()
    $seen = @{}
    $resetLists = @($Findings | Where-Object { $_.Fix -and $_.Fix.Action -eq 'ResetListInheritance' } | ForEach-Object { $_.Fix.List })
    foreach ($f in @($Findings | Where-Object Fix)) {
        $fix = $f.Fix
        if ($fix.Action -eq 'SetSite') {
            foreach ($p in $fix.PSObject.Properties | Where-Object Name -ne 'Action') { $site[$p.Name] = $p.Value }
            continue
        }
        # a grant on a list that is going to be reset disappears with the reset
        if ($fix.Action -eq 'RemoveGrant' -and $fix.Kind -eq 'List' -and $fix.List -in $resetLists) { continue }
        $key = ($fix | ConvertTo-Json -Compress -Depth 5)
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $rest.Add([pscustomobject]@{ Order = @{ RemoveSharingLink = 1; ResetItemInheritance = 2; RemoveGrant = 3; ResetListInheritance = 4; RemoveGroupMember = 5 }[$fix.Action]; Rule = $f.Rule; Fix = $fix })
    }
    if ($site.Count) { [pscustomobject]@{ Rule = 'site'; Fix = (New-MgFix 'SetSite' $site) } }
    $rest | Sort-Object Order, { $_.Fix | ConvertTo-Json -Compress } | Select-Object Rule, Fix
}

# ---- Tenant: snapshot ----------------------------------------------------------------------------------------------

function Get-MgRoleAssignment {
    <#
    .SYNOPSIS  Loads the role assignments of a CSOM securable object (web, list, list item) as plain objects.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$ClientObject, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $ras = Get-PnPProperty -ClientObject $ClientObject -Property RoleAssignments @c
    foreach ($ra in $ras) {
        $null = Get-PnPProperty -ClientObject $ra -Property Member, RoleDefinitionBindings @c
        [pscustomobject]@{
            title         = $ra.Member.Title
            loginName     = $ra.Member.LoginName
            principalType = "$($ra.Member.PrincipalType)"
            roles         = @($ra.RoleDefinitionBindings | ForEach-Object Name)
        }
    }
}

function ConvertTo-MgMember($User) {
    [pscustomobject]@{ title = $User.Title; loginName = $User.LoginName; principalType = "$($User.PrincipalType)" }
}

function Get-MgPermissionSnapshot {
    <#
    .SYNOPSIS  Reads what a site really has. Needs SharePoint admin (site sharing settings) and site admin.
    .PARAMETER MaxFilesForLinks  Sharing links are read per file (Microsoft Graph); larger libraries are skipped.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$SiteUrl, [int]$MaxFilesForLinks = 500, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $site = Get-PnPTenantSite -Identity $SiteUrl @c
    $web = Get-PnPWeb -Includes HasUniqueRoleAssignments, ServerRelativeUrl, Title @c
    $assoc = [ordered]@{}
    foreach ($r in 'Owners', 'Members', 'Visitors') {
        $sw = @{ "Associated$($r.TrimEnd('s'))Group" = $true }
        $g = Get-PnPGroup @sw @c
        if ($g) { $assoc[$r] = $g.Title }
    }
    $groups = foreach ($g in @(Get-PnPGroup @c)) {
        [pscustomobject]@{ title = $g.Title; members = @(Get-PnPGroupMember -Group $g.Title @c | ForEach-Object { ConvertTo-MgMember $_ }) }
    }
    $scopes = [System.Collections.Generic.List[object]]::new()
    $scopes.Add([pscustomobject]@{ kind = 'Web'; path = '/'; title = $web.Title; unique = $true; assignments = @(Get-MgRoleAssignment -ClientObject $web @c) })
    $links = [System.Collections.Generic.List[object]]::new()
    foreach ($list in @(Get-PnPList -Includes HasUniqueRoleAssignments, ItemCount, Hidden, BaseType @c | Where-Object { -not $_.Hidden })) {
        $scopes.Add([pscustomobject]@{
                kind = 'List'; path = $list.Title; title = $list.Title; unique = [bool]$list.HasUniqueRoleAssignments; itemCount = $list.ItemCount
                assignments = @(if ($list.HasUniqueRoleAssignments) { Get-MgRoleAssignment -ClientObject $list @c })
            })
        if ($list.ItemCount -eq 0) { continue }
        $items = @(Get-PnPListItem -List $list.Id -PageSize 500 -Fields 'FileRef', 'FileLeafRef', 'FSObjType' -Includes HasUniqueRoleAssignments @c)
        foreach ($it in $items | Where-Object { $_.HasUniqueRoleAssignments }) {
            $scopes.Add([pscustomobject]@{
                    kind = 'Item'; path = $it['FileRef']; list = $list.Title; id = $it.Id; unique = $true
                    assignments = @(Get-MgRoleAssignment -ClientObject $it @c)
                })
        }
        if ("$($list.BaseType)" -eq 'DocumentLibrary' -and $items.Count -le $MaxFilesForLinks) {
            foreach ($it in $items | Where-Object { "$($_['FSObjType'])" -eq '0' }) {
                foreach ($p in @(Get-PnPFileSharingLink -Identity $it['FileRef'] @c | Where-Object { $null -ne $_.Link })) {
                    $links.Add([pscustomobject]@{
                            path = $it['FileLeafRef']; fileUrl = $it['FileRef']; list = $list.Title; id = $p.Id
                            scope = "$($p.Link.Scope)"; type = "$($p.Link.Type)"
                            expires = if ($p.ExpirationDateTime -and $p.ExpirationDateTime -gt [datetime]'1900-01-01') { $p.ExpirationDateTime.ToString('yyyy-MM-dd') } else { $null }
                        })
                }
            }
        }
    }
    [pscustomobject]@{
        url                    = $SiteUrl
        title                  = $web.Title
        sharingCapability      = "$($site.SharingCapability)"
        defaultSharingLinkType = "$($site.DefaultSharingLinkType)"
        defaultLinkPermission  = "$($site.DefaultLinkPermission)"
        sensitivityLabel       = if ($site.SensitivityLabel -and $site.SensitivityLabel -ne [guid]::Empty.ToString()) { "$($site.SensitivityLabel)" } else { $null }
        siteAdmins             = @(Get-PnPSiteCollectionAdmin @c | ForEach-Object { ConvertTo-MgMember $_ })
        associatedGroups       = [pscustomobject]$assoc
        groups                 = @($groups)
        scopes                 = $scopes.ToArray()
        sharingLinks           = $links.ToArray()
    }
}

# ---- Tenant: remediation -------------------------------------------------------------------------------------------

function Invoke-MgRemediation {
    <#
    .SYNOPSIS  Applies a remediation plan with the real PnP cmdlets. Supports -WhatIf. Returns one row per fix.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string]$SiteUrl, [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Plan, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    foreach ($step in $Plan) {
        $f = $step.Fix
        $detail = ($f.PSObject.Properties | Where-Object Name -ne 'Action' | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ' '
        $row = [pscustomobject]@{ Action = $f.Action; Rule = $step.Rule; Detail = $detail; Done = $false }
        if (-not $PSCmdlet.ShouldProcess($detail, $f.Action)) { $row; continue }
        switch ($f.Action) {
            'SetSite' {
                $p = @{}
                foreach ($k in 'SharingCapability', 'DefaultSharingLinkType', 'DefaultLinkPermission', 'SensitivityLabel') {
                    if ($f.PSObject.Properties[$k]) { $p[$k] = $f.$k }
                }
                Set-PnPTenantSite -Identity $SiteUrl @p @c
            }
            'RemoveSharingLink' { Remove-PnPFileSharingLink -FileUrl $f.FileUrl -Identity $f.LinkId -Force @c }
            'ResetItemInheritance' { Set-PnPListItemPermission -List $f.List -Identity $f.ItemId -InheritPermissions @c }
            'ResetListInheritance' { Set-PnPList -Identity $f.List -ResetRoleInheritance @c }
            'RemoveGroupMember' { Remove-PnPGroupMember -Group $f.Group -LoginName $f.LoginName @c }
            'RemoveGrant' {
                $who = if ($f.PSObject.Properties['Group']) { @{ Group = $f.Group } } else { @{ User = $f.User } }
                switch ($f.Kind) {
                    'Web' { Set-PnPWebPermission @who -RemoveRole $f.Role @c }
                    'List' { Set-PnPListPermission -Identity $f.List @who -RemoveRole $f.Role @c }
                    'Item' { Set-PnPListItemPermission -List $f.List -Identity $f.ItemId @who -RemoveRole $f.Role @c }
                }
            }
            default { throw "Unknown fix '$($f.Action)'." }
        }
        $row.Done = $true
        $row
    }
}

Export-ModuleMember -Function Import-MgJson, Compare-MgSharingCapability, Get-MgSharingLabel, Test-MgGovernancePolicy,
    Test-MgPermissionSnapshot, Get-MgScopeSummary, Get-MgRemediationPlan, Get-MgRoleAssignment, Get-MgPermissionSnapshot,
    Invoke-MgRemediation
