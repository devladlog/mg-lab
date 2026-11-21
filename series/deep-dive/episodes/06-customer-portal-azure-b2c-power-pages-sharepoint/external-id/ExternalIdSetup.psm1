# Sets up the Microsoft Entra External ID side of the customer portal, in the EXTERNAL tenant, with Microsoft Graph:
#   1. app registration for the Power Pages site (web redirect URI = the site's reply URL, ID + access tokens on)
#   2. its service principal (a user flow can only be linked to an app that has one)
#   3. delegated openid + profile with admin consent (looked up by name, no hard-coded permission IDs)
#   4. a sign-up/sign-in user flow (email with password, collects display name)
#   5. links the app to the user flow (an app can be linked to ONE user flow)
# Then prints the values the Power Pages "Microsoft Entra External ID" provider asks for. Idempotent.
# Uses Invoke-MgGraphRequest (Microsoft.Graph.Authentication).

$script:Graph = 'https://graph.microsoft.com/v1.0'
$script:GraphAppId = '00000003-0000-0000-c000-000000000000'

function Invoke-ExtGraph {
    [CmdletBinding()]
    param([ValidateSet('GET', 'POST', 'PATCH')] [string] $Method = 'GET', [Parameter(Mandatory)] [string] $Uri, $Body)
    $params = @{ Method = $Method; Uri = $(if ($Uri -match '^https://') { $Uri } else { $script:Graph + $Uri }); OutputType = 'PSObject' }
    if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json -Depth 20 -Compress); $params.ContentType = 'application/json' }
    Invoke-MgGraphRequest @params
}

function Get-ExtAll {
    <# GET with @odata.nextLink paging. #>
    param([Parameter(Mandatory)] [string] $Uri)
    $items = @()
    $next = $Uri
    while ($next) {
        $r = Invoke-ExtGraph -Uri $next
        $items += @($r.value)
        $next = if ($r.PSObject.Properties['@odata.nextLink']) { $r.'@odata.nextLink' } else { $null }
    }
    return $items
}

function Get-ExtTenantInfo {
    <# Tenant ID and the subdomain of the initial domain (<subdomain>.onmicrosoft.com), used in <subdomain>.ciamlogin.com. #>
    [CmdletBinding()]
    param()
    $org = @((Invoke-ExtGraph -Uri '/organization?$select=id,displayName,verifiedDomains').value)[0]
    $initial = @($org.verifiedDomains | Where-Object { $_.isInitial })[0].name
    if (-not $initial) { throw 'No initial domain found on the tenant.' }
    return [pscustomobject]@{ TenantId = $org.id; DisplayName = $org.displayName; Subdomain = $initial.Split('.')[0] }
}

function Test-ExtReplyUrl {
    [CmdletBinding()]
    [OutputType([bool])]
    param([Parameter(Mandatory)] [string] $ReplyUrl)
    $u = $null
    if (-not [uri]::TryCreate($ReplyUrl, [UriKind]::Absolute, [ref]$u)) { return $false }
    return $u.Scheme -eq 'https' -and -not $u.Query -and -not $u.Fragment
}

function Set-ExtPortalApp {
    <# Creates the app registration, or adds what's missing to the existing one. Returns @{ App; Result }. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [string] $DisplayName, [Parameter(Mandatory)] [string] $ReplyUrl)

    if (-not (Test-ExtReplyUrl $ReplyUrl)) { throw "Reply URL '$ReplyUrl' must be an absolute https URL without query or fragment (copy it from the Power Pages wizard)." }
    $filter = [uri]::EscapeDataString("displayName eq '$($DisplayName.Replace("'", "''"))'")
    $apps = @(Get-ExtAll -Uri "/applications?`$filter=$filter&`$select=id,appId,displayName,web")
    if ($apps.Count -gt 1) { throw "More than one app registration is called '$DisplayName'; rename or delete the extra ones." }
    if ($apps.Count -eq 0) {
        if (-not $PSCmdlet.ShouldProcess($DisplayName, 'Create app registration')) { return [pscustomobject]@{ App = $null; Result = 'WhatIf' } }
        $app = Invoke-ExtGraph -Method POST -Uri '/applications' -Body @{
            displayName    = $DisplayName
            signInAudience = 'AzureADMyOrg'
            web            = @{ redirectUris = @($ReplyUrl); implicitGrantSettings = @{ enableIdTokenIssuance = $true; enableAccessTokenIssuance = $true } }
        }
        return [pscustomobject]@{ App = $app; Result = 'Added' }
    }
    $app = $apps[0]
    $uris = @($app.web.redirectUris)
    $needsUri = $uris -notcontains $ReplyUrl
    $needsTokens = -not ($app.web.implicitGrantSettings.enableIdTokenIssuance -and $app.web.implicitGrantSettings.enableAccessTokenIssuance)
    if (-not $needsUri -and -not $needsTokens) { return [pscustomobject]@{ App = $app; Result = 'Exists' } }
    if ($PSCmdlet.ShouldProcess($DisplayName, 'Update redirect URI / token settings')) {
        Invoke-ExtGraph -Method PATCH -Uri "/applications/$($app.id)" -Body @{
            web = @{ redirectUris = @($uris + $(if ($needsUri) { $ReplyUrl }) | Where-Object { $_ }); implicitGrantSettings = @{ enableIdTokenIssuance = $true; enableAccessTokenIssuance = $true } }
        } | Out-Null
        return [pscustomobject]@{ App = $app; Result = 'Updated' }
    }
    return [pscustomobject]@{ App = $app; Result = 'WhatIf' }
}

function Set-ExtServicePrincipal {
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [string] $AppId)
    $sp = @(Get-ExtAll -Uri ("/servicePrincipals?`$filter=" + [uri]::EscapeDataString("appId eq '$AppId'")))
    if ($sp.Count) { return [pscustomobject]@{ ServicePrincipal = $sp[0]; Result = 'Exists' } }
    if (-not $PSCmdlet.ShouldProcess($AppId, 'Create service principal')) { return [pscustomobject]@{ ServicePrincipal = $null; Result = 'WhatIf' } }
    return [pscustomobject]@{ ServicePrincipal = (Invoke-ExtGraph -Method POST -Uri '/servicePrincipals' -Body @{ appId = $AppId }); Result = 'Added' }
}

function Grant-ExtSignInConsent {
    <# Admin consent for delegated openid + profile on Microsoft Graph (requiredResourceAccess + an AllPrincipals grant). #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] $App, [Parameter(Mandatory)] $ServicePrincipal, [string[]] $Scopes = @('openid', 'profile'))

    $graph = @(Get-ExtAll -Uri ("/servicePrincipals?`$filter=" + [uri]::EscapeDataString("appId eq '$script:GraphAppId'")))[0]
    $access = foreach ($s in $Scopes) {
        $scope = @($graph.oauth2PermissionScopes | Where-Object value -eq $s)
        if ($scope.Count -ne 1) { throw "Microsoft Graph has no delegated permission '$s'." }
        @{ id = $scope[0].id; type = 'Scope' }
    }
    $grants = @(Get-ExtAll -Uri ("/oauth2PermissionGrants?`$filter=" + [uri]::EscapeDataString("clientId eq '$($ServicePrincipal.id)'")))
    $existing = $grants | Where-Object { $_.resourceId -eq $graph.id -and $_.consentType -eq 'AllPrincipals' } | Select-Object -First 1
    $have = if ($existing) { @(([string]$existing.scope).Split(' ', [StringSplitOptions]::RemoveEmptyEntries)) } else { @() }
    $missing = @($Scopes | Where-Object { $have -notcontains $_ })
    if (-not $missing.Count) { return [pscustomobject]@{ Result = 'Exists'; Scope = ($have -join ' ') } }
    if (-not $PSCmdlet.ShouldProcess($App.displayName, "Grant admin consent: $($Scopes -join ', ')")) { return [pscustomobject]@{ Result = 'WhatIf'; Scope = '' } }
    Invoke-ExtGraph -Method PATCH -Uri "/applications/$($App.id)" -Body @{ requiredResourceAccess = @(@{ resourceAppId = $script:GraphAppId; resourceAccess = @($access) }) } | Out-Null
    $scope = (@($have) + $missing) -join ' '
    if ($existing) {
        Invoke-ExtGraph -Method PATCH -Uri "/oauth2PermissionGrants/$($existing.id)" -Body @{ scope = $scope } | Out-Null
    } else {
        Invoke-ExtGraph -Method POST -Uri '/oauth2PermissionGrants' -Body @{ clientId = $ServicePrincipal.id; consentType = 'AllPrincipals'; resourceId = $graph.id; scope = $scope } | Out-Null
    }
    return [pscustomobject]@{ Result = 'Added'; Scope = $scope }
}

function New-ExtUserFlowBody {
    <# Same shape as Learn's "Create authenticationEventsFlow" example: email + password, sign-up allowed, collect display name. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $DisplayName)
    return [ordered]@{
        '@odata.type'                   = '#microsoft.graph.externalUsersSelfServiceSignUpEventsFlow'
        displayName                     = $DisplayName
        onAuthenticationMethodLoadStart = [ordered]@{
            '@odata.type'     = '#microsoft.graph.onAuthenticationMethodLoadStartExternalUsersSelfServiceSignUp'
            identityProviders = @(@{ id = 'EmailPassword-OAUTH' })
        }
        onInteractiveAuthFlowStart      = [ordered]@{
            '@odata.type'   = '#microsoft.graph.onInteractiveAuthFlowStartExternalUsersSelfServiceSignUp'
            isSignUpAllowed = $true
        }
        onAttributeCollection           = [ordered]@{
            '@odata.type'           = '#microsoft.graph.onAttributeCollectionExternalUsersSelfServiceSignUp'
            attributes              = @(
                [ordered]@{ id = 'email'; displayName = 'Email Address'; description = 'Email address of the user'; userFlowAttributeType = 'builtIn'; dataType = 'string' },
                [ordered]@{ id = 'displayName'; displayName = 'Display Name'; description = 'Display Name of the User.'; userFlowAttributeType = 'builtIn'; dataType = 'string' })
            attributeCollectionPage = @{ views = @(@{ inputs = @(
                [ordered]@{ attribute = 'email'; label = 'Email Address'; inputType = 'Text'; hidden = $true; editable = $false; writeToDirectory = $true; required = $true },
                [ordered]@{ attribute = 'displayName'; label = 'Your name'; inputType = 'text'; hidden = $false; editable = $true; writeToDirectory = $true; required = $true }) }) }
        }
    }
}

function Set-ExtUserFlow {
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [string] $DisplayName)
    $flows = @(Get-ExtAll -Uri '/identity/authenticationEventsFlows') | Where-Object { $_.displayName -eq $DisplayName }
    if (@($flows).Count -gt 1) { throw "More than one user flow is called '$DisplayName'." }
    if (@($flows).Count -eq 1) { return [pscustomobject]@{ Flow = @($flows)[0]; Result = 'Exists' } }
    if (-not $PSCmdlet.ShouldProcess($DisplayName, 'Create user flow')) { return [pscustomobject]@{ Flow = $null; Result = 'WhatIf' } }
    return [pscustomobject]@{ Flow = (Invoke-ExtGraph -Method POST -Uri '/identity/authenticationEventsFlows' -Body (New-ExtUserFlowBody -DisplayName $DisplayName)); Result = 'Added' }
}

function Add-ExtAppToUserFlow {
    <# Links the app to the flow. Refuses if the app already belongs to another flow (one flow per app). #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [string] $FlowId, [Parameter(Mandatory)] [string] $AppId)
    foreach ($flow in @(Get-ExtAll -Uri '/identity/authenticationEventsFlows')) {
        $linked = @(Get-ExtAll -Uri "/identity/authenticationEventsFlows/$($flow.id)/conditions/applications/includeApplications")
        if ($linked.appId -contains $AppId) {
            if ($flow.id -eq $FlowId) { return [pscustomobject]@{ Result = 'Exists' } }
            throw "The app is already linked to user flow '$($flow.displayName)'. An application can only be linked to one user flow: unlink it there first."
        }
    }
    if (-not $PSCmdlet.ShouldProcess($AppId, "Link to user flow $FlowId")) { return [pscustomobject]@{ Result = 'WhatIf' } }
    Invoke-ExtGraph -Method POST -Uri "/identity/authenticationEventsFlows/$FlowId/conditions/applications/includeApplications" -Body @{
        '@odata.type' = '#microsoft.graph.authenticationConditionApplication'; appId = $AppId } | Out-Null
    return [pscustomobject]@{ Result = 'Added' }
}

function Get-ExtPowerPagesSettings {
    <# Values for Power Pages > Security > Identity providers > Microsoft Entra External ID. Compare Authority with the
       app's Endpoints blade and use the blade's value if it differs. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $TenantId, [Parameter(Mandatory)] [string] $Subdomain, [Parameter(Mandatory)] [string] $AppId, [Parameter(Mandatory)] [string] $ReplyUrl)
    $authority = "https://$Subdomain.ciamlogin.com/$TenantId/v2.0"
    return [ordered]@{
        'Client ID'        = $AppId
        'Authority'        = $authority
        'Redirect URL'     = $ReplyUrl
        'Metadata address' = "$authority/.well-known/openid-configuration"
    }
}

function Initialize-ExtPortalIdentity {
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [string] $ReplyUrl, [string] $AppName = 'Contoso support portal', [string] $FlowName = 'Contoso support sign-up and sign-in')

    $tenant = Get-ExtTenantInfo
    $steps = [System.Collections.Generic.List[object]]::new()
    $app = Set-ExtPortalApp -DisplayName $AppName -ReplyUrl $ReplyUrl -WhatIf:$WhatIfPreference
    $steps.Add([pscustomobject]@{ Step = 'App registration'; Result = $app.Result })
    if (-not $app.App) { return [pscustomobject]@{ Steps = $steps; Settings = $null } }
    $sp = Set-ExtServicePrincipal -AppId $app.App.appId -WhatIf:$WhatIfPreference
    $steps.Add([pscustomobject]@{ Step = 'Service principal'; Result = $sp.Result })
    if ($sp.ServicePrincipal) {
        $steps.Add([pscustomobject]@{ Step = 'Consent openid profile'; Result = (Grant-ExtSignInConsent -App $app.App -ServicePrincipal $sp.ServicePrincipal -WhatIf:$WhatIfPreference).Result })
    }
    $flow = Set-ExtUserFlow -DisplayName $FlowName -WhatIf:$WhatIfPreference
    $steps.Add([pscustomobject]@{ Step = 'User flow'; Result = $flow.Result })
    if ($flow.Flow -and $sp.ServicePrincipal) {
        $steps.Add([pscustomobject]@{ Step = 'App linked to user flow'; Result = (Add-ExtAppToUserFlow -FlowId $flow.Flow.id -AppId $app.App.appId -WhatIf:$WhatIfPreference).Result })
    }
    return [pscustomobject]@{ Steps = $steps; Settings = (Get-ExtPowerPagesSettings -TenantId $tenant.TenantId -Subdomain $tenant.Subdomain -AppId $app.App.appId -ReplyUrl $ReplyUrl) }
}

Export-ModuleMember -Function Invoke-ExtGraph, Get-ExtAll, Get-ExtTenantInfo, Test-ExtReplyUrl, Set-ExtPortalApp, Set-ExtServicePrincipal,
    Grant-ExtSignInConsent, New-ExtUserFlowBody, Set-ExtUserFlow, Add-ExtAppToUserFlow, Get-ExtPowerPagesSettings, Initialize-ExtPortalIdentity
