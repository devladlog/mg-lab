#requires -Version 7.2
<#
.SYNOPSIS
    Creates the two Entra app registrations for episode 7 with the Azure CLI (needs tenant, run as the lab admin).
.DESCRIPTION
    1. "contoso-purchase-gateway": the API. Application ID URI api://<appId>, v2.0 access tokens, app role Purchase.Submit.
    2. "contoso-purchase-caller": a client that has the role, plus one client secret (printed once, never stored).
    Idempotent by display name. -WhatIf only reads `az account show` (to print the tenant), then stops before changing anything.
    Prints the values Bicep and the demo need: tenantId, apiClientId, callerClientId. The secret goes to the
    PURCHASE_CALLER_SECRET environment variable of THIS session only.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $ApiName = 'contoso-purchase-gateway',
    [string] $CallerName = 'contoso-purchase-caller'
)
$ErrorActionPreference = 'Stop'

function Invoke-Az {
    # Runs az, returns parsed JSON (or $null), and throws on a non-zero exit code.
    $out = & az @args --only-show-errors -o json 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az $($args -join ' ') failed: $out" }
    if ($out) { $out | ConvertFrom-Json }
}

$tenantId = (Invoke-Az account show).tenantId
$roleValue = 'Purchase.Submit'

if (-not $PSCmdlet.ShouldProcess($tenantId, "create/update $ApiName and $CallerName")) { return }

# ---- 1. the API -----------------------------------------------------------------------------------------------
$api = Invoke-Az ad app list --display-name $ApiName | Where-Object displayName -eq $ApiName | Select-Object -First 1
if (-not $api) {
    $roleId = [guid]::NewGuid().ToString()
    $roles = @(@{
            allowedMemberTypes = @('Application')
            description        = 'Submit purchase events through the gateway.'
            displayName        = $roleValue
            id                 = $roleId
            isEnabled          = $true
            value              = $roleValue
        }) | ConvertTo-Json -AsArray -Compress
    $rolesFile = New-TemporaryFile
    try {
        Set-Content -Path $rolesFile -Value $roles -Encoding utf8
        $api = Invoke-Az ad app create --display-name $ApiName --sign-in-audience AzureADMyOrg --app-roles "@$rolesFile"
    }
    finally { Remove-Item $rolesFile -Force }
    Invoke-Az ad app update --id $api.appId --identifier-uris "api://$($api.appId)" `
        --set api.requestedAccessTokenVersion=2 | Out-Null
    Invoke-Az ad sp create --id $api.appId | Out-Null
    Write-Host "Created $ApiName ($($api.appId))"
}
else { Write-Host "$ApiName exists ($($api.appId))" }
$roleId = ($api.appRoles | Where-Object value -eq $roleValue).id
if (-not $roleId) { $roleId = (Invoke-Az ad app show --id $api.appId).appRoles | Where-Object value -eq $roleValue | Select-Object -ExpandProperty id }

# ---- 2. the caller --------------------------------------------------------------------------------------------
$caller = Invoke-Az ad app list --display-name $CallerName | Where-Object displayName -eq $CallerName | Select-Object -First 1
$newSecret = $false
if (-not $caller) {
    $caller = Invoke-Az ad app create --display-name $CallerName --sign-in-audience AzureADMyOrg
    Invoke-Az ad sp create --id $caller.appId | Out-Null
    $newSecret = $true
    Write-Host "Created $CallerName ($($caller.appId))"
}
else { Write-Host "$CallerName exists ($($caller.appId))" }

$apiSp = Invoke-Az ad sp show --id $api.appId
$callerSp = Invoke-Az ad sp show --id $caller.appId

# ---- 3. grant the role (app role assignment on the API's service principal) -----------------------------------
$existing = Invoke-Az rest --method GET --url "https://graph.microsoft.com/v1.0/servicePrincipals/$($apiSp.id)/appRoleAssignedTo"
if (-not ($existing.value | Where-Object { $_.principalId -eq $callerSp.id -and $_.appRoleId -eq $roleId })) {
    $assignment = @{ principalId = $callerSp.id; resourceId = $apiSp.id; appRoleId = $roleId } | ConvertTo-Json -Compress
    $assignmentFile = New-TemporaryFile
    try {
        Set-Content -Path $assignmentFile -Value $assignment -Encoding utf8
        Invoke-Az rest --method POST --url "https://graph.microsoft.com/v1.0/servicePrincipals/$($apiSp.id)/appRoleAssignedTo" `
            --headers 'Content-Type=application/json' --body "@$assignmentFile" | Out-Null
    }
    finally { Remove-Item $assignmentFile -Force }
    Write-Host "Granted $roleValue to $CallerName"
}

if ($newSecret) {
    $cred = Invoke-Az ad app credential reset --id $caller.appId --append --display-name 'episode-7 demo' --years 1
    $env:PURCHASE_CALLER_SECRET = $cred.password
    Write-Host 'Client secret stored in $env:PURCHASE_CALLER_SECRET for this session (not printed).'
}

[pscustomobject]@{ tenantId = $tenantId; apiClientId = $api.appId; callerClientId = $caller.appId }
