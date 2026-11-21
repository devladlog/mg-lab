<#
.SYNOPSIS
  Runs the episode 5 test suites (xUnit v3 + NUnit, both on Microsoft.Testing.Platform).
  Works in PowerShell 7 on Windows (the recording laptop) and Linux. Run from anywhere.

.EXAMPLE
  ./deploy/Invoke-Tests.ps1                 # both suites
  ./deploy/Invoke-Tests.ps1 -Mode Unit      # unit tests only, filter routed per framework
  ./deploy/Invoke-Tests.ps1 -Mode FilterGotcha   # the xUnit-only option that breaks the NUnit app (exit code 5)
  ./deploy/Invoke-Tests.ps1 -Mode Coverage  # cobertura + TRX for both, merged HTML report in coverage-report/
  $env:REQUESTS_TEST_SQLSERVER = '<connection string, no database>'; ./deploy/Invoke-Tests.ps1 -Mode SqlServer
#>
[CmdletBinding()]
param(
    [ValidateSet('All', 'Unit', 'Integration', 'FilterGotcha', 'Coverage', 'SqlServer')]
    [string] $Mode = 'All'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    # One filter per framework: xUnit v3 uses --filter-trait, NUnit keeps the VSTest-style --filter.
    # Directory.Build.targets appends XunitArgs / NUnitArgs only to the projects that understand them.
    function Invoke-Filtered([string] $category) {
        dotnet test "-p:XunitArgs=--filter-trait Category=$category" "-p:NUnitArgs=--filter TestCategory=$category"
    }

    switch ($Mode) {
        'All'          { dotnet test }
        'Unit'         { Invoke-Filtered 'Unit' }
        'Integration'  { Invoke-Filtered 'Integration' }
        'SqlServer'    {
            if (-not $env:REQUESTS_TEST_SQLSERVER) { throw 'Set $env:REQUESTS_TEST_SQLSERVER first (see demo.md).' }
            Invoke-Filtered 'SqlServer'
        }
        'FilterGotcha' { dotnet test --filter-trait Category=Unit }      # NUnit app: "Unknown option", exit code 5
        'Coverage'     {
            Remove-Item -Recurse -Force TestResults, coverage-report -ErrorAction SilentlyContinue
            dotnet test --results-directory TestResults --coverage --coverage-output-format cobertura --report-trx
            $testExit = $LASTEXITCODE
            dotnet tool restore | Out-Null
            dotnet reportgenerator "-reports:TestResults/*.cobertura.xml" "-targetdir:coverage-report" `
                "-reporttypes:Html;TextSummary" "-classfilters:-Microsoft.*;-ProjectRequests.Api.Migrations.*" | Out-Null
            Get-Content coverage-report/Summary.txt -TotalCount 12
            Write-Host "HTML report: $(Join-Path $root 'coverage-report/index.html')"
            $global:LASTEXITCODE = $testExit
        }
    }
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
