BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'scripts' 'SaasLab.psm1') -Force
    $script:Api = [guid]'00000000-0000-0000-0000-0000000000a1'
    $script:Cli = [guid]'00000000-0000-0000-0000-0000000000a2'
    $script:Scope = [guid]'00000000-0000-0000-0000-0000000000c1'
    $script:Role = [guid]'00000000-0000-0000-0000-0000000000c2'
    function New-FakeToken([hashtable] $claims) {
        $b64 = { param($o) [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($o | ConvertTo-Json -Compress))).TrimEnd('=').Replace('+', '-').Replace('/', '_') }
        "$(& $b64 @{alg='none'}).$(& $b64 $claims).sig"
    }
}

Describe 'App registration bodies' {
    It 'makes the API multitenant, v2.0, with one delegated scope and one provider-only role' {
        $b = New-SaasApiAppBody -DisplayName 'contoso-saas-api' -ScopeId $Scope -RoleId $Role -KnownClientIds $Cli
        $b.signInAudience | Should -Be 'AzureADMultipleOrgs'
        $b.api.requestedAccessTokenVersion | Should -Be 2
        $b.api.knownClientApplications | Should -Be @($Cli.ToString())
        $b.api.oauth2PermissionScopes.Count | Should -Be 1
        $b.api.oauth2PermissionScopes[0].value | Should -Be 'Requests.ReadWrite'
        $b.api.oauth2PermissionScopes[0].type | Should -Be 'User'
        $b.appRoles.Count | Should -Be 1
        $b.appRoles[0].value | Should -Be 'Platform.Admin'
        $b.appRoles[0].allowedMemberTypes | Should -Be @('User')
    }
    It 'serialises to the JSON shape Graph expects' {
        $json = New-SaasApiAppBody -DisplayName 'x' -ScopeId $Scope -RoleId $Role | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $json.api.oauth2PermissionScopes[0].id | Should -Be $Scope.ToString()
        $json.appRoles[0].id | Should -Be $Role.ToString()
    }
    It 'makes the client a multitenant public client that asks for the API scope' {
        $b = New-SaasCliAppBody -DisplayName 'contoso-saas-cli' -ApiAppId $Api -ScopeId $Scope
        $b.signInAudience | Should -Be 'AzureADMultipleOrgs'
        $b.isFallbackPublicClient | Should -BeTrue
        $b.requiredResourceAccess[0].resourceAppId | Should -Be $Api.ToString()
        $b.requiredResourceAccess[0].resourceAccess[0].id | Should -Be $Scope.ToString()
        $b.requiredResourceAccess[0].resourceAccess[0].type | Should -Be 'Scope'
    }
    It 'builds the v2.0 admin consent URL for one customer tenant' {
        $u = Get-AdminConsentUrl -CustomerTenantId '00000000-0000-0000-0000-0000000000b1' -CliClientId $Cli -ApiClientId $Api
        $u | Should -BeLike 'https://login.microsoftonline.com/00000000-0000-0000-0000-0000000000b1/v2.0/adminconsent?client_id=00000000-0000-0000-0000-0000000000a2&scope=api%3A%2F%2F00000000-0000-0000-0000-0000000000a1%2F.default&redirect_uri=*'
    }
}

Describe 'Device code sign-in' {
    BeforeEach {
        Mock -ModuleName SaasLab Start-Sleep {}
        Mock -ModuleName SaasLab Write-Host {}
    }
    It 'polls until the user has signed in and returns the access token' {
        $script:calls = 0
        Mock -ModuleName SaasLab Invoke-RestMethod {
            if ($Uri -like '*/devicecode') { return [pscustomobject]@{ device_code = 'dc'; user_code = 'ABC'; message = 'Go to the page and enter ABC'; interval = 1; expires_in = 900 } }
            $script:calls++
            if ($script:calls -lt 3) { [pscustomobject]@{ error = 'authorization_pending' } } else { [pscustomobject]@{ access_token = 'the-token'; token_type = 'Bearer' } }
        }
        Get-DeviceCodeToken -TenantId 'organizations' -ClientId $Cli -Scope 'api://x/Requests.ReadWrite' | Should -Be 'the-token'
        $script:calls | Should -Be 3
        Should -Invoke -ModuleName SaasLab Invoke-RestMethod -ParameterFilter { $Uri -eq 'https://login.microsoftonline.com/organizations/oauth2/v2.0/devicecode' -and $Body.client_id -eq $Cli.ToString() } -Times 1
        Should -Invoke -ModuleName SaasLab Invoke-RestMethod -ParameterFilter { $Uri -like '*/token' -and $Body.grant_type -eq 'urn:ietf:params:oauth:grant-type:device_code' -and $Body.device_code -eq 'dc' } -Times 3
    }
    It 'stops with the service error when the user declines' {
        Mock -ModuleName SaasLab Invoke-RestMethod {
            if ($Uri -like '*/devicecode') { return [pscustomobject]@{ device_code = 'dc'; message = 'm'; interval = 1; expires_in = 900 } }
            [pscustomobject]@{ error = 'authorization_declined'; error_description = 'The user denied.' }
        }
        { Get-DeviceCodeToken -TenantId 'organizations' -ClientId $Cli -Scope 's' } | Should -Throw '*authorization_declined*'
    }
    It 'slows down when asked to' {
        $script:n = 0
        Mock -ModuleName SaasLab Invoke-RestMethod {
            if ($Uri -like '*/devicecode') { return [pscustomobject]@{ device_code = 'dc'; message = 'm'; interval = 5; expires_in = 900 } }
            $script:n++
            if ($script:n -eq 1) { [pscustomobject]@{ error = 'slow_down' } } else { [pscustomobject]@{ access_token = 't' } }
        }
        Get-DeviceCodeToken -TenantId 'organizations' -ClientId $Cli -Scope 's' | Should -Be 't'
        Should -Invoke -ModuleName SaasLab Start-Sleep -ParameterFilter { $Seconds -eq 10 } -Times 1
    }
}

Describe 'Token claims and API client' {
    It 'shows tid and the issuer from a token payload' {
        $c = Get-TokenClaims (New-FakeToken @{ tid = '00000000-0000-0000-0000-0000000000b1'; iss = 'https://login.microsoftonline.com/00000000-0000-0000-0000-0000000000b1/v2.0'; scp = 'Requests.ReadWrite' })
        $c.tid | Should -Be '00000000-0000-0000-0000-0000000000b1'
        $c.scp | Should -Be 'Requests.ReadWrite'
    }
    It 'keeps the status code of a refusal and parses the problem details' {
        Mock -ModuleName SaasLab Invoke-WebRequest { [pscustomobject]@{ StatusCode = 403; Content = '{"title":"Tenant not active","status":403}' } }
        $r = Invoke-SaasApi -BaseUrl 'https://app.example/' -Path '/requests' -Token 'tok'
        $r.Status | Should -Be 403
        $r.Body.title | Should -Be 'Tenant not active'
        Should -Invoke -ModuleName SaasLab Invoke-WebRequest -ParameterFilter { $Uri -eq 'https://app.example/requests' -and $Headers.Authorization -eq 'Bearer tok' -and $SkipHttpErrorCheck } -Times 1
    }
    It 'sends a JSON body and extra headers' {
        Mock -ModuleName SaasLab Invoke-WebRequest { [pscustomobject]@{ StatusCode = 201; Content = '{"id":"1"}' } }
        $r = Invoke-SaasApi -BaseUrl 'https://app.example' -Path '/requests' -Token 'tok' -Method POST -Body @{ title = 'Laptops'; amount = 10 } -Headers @{ 'X-Tenant-Id' = 'other' }
        $r.Status | Should -Be 201
        Should -Invoke -ModuleName SaasLab Invoke-WebRequest -ParameterFilter { $Method -eq 'POST' -and $ContentType -eq 'application/json' -and ($Body | ConvertFrom-Json).title -eq 'Laptops' -and $Headers['X-Tenant-Id'] -eq 'other' } -Times 1
    }
}

Describe 'New-SaasApps.ps1' {
    It 'parses and supports -WhatIf' {
        $path = Join-Path $PSScriptRoot '..' 'scripts' 'New-SaasApps.ps1'
        { [scriptblock]::Create((Get-Content $path -Raw)) } | Should -Not -Throw
        (Get-Command $path).Parameters.ContainsKey('WhatIf') | Should -BeTrue
    }
}
