<#
.SYNOPSIS
  Runs the OData text you are about to paste into a flow (Filter rows, Select columns, Expand query, Sort by, Row count)
  against the Dataverse Web API, so you see which rows it returns before the flow does.

.DESCRIPTION
  * The token comes from $env:DATAVERSE_TOKEN (never from a file or a parameter).
  * -Filter is the text of the flow's "Filter rows" box: it must not contain '$filter=' (Learn).
  * Paging follows @odata.nextLink unchanged, with the same page size (Learn: Page results by using OData).
    -Top and -PageSize can't be combined: Dataverse ignores $top when Prefer: odata.maxpagesize is present.
  * A 429 (service protection limit) waits for the Retry-After header and tries again.
  * -PrintOnly shows the URL and headers and sends nothing.

.EXAMPLE
  $env:DATAVERSE_TOKEN = '<token>'   # the token is obtained out of band; it is never printed
  ./Invoke-DataverseQuery.ps1 -OrgUrl https://contoso.crm4.dynamics.com -Table opportunities `
      -Filter "statecode eq 0 and estimatedclosedate lt 2026-11-21" -Select name,estimatedvalue,estimatedclosedate `
      -Expand 'parentaccountid($select=name)' -OrderBy 'estimatedclosedate asc,opportunityid asc' -PageSize 50 -FormattedValues
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OrgUrl,
    [Parameter(Mandatory)][string]$Table,                 # entity set name, for example opportunities
    [string]$Filter,
    [string[]]$Select,
    [string]$Expand,
    [string]$OrderBy,
    [ValidateRange(1, 5000)][int]$Top,
    [ValidateRange(1, 5000)][int]$PageSize,
    [ValidateRange(1, 1000)][int]$MaxPages = 20,
    [ValidateRange(0, 10)][int]$MaxRetries = 3,
    [switch]$FormattedValues,
    [switch]$PrintOnly
)
$ErrorActionPreference = 'Stop'

if (-not $env:DATAVERSE_TOKEN -and -not $PrintOnly) { throw 'Set $env:DATAVERSE_TOKEN first (an access token for the environment).' }
if ($Table -notmatch '^[a-z][a-z0-9_]*$') { throw "Table '$Table' doesn't look like an entity set name (for example opportunities)." }
if ($Filter -and $Filter -match '(?i)\$filter\s*=') { throw "-Filter must be the expression only: remove '`$filter=' (Learn: it only applies when you call the API directly)." }
if ($Top -and $PageSize) { throw '-Top and -PageSize can''t be combined: Dataverse ignores $top when odata.maxpagesize is set.' }
if ($Filter -and ($Filter.ToCharArray() | Where-Object { $_ -eq "'" }).Count % 2) { throw "-Filter has an odd number of single quotes: double the quote inside a value ('O''Bryan')." }

# URL-encode the characters Learn lists (& # + , / : ; = ? @ $) only inside quoted literals; operators and the
# structure of the expression stay readable. Everything else is left to the HTTP client.
function ConvertTo-EncodedFilter([string]$text) {
    [regex]::Replace($text, "'((?:[^']|'')*)'", {
        param($m)
        $inner = $m.Groups[1].Value
        foreach ($pair in @(@('%', '%25'), @('&', '%26'), @('#', '%23'), @('+', '%2B'))) { $inner = $inner.Replace($pair[0], $pair[1]) }
        "'" + $inner + "'"
    })
}

$query = [System.Collections.Generic.List[string]]::new()
if ($Select) { $query.Add('$select=' + ($Select -join ',')) }
if ($Filter) { $query.Add('$filter=' + (ConvertTo-EncodedFilter $Filter)) }
if ($Expand) { $query.Add('$expand=' + $Expand) }
if ($OrderBy) { $query.Add('$orderby=' + $OrderBy) }
if ($Top) { $query.Add('$top=' + $Top) }
$uri = $OrgUrl.TrimEnd('/') + '/api/data/v9.2/' + $Table
if ($query.Count) { $uri += '?' + ($query -join '&') }

$prefer = [System.Collections.Generic.List[string]]::new()
if ($FormattedValues) { $prefer.Add('odata.include-annotations="OData.Community.Display.V1.FormattedValue"') }
if ($PageSize) { $prefer.Add("odata.maxpagesize=$PageSize") }
$headers = @{ Accept = 'application/json'; 'OData-MaxVersion' = '4.0'; 'OData-Version' = '4.0' }
if ($prefer.Count) { $headers['Prefer'] = $prefer -join ',' }

if ($PrintOnly) {
    Write-Host "GET $uri"
    foreach ($k in $headers.Keys | Sort-Object) { Write-Host "${k}: $($headers[$k])" }
    return
}
$headers['Authorization'] = 'Bearer ' + $env:DATAVERSE_TOKEN

function Send-Get([string]$url) {
    for ($attempt = 0; ; $attempt++) {
        try {
            return Invoke-RestMethod -Method Get -Uri $url -Headers $headers -MaximumRetryCount 0
        }
        catch {
            $resp = $_.Exception.Response
            $code = if ($resp) { [int]$resp.StatusCode } else { 0 }
            if ($code -ne 429 -or $attempt -ge $MaxRetries) { throw }
            $wait = 5  # Retry-After is always sent with a service protection 429 (Learn); 5 s is only a fallback
            if ($resp.Headers.RetryAfter -and $resp.Headers.RetryAfter.Delta) { $wait = [math]::Ceiling($resp.Headers.RetryAfter.Delta.TotalSeconds) }
            Write-Warning "429 Too Many Requests: waiting $wait s (retry $($attempt + 1) of $MaxRetries)"
            Start-Sleep -Seconds $wait
        }
    }
}

$rows = [System.Collections.Generic.List[object]]::new()
$pages = 0
$url = $uri
while ($url -and $pages -lt $MaxPages) {
    $r = Send-Get $url
    $pages++
    foreach ($row in $r.value) { $rows.Add($row) }
    $url = $r.'@odata.nextLink'   # used as is: never modified or extended (Learn)
}
if ($url) { Write-Warning "Stopped after $MaxPages page(s); more rows exist (raise -MaxPages)." }
Write-Host "$($rows.Count) row(s) in $pages page(s)"
$rows.ToArray()
