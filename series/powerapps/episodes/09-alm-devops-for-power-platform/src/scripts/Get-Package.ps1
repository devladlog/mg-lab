<#
.SYNOPSIS
  Finds the managed solution zip in a build artifact folder and, in a pipeline, publishes its path as a variable.

.DESCRIPTION
  The packed zips carry the version in their name (EquipmentDesk_1_0_20261121_3_managed.zip), which the
  deployment stages cannot know when the YAML is written. Exactly one *_managed.zip must be there:
  none or several is an error, so a stale file can never be imported by accident.
  With -SetVariable NAME the script also prints the Azure Pipelines logging command that sets NAME
  to the path for the following steps.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Directory,
    [string] $SetVariable
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$found = @(Get-ChildItem -LiteralPath $Directory -Filter '*_managed.zip' -File -ErrorAction Stop)
if ($found.Count -ne 1) {
    throw "Expected exactly one *_managed.zip in $Directory, found $($found.Count)."
}
$path = $found[0].FullName
if ($SetVariable) { Write-Output "##vso[task.setvariable variable=$SetVariable]$path" }
Write-Output $path
