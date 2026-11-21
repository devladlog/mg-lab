<#
.SYNOPSIS
  Packs an unpacked solution folder into an unmanaged and a managed zip and checks both.

.DESCRIPTION
  `pac solution pack --packagetype Both` writes <name>.zip (unmanaged) and <name>_managed.zip.
  The zips are named after the solution version, e.g. EquipmentDesk_1_0_20261121_3.zip, so a build
  artifact always says what it is. After packing, both zips are opened and checked: solution.xml
  must say Managed 0 / Managed 1 and carry the folder's version. Prints the two paths, unmanaged first.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $SourcePath,
    [Parameter(Mandatory)] [string] $OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (-not (Get-Command pac -ErrorAction SilentlyContinue)) { throw 'pac (Power Platform CLI) is not on the PATH.' }
$manifest = ([xml](Get-Content -LiteralPath (Join-Path $SourcePath 'Other/Solution.xml') -Raw)).ImportExportXml.SolutionManifest
$name = $manifest.UniqueName
$version = $manifest.Version
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$base = "{0}_{1}" -f $name, ($version -replace '\.', '_')
$unmanaged = Join-Path (Resolve-Path $OutputDirectory) "$base.zip"
$managed = Join-Path (Resolve-Path $OutputDirectory) "${base}_managed.zip"

$output = & pac solution pack --zipfile $unmanaged --folder $SourcePath --packagetype Both 2>&1
if ($LASTEXITCODE -ne 0) { throw "pac solution pack failed:`n$($output -join "`n")" }

foreach ($case in @(@{ File = $unmanaged; Managed = '0' }, @{ File = $managed; Managed = '1' })) {
    if (-not (Test-Path -LiteralPath $case.File)) { throw "pac did not write $($case.File)" }
    $zip = [System.IO.Compression.ZipFile]::OpenRead($case.File)
    try {
        $entry = $zip.Entries | Where-Object { $_.FullName -eq 'solution.xml' } | Select-Object -First 1
        if (-not $entry) { throw "$($case.File) has no solution.xml" }
        $reader = [System.IO.StreamReader]::new($entry.Open())
        try { $xml = [xml] $reader.ReadToEnd() } finally { $reader.Dispose() }
    }
    finally { $zip.Dispose() }
    $m = $xml.ImportExportXml.SolutionManifest
    if ("$($m.Managed)" -ne $case.Managed) { throw "$($case.File): <Managed> is $($m.Managed), expected $($case.Managed)" }
    if ($m.Version -ne $version) { throw "$($case.File): version is $($m.Version), expected $version" }
}

Write-Output $unmanaged
Write-Output $managed
