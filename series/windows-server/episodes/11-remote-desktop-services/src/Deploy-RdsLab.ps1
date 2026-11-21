<#
.SYNOPSIS
Brings a Remote Desktop Services deployment to rds-lab.json, or logs off stale sessions. Everything supports -WhatIf; read the plan first.
.DESCRIPTION
 -Step Plan       Read the deployment (read-only) and print the plan: what would change, and the value found now.
 -Step Apply      Plan, then apply: license role + mode, session collection, collection settings. The role service install
                  (New-RDSessionDeployment) is disruptive and only runs with -AllowDeployment.
 -Step Logoff     Log off DISCONNECTED sessions of the users matching -UserName (a -like pattern). Run on the connection broker.
Run on the connection broker (or a host with the RemoteDesktop module that can reach it) as a member of local Administrators there.
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)] [ValidateSet('Plan', 'Apply', 'Logoff')] [string] $Step,
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'rds-lab.json'),
    [pscredential] $Credential,
    [switch] $AllowDeployment,
    [string] $UserName
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'RdsLab/RdsLab.psd1') -Force
$config = Read-RdsLabConfig -Path $ConfigPath

switch ($Step) {
    { $_ -in 'Plan', 'Apply' } {
        $facts = Get-RdsFacts -Config $config -Credential $Credential
        $plan = @(Get-RdsDeploymentPlan -Config $config -Facts $facts)
        if (-not $plan.Count) { Write-Output 'Nothing to change.'; return }
        $plan | Format-Table Order, Id, Cmdlet, Disruptive, Why -Wrap | Out-String -Width 200 | Write-Output
        $plan | Where-Object { $_.Before } | ForEach-Object { '{0}: before = {1}' -f $_.Id, (($_.Before.GetEnumerator() | ForEach-Object { '{0}={1}' -f $_.Key, $_.Value }) -join '; ') }
        if ($Step -eq 'Apply') { Invoke-RdsDeploymentPlan -Plan $plan -AllowDeployment:$AllowDeployment -WhatIf:$WhatIfPreference -Confirm:$false }
    }
    'Logoff' {
        if (-not $UserName) { throw '-Step Logoff needs -UserName (a -like pattern, for example alex.demo).' }
        Import-Module RemoteDesktop
        Invoke-RdsDisconnectedLogoff -UserName $UserName -ConnectionBroker ([string]$config.Deployment.ConnectionBroker) -CollectionName ([string]$config.Collection.Name) -WhatIf:$WhatIfPreference -Confirm:$false
    }
}
