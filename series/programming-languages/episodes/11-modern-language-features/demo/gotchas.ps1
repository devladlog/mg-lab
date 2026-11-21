#Requires -Version 7.4
<#
.SYNOPSIS
    The three things in this episode that bite, each shown for real.
#>
[CmdletBinding()]
param([string] $Python = $env:PYTHON)

$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    if (-not $Python) { $Python = (Get-Command python, python3 -ErrorAction SilentlyContinue | Select-Object -First 1)?.Source }

    Write-Host '== 1. enum is not erasable syntax'
    Write-Host '$ node demo/ts/uses-enum.ts'
    (node demo/ts/uses-enum.ts 2>&1 | Select-String 'ERR_UNSUPPORTED|SyntaxError') | ForEach-Object { $_.Line }
    Write-Host '$ npx tsc -p demo/ts/tsconfig.json'
    npx tsc -p demo/ts/tsconfig.json --pretty false

    Write-Host ''
    Write-Host '== 2. file-based apps target native AOT by default'
    Write-Host '$ dotnet run demo/cs/no-aot-flag.cs -- samples/requests.json'
    (dotnet run demo/cs/no-aot-flag.cs -- samples/requests.json 2>&1 | Select-Object -First 1)
    Write-Host '(the same file with #:property PublishAot=false is src/cs/digest.cs, and it works)'

    Write-Host ''
    Write-Host '== 3. the same expression, 0.29 * 100, in four languages'
    node demo/ts/float-cents.ts
    dotnet run demo/cs/float-cents.cs 2>&1 | Select-Object -Last 1
    & $Python -W default demo/py/float_cents.py 2>&1 | Where-Object { $_ -notmatch '^\s+print' }
    pwsh -NoProfile -Command '$b = 0.29; "PowerShell: [long](0.29 * 100) = $([long]($b * 100)), [Math]::Truncate = $([Math]::Truncate($b * 100))"'
}
finally { Pop-Location }
