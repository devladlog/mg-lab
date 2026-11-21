# Pester tests for external-id/ExternalIdSetup.psm1. Invoke-MgGraphRequest is replaced by an in-memory external
# tenant (tests only) that follows the documented rules: one user flow per app, the app needs a service principal.
BeforeAll {
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        function global:Invoke-MgGraphRequest { [CmdletBinding()] param($Method, $Uri, $Body, $OutputType, $ContentType) }
    }
    Import-Module (Join-Path $PSScriptRoot '..' 'external-id' 'ExternalIdSetup.psm1') -Force

    class FakeTenant {
        [System.Collections.Generic.List[hashtable]] $Apps = [System.Collections.Generic.List[hashtable]]::new()
        [System.Collections.Generic.List[hashtable]] $Sps = [System.Collections.Generic.List[hashtable]]::new()
        [System.Collections.Generic.List[hashtable]] $Flows = [System.Collections.Generic.List[hashtable]]::new()
        [System.Collections.Generic.List[hashtable]] $Grants = [System.Collections.Generic.List[hashtable]]::new()
        [System.Collections.Generic.List[string]] $Writes = [System.Collections.Generic.List[string]]::new()
        [int] $PageSize = 100

        FakeTenant() {
            $this.Sps.Add(@{ id = 'graph-sp'; appId = '00000003-0000-0000-c000-000000000000'; oauth2PermissionScopes = @(
                @{ id = 's-openid'; value = 'openid' }, @{ id = 's-profile'; value = 'profile' }, @{ id = 's-user'; value = 'User.Read' }) })
        }
        [object] Out($o) { return ($o | ConvertTo-Json -Depth 20 | ConvertFrom-Json -Depth 20) }
        [object] Page([object[]] $items) { return $this.Out(@{ value = @($items) }) }
        [string] Eq([string] $uri) {
            $q = [uri]::UnescapeDataString(($uri -split '\$filter=')[1].Split('&')[0])
            if ($q -notmatch "eq '(?<v>(?:[^']|'')*)'") { throw "can't parse $q" }
            return $Matches['v'].Replace("''", "'")
        }
        [object] Invoke([string] $method, [string] $uri, [string] $body) {
            $path = $uri -replace '^https://graph.microsoft.com/v1.0', ''
            $b = if ($body) { $body | ConvertFrom-Json -AsHashtable -Depth 20 } else { $null }
            if ($method -ne 'GET') { $this.Writes.Add("$method $($path.Split('?')[0])") }
            switch -Regex ($path) {
                '^/organization' { return $this.Page(@(@{ id = '00000000-0000-0000-0000-0000000000e1'; displayName = 'Contoso customers'
                    verifiedDomains = @(@{ name = 'contosocustomers.onmicrosoft.com'; isInitial = $true }) })) }
                '^/applications\?' { $v = $this.Eq($uri); return $this.Page(@($this.Apps | Where-Object { $_.displayName -eq $v })) }
                '^/applications$' {
                    $app = @{ id = "app-$($this.Apps.Count + 1)"; appId = "00000000-0000-0000-0000-00000000a00$($this.Apps.Count + 1)"; displayName = $b.displayName; web = $b.web }
                    $this.Apps.Add($app); return $this.Out($app)
                }
                '^/applications/(?<id>[^/?]+)$' {
                    $app = $this.Apps | Where-Object id -eq $Matches['id']
                    foreach ($k in $b.Keys) { $app[$k] = $b[$k] }
                    return $null
                }
                '^/servicePrincipals\?' { $v = $this.Eq($uri); return $this.Page(@($this.Sps | Where-Object { $_.appId -eq $v })) }
                '^/servicePrincipals$' { $sp = @{ id = "sp-$($b.appId)"; appId = $b.appId }; $this.Sps.Add($sp); return $this.Out($sp) }
                '^/oauth2PermissionGrants\?' { $v = $this.Eq($uri); return $this.Page(@($this.Grants | Where-Object { $_.clientId -eq $v })) }
                '^/oauth2PermissionGrants$' { $g = $b.Clone(); $g.id = "g-$($this.Grants.Count + 1)"; $this.Grants.Add($g); return $this.Out($g) }
                '^/oauth2PermissionGrants/(?<id>[^/]+)$' { ($this.Grants | Where-Object id -eq $Matches['id']).scope = $b.scope; return $null }
                '^/identity/authenticationEventsFlows$' {
                    if ($method -eq 'POST') {
                        $f = $b.Clone(); $f.id = "flow-$($this.Flows.Count + 1)"; $f.apps = [System.Collections.Generic.List[string]]::new()
                        $this.Flows.Add($f); return $this.Out(@{ id = $f.id; displayName = $f.displayName })
                    }
                    return $this.Page(@($this.Flows | ForEach-Object { @{ id = $_.id; displayName = $_.displayName } }))
                }
                '^/identity/authenticationEventsFlows/(?<id>[^/]+)/conditions/applications/includeApplications$' {
                    $f = $this.Flows | Where-Object id -eq $Matches['id']
                    if ($method -eq 'POST') {
                        if (-not ($this.Sps | Where-Object appId -eq $b.appId)) { throw 'The app must have an associated service principal.' }
                        if ($this.Flows | Where-Object { $_.apps -contains $b.appId }) { throw 'An application can only be linked to one user flow.' }
                        $f.apps.Add($b.appId); return $this.Out(@{ appId = $b.appId })
                    }
                    return $this.Page(@($f.apps | ForEach-Object { @{ appId = $_ } }))
                }
            }
            throw "FakeTenant: no route for $method $path"
        }
    }
    $script:Reply = 'https://contoso-support.powerappsportals.com/signin-openid_1'
}

Describe 'External ID setup' {
    BeforeEach {
        $global:ExtFake = [FakeTenant]::new()
        Mock -ModuleName ExternalIdSetup Invoke-MgGraphRequest { $global:ExtFake.Invoke($Method, $Uri, $Body) }
    }
    AfterAll { Remove-Variable -Name ExtFake -Scope Global -ErrorAction SilentlyContinue }

    It 'sets up an empty external tenant and prints the Power Pages values' {
        $r = Initialize-ExtPortalIdentity -ReplyUrl $script:Reply
        ($r.Steps | ForEach-Object Result) | Should -Be @('Added', 'Added', 'Added', 'Added', 'Added')
        $app = $global:ExtFake.Apps[0]
        $app.web.redirectUris | Should -Be @($script:Reply)
        $app.web.implicitGrantSettings.enableIdTokenIssuance | Should -BeTrue
        $app.web.implicitGrantSettings.enableAccessTokenIssuance | Should -BeTrue
        $app.requiredResourceAccess[0].resourceAccess.id | Should -Be @('s-openid', 's-profile')
        $global:ExtFake.Grants[0].scope | Should -Be 'openid profile'
        $global:ExtFake.Grants[0].consentType | Should -Be 'AllPrincipals'
        $global:ExtFake.Flows[0].apps | Should -Be @($app.appId)
        $r.Settings['Client ID'] | Should -Be $app.appId
        $r.Settings['Authority'] | Should -Be 'https://contosocustomers.ciamlogin.com/00000000-0000-0000-0000-0000000000e1/v2.0'
        $r.Settings['Metadata address'] | Should -Be 'https://contosocustomers.ciamlogin.com/00000000-0000-0000-0000-0000000000e1/v2.0/.well-known/openid-configuration'
        $r.Settings['Redirect URL'] | Should -Be $script:Reply
    }
    It 'is idempotent: a second run writes nothing' {
        Initialize-ExtPortalIdentity -ReplyUrl $script:Reply | Out-Null
        $writes = $global:ExtFake.Writes.Count
        $r = Initialize-ExtPortalIdentity -ReplyUrl $script:Reply
        ($r.Steps | ForEach-Object Result) | Should -Be @('Exists', 'Exists', 'Exists', 'Exists', 'Exists')
        $global:ExtFake.Writes.Count | Should -Be $writes
    }
    It 'adds a missing reply URL (custom domain) to the existing app without dropping the old one' {
        Initialize-ExtPortalIdentity -ReplyUrl $script:Reply | Out-Null
        (Set-ExtPortalApp -DisplayName 'Contoso support portal' -ReplyUrl 'https://support.contoso.com/signin-openid_1').Result | Should -Be 'Updated'
        $global:ExtFake.Apps[0].web.redirectUris | Should -Be @($script:Reply, 'https://support.contoso.com/signin-openid_1')
    }
    It 'refuses to steal an app that another user flow already owns' {
        Initialize-ExtPortalIdentity -ReplyUrl $script:Reply | Out-Null
        $other = (Set-ExtUserFlow -DisplayName 'Some other flow').Flow
        { Add-ExtAppToUserFlow -FlowId $other.id -AppId $global:ExtFake.Apps[0].appId } | Should -Throw '*only be linked to one user flow*'
    }
    It 'completes a partial consent instead of creating a second grant' {
        $r = Initialize-ExtPortalIdentity -ReplyUrl $script:Reply
        $global:ExtFake.Grants[0].scope = 'openid'
        $sp = $global:ExtFake.Sps | Where-Object appId -eq $global:ExtFake.Apps[0].appId
        (Grant-ExtSignInConsent -App ([pscustomobject]$global:ExtFake.Apps[0]) -ServicePrincipal ([pscustomobject]$sp)).Result | Should -Be 'Added'
        $global:ExtFake.Grants.Count | Should -Be 1
        $global:ExtFake.Grants[0].scope | Should -Be 'openid profile'
    }
    It 'rejects reply URLs that are not https or carry a query' {
        { Set-ExtPortalApp -DisplayName 'x' -ReplyUrl 'http://contoso-support.powerappsportals.com/signin-openid_1' } | Should -Throw '*https*'
        { Set-ExtPortalApp -DisplayName 'x' -ReplyUrl 'https://a.b/c?x=1' } | Should -Throw '*https*'
        Test-ExtReplyUrl $script:Reply | Should -BeTrue
    }
    It '-WhatIf writes nothing' {
        $r = Initialize-ExtPortalIdentity -ReplyUrl $script:Reply -WhatIf
        $global:ExtFake.Writes.Count | Should -Be 0
        $r.Steps[0].Result | Should -Be 'WhatIf'
    }
    It 'builds the user flow like the Learn example: email with password, sign-up on, email + display name' {
        $b = New-ExtUserFlowBody -DisplayName 'f' | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable
        $b['@odata.type'] | Should -Be '#microsoft.graph.externalUsersSelfServiceSignUpEventsFlow'
        $b.onAuthenticationMethodLoadStart.identityProviders.id | Should -Be @('EmailPassword-OAUTH')
        $b.onInteractiveAuthFlowStart.isSignUpAllowed | Should -BeTrue
        $b.onAttributeCollection.attributes.id | Should -Be @('email', 'displayName')
        $b.onAttributeCollection.attributeCollectionPage.views[0].inputs.attribute | Should -Be @('email', 'displayName')
    }
    It 'follows @odata.nextLink' {
        $script:calls = 0
        Mock -ModuleName ExternalIdSetup Invoke-MgGraphRequest {
            $script:calls++
            if ($Uri -like '*page2*') { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 2 }) } }
            [pscustomobject]@{ value = @([pscustomobject]@{ id = 1 }); '@odata.nextLink' = 'https://graph.microsoft.com/v1.0/x?page2' }
        }
        (Get-ExtAll -Uri '/x').id | Should -Be @(1, 2)
    }
    It 'the entry script parses' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..' 'external-id' 'Initialize-ExternalId.ps1'), [ref]$null, [ref]$errors) | Out-Null
        $errors | Should -BeNullOrEmpty
    }
}
