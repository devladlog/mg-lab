<#
  MG Lab #6 — end-to-end run. Usage (Cloud Shell, pwsh):
    ./run-migration.ps1 -SiteUrl https://<tenant>.sharepoint.com/sites/<site> -ClientId <app-id> [-WhatIf]
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string] $SiteUrl,
    [Parameter(Mandatory)][string] $ClientId,
    [string] $SourcePath = './legacy-share',
    [string] $Library = 'Migrated Documents'
)
$ErrorActionPreference = 'Stop'
Import-Module "$PSScriptRoot/src/MgMigration.psm1" -Force

Write-Host "`n1. Inventory + pre-flight" -ForegroundColor Cyan
$siteRel = ([uri]$SiteUrl).AbsolutePath.TrimEnd('/')
$inventory = Get-MgMigrationInventory -SourcePath $SourcePath -TargetLibraryUrl "$siteRel/$Library"
$inventory | Export-Csv ./inventory.csv -NoTypeInformation -Encoding utf8
$inventory | Group-Object Ready | ForEach-Object { '   {0}: {1}' -f ($_.Name -eq 'True' ? 'Ready' : 'Blocked'), $_.Count }
$inventory | Where-Object { -not $_.Ready } | Format-Table RelativePath, Issues -AutoSize | Out-String -Width 160 | Write-Host

Write-Host "2. Connect (delegated, device code)" -ForegroundColor Cyan
Connect-PnPOnline -Url $SiteUrl -ClientId $ClientId -DeviceLogin

Write-Host "3. Provision target (idempotent)" -ForegroundColor Cyan
Initialize-MgMigrationTarget -Library $Library

Write-Host "4. Migrate" -ForegroundColor Cyan
$log = Invoke-MgMigration -SourcePath $SourcePath -Inventory $inventory -Library $Library -WhatIf:$WhatIfPreference
$log | Group-Object Status | Format-Table Name, Count -AutoSize | Out-String | Write-Host

Write-Host "5. Verify" -ForegroundColor Cyan
Test-MgMigrationResult -Inventory $inventory -Library $Library | Format-Table -AutoSize | Out-String | Write-Host
