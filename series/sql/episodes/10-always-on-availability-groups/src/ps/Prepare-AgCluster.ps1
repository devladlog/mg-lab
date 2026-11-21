<#
.SYNOPSIS
    Episode 10 lab preparation: a two-node Windows Server Failover Cluster (CON-SQL01 + CON-SQL02) with a file
    share witness on CON-SRV01, and Always On enabled on both SQL Server instances.

.DESCRIPTION
    Run it as the lab Administrator (a domain account that may create computer objects, or with the cluster name
    object prestaged), ELEVATED, on CON-SQL01's console or a PowerShell session on it. New-Cluster cannot be run
    remotely without CredSSP, so the cluster is created locally. Needs the FailoverClusters module (installed with the
    feature in step 1) and the SqlServer module (for Enable-SqlAlwaysOn). Nothing is stored: it asks for no credentials and writes none.
    Use -WhatIf to see what it would do.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string[]] $Nodes = @('CON-SQL01', 'CON-SQL02'),
    [string] $ClusterName = 'CON-AGCL01',
    [string] $ClusterIp = '10.50.0.44',
    [string] $WitnessHost = 'CON-SRV01',
    [string] $WitnessShare = 'AgWitness',
    [string] $WitnessPath = 'C:\AgWitness',
    [string] $Domain = 'CONTOSO'
)

$ErrorActionPreference = 'Stop'

# 1. The Failover Clustering feature on every node.
if ($PSCmdlet.ShouldProcess(($Nodes -join ', '), 'Install-WindowsFeature Failover-Clustering')) {
    Invoke-Command -ComputerName $Nodes -ScriptBlock {
        Install-WindowsFeature -Name Failover-Clustering -IncludeManagementTools
    }
}

# 2. Validate the nodes (a full validation report; read it before going on).
if ($PSCmdlet.ShouldProcess(($Nodes -join ', '), 'Test-Cluster')) {
    Test-Cluster -Node $Nodes
}

# 3. Create the cluster: static address, no shared storage (an AG does not use any).
if ($PSCmdlet.ShouldProcess($ClusterName, 'New-Cluster')) {
    New-Cluster -Name $ClusterName -Node $Nodes -StaticAddress $ClusterIp -NoStorage
}

# 4. A file share witness on another server, dedicated to this cluster: the cluster name object gets Change on the
#    share and Modify on the folder (Learn: deploy a quorum witness).
$cno = "${Domain}\${ClusterName}$"
if ($PSCmdlet.ShouldProcess("\\$WitnessHost\$WitnessShare", 'create the witness share and set the quorum')) {
    Invoke-Command -ComputerName $WitnessHost -ArgumentList $WitnessPath, $WitnessShare, $cno -ScriptBlock {
        param($path, $share, $account)
        New-Item -ItemType Directory -Path $path -Force | Out-Null
        New-SmbShare -Name $share -Path $path -ChangeAccess $account | Out-Null
        & icacls.exe $path /grant "${account}:(OI)(CI)(M)" | Out-Null
    }
    Set-ClusterQuorum -Cluster $ClusterName -FileShareWitness "\\$WitnessHost\$WitnessShare"
}

# 5. Always On on every instance. This RESTARTS the SQL Server service (-Force skips the prompt).
foreach ($node in $Nodes) {
    if ($PSCmdlet.ShouldProcess($node, 'Enable-SqlAlwaysOn (restarts SQL Server)')) {
        Enable-SqlAlwaysOn -ServerInstance $node -Force
    }
}

# 6. The endpoint port must be reachable between the nodes.
if ($PSCmdlet.ShouldProcess(($Nodes -join ', '), 'open TCP 5022 for the mirroring endpoint')) {
    Invoke-Command -ComputerName $Nodes -ScriptBlock {
        New-NetFirewallRule -DisplayName 'MGLab AG endpoint 5022' -Direction Inbound -Protocol TCP -LocalPort 5022 -Action Allow | Out-Null
    }
}

Get-ClusterNode -Cluster $ClusterName | Format-Table Name, State
Get-ClusterQuorum -Cluster $ClusterName | Format-List *
