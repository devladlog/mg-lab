<#
.SYNOPSIS
  Lists the Fabric workspaces you can see and says whether each one sits on a capacity that can run Copilot.
.DESCRIPTION
  Read-only. Calls two Fabric REST API operations (Learn: Capacities - List Capacities, Workspaces - List Workspaces)
  and applies the documented rule: Copilot in Power BI and Fabric needs a paid Fabric capacity F2 or higher, or Power BI
  Premium P1 or higher. Trial capacities and free SKUs are not supported. Region support and tenant settings are NOT
  checked here: compare the Region column with the Fabric region availability page and look at the tenant settings
  in the admin portal.
  Needs a token for https://api.fabric.microsoft.com with Capacity.Read.All and Workspace.Read.All. Pass -AccessToken,
  or sign in with Connect-AzAccount first and the script asks Az.Accounts for one. Nothing is written anywhere.
.EXAMPLE
  ./Get-FabricCopilotCapacity.ps1 | Format-Table -AutoSize
#>
[CmdletBinding()]
param(
    [string]$AccessToken,
    [string]$BaseUri = 'https://api.fabric.microsoft.com/v1',
    [switch]$AsJson
)

function Get-CopilotSkuVerdict {
    <# Applies the documented SKU rule to one capacity SKU string. #>
    param([string]$Sku, [string]$State = 'Active')
    if ([string]::IsNullOrWhiteSpace($Sku)) {
        return [pscustomobject]@{ CopilotCapable = $false; Reason = 'No capacity assigned: Pro and PPU workspaces need a Fabric Copilot capacity' }
    }
    if ($State -and $State -ne 'Active') {
        return [pscustomobject]@{ CopilotCapable = $false; Reason = "Capacity state is $State (paused or inactive)" }
    }
    if ($Sku -match '(?i)trial|^FT') {
        return [pscustomobject]@{ CopilotCapable = $false; Reason = 'Trial capacity: Copilot in Fabric is not supported on trial SKUs' }
    }
    if ($Sku -match '^F(\d+)$') {
        if ([int]$Matches[1] -ge 2) {
            return [pscustomobject]@{ CopilotCapable = $true; Reason = 'Paid F SKU, F2 or higher' }
        }
    }
    if ($Sku -match '^P([1-5])$') {
        return [pscustomobject]@{ CopilotCapable = $true; Reason = 'Power BI Premium P1 or higher (Copilot must be enabled for the capacity)' }
    }
    return [pscustomobject]@{ CopilotCapable = $false; Reason = "SKU $Sku is not F2+ or P1+" }
}

function Invoke-FabricPagedGet {
    <# GET with continuationToken paging (documented for both operations). #>
    param([string]$Uri, [hashtable]$Headers)
    $items = [System.Collections.Generic.List[object]]::new()
    $next = $Uri
    while ($next) {
        $page = Invoke-RestMethod -Method Get -Uri $next -Headers $Headers
        if ($page.value) { $items.AddRange(@($page.value)) }
        if ($page.continuationToken) {
            $sep = if ($Uri.Contains('?')) { '&' } else { '?' }
            $next = "$Uri$sep" + 'continuationToken=' + [uri]::EscapeDataString($page.continuationToken)
        } else {
            $next = $null
        }
    }
    return $items
}

function Get-FabricCopilotReport {
    param([string]$BaseUri, [hashtable]$Headers)
    $caps = Invoke-FabricPagedGet -Uri "$BaseUri/capacities" -Headers $Headers
    $byId = @{}
    foreach ($c in $caps) { $byId[[string]$c.id] = $c }
    $workspaces = Invoke-FabricPagedGet -Uri "$BaseUri/workspaces" -Headers $Headers
    foreach ($w in $workspaces) {
        if ($w.type -eq 'Personal' -or $w.type -eq 'AdminWorkspace') { continue }
        $cap = $null
        if ($w.capacityId) { $cap = $byId[[string]$w.capacityId] }
        if ($w.capacityId -and -not $cap) {
            $verdict = [pscustomobject]@{ CopilotCapable = $false; Reason = 'Capacity not visible to you (you need admin or contributor on it)' }
        } elseif ($cap) {
            $verdict = Get-CopilotSkuVerdict -Sku $cap.sku -State $cap.state
        } else {
            $verdict = Get-CopilotSkuVerdict -Sku ''
        }
        [pscustomobject]@{
            Workspace      = $w.displayName
            Capacity       = if ($cap) { $cap.displayName } else { '' }
            Sku            = if ($cap) { $cap.sku } else { '' }
            Region         = if ($cap) { $cap.region } elseif ($w.capacityRegion) { $w.capacityRegion } else { '' }
            State          = if ($cap) { $cap.state } else { '' }
            CopilotCapable = $verdict.CopilotCapable
            Reason         = $verdict.Reason
        }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    if (-not $AccessToken) {
        if (Get-Command Get-AzAccessToken -ErrorAction SilentlyContinue) {
            $tok = Get-AzAccessToken -ResourceUrl 'https://api.fabric.microsoft.com'
            $AccessToken = if ($tok.Token -is [securestring]) { [System.Net.NetworkCredential]::new('', $tok.Token).Password } else { $tok.Token }
        } else {
            throw 'No token: pass -AccessToken, or install Az.Accounts and run Connect-AzAccount first.'
        }
    }
    $headers = @{ Authorization = "Bearer $AccessToken" }
    $report = @(Get-FabricCopilotReport -BaseUri $BaseUri -Headers $headers)
    if ($AsJson) { $report | ConvertTo-Json -Depth 4 } else { $report }
}
