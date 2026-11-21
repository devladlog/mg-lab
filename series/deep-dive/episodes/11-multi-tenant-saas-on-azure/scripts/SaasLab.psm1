# Helpers for the multitenant SaaS episode: app registration bodies (Microsoft Graph), a device-code sign-in
# that works in any tenant, and a small API client that keeps the HTTP status. PowerShell 7.

Set-StrictMode -Version Latest

$script:Authority = 'https://login.microsoftonline.com'

function New-SaasApiAppBody {
    <# Microsoft Graph "application" body for the multitenant API: any work or school tenant, v2.0 tokens,
       one delegated scope, one app role for the provider's own staff, and the CLI as a known client
       (so one consent covers both registrations). #>
    param(
        [Parameter(Mandatory)] [string] $DisplayName,
        [Parameter(Mandatory)] [guid] $ScopeId,
        [Parameter(Mandatory)] [guid] $RoleId,
        [guid[]] $KnownClientIds = @()
    )
    [ordered]@{
        displayName    = $DisplayName
        signInAudience = 'AzureADMultipleOrgs'
        api            = [ordered]@{
            requestedAccessTokenVersion = 2
            knownClientApplications     = @($KnownClientIds | ForEach-Object { $_.ToString() })
            oauth2PermissionScopes      = @(
                [ordered]@{
                    id                      = $ScopeId.ToString()
                    value                   = 'Requests.ReadWrite'
                    type                    = 'User'
                    isEnabled               = $true
                    adminConsentDisplayName = 'Read and write purchase requests of your organisation'
                    adminConsentDescription = 'Lets the app read and write purchase requests of the signed-in user''s organisation.'
                    userConsentDisplayName  = 'Read and write your organisation''s purchase requests'
                    userConsentDescription  = 'Lets the app read and write your organisation''s purchase requests.'
                })
        }
        appRoles       = @(
            [ordered]@{
                id                 = $RoleId.ToString()
                value              = 'Platform.Admin'
                displayName        = 'Platform administrator'
                description        = 'Onboard and suspend customer tenants. Only honoured for users of the provider tenant.'
                allowedMemberTypes = @('User')
                isEnabled          = $true
            })
    }
}

function New-SaasCliAppBody {
    <# The sign-in client: multitenant, public client (device code), asks for the API's scope. #>
    param(
        [Parameter(Mandatory)] [string] $DisplayName,
        [Parameter(Mandatory)] [guid] $ApiAppId,
        [Parameter(Mandatory)] [guid] $ScopeId
    )
    [ordered]@{
        displayName            = $DisplayName
        signInAudience         = 'AzureADMultipleOrgs'
        isFallbackPublicClient = $true
        publicClient           = [ordered]@{ redirectUris = @("$script:Authority/common/oauth2/nativeclient") }
        requiredResourceAccess = @(
            [ordered]@{
                resourceAppId  = $ApiAppId.ToString()
                resourceAccess = @([ordered]@{ id = $ScopeId.ToString(); type = 'Scope' })
            })
    }
}

function Get-AdminConsentUrl {
    <# Where a customer's administrator approves the app for their organisation (Learn: v2.0 admin consent endpoint). #>
    param(
        [Parameter(Mandatory)] [string] $CustomerTenantId,
        [Parameter(Mandatory)] [guid] $CliClientId,
        [Parameter(Mandatory)] [guid] $ApiClientId,
        [string] $RedirectUri = "$script:Authority/common/oauth2/nativeclient"
    )
    $scope = [uri]::EscapeDataString("api://$ApiClientId/.default")
    "$script:Authority/$CustomerTenantId/v2.0/adminconsent?client_id=$CliClientId&scope=$scope&redirect_uri=$([uri]::EscapeDataString($RedirectUri))"
}

function Get-DeviceCodeToken {
    <# OAuth 2.0 device authorization grant against ONE tenant (or 'organizations'). Returns the access token. #>
    param(
        [Parameter(Mandatory)] [string] $TenantId,
        [Parameter(Mandatory)] [guid] $ClientId,
        [Parameter(Mandatory)] [string] $Scope,
        [string] $Label = ''
    )
    $base = "$script:Authority/$TenantId/oauth2/v2.0"
    $dc = Invoke-RestMethod -Method Post -Uri "$base/devicecode" -Body @{ client_id = $ClientId.ToString(); scope = $Scope }
    Write-Host ("{0}{1}" -f ($Label ? "[$Label] " : ''), $dc.message)

    $interval = [Math]::Max(1, [int]$dc.interval)
    $deadline = (Get-Date).AddSeconds([int]$dc.expires_in)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds $interval
        $r = Invoke-RestMethod -Method Post -Uri "$base/token" -SkipHttpErrorCheck -Body @{
            grant_type  = 'urn:ietf:params:oauth:grant-type:device_code'
            client_id   = $ClientId.ToString()
            device_code = $dc.device_code
        }
        if ($r.PSObject.Properties['access_token']) { return $r.access_token }
        switch ($r.error) {
            'authorization_pending' { continue }
            'slow_down' { $interval += 5; continue }   # RFC 8628; Learn lists the other errors
            default { throw "Sign-in failed: $($r.error). $($r.error_description)" }
        }
    }
    throw 'Sign-in timed out: the device code expired.'
}

function Get-TokenClaims {
    <# Decodes the payload of a token for OUR OWN API, to show which tenant it is from. Never trust it as a check:
       the API validates the signature. Learn warns against reading tokens of APIs you do not own. #>
    param([Parameter(Mandatory)] [string] $Token)
    $part = $Token.Split('.')[1].Replace('-', '+').Replace('_', '/')
    $part = $part.PadRight($part.Length + (4 - $part.Length % 4) % 4, '=')
    [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($part)) | ConvertFrom-Json
}

function Invoke-SaasApi {
    <# Calls the API and keeps the status code, so a 403 or a 404 is data on screen and not an exception. #>
    param(
        [Parameter(Mandatory)] [string] $BaseUrl,
        [Parameter(Mandatory)] [string] $Path,
        [string] $Token,
        [ValidateSet('GET', 'POST', 'PUT', 'DELETE')] [string] $Method = 'GET',
        $Body,
        [hashtable] $Headers = @{}
    )
    $h = @{} + $Headers
    if ($Token) { $h['Authorization'] = "Bearer $Token" }
    $req = @{ Uri = ($BaseUrl.TrimEnd('/') + $Path); Method = $Method; Headers = $h; SkipHttpErrorCheck = $true }
    if ($PSBoundParameters.ContainsKey('Body')) { $req.Body = ($Body | ConvertTo-Json -Depth 5); $req.ContentType = 'application/json' }
    $resp = Invoke-WebRequest @req
    $parsed = $null
    if ($resp.Content) { try { $parsed = $resp.Content | ConvertFrom-Json -Depth 10 } catch { $parsed = $resp.Content } }
    [pscustomobject]@{ Status = [int]$resp.StatusCode; Body = $parsed }
}

Export-ModuleMember -Function New-SaasApiAppBody, New-SaasCliAppBody, Get-AdminConsentUrl, Get-DeviceCodeToken, Get-TokenClaims, Invoke-SaasApi
