# Test harness only: stand-ins for Connect-PnPOnline and Submit-PnPSearchQuery, then runs Get-AgentFileInventory.ps1.
# Nothing here talks to SharePoint.
param([string]$Script, [string]$CallLog, [string]$ArgsJson, [string]$Rows)

$global:Calls = [System.Collections.Generic.List[object]]::new()
function global:Connect-PnPOnline { [CmdletBinding()] param($Url, [switch]$Interactive, $ClientId)
    $global:Calls.Add([ordered]@{ cmd = 'Connect-PnPOnline'; Url = "$Url"; ClientId = "$ClientId"; Interactive = [bool]$Interactive }) }
function global:Submit-PnPSearchQuery { [CmdletBinding()] param($Query, [switch]$All, [string[]]$SelectProperties)
    $global:Calls.Add([ordered]@{ cmd = 'Submit-PnPSearchQuery'; Query = "$Query"; All = [bool]$All; Select = ($SelectProperties -join ',') })
    $list = @()
    if ($Rows) { foreach ($r in (Get-Content -Raw $Rows | ConvertFrom-Json)) { $h = @{}; $r.PSObject.Properties | ForEach-Object { $h[$_.Name] = $_.Value }; $list += , $h } }
    [pscustomobject]@{ ResultRows = $list }
}
$splat = @{}
(Get-Content -Raw $ArgsJson | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $splat[$_.Name] = $_.Value }
$err = $null
try { & $Script @splat | Out-Null } catch { $err = $_.Exception.Message }
@{ calls = $global:Calls; error = $err } | ConvertTo-Json -Depth 5 | Set-Content -Path $CallLog
