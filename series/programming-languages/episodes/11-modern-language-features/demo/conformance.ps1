#Requires -Version 7.4
<#
.SYNOPSIS
    Runs the same request digest in TypeScript, C#, Python and PowerShell and checks that all four
    print exactly expected/digest.txt. Works on Windows and Linux (line endings are normalised).
.PARAMETER Python
    Python launcher to use. Defaults to $env:PYTHON, then python, then python3.
#>
[CmdletBinding()]
param([string] $Python = $env:PYTHON)

$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    if (-not $Python) { $Python = (Get-Command python, python3 -ErrorAction SilentlyContinue | Select-Object -First 1)?.Source }
    if (-not $Python) { throw 'No python on PATH. Set $env:PYTHON.' }

    $sample = 'samples/requests.json'
    $expected = (Get-Content -LiteralPath 'expected/digest.txt' -Raw -Encoding utf8) -replace "`r`n", "`n"

    Write-Host 'Toolchain'
    Write-Host "  node       $(node --version)"
    Write-Host "  dotnet     $(dotnet --version)"
    Write-Host "  python     $(& $Python --version)"
    Write-Host "  pwsh       $($PSVersionTable.PSVersion)"
    Write-Host ''

    $runs = [ordered]@{
        'TypeScript  node src/ts/main.ts'           = { node src/ts/main.ts $sample }
        'C#          dotnet run src/cs/digest.cs'   = { dotnet run src/cs/digest.cs -- $sample }
        'Python      python src/py/digest.py'       = { & $Python src/py/digest.py $sample }
        'PowerShell  pwsh src/ps/digest.ps1'        = { pwsh -NoProfile -File src/ps/digest.ps1 $sample }
    }

    $failed = 0
    foreach ($name in $runs.Keys) {
        $actual = ((& $runs[$name]) -join "`n") + "`n"
        $lines = ($actual -split "`n").Count - 1
        if ($actual -ceq $expected) {
            Write-Host ('[ok]   {0,-42} {1} lines, identical to expected/digest.txt' -f $name, $lines)
        }
        else {
            $failed++
            Write-Host ('[FAIL] {0,-42} differs from expected/digest.txt' -f $name)
            Compare-Object ($expected -split "`n") ($actual -split "`n") | Select-Object -First 10 | Out-Host
        }
    }

    Write-Host ''
    Write-Host ($failed -eq 0 ? 'All four languages print the same digest.' : "$failed language(s) differ.")
    exit ($failed -eq 0 ? 0 : 1)
}
finally { Pop-Location }
