#Requires -Version 7.2
<#
.SYNOPSIS
    Apply (or export, or reset) column and view formatting JSON listed in formats/map.json, with PnP PowerShell.
    Formats live in git; this script is the only way they reach the list.

.EXAMPLE
    ./Set-ListFormatting.ps1 -SiteUrl https://contoso.sharepoint.com/sites/ListsDemo -ClientId 00000000-0000-0000-0000-000000000000
.EXAMPLE
    ./Set-ListFormatting.ps1 -Export ./backup -SiteUrl ... -ClientId ...      # save what is live now
.EXAMPLE
    ./Set-ListFormatting.ps1 -Reset -SiteUrl ... -ClientId ... -WhatIf        # back to default rendering
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Apply')]
param(
    [string]$MapPath = (Join-Path $PSScriptRoot 'formats' 'map.json'),
    [string]$SiteUrl,
    [string]$ClientId,
    [switch]$NoConnect,                                   # already connected with Connect-PnPOnline
    [Parameter(ParameterSetName = 'Apply')][switch]$SkipLint,
    [Parameter(ParameterSetName = 'Export', Mandatory)][string]$Export,
    [Parameter(ParameterSetName = 'Reset', Mandatory)][switch]$Reset
)

$ErrorActionPreference = 'Stop'
$map = Get-Content -LiteralPath $MapPath -Raw | ConvertFrom-Json -AsHashtable
$base = Split-Path -Parent (Resolve-Path $MapPath)
$list = $map.list

function Get-FormatJson([string]$File) {
    # Compact JSON: what SharePoint stores in CustomFormatter.
    Get-Content -LiteralPath (Join-Path $base $File) -Raw | ConvertFrom-Json -AsHashtable | ConvertTo-Json -Depth 50 -Compress
}

if ($PSCmdlet.ParameterSetName -eq 'Apply' -and -not $SkipLint) {
    $python = (Get-Command python3, python -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $python) { throw 'python3 not found: install it, or use -SkipLint.' }
    Push-Location $PSScriptRoot
    try { & $python -m formatlint lint $MapPath | Out-Host; $lintExit = $LASTEXITCODE } finally { Pop-Location }
    if ($lintExit -ne 0) { throw 'formatlint found errors; nothing was applied.' }
}

if (-not $NoConnect) {
    if (-not $SiteUrl -or -not $ClientId) { throw 'Provide -SiteUrl and -ClientId, or connect first and use -NoConnect.' }
    Import-Module PnP.PowerShell -ErrorAction Stop
    Connect-PnPOnline -Url $SiteUrl -ClientId $ClientId -DeviceLogin
}

switch ($PSCmdlet.ParameterSetName) {
    'Export' {
        New-Item -ItemType Directory -Path $Export -Force | Out-Null
        foreach ($column in $map.columns.Keys) {
            $f = Get-PnPField -List $list -Identity $column
            $json = if ($f.CustomFormatter) { $f.CustomFormatter | ConvertFrom-Json | ConvertTo-Json -Depth 50 } else { '' }
            Set-Content -LiteralPath (Join-Path $Export "$column.column.json") -Value $json -Encoding utf8
            [pscustomobject]@{ Action = 'Exported'; Target = "$list/$column"; Bytes = $json.Length }
        }
        foreach ($view in $map.views.Keys) {
            $v = Get-PnPView -List $list -Identity $view -Includes CustomFormatter
            $json = if ($v.CustomFormatter) { $v.CustomFormatter | ConvertFrom-Json | ConvertTo-Json -Depth 50 } else { '' }
            $file = ($view -replace '[^\w]+', '-').ToLowerInvariant() + '.view.json'
            Set-Content -LiteralPath (Join-Path $Export $file) -Value $json -Encoding utf8
            [pscustomobject]@{ Action = 'Exported'; Target = "$list/$view"; Bytes = $json.Length }
        }
    }
    default {
        $reset = $PSCmdlet.ParameterSetName -eq 'Reset'
        foreach ($column in $map.columns.Keys) {
            $json = if ($reset) { '' } else { Get-FormatJson $map.columns[$column] }
            if ($PSCmdlet.ShouldProcess("$list/$column", $(if ($reset) { 'Reset column formatting' } else { 'Apply column formatting' }))) {
                Set-PnPField -List $list -Identity $column -Values @{ CustomFormatter = $json } | Out-Null
            }
            [pscustomobject]@{ Action = $(if ($reset) { 'Reset' } else { 'Column' }); Target = "$list/$column"; Bytes = $json.Length }
        }
        foreach ($view in $map.views.Keys) {
            $file = $map.views[$view].format
            if (-not $file -and -not $reset) { continue }
            $json = if ($reset) { '' } else { Get-FormatJson $file }
            if ($PSCmdlet.ShouldProcess("$list/$view", $(if ($reset) { 'Reset view formatting' } else { 'Apply view formatting' }))) {
                Set-PnPView -List $list -Identity $view -Values @{ CustomFormatter = $json } | Out-Null
            }
            [pscustomobject]@{ Action = $(if ($reset) { 'Reset' } else { 'View' }); Target = "$list/$view"; Bytes = $json.Length }
        }
    }
}
