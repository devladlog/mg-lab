<#
.SYNOPSIS
  Registers the two multitenant app registrations in the PROVIDER tenant (Microsoft Graph through 'az rest').
.DESCRIPTION
  contoso-saas-api : the API (v2.0 tokens, scope Requests.ReadWrite, app role Platform.Admin)
  contoso-saas-cli : a public client for device-code sign-in; the API lists it as a known client
  Needs 'az login' as a user who may create app registrations. Prints the two client IDs. Idempotent by display name.
.EXAMPLE
  ./New-SaasApps.ps1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $ApiName = 'contoso-saas-api',
    [string] $CliName = 'contoso-saas-cli'
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'SaasLab.psm1') -Force

function Invoke-Graph([string] $Method, [string] $Path, $Body) {
    $a = @('rest', '--method', $Method, '--url', "https://graph.microsoft.com/v1.0$Path", '--headers', 'Content-Type=application/json')
    if ($null -ne $Body) { $a += @('--body', ($Body | ConvertTo-Json -Depth 10 -Compress)) }
    $out = & az @a
    if ($LASTEXITCODE -ne 0) { throw "az rest $Method $Path failed." }
    if ($out) { $out | ConvertFrom-Json -Depth 20 }
}

function Find-App([string] $Name) {
    $r = Invoke-Graph GET ("/applications?`$filter=displayName eq '$Name'&`$select=id,appId,displayName") $null
    @($r.value)[0]
}

$scopeId = [guid]::NewGuid(); $roleId = [guid]::NewGuid()
$api = Find-App $ApiName
$cli = Find-App $CliName

if (-not $api) {
    if ($PSCmdlet.ShouldProcess($ApiName, 'Create multitenant API app registration')) {
        $api = Invoke-Graph POST '/applications' (New-SaasApiAppBody -DisplayName $ApiName -ScopeId $scopeId -RoleId $roleId)
        # Application ID URI after creation, because it contains the appId. Multitenant apps normally need a verified
        # domain in the URI; api://<appId> is the documented default for APIs.
        Invoke-Graph PATCH "/applications/$($api.id)" @{ identifierUris = @("api://$($api.appId)") } | Out-Null
    }
}
if (-not $cli -and $api) {
    if ($PSCmdlet.ShouldProcess($CliName, 'Create multitenant public client')) {
        $existingScope = (Invoke-Graph GET "/applications/$($api.id)?`$select=api" $null).api.oauth2PermissionScopes | Where-Object value -eq 'Requests.ReadWrite'
        $cli = Invoke-Graph POST '/applications' (New-SaasCliAppBody -DisplayName $CliName -ApiAppId $api.appId -ScopeId $existingScope.id)
        Invoke-Graph PATCH "/applications/$($api.id)" @{ api = @{ knownClientApplications = @($cli.appId) } } | Out-Null
    }
}
if ($api -and $cli) {
    [pscustomobject]@{ ApiClientId = $api.appId; CliClientId = $cli.appId }
}
