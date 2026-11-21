# Three things that bite in PowerShell automation. Run: pwsh -NoProfile -File demo/gotchas.ps1
$ErrorActionPreference = 'Continue'
Import-Module (Join-Path $PSScriptRoot '../src/ContosoRequests/ContosoRequests.psd1') -Force
$csv = Join-Path $PSScriptRoot '../samples/requests.csv'
$approvers = Join-Path $PSScriptRoot '../samples/approvers.json'

Write-Output '--- 1. try/catch does not see non-terminating errors'
$all = $null; $caught = $false
try { $all = @(Import-ContosoRequest $csv -ErrorAction SilentlyContinue) } catch { $caught = $true }
Write-Output "default          : caught=$caught  requests=$($all.Count)"

$all = $null; $caught = $false; $why = ''
try { $all = @(Import-ContosoRequest $csv -ErrorAction Stop) } catch { $caught = $true; $why = $_.FullyQualifiedErrorId }
Write-Output "-ErrorAction Stop: caught=$caught ($why)  requests=$($all.Count)"

Write-Output ''
Write-Output '--- 2. Output you did not ask for'
function Get-CodeListWrong {
    $list = [System.Collections.ArrayList]::new()
    foreach ($code in 'PR-1', 'PR-2') { $list.Add($code) }      # Add returns the new index
    $list
}
function Get-CodeListRight {
    $list = [System.Collections.ArrayList]::new()
    foreach ($code in 'PR-1', 'PR-2') { $null = $list.Add($code) }
    $list
}
Write-Output ('wrong : ' + ((Get-CodeListWrong) -join ' | '))
Write-Output ('right : ' + ((Get-CodeListRight) -join ' | '))

Write-Output ''
Write-Output '--- 3. ConvertTo-Json stops at depth 2'
$route = Import-ContosoRequest $csv -ErrorAction SilentlyContinue |
    Where-Object Code -eq 'PR-2026-0303' |
    Get-ContosoApprovalRoute -ApproverPath $approvers
$shape = [ordered]@{
    route = [ordered]@{
        approvers = @($route.Approvers | ForEach-Object { [ordered]@{ role = $_.Role; name = $_.Name } })
    }
}
$flat = $shape | ConvertTo-Json -Compress -WarningVariable depthWarning -WarningAction SilentlyContinue
Write-Output "default : $flat"
Write-Output "warning : $($depthWarning[0].Message)"
Write-Output ('-Depth 5: ' + ($shape | ConvertTo-Json -Compress -Depth 5))
