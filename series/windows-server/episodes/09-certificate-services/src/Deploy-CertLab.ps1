<#
.SYNOPSIS
Builds and maintains the lab CA. All steps honor -WhatIf.
  -Step Ca     install the CA role service, configure an enterprise root CA, set the CRL periods (runs on the CA server from cert-lab.json)
  -Step Http   serve the CRL over HTTP and add that URL to issued certificates
  -Step Renew  renew the certificates the check found expired or expiring (needs -FromFacts or a live check)
.EXAMPLE
./Deploy-CertLab.ps1 -Step Ca -WhatIf ; ./Deploy-CertLab.ps1 -Step Ca -AllowCaInstall
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [ValidateSet('Ca', 'Http', 'Renew')] [string] $Step,
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'cert-lab.json'),
    [string] $FromFacts,
    [datetime] $Now = [datetime]::UtcNow,
    [pscredential] $Credential,
    [switch] $AllowCaInstall
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'CertLab/CertLab.psd1') -Force
$config = Read-CertLabConfig -Path $ConfigPath

if ($Step -eq 'Renew') {
    if ($FromFacts) { $facts = Get-Content -Raw -LiteralPath $FromFacts | ConvertFrom-Json }
    else { $facts = Get-CertFacts -ComputerName @($config.Targets | ForEach-Object { [string]$_.Name }) -Credential $Credential }
    $hosts = @($facts.Hosts)
    $findings = @($hosts | ForEach-Object { Test-CertHost -Facts $_ -Config $config -Now $Now })
    $plan = @(Get-CertRenewalPlan -Hosts $hosts -Findings $findings -Now $Now)
    $plan | Format-Table Target, Kind, DaysLeft, Template, Subject, Why -Wrap | Out-String -Width 200 | Write-Output
    if ($FromFacts -and -not $WhatIfPreference) { Write-Warning 'Saved facts are a snapshot: renewing from them is only sensible with -WhatIf.' }
    Invoke-CertRenewal -Plan $plan -Credential $Credential -WhatIf:$WhatIfPreference
    return
}
$plan = @(Get-CertCaPlan -Config $config -Step $Step)
$plan | Format-Table Id, Irreversible, Description -Wrap | Out-String -Width 200 | Write-Output
Invoke-CertCaPlan -Plan $plan -ComputerName ([string]$config.Ca.Server) -Credential $Credential -AllowCaInstall:$AllowCaInstall -WhatIf:$WhatIfPreference
