#Requires -Version 7.2
<#
.SYNOPSIS
  Builds the guest page and the API and writes a ready-to-deploy zip for Flex Consumption (az functionapp deployment source config-zip).
.DESCRIPTION
  Works in a staging folder under the temp directory, never inside the repo: the staging copy gets production-only
  node_modules. Checks that every function module loads before it zips.
.EXAMPLE
  ./Build-Package.ps1 -OutFile ./hybrid-api.zip
#>
[CmdletBinding()]
param([string]$OutFile = (Join-Path ([IO.Path]::GetTempPath()) 'hybrid-api.zip'))
$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot '..' 'src' | Resolve-Path
$stage = Join-Path ([IO.Path]::GetTempPath()) ("hybrid-stage-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    Push-Location (Join-Path $src 'join'); try { npm ci --no-audit --no-fund --loglevel=error; npm run build --silent } finally { Pop-Location }
    Push-Location (Join-Path $src 'api');  try { npm ci --no-audit --no-fund --loglevel=error; npm run build --silent } finally { Pop-Location }

    foreach ($item in 'package.json', 'package-lock.json', 'host.json', 'dist', 'site') {
        Copy-Item -Recurse -Path (Join-Path $src 'api' $item) -Destination $stage
    }
    Push-Location $stage; try { npm ci --omit=dev --no-audit --no-fund --loglevel=error } finally { Pop-Location }

    # Smoke test: each function module must load (this catches a bad import path before Azure does).
    Push-Location $stage
    try {
        foreach ($f in 'invites', 'token', 'page') {
            node -e "require('./dist/functions/$f.js')" 2>&1 | Out-Null   # prints "test mode" warnings outside the Functions host
            if ($LASTEXITCODE -ne 0) { throw "dist/functions/$f.js does not load" }
        }
    }
    finally { Pop-Location }
    foreach ($f in 'index.html', 'join.js', 'join.css') {
        if (-not (Test-Path (Join-Path $stage 'site' $f))) { throw "site/$f is missing" }
    }
    if (Test-Path $OutFile) { Remove-Item $OutFile }
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $OutFile
    $mb = [math]::Round((Get-Item $OutFile).Length / 1MB, 1)
    "Wrote $OutFile ($mb MB)"
}
finally { Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue }
