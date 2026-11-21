<#
.SYNOPSIS
    Episode 10 tear-down of the cluster side: Always On off on both instances, the cluster destroyed (and its Active
    Directory objects), the witness share removed. Run it ELEVATED on CON-SQL01 AFTER `ag_lab.py --reset-only`
    (the availability group and database are gone). The Failover Clustering feature stays installed.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string[]] $Nodes = @('CON-SQL01', 'CON-SQL02'),
    [string] $ClusterName = 'CON-AGCL01',
    [string] $WitnessHost = 'CON-SRV01',
    [string] $WitnessShare = 'AgWitness',
    [string] $WitnessPath = 'C:\AgWitness'
)

$ErrorActionPreference = 'Stop'

foreach ($node in $Nodes) {
    if ($PSCmdlet.ShouldProcess($node, 'Disable-SqlAlwaysOn (restarts SQL Server)')) {
        Disable-SqlAlwaysOn -ServerInstance $node -Force
    }
}

if ($PSCmdlet.ShouldProcess($ClusterName, 'Remove-Cluster')) {
    Get-Cluster -Name $ClusterName | Remove-Cluster -Force -CleanupAD
}

if ($PSCmdlet.ShouldProcess("\\$WitnessHost\$WitnessShare", 'remove the witness share and folder')) {
    Invoke-Command -ComputerName $WitnessHost -ArgumentList $WitnessPath, $WitnessShare -ScriptBlock {
        param($path, $share)
        Remove-SmbShare -Name $share -Force
        Remove-Item -Path $path -Recurse -Force
    }
}

if ($PSCmdlet.ShouldProcess(($Nodes -join ', '), 'remove the firewall rule')) {
    Invoke-Command -ComputerName $Nodes -ScriptBlock {
        Remove-NetFirewallRule -DisplayName 'MGLab AG endpoint 5022'
    }
}
