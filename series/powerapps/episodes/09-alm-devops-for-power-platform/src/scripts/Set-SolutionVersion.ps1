<#
.SYNOPSIS
  Stamps the build and revision parts of the solution version into an unpacked solution folder.

.DESCRIPTION
  Uses `pac solution version`. In Power Platform CLI 2.16.1 the command rejects --buildversion and
  --revisionversion in the same call ("Must provide either --buildversion or --revisionversion or --strategy"),
  so this script calls it twice. major.minor stay as they are in Solution.xml: people change those when
  the release changes, the pipeline only counts builds. Prints the resulting version.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Path,
    [Parameter(Mandatory)] [ValidateRange(0, [int]::MaxValue)] [int] $BuildVersion,
    [Parameter(Mandatory)] [ValidateRange(0, [int]::MaxValue)] [int] $RevisionVersion
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Command pac -ErrorAction SilentlyContinue)) { throw 'pac (Power Platform CLI) is not on the PATH.' }
$solutionFile = Join-Path $Path 'Other/Solution.xml'
if (-not (Test-Path -LiteralPath $solutionFile)) { throw "No Other/Solution.xml under $Path" }

foreach ($arguments in @(
        @('--buildversion', "$BuildVersion"),
        @('--revisionversion', "$RevisionVersion"))) {
    $output = & pac solution version @arguments --solutionPath $Path 2>&1
    if ($LASTEXITCODE -ne 0) { throw "pac solution version $($arguments -join ' ') failed:`n$($output -join "`n")" }
}

$version = ([xml](Get-Content -LiteralPath $solutionFile -Raw)).ImportExportXml.SolutionManifest.Version
$expected = "{0}.{1}" -f $BuildVersion, $RevisionVersion
if (-not $version.EndsWith(".$expected")) { throw "Solution.xml says $version after the update, expected ...$expected" }
Write-Output $version
