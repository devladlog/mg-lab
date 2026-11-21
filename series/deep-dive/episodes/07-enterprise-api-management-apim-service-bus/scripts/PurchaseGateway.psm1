#requires -Version 7.2
# DEVLADLOG Deep Dive #7: a tiny client for the gateway, used on camera.
Set-StrictMode -Version Latest

function Get-GatewayToken {
    <#
    .SYNOPSIS
        Gets an app-only access token for the purchase gateway API (OAuth 2.0 client credentials flow).
    .DESCRIPTION
        The secret is read from the SecureString parameter or from the PURCHASE_CALLER_SECRET environment variable.
        It is never echoed. Scope is api://<api client id>/.default; the caller app needs the Purchase.Submit app role.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $TenantId,
        [Parameter(Mandatory)] [string] $CallerClientId,
        [Parameter(Mandatory)] [string] $ApiClientId,
        [securestring] $CallerSecret
    )
    $plain = if ($CallerSecret) { [System.Net.NetworkCredential]::new('', $CallerSecret).Password } else { $env:PURCHASE_CALLER_SECRET }
    if ([string]::IsNullOrEmpty($plain)) { throw 'No client secret: pass -CallerSecret or set PURCHASE_CALLER_SECRET.' }

    $body = @{
        grant_type    = 'client_credentials'
        client_id     = $CallerClientId
        client_secret = $plain
        scope         = "api://$ApiClientId/.default"
    }
    $response = Invoke-RestMethod -Method Post -Uri "https://login.microsoftonline.com/$TenantId/oauth2/v2.0/token" `
        -ContentType 'application/x-www-form-urlencoded' -Body $body
    $response.access_token
}

function Send-PurchaseEvent {
    <#
    .SYNOPSIS
        Posts one purchase event to the gateway and returns the status code and the headers that matter.
    .EXAMPLE
        Send-PurchaseEvent -GatewayUrl $url -SubscriptionKey $key -Token $token -PurchaseRequestId PR-1002 -Total 7380
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $GatewayUrl,
        [Parameter(Mandatory)] [string] $SubscriptionKey,
        [string] $Token,
        [Parameter(Mandatory)] [ValidatePattern('^PR-[0-9]{4,8}$')] [string] $PurchaseRequestId,
        [Parameter(Mandatory)] [decimal] $Total,
        [ValidateSet('EUR', 'USD', 'GBP')] [string] $Currency = 'EUR',
        [ValidateSet('submitted', 'approved', 'rejected')] [string] $EventType = 'submitted',
        [string] $RequestedBy = 'alex.demo@contoso.com',
        [string] $IdempotencyKey = ([guid]::NewGuid().ToString()),
        [string] $RawBody
    )
    $headers = @{
        'Ocp-Apim-Subscription-Key' = $SubscriptionKey
        'Idempotency-Key'           = $IdempotencyKey
    }
    if ($Token) { $headers['Authorization'] = "Bearer $Token" }

    $body = if ($PSBoundParameters.ContainsKey('RawBody')) { $RawBody } else {
        [ordered]@{
            eventType         = $EventType
            purchaseRequestId = $PurchaseRequestId
            requestedBy       = $RequestedBy
            total             = $Total
            currency          = $Currency
        } | ConvertTo-Json -Compress
    }

    $uri = ($GatewayUrl.TrimEnd('/')) + '/purchasing/purchase-events'
    $r = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' -Body $body -SkipHttpErrorCheck

    $first = { param($name) if ($r.Headers.ContainsKey($name)) { @($r.Headers[$name])[0] } else { $null } }
    [pscustomobject]@{
        StatusCode     = [int]$r.StatusCode
        IdempotencyKey = $IdempotencyKey
        Remaining      = & $first 'x-ratelimit-remaining'
        RetryAfter     = & $first 'Retry-After'
        Body           = $r.Content
    }
}

Export-ModuleMember -Function Get-GatewayToken, Send-PurchaseEvent
