<#
.SYNOPSIS
Applies the remediation plan and the Windows LAPS rollout. Everything supports -WhatIf; read the plan first.
.DESCRIPTION
 -Step Harden    Check -> plan -> apply the safe fixes (SMB 1 off, inbound SMB signing, WDigest off, Process Creation audit + command line). -IncludeRisky adds LmCompatibilityLevel.
 -Step Rollback  Reverse of the Harden plan from the values read before (writes them back; the audit setting is turned off again)
 -Step Laps      Windows LAPS in Active Directory: schema (only with -AllowSchemaUpdate), OU permission, GPO, link. Run on CON-DC01 or a host with RSAT (LAPS, GroupPolicy, ActiveDirectory modules)
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)] [ValidateSet('Harden', 'Rollback', 'Laps')] [string] $Step,
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'sec-lab.json'),
    [string[]] $ComputerName,
    [pscredential] $Credential,
    [switch] $IncludeRisky,
    [switch] $AllowSchemaUpdate,
    [string] $RollbackFile
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'SecLab/SecLab.psd1') -Force
$config = Read-SecLabConfig -Path $ConfigPath

switch ($Step) {
    'Harden' {
        if (-not $ComputerName) { $ComputerName = @($config.Targets | Where-Object { -not $_.Optional } | ForEach-Object { [string]$_.Name }) }
        $facts = @(Get-SecFacts -ComputerName $ComputerName -Credential $Credential)
        $findings = @($facts | ForEach-Object { Test-SecHost -Facts $_ -Config $config })
        $plan = @(Get-SecRemediationPlan -Findings $findings -Config $config -Facts $facts -IncludeRisky:$IncludeRisky)
        if (-not $plan.Count) { Write-Output 'Nothing to change.'; return }
        $plan | Format-Table Target, Fix, Before, Value, Why -Wrap | Out-String -Width 200 | Write-Output
        if ($RollbackFile) { ConvertTo-Json -InputObject @(Get-SecRollbackPlan -Plan $plan) -Depth 5 | Set-Content -LiteralPath $RollbackFile -Encoding UTF8 }
        Invoke-SecRemediation -Plan $plan -Credential $Credential -WhatIf:$WhatIfPreference -Confirm:$false
    }
    'Rollback' {
        if (-not $RollbackFile) { throw '-Step Rollback needs -RollbackFile (written by -Step Harden -RollbackFile).' }
        $plan = @(Get-Content -Raw -LiteralPath $RollbackFile | ConvertFrom-Json)
        Invoke-SecRemediation -Plan $plan -Credential $Credential -WhatIf:$WhatIfPreference -Confirm:$false
    }
    'Laps' {
        $domainDn = [string](Get-ADDomain).DistinguishedName
        $schemaDn = [string](Get-ADRootDSE).schemaNamingContext
        $present = [bool](Get-ADObject -SearchBase $schemaDn -Filter "name -eq 'ms-LAPS-Password'" -ErrorAction SilentlyContinue)
        $plan = @(Get-SecLapsPlan -Config $config -SchemaPresent $present -DomainDn $domainDn)
        $plan | Format-Table Order, Action, Cmdlet, Irreversible, Why -Wrap | Out-String -Width 200 | Write-Output
        Invoke-SecLapsPlan -Plan $plan -AllowSchemaUpdate:$AllowSchemaUpdate -WhatIf:$WhatIfPreference -Confirm:$false
    }
}
