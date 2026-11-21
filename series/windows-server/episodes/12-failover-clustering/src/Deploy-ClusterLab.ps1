<#
.SYNOPSIS
Builds, drills and removes the lab failover cluster. Everything supports -WhatIf; read the plan first.
.DESCRIPTION
 -Step Plan    Read the nodes (read-only) and print the build plan.
 -Step Build   Plan, then apply: Failover Clustering and IIS on the nodes, validation, New-Cluster, witness share, quorum, clustered role.
               Run it ON a cluster node (the console of CON-NODE01): Learn says New-Cluster and Add-ClusterGenericServiceRole cannot run remotely without CredSSP.
 -Step Drain   Planned failover: pause the node that owns the role with -Drain, show where it went, resume the node. Run on a node.
 -Step Remove  Tear-down: Remove-Cluster -CleanupAD and the witness share. Run on a node.
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)] [ValidateSet('Plan', 'Build', 'Drain', 'Remove')] [string] $Step,
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'cluster-lab.json'),
    [pscredential] $Credential
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ClusterLab/ClusterLab.psd1') -Force
$config = Read-ClfLabConfig -Path $ConfigPath
$nodes = @($config.Cluster.Nodes | ForEach-Object { [string]$_ })

switch ($Step) {
    { $_ -in 'Plan', 'Build' } {
        $facts = Get-ClfFacts -Config $config -Credential $Credential
        $plan = @(Get-ClfBuildPlan -Config $config -Facts $facts)
        $plan | Format-Table Order, Id, Cmdlet, LocalOnly, CreatesAdObjects, Why -Wrap | Out-String -Width 220 | Write-Output
        if ($Step -eq 'Build') {
            Invoke-ClfPlan -Plan $plan -NodeName $nodes -Credential $Credential -WhatIf:$WhatIfPreference -Confirm:$false
            if (-not $WhatIfPreference) { Get-ClusterNode -Cluster $config.Cluster.Name | Format-Table Name, State; Get-ClusterGroup -Cluster $config.Cluster.Name | Format-Table Name, OwnerNode, State; Get-ClusterQuorum -Cluster $config.Cluster.Name | Format-List * }
        }
    }
    'Drain' { Invoke-ClfDrain -Cluster ([string]$config.Cluster.Name) -Role ([string]$config.Role.Name) -NodeName $nodes -WhatIf:$WhatIfPreference -Confirm:$false }
    'Remove' {
        $plan = @(Get-ClfRemovePlan -Config $config)
        $plan | Format-Table Order, Id, Cmdlet, LocalOnly, Why -Wrap | Out-String -Width 200 | Write-Output
        Invoke-ClfPlan -Plan $plan -NodeName $nodes -Credential $Credential -WhatIf:$WhatIfPreference -Confirm:$false
    }
}
