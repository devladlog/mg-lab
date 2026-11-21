#requires -Version 7.2
<#
.SYNOPSIS  The same Key Vault, seen from outside and from inside the network (DEVLADLOG Deep Dive #9).
.DESCRIPTION
  Outside (your laptop): the vault name resolves to a public address and the data plane answers 403.
  Inside (the workload VM): the name resolves to the private endpoint, the VM's managed identity reads the secret.
  Needs `az login` as an account that may run commands on the VM. Use -PrintOnly to see the commands without running them.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$VaultName,
    [Parameter(Mandatory)][string]$VmName,
    [string]$VaultSuffix = 'vault.azure.net',
    [switch]$PrintOnly
)
$ErrorActionPreference = 'Stop'
$hostName = "$VaultName.$VaultSuffix"
$checkScript = Join-Path $PSScriptRoot 'vm-check.sh'

$outside = "az keyvault secret show --vault-name $VaultName --name demo-secret --query value -o tsv"
$inside = "az vm run-command invoke -g $ResourceGroup -n $VmName --command-id RunShellScript --scripts `@$checkScript --parameters $hostName --query value[0].message -o tsv"

if ($PrintOnly) { $outside; $inside; return }

Write-Host "`n== OUTSIDE: from this machine" -ForegroundColor Cyan
Write-Host "DNS:"; (Resolve-DnsName $hostName -Type A -ErrorAction SilentlyContinue | Where-Object IPAddress | Select-Object Name, IPAddress | Format-Table | Out-String).Trim()
Write-Host "Data plane (expect a Forbidden error):"
try { Invoke-Expression $outside 2>&1 | Select-Object -First 3 } catch { $_.Exception.Message }

Write-Host "`n== INSIDE: from the workload VM" -ForegroundColor Cyan
Invoke-Expression $inside
