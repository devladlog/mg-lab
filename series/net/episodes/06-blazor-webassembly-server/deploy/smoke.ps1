<#
.SYNOPSIS
  Smoke test against the two RUNNING apps (start them first, see demo.md):
    API  http://localhost:5207  (src/ProjectRequests.Api,  dotnet run --launch-profile http)
    Web  http://localhost:5180  (src/ProjectRequests.Web,  dotnet run --launch-profile http)
  Creates two requests through the API, then checks what the Blazor app serves and the CORS preflight.
#>
param(
    [string] $Api = 'http://localhost:5207',
    [string] $Web = 'http://localhost:5180'
)
$ErrorActionPreference = 'Stop'

function Step([string] $text) { Write-Host "`n== $text" -ForegroundColor Cyan }

Step '1. Two requests through the API'
foreach ($body in @(
        @{ title = 'Laptop refresh'; budget = 12000; requestedBy = 'alex.demo@contoso.com'; departmentCode = 'FIN' },
        @{ title = 'Data platform';  budget = 80000; requestedBy = 'alex.demo@contoso.com'; departmentCode = 'IT' })) {
    $r = Invoke-RestMethod -Method Post -Uri "$Api/api/requests" -ContentType 'application/json' -Body ($body | ConvertTo-Json)
    "#$($r.id) $($r.title): $($r.priority), $($r.status)"
}

Step '2. /requests - static SSR + streaming: no circuit, no WebAssembly'
$list = (Invoke-WebRequest -Uri "$Web/requests").Content
"Rendered by Static:     $($list -match 'Rendered by: <strong>Static</strong>')"
"Streamed update chunk:  $($list -match '<blazor-ssr>')"
"Contains 'Data platform': $($list -match 'Data platform')"

Step '3. /requests/1 - Interactive Server, prerendered'
$detail = (Invoke-WebRequest -Uri "$Web/requests/1").Content
"Server component marker:  $($detail -match '"type":"server"')"
"Persisted state in page:  $($detail -match 'Blazor-Server-Component-State')"
"Buttons disabled (prerender): $($detail -match '<button id="approve" disabled>')"

Step '4. /requests/new - Interactive WebAssembly, prerendered on the server'
$new = (Invoke-WebRequest -Uri "$Web/requests/new").Content
"WebAssembly component marker: $($new -match '"type":"webassembly"')"
$cfg = Invoke-RestMethod -Uri "$Web/appsettings.json"
"Client config (public!):     RequestsApi:BaseUrl = $($cfg.RequestsApi.BaseUrl)"

Step '5. CORS preflight to the API, as the browser sends it'
foreach ($origin in @($Web, 'http://localhost:5181')) {
    $pre = Invoke-WebRequest -Method Options -Uri "$Api/api/requests" -SkipHttpErrorCheck -Headers @{
        Origin = $origin; 'Access-Control-Request-Method' = 'POST'; 'Access-Control-Request-Headers' = 'content-type' }
    $allow = $pre.Headers['Access-Control-Allow-Origin']
    "Origin $origin -> $($pre.StatusCode), Access-Control-Allow-Origin: $(if ($allow) { $allow } else { '(none)' })"
}
