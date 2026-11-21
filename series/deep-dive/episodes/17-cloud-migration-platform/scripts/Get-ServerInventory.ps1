<#
.SYNOPSIS
  Collect the facts Azure Migrate's CSV import needs from Windows servers, as the inventory JSON that `python -m migplan` reads.
.EXAMPLE
  # Local machine
  ./Get-ServerInventory.ps1 -OutFile inventory.json
.EXAMPLE
  # Several servers over PowerShell remoting. The credential is prompted for or passed in, never stored in a file.
  $cred = Get-Credential
  ./Get-ServerInventory.ps1 -ComputerName fs01,app01 -Credential $cred -OutFile inventory.json
.EXAMPLE
  # Convert facts you saved earlier (works on Linux too, used by the tests)
  ./Get-ServerInventory.ps1 -FromFacts facts.json -OutFile inventory.json
#>
[CmdletBinding()]
param(
    [string[]]$ComputerName,
    [pscredential]$Credential,
    [string]$FromFacts,
    [string]$Role = 'unknown',
    [string]$Criticality = 'medium',
    [Parameter(Mandatory)][string]$OutFile
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Inventory.psm1') -Force

if ($FromFacts) {
    $raw = Get-Content -Raw -Path $FromFacts | ConvertFrom-Json
    $facts = @($raw | ForEach-Object {
        @{
            server      = ConvertTo-ServerRecord -ComputerSystem $_.computerSystem -OperatingSystem $_.operatingSystem -Processors @($_.processors) `
                              -Disks @($_.disks) -IPAddresses @($_.ipAddresses) -FirmwareType $_.firmwareType `
                              -CpuUtilPct $_.cpuUtilPct -MemUtilPct $_.memUtilPct -Role $Role -Criticality $Criticality
            connections = @(ConvertTo-ConnectionRecords -Source $_.computerSystem.Name -Rows @($_.tcpConnections))
        }
    })
}
elseif ($ComputerName) {
    $moduleText = Get-Content -Raw -Path (Join-Path $PSScriptRoot 'Inventory.psm1')
    $facts = foreach ($name in $ComputerName) {
        $args = @{ ComputerName = $name; ArgumentList = @($moduleText, $Role, $Criticality) }
        if ($Credential) { $args.Credential = $Credential }
        Invoke-Command @args -ScriptBlock {
            param($text, $r, $c)
            $tmp = Join-Path $env:TEMP 'Inventory.psm1'
            Set-Content -Path $tmp -Value $text
            Import-Module $tmp -Force
            Get-LocalServerFacts -Role $r -Criticality $c
        }
    }
}
else {
    $facts = @(Get-LocalServerFacts -Role $Role -Criticality $Criticality)
}

ConvertTo-InventoryJson -Facts @($facts) | Set-Content -Path $OutFile -Encoding utf8
Write-Host "Wrote $OutFile ($(@($facts).Count) server(s))"
