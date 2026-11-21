#Requires -Version 7.4
[CmdletBinding()]
param([Parameter(Mandatory, Position = 0)][string] $Path)

Import-Module (Join-Path $PSScriptRoot 'Digest.psm1') -Force
[Console]::Out.Write((Invoke-Digest -Path $Path))
