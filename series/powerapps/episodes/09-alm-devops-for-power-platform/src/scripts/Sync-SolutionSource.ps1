<#
.SYNOPSIS
  Replaces the solution source folder in the repo with a fresh unpack, deleting what is no longer there.

.DESCRIPTION
  `pac solution unpack` does not delete files by default: it prints "Not deleting files" and leaves
  the folder of a component that was removed from the solution, so the next pack would bring it back.
  The export pipeline therefore unpacks into an empty temp folder and this script mirrors that folder
  into source control (git shows the real difference), then runs Test-SolutionSource.ps1 on the result.
  Prints the list of files that were added, changed and removed.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $UnpackedPath,
    [Parameter(Mandatory)] [string] $SourcePath,
    [string] $ExpectedName = 'EquipmentDesk',
    [string] $ExpectedPrefix = 'contoso'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath (Join-Path $UnpackedPath 'Other/Solution.xml'))) {
    throw "$UnpackedPath does not look like an unpacked solution (no Other/Solution.xml); nothing was changed."
}

function Get-FileHashMap([string] $Root) {
    if (-not (Test-Path -LiteralPath $Root)) { return @{} }
    $map = @{}
    $full = (Resolve-Path -LiteralPath $Root).Path
    Get-ChildItem -LiteralPath $full -Recurse -File | ForEach-Object {
        $map[$_.FullName.Substring($full.Length).TrimStart('/\').Replace('\', '/')] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }
    return $map
}

$before = Get-FileHashMap $SourcePath
$new = Get-FileHashMap $UnpackedPath

if (Test-Path -LiteralPath $SourcePath) { Get-ChildItem -LiteralPath $SourcePath -Force | Remove-Item -Recurse -Force }
New-Item -ItemType Directory -Force -Path $SourcePath | Out-Null
Copy-Item -Path (Join-Path $UnpackedPath '*') -Destination $SourcePath -Recurse -Force

foreach ($f in ($new.Keys | Sort-Object)) {
    if (-not $before.ContainsKey($f)) { Write-Output "added    $f" }
    elseif ($before[$f] -ne $new[$f]) { Write-Output "changed  $f" }
}
foreach ($f in ($before.Keys | Sort-Object)) {
    if (-not $new.ContainsKey($f)) { Write-Output "removed  $f" }
}

& (Join-Path $PSScriptRoot 'Test-SolutionSource.ps1') -Path $SourcePath -ExpectedName $ExpectedName -ExpectedPrefix $ExpectedPrefix
exit $LASTEXITCODE
