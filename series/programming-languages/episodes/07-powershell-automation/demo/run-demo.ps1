<#
.SYNOPSIS
    The screens of episode 7 in one script, for rehearsal. On camera, type the commands one by one.
.EXAMPLE
    pwsh -NoProfile -File ./demo/run-demo.ps1
#>
[CmdletBinding()]
param()

Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')
$InformationPreference = 'Continue'
if (Test-Path -LiteralPath ./out) { Remove-Item -LiteralPath ./out -Recurse -Force }

Write-Output '### Screen 1: the legacy script against the analyzer'
Invoke-ScriptAnalyzer -Path ./demo/bad-script.ps1 -Settings ./PSScriptAnalyzerSettings.psd1 |
    Sort-Object Line | Format-Table RuleName, Severity, Line -AutoSize | Out-String -Width 150
$clean = Invoke-ScriptAnalyzer -Path ./src -Recurse -Settings ./PSScriptAnalyzerSettings.psd1
Write-Output "src (the module): $(@($clean).Count) findings"

Write-Output ''
Write-Output '### Screen 2: objects in the pipeline, bad rows as errors'
Import-Module ./src/ContosoRequests/ContosoRequests.psd1 -Force
$requests = Import-ContosoRequest -Path ./samples/requests.csv -ErrorVariable rejected -ErrorAction SilentlyContinue
Write-Output "$(@($requests).Count) valid, $(@($rejected).Count) rejected"
$requests | Format-Table Code, Title, Department, Budget, Priority -AutoSize | Out-String -Width 150
$rejected | ForEach-Object { '{0,-30} {1}' -f $_.FullyQualifiedErrorId.Split(',')[0], $_.ErrorDetails.Message }

Write-Output ''
Write-Output '### Screen 3: -WhatIf, then for real, then again'
$routes = $requests | Get-ContosoApprovalRoute -ApproverPath ./samples/approvers.json -ErrorVariable unrouted -ErrorAction SilentlyContinue
Write-Output "no route: $($unrouted[0].Exception.Message)"
$routes | Export-ContosoApprovalPack -Destination ./out -WhatIf
Write-Output "exists after -WhatIf: $(Test-Path ./out)"
$routes | Export-ContosoApprovalPack -Destination ./out -PassThru | Format-Table Code, Priority, Approvers -AutoSize | Out-String -Width 150
Get-ChildItem ./out -Recurse -File | Resolve-Path -Relative | Sort-Object
Get-Content ./out/IT/PR-2026-0304.json
Write-Output ''
$routes | Export-ContosoApprovalPack -Destination ./out -ErrorVariable again -ErrorAction SilentlyContinue
Write-Output "second run: $(@($again).Count) errors, first: $($again[0].FullyQualifiedErrorId.Split(',')[0])"
Remove-Item -LiteralPath ./out -Recurse -Force
