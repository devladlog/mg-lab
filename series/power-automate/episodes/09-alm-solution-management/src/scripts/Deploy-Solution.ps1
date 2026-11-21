<#
.SYNOPSIS
  Packs the unpacked solution as managed and imports it into one environment with a deployment settings file.
.DESCRIPTION
  The same steps as pipelines/release.yml, for a laptop: no Azure DevOps needed. Sign in first
  (`pac auth create`) or set PAC_APPLICATION_ID, PAC_CLIENT_SECRET and PAC_TENANT_ID for a service principal.
  Upgrade imports with --stage-and-upgrade (components removed from the solution are removed from the target);
  Update leaves them there.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SolutionFolder,
    [Parameter(Mandatory)][string]$SettingsFile,
    [Parameter(Mandatory)][string]$EnvironmentUrl,
    [ValidateSet('Update', 'Upgrade')][string]$Mode = 'Upgrade',
    [string]$OutputFolder = (Join-Path ([IO.Path]::GetTempPath()) 'alm-out'),
    [string]$Pac = 'pac'
)
$ErrorActionPreference = 'Stop'

function Invoke-Pac {
    param([string[]]$Arguments)
    & $Pac @Arguments
    if ($LASTEXITCODE -ne 0) { throw "pac $($Arguments[0..1] -join ' ') failed with exit code $LASTEXITCODE" }
}

if (-not (Test-Path -LiteralPath $SettingsFile)) { throw "Settings file not found: $SettingsFile" }
$settingsText = Get-Content -LiteralPath $SettingsFile -Raw
$left = [regex]::Matches($settingsText, '\$\{[A-Za-z_][A-Za-z0-9_]*\}') | ForEach-Object { $_.Value } | Sort-Object -Unique
if ($left) { throw "Settings file still has unresolved tokens: $($left -join ', '). Render it first (python -m almkit render-settings)." }

$solutionXml = Join-Path $SolutionFolder 'Other/Solution.xml'
if (-not (Test-Path -LiteralPath $solutionXml)) { throw "Not an unpacked solution (no Other/Solution.xml): $SolutionFolder" }
$name = ([xml](Get-Content -LiteralPath $solutionXml -Raw -Encoding utf8)).ImportExportXml.SolutionManifest.UniqueName
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null
$zip = Join-Path $OutputFolder "${name}_managed.zip"

if ($env:PAC_CLIENT_SECRET) {
    Invoke-Pac @('auth', 'create', '--applicationId', $env:PAC_APPLICATION_ID, '--clientSecret', $env:PAC_CLIENT_SECRET,
        '--tenant', $env:PAC_TENANT_ID, '--environment', $EnvironmentUrl)
}

Invoke-Pac @('solution', 'pack', '--zipfile', $zip, '--folder', $SolutionFolder, '--packagetype', 'Managed')

$import = @('solution', 'import', '--path', $zip, '--environment', $EnvironmentUrl, '--settings-file', $SettingsFile,
    '--activate-plugins', '--publish-changes', '--async')
if ($Mode -eq 'Upgrade') { $import += '--stage-and-upgrade' }
Invoke-Pac $import
Write-Host "Imported $name ($Mode) into $EnvironmentUrl"
