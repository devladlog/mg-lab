#requires -Modules Pester
BeforeAll {
    Import-Module (Join-Path $PSScriptRoot 'PurchaseGateway.psm1') -Force
}

Describe 'Send-PurchaseEvent' {
    BeforeEach {
        $script:captured = $null
        Mock -ModuleName PurchaseGateway Invoke-WebRequest {
            $script:captured = @{ Uri = $Uri; Headers = $Headers; Body = $Body; ContentType = $ContentType }
            [pscustomobject]@{
                StatusCode = 202
                Content    = '{"status":"accepted"}'
                Headers    = @{ 'x-ratelimit-remaining' = @('19') }
            }
        }
    }

    It 'posts the JSON the gateway schema expects, with the idempotency key and both credentials' {
        $r = Send-PurchaseEvent -GatewayUrl 'https://apim-example.azure-api.net/' -SubscriptionKey 'key' -Token 'tok' `
            -PurchaseRequestId PR-1002 -Total 7380 -IdempotencyKey '3f2504e0-4f89-11d3-9a0c-0305e82c3301'
        $r.StatusCode | Should -Be 202
        $r.Remaining | Should -Be '19'
        $captured.Uri | Should -Be 'https://apim-example.azure-api.net/purchasing/purchase-events'
        $captured.Headers['Authorization'] | Should -Be 'Bearer tok'
        $captured.Headers['Ocp-Apim-Subscription-Key'] | Should -Be 'key'
        $captured.Headers['Idempotency-Key'] | Should -Be '3f2504e0-4f89-11d3-9a0c-0305e82c3301'
        $json = $captured.Body | ConvertFrom-Json
        $json.eventType | Should -Be 'submitted'
        $json.purchaseRequestId | Should -Be 'PR-1002'
        $json.total | Should -Be 7380
        $json.currency | Should -Be 'EUR'
    }

    It 'sends no Authorization header when no token is given (the 401 take)' {
        Send-PurchaseEvent -GatewayUrl 'https://x' -SubscriptionKey 'key' -PurchaseRequestId PR-1001 -Total 10 | Out-Null
        $captured.Headers.ContainsKey('Authorization') | Should -BeFalse
    }

    It 'generates a new GUID key per call unless one is given' {
        $a = Send-PurchaseEvent -GatewayUrl 'https://x' -SubscriptionKey 'k' -PurchaseRequestId PR-1001 -Total 10
        $b = Send-PurchaseEvent -GatewayUrl 'https://x' -SubscriptionKey 'k' -PurchaseRequestId PR-1001 -Total 10
        { [guid]$a.IdempotencyKey } | Should -Not -Throw
        $a.IdempotencyKey | Should -Not -Be $b.IdempotencyKey
    }

    It 'can send a raw body to show the schema check (the 400 take)' {
        Send-PurchaseEvent -GatewayUrl 'https://x' -SubscriptionKey 'k' -PurchaseRequestId PR-1001 -Total 10 -RawBody '{"total":-1}' | Out-Null
        $captured.Body | Should -Be '{"total":-1}'
    }

    It 'rejects an id that breaks the PR-nnnn pattern before calling anything' {
        { Send-PurchaseEvent -GatewayUrl 'https://x' -SubscriptionKey 'k' -PurchaseRequestId 'PR-1' -Total 10 } | Should -Throw
    }
}

Describe 'Get-GatewayToken' {
    It 'asks for api://<api>/.default with the client credentials grant and returns only the token' {
        Mock -ModuleName PurchaseGateway Invoke-RestMethod { $script:tokenCall = @{ Uri = $Uri; Body = $Body }; [pscustomobject]@{ access_token = 'abc' } }
        $secret = ConvertTo-SecureString 'not-a-real-secret' -AsPlainText -Force
        $t = Get-GatewayToken -TenantId '00000000-0000-0000-0000-000000000000' -CallerClientId '11111111-1111-1111-1111-111111111111' `
            -ApiClientId '22222222-2222-2222-2222-222222222222' -CallerSecret $secret
        $t | Should -Be 'abc'
        $tokenCall.Uri | Should -Be 'https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/oauth2/v2.0/token'
        $tokenCall.Body.grant_type | Should -Be 'client_credentials'
        $tokenCall.Body.scope | Should -Be 'api://22222222-2222-2222-2222-222222222222/.default'
    }

    It 'fails clearly when there is no secret' {
        $old = $env:PURCHASE_CALLER_SECRET; $env:PURCHASE_CALLER_SECRET = $null
        try { { Get-GatewayToken -TenantId t -CallerClientId c -ApiClientId a } | Should -Throw '*No client secret*' }
        finally { $env:PURCHASE_CALLER_SECRET = $old }
    }
}
