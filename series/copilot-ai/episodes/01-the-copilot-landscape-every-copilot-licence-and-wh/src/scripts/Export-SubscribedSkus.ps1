<#
.SYNOPSIS
  Exports the tenant's subscribed SKUs (with service plans) to JSON for copilot_landscape's licence audit.
.DESCRIPTION
  Uses the Microsoft Graph PowerShell SDK (Get-MgSubscribedSku, GET /subscribedSkus).
  Delegated permission: LicenseAssignment.Read.All (least privileged). Read-only: nothing in the tenant changes.
  Needs the tenant: run it as the lab admin, signing in interactively on camera is fine, never paste secrets.
.EXAMPLE
  ./Export-SubscribedSkus.ps1 -OutFile ./skus.json
  python -m copilot_landscape audit --skus ./skus.json
#>
[CmdletBinding()]
param(
    [string]$OutFile = './skus.json'
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Module -ListAvailable -Name Microsoft.Graph.Identity.DirectoryManagement)) {
    throw 'Install the SDK first: Install-Module Microsoft.Graph.Identity.DirectoryManagement -Scope CurrentUser'
}

Connect-MgGraph -Scopes 'LicenseAssignment.Read.All' -NoWelcome
try {
    $skus = Get-MgSubscribedSku -All
    # PascalCase property names; the Python loader lower-cases keys, so both shapes work.
    $skus | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutFile -Encoding utf8
    Write-Host ("{0} SKUs written to {1}" -f @($skus).Count, $OutFile)
}
finally {
    Disconnect-MgGraph | Out-Null
}
