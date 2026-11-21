BeforeAll {
    $script:Src = Join-Path $PSScriptRoot '../src'
    $script:Fixtures = Join-Path $PSScriptRoot 'fixtures'
    Import-Module (Join-Path $script:Src 'ClusterLab/ClusterLab.psd1') -Force
    $script:ConfigPath = Join-Path $script:Src 'cluster-lab.json'
    $script:Config = Read-ClfLabConfig -Path $script:ConfigPath
    function Get-Facts([string] $Name) { Get-Content -Raw (Join-Path $script:Fixtures "$Name.json") | ConvertFrom-Json }
    function Get-ConfigCopy { Get-Content -Raw $script:ConfigPath | ConvertFrom-Json }
    function Test-Facts($Facts, $Config = $script:Config) { @(Test-ClfReadiness -Facts $Facts -Config $Config) }
    function Get-Checks($Findings) { @($Findings | ForEach-Object Check) }
    function Get-Ids($Plan) { @($Plan | ForEach-Object Id) }

    # FailoverClusters and ServerManager cmdlets exist only on Windows with the feature: stubs with the parameters the module passes
    $script:Stub = {
        [CmdletBinding(SupportsShouldProcess)]
        param($Name, $IncludeManagementTools, $ComputerName, $Node, $Ignore, $StaticAddress, $NoStorage, $Cluster, $FileShareWitness,
            $ServiceName, [switch] $Force, [switch] $CleanupAD, [switch] $Drain, $TargetNode, [switch] $Wait, $Failback)
    }
    foreach ($n in 'Install-WindowsFeature', 'Test-Cluster', 'New-Cluster', 'Set-ClusterQuorum', 'Add-ClusterGenericServiceRole', 'Remove-Cluster', 'Suspend-ClusterNode', 'Resume-ClusterNode') {
        Set-Item -Path "function:global:$n" -Value $script:Stub
    }
    Set-Item -Path 'function:global:Get-ClusterGroup' -Value { param($Name, $Cluster) }
}

AfterAll {
    foreach ($n in 'Install-WindowsFeature', 'Test-Cluster', 'New-Cluster', 'Set-ClusterQuorum', 'Add-ClusterGenericServiceRole', 'Remove-Cluster', 'Suspend-ClusterNode', 'Resume-ClusterNode', 'Get-ClusterGroup') {
        Remove-Item "function:global:$n" -ErrorAction SilentlyContinue
    }
}

Describe 'Read-ClfLabConfig' {
    It 'reads the lab config' {
        $script:Config.Cluster.Name | Should -Be 'CON-CL01'
        @($script:Config.Cluster.Nodes).Count | Should -Be 2
        $script:Config.Role.ServiceName | Should -Be 'W3SVC'
    }
    It 'rejects bad values' {
        $f = Join-Path $TestDrive 'c.json'
        $c = Get-ConfigCopy; $c.Cluster.Nodes = @('CON-NODE01'); $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-ClfLabConfig -Path $f } | Should -Throw '*at least two*'
        $c = Get-ConfigCopy; $c.Cluster.Nodes = @('CON-NODE01', 'con-node01'); $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-ClfLabConfig -Path $f } | Should -Throw '*duplicate*'
        $c = Get-ConfigCopy; $c.Cluster.StaticAddress = '10.50.0.300'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-ClfLabConfig -Path $f } | Should -Throw '*not an IPv4*'
        $c = Get-ConfigCopy; $c.Role.StaticAddress = $c.Cluster.StaticAddress; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-ClfLabConfig -Path $f } | Should -Throw '*must differ*'
        $c = Get-ConfigCopy; $c.Witness.Host = 'CON-NODE02'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-ClfLabConfig -Path $f } | Should -Throw '*must not live on a cluster node*'
        $c = Get-ConfigCopy; $c.Witness.Host = 'con-node02.lab.contoso.com'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-ClfLabConfig -Path $f } | Should -Throw '*must not live on a cluster node*'
        $c = Get-ConfigCopy; $c.Role.Name = 'CON-CL01'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-ClfLabConfig -Path $f } | Should -Throw '*Role.Name must differ*'
        $c = Get-ConfigCopy; $c.Cluster.Name = 'con-node01'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-ClfLabConfig -Path $f } | Should -Throw '*differ from every node*'
        $c = Get-ConfigCopy; $c.Witness.Type = 'Cloud'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-ClfLabConfig -Path $f } | Should -Throw '*FileShare or None*'
    }
}

Describe 'Test-ClfSameSubnet' {
    It 'compares networks by prefix length' {
      InModuleScope ClusterLab {
        Test-ClfSameSubnet -Address '10.50.0.60' -NodeAddress '10.50.0.51' -PrefixLength 24 | Should -BeTrue
        Test-ClfSameSubnet -Address '10.50.1.60' -NodeAddress '10.50.0.51' -PrefixLength 24 | Should -BeFalse
        Test-ClfSameSubnet -Address '10.50.1.60' -NodeAddress '10.50.0.51' -PrefixLength 16 | Should -BeTrue
        Test-ClfSameSubnet -Address '10.50.0.200' -NodeAddress '10.50.0.51' -PrefixLength 25 | Should -BeFalse
        Test-ClfSameSubnet -Address '10.50.0.100' -NodeAddress '10.50.0.51' -PrefixLength 25 | Should -BeTrue
        Test-ClfSameSubnet -Address '192.168.1.1' -NodeAddress '10.50.0.51' -PrefixLength 0 | Should -BeTrue
      }
    }
}

Describe 'Get-ClfQuorumMath' {
    It 'two nodes without a witness cannot lose a node' {
        $q = Get-ClfQuorumMath -Nodes 2 -Witness $false
        $q.Votes | Should -Be 2; $q.QuorumNeeded | Should -Be 2; $q.VoteLossesTolerated | Should -Be 0
        $q.SurvivesOneNodeLoss | Should -BeFalse
        $q.Model | Should -Be 'Node Majority'
    }
    It 'two nodes with a witness can lose one node' {
        $q = Get-ClfQuorumMath -Nodes 2 -Witness $true
        $q.Votes | Should -Be 3; $q.QuorumNeeded | Should -Be 2; $q.VoteLossesTolerated | Should -Be 1
        $q.SurvivesOneNodeLoss | Should -BeTrue
        $q.SurvivesWitnessLoss | Should -BeTrue
    }
    It 'odd node counts need no witness for one loss' {
        (Get-ClfQuorumMath -Nodes 3).SurvivesOneNodeLoss | Should -BeTrue
        (Get-ClfQuorumMath -Nodes 3).QuorumNeeded | Should -Be 2
        (Get-ClfQuorumMath -Nodes 5).VoteLossesTolerated | Should -Be 2
    }
    It 'four nodes tolerate one loss, not two' {
        $q = Get-ClfQuorumMath -Nodes 4
        $q.QuorumNeeded | Should -Be 3; $q.VoteLossesTolerated | Should -Be 1
    }
    It 'a single node without a witness cannot survive losing itself' {
        (Get-ClfQuorumMath -Nodes 1).SurvivesOneNodeLoss | Should -BeFalse
    }
    It 'rejects zero nodes' { { Get-ClfQuorumMath -Nodes 0 } | Should -Throw '*at least 1*' }
}

Describe 'Test-ClfReadiness: fresh nodes' {
    BeforeAll { $script:F = Test-Facts (Get-Facts 'facts-fresh') }
    It 'finds the missing feature on both nodes and the missing witness share, nothing High' {
        @($script:F | Where-Object Check -eq 'FeatureMissing').Count | Should -Be 2
        Get-Checks $script:F | Should -Contain 'WitnessShareMissing'
        @($script:F | Where-Object Severity -eq 'High').Count | Should -Be 0
    }
    It 'adds the quorum arithmetic as information' {
        ($script:F | Where-Object Check -eq 'QuorumMath').Message | Should -BeLike '*3 votes, quorum needs 2, survives losing one node: yes*'
    }
    It 'accepts clocks a few seconds apart' { Get-Checks $script:F | Should -Not -Contain 'ClockSkew' }
}

Describe 'Test-ClfReadiness: ready nodes' {
    It 'has only information left' {
        $r = Test-Facts (Get-Facts 'facts-ready')
        @($r | Where-Object Severity -ne 'Info').Count | Should -Be 0
    }
}

Describe 'Test-ClfReadiness: badly prepared nodes' {
    BeforeAll { $script:F = Test-Facts (Get-Facts 'facts-bad') }
    It 'flags what stops a cluster from forming as High' {
        $h = @($script:F | Where-Object Severity -eq 'High' | ForEach-Object Check)
        $h | Should -Contain 'NotDomainJoined'
        $h | Should -Contain 'NodesInDifferentDomains'
        $h | Should -Contain 'ClockSkew'
        $h | Should -Contain 'ClusterIpNotOnNodeNetwork'
        $h | Should -Contain 'RoleIpNotOnNodeNetwork'
        $h | Should -Contain 'NoDnsServer'
    }
    It 'reports the clock spread in seconds' { ($script:F | Where-Object Check -eq 'ClockSkew').Message | Should -BeLike '*722 s*' }
    It 'flags the softer problems' {
        $c = Get-Checks $script:F
        $c | Should -Contain 'NodeBuildMismatch'
        $c | Should -Contain 'PendingReboot'
        $c | Should -Contain 'NodeAlreadyClustered'
        $c | Should -Contain 'NodeAddressDhcp'
        $c | Should -Contain 'NodeEditionDiffers'
        $c | Should -Contain 'NodeInstallTypeDiffers'
    }
    It 'distinguishes a different build from a different update level' {
        $f = Get-Facts 'facts-ready'; $f.Nodes[1].Revision = 1700
        $c = Get-Checks (Test-Facts $f)
        $c | Should -Contain 'NodeUpdateLevelDiffers'
        $c | Should -Not -Contain 'NodeBuildMismatch'
    }
    It 'sorts High before Info' {
        $order = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
        $ranks = @($script:F | ForEach-Object { $order[$_.Severity] })
        $ranks | Should -Be @($ranks | Sort-Object)
    }
}

Describe 'Test-ClfReadiness: other shapes' {
    It 'reports an unreachable node and does not invent facts for it' {
        $r = Test-Facts (Get-Facts 'facts-unreachable')
        ($r | Where-Object Check -eq 'NodeUnreachable').Target | Should -Be 'CON-NODE02'
        Get-Checks $r | Should -Not -Contain 'NodeBuildMismatch'
    }
    It 'demands a witness for an even number of nodes when the policy says no witness is configured' {
        $cfg = Get-ConfigCopy; $cfg.Witness.Type = 'None'
        $r = Test-Facts (Get-Facts 'facts-ready') $cfg
        ($r | Where-Object Check -eq 'NoWitnessEvenNodes').Severity | Should -Be 'High'
        ($r | Where-Object Check -eq 'QuorumMath').Message | Should -BeLike '*survives losing one node: NO*'
    }
    It 'flags a single node' {
        $f = Get-Facts 'facts-ready'; $f.Nodes = @($f.Nodes[0])
        Get-Checks (Test-Facts $f) | Should -Contain 'TooFewNodes'
    }
    It 'treats DHCP as acceptable when the policy allows it' {
        $cfg = Get-ConfigCopy; $cfg.Policy.RequireStaticNodeAddresses = $false
        $f = Get-Facts 'facts-ready'; $f.Nodes[0].Adapters[0].Dhcp = $true
        Get-Checks (Test-Facts $f $cfg) | Should -Not -Contain 'NodeAddressDhcp'
    }
}

Describe 'Get-ClfBuildPlan' {
    It 'plans everything for fresh nodes, in an order that works' {
        $p = @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-fresh'))
        Get-Ids $p | Should -Be @('InstallFeature:CON-NODE01', 'InstallFeature:CON-NODE02', 'InstallIis:CON-NODE01', 'InstallIis:CON-NODE02', 'IndexPage:CON-NODE01', 'IndexPage:CON-NODE02',
            'TestCluster', 'NewCluster', 'WitnessShare', 'SetQuorum', 'AddRole')
        @($p | ForEach-Object Order) | Should -Be @(1..11)
    }
    It 'creates the witness share after the cluster (the cluster name object must exist) and sets the quorum after the share' {
        $ids = Get-Ids @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-fresh'))
        $ids.IndexOf('NewCluster') | Should -BeLessThan $ids.IndexOf('WitnessShare')
        $ids.IndexOf('WitnessShare') | Should -BeLessThan $ids.IndexOf('SetQuorum')
        $ids.IndexOf('TestCluster') | Should -BeLessThan $ids.IndexOf('NewCluster')
    }
    It 'marks the steps that cannot run remotely and the ones that create AD objects' {
        $p = @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-fresh'))
        @($p | Where-Object LocalOnly | ForEach-Object Id) | Should -Be @('NewCluster', 'AddRole')
        @($p | Where-Object CreatesAdObjects | ForEach-Object Id) | Should -Be @('NewCluster', 'AddRole')
    }
    It 'passes the configured values' {
        $p = @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-fresh'))
        $nc = $p | Where-Object Id -eq 'NewCluster'
        $nc.Parameters.Name | Should -Be 'CON-CL01'
        $nc.Parameters.StaticAddress | Should -Be '10.50.0.60'
        $nc.Parameters.NoStorage | Should -BeTrue
        @($nc.Parameters.Node) | Should -Be @('CON-NODE01', 'CON-NODE02')
        ($p | Where-Object Id -eq 'SetQuorum').Parameters.FileShareWitness | Should -Be '\\CON-SRV01\ClusterWitness'
        ($p | Where-Object Id -eq 'WitnessShare').Parameters.Account | Should -Be 'CONTOSO\CON-CL01$'
        $ar = $p | Where-Object Id -eq 'AddRole'
        $ar.Parameters.ServiceName | Should -Be 'W3SVC'; $ar.Parameters.StaticAddress | Should -Be '10.50.0.61'
        ($p | Where-Object Id -eq 'TestCluster').Parameters.Ignore | Should -Be 'Storage'
    }
    It 'drops done steps when the features are installed' {
        $p = @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-ready'))
        Get-Ids $p | Should -Be @('IndexPage:CON-NODE01', 'IndexPage:CON-NODE02', 'TestCluster', 'NewCluster', 'WitnessShare', 'SetQuorum', 'AddRole')
    }
    It 'does not create a second cluster when the nodes already run the cluster service' {
        $p = @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-clustered'))
        Get-Ids $p | Should -Not -Contain 'NewCluster'
        Get-Ids $p | Should -Not -Contain 'TestCluster'
        Get-Ids $p | Should -Contain 'AddRole'
    }
    It 'has no witness steps when no witness is configured' {
        $cfg = Get-ConfigCopy; $cfg.Witness.Type = 'None'
        $ids = Get-Ids @(Get-ClfBuildPlan -Config $cfg -Facts (Get-Facts 'facts-ready'))
        $ids | Should -Not -Contain 'WitnessShare'
        $ids | Should -Not -Contain 'SetQuorum'
    }
    It 'plans from no facts at all' {
        @(Get-ClfBuildPlan -Config $script:Config -Facts $null).Count | Should -Be 11
    }
    It 'plans the tear-down: cluster and AD objects first, then the share' {
        $p = @(Get-ClfRemovePlan -Config $script:Config)
        Get-Ids $p | Should -Be @('RemoveCluster', 'RemoveWitnessShare')
        $p[0].Parameters.CleanupAD | Should -BeTrue
        $p[0].LocalOnly | Should -BeTrue
    }
}

Describe 'Invoke-ClfPlan' {
    BeforeEach {
        foreach ($n in 'Install-WindowsFeature', 'Test-Cluster', 'New-Cluster', 'Set-ClusterQuorum', 'Add-ClusterGenericServiceRole', 'Remove-Cluster') {
            Mock -CommandName $n -MockWith { } -ModuleName ClusterLab
        }
        Mock -CommandName Invoke-Command -MockWith { } -ModuleName ClusterLab
        $script:Nodes = @('CON-NODE01', 'CON-NODE02')
    }
    It 'refuses to start on a machine that is not a node, before changing anything' {
        $p = @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-fresh'))
        { Invoke-ClfPlan -Plan $p -NodeName $script:Nodes -LocalComputerName 'CON-SRV02' -Confirm:$false } | Should -Throw '*Run it ON a cluster node*'
        Should -Invoke Install-WindowsFeature -ModuleName ClusterLab -Times 0 -Exactly
        Should -Invoke Invoke-Command -ModuleName ClusterLab -Times 0 -Exactly
    }
    It 'applies every step on a node' {
        $p = @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-fresh'))
        $r = @(Invoke-ClfPlan -Plan $p -NodeName $script:Nodes -LocalComputerName 'con-node01' -Confirm:$false)
        $r.Count | Should -Be 11
        Should -Invoke Install-WindowsFeature -ModuleName ClusterLab -Times 4 -Exactly
        Should -Invoke Test-Cluster -ModuleName ClusterLab -Times 1 -Exactly -ParameterFilter { $Ignore -eq 'Storage' -and @($Node).Count -eq 2 }
        Should -Invoke New-Cluster -ModuleName ClusterLab -Times 1 -Exactly -ParameterFilter { $Name -eq 'CON-CL01' -and $StaticAddress -eq '10.50.0.60' -and $NoStorage }
        Should -Invoke Set-ClusterQuorum -ModuleName ClusterLab -Times 1 -Exactly -ParameterFilter { $FileShareWitness -eq '\\CON-SRV01\ClusterWitness' -and $Cluster -eq 'CON-CL01' }
        Should -Invoke Add-ClusterGenericServiceRole -ModuleName ClusterLab -Times 1 -Exactly -ParameterFilter { $ServiceName -eq 'W3SVC' -and $Name -eq 'CON-WEB' -and $StaticAddress -eq '10.50.0.61' }
        Should -Invoke Invoke-Command -ModuleName ClusterLab -Times 3 -Exactly   # two index pages and the witness share
        Should -Invoke Invoke-Command -ModuleName ClusterLab -Times 1 -Exactly -ParameterFilter { $ComputerName -eq 'CON-SRV01' }
    }
    It 'changes nothing with -WhatIf, even on a node' {
        $p = @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-fresh'))
        Invoke-ClfPlan -Plan $p -NodeName $script:Nodes -LocalComputerName 'CON-NODE01' -WhatIf | Out-Null
        foreach ($n in 'Install-WindowsFeature', 'Test-Cluster', 'New-Cluster', 'Set-ClusterQuorum', 'Add-ClusterGenericServiceRole') { Should -Invoke $n -ModuleName ClusterLab -Times 0 -Exactly }
        Should -Invoke Invoke-Command -ModuleName ClusterLab -Times 0 -Exactly
    }
    It 'reports a restart that Install-WindowsFeature asks for' {
        Mock -CommandName Install-WindowsFeature -MockWith { [pscustomobject]@{ RestartNeeded = 'Yes'; Success = $true } } -ModuleName ClusterLab
        $p = @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-fresh') | Where-Object { $_.Id -eq 'InstallFeature:CON-NODE01' })
        $r = @(Invoke-ClfPlan -Plan $p -NodeName $script:Nodes -LocalComputerName 'CON-NODE01' -Confirm:$false)
        $r[0].RestartNeeded | Should -Be 'Yes'
    }
    It 'refuses a plan that names a cmdlet outside the allow-list' {
        $evil = [pscustomobject]@{ Order = 1; Id = 'X'; Kind = 'Cmdlet'; Cmdlet = 'Remove-Item'; Parameters = @{ Path = 'C:\' }; LocalOnly = $false; Why = 'x' }
        { Invoke-ClfPlan -Plan @($evil) -NodeName $script:Nodes -LocalComputerName 'CON-NODE01' -Confirm:$false } | Should -Throw '*not an allowed cmdlet*'
    }
    It 'runs the remove plan on a node' {
        $p = @(Get-ClfRemovePlan -Config $script:Config)
        Invoke-ClfPlan -Plan $p -NodeName $script:Nodes -LocalComputerName 'CON-NODE02' -Confirm:$false | Out-Null
        Should -Invoke Remove-Cluster -ModuleName ClusterLab -Times 1 -Exactly -ParameterFilter { $Cluster -eq 'CON-CL01' -and $CleanupAD -and $Force }
        Should -Invoke Invoke-Command -ModuleName ClusterLab -Times 1 -Exactly -ParameterFilter { $ComputerName -eq 'CON-SRV01' }
    }
    It 'plans that only need remote-safe cmdlets can run from any machine' {
        $p = @(Get-ClfBuildPlan -Config $script:Config -Facts (Get-Facts 'facts-fresh') | Where-Object { -not $_.LocalOnly -and $_.Id -like 'Install*' })
        Invoke-ClfPlan -Plan $p -NodeName $script:Nodes -LocalComputerName 'CON-SRV02' -Confirm:$false | Out-Null
        Should -Invoke Install-WindowsFeature -ModuleName ClusterLab -Times 4 -Exactly
    }
}

Describe 'Invoke-ClfDrain' {
    BeforeEach {
        $script:Calls = 0
        Mock -CommandName Get-ClusterGroup -ModuleName ClusterLab -MockWith {
            $script:Calls++
            if ($script:Calls -eq 1) { [pscustomobject]@{ Name = 'CON-WEB'; State = 'Online'; OwnerNode = [pscustomobject]@{ Name = 'CON-NODE01' } } }
            else { [pscustomobject]@{ Name = 'CON-WEB'; State = 'Online'; OwnerNode = [pscustomobject]@{ Name = 'CON-NODE02' } } }
        }
        Mock -CommandName Suspend-ClusterNode -MockWith { } -ModuleName ClusterLab
        Mock -CommandName Resume-ClusterNode -MockWith { } -ModuleName ClusterLab
    }
    It 'drains the owner towards the other node and resumes it without failback' {
        $r = Invoke-ClfDrain -Cluster 'CON-CL01' -Role 'CON-WEB' -NodeName @('CON-NODE01', 'CON-NODE02') -Confirm:$false
        $r.From | Should -Be 'CON-NODE01'; $r.To | Should -Be 'CON-NODE02'; $r.State | Should -Be 'Online'
        Should -Invoke Suspend-ClusterNode -ModuleName ClusterLab -Times 1 -Exactly -ParameterFilter { $Name -eq 'CON-NODE01' -and $Drain -and $TargetNode -eq 'CON-NODE02' -and $Wait -and $Cluster -eq 'CON-CL01' }
        Should -Invoke Resume-ClusterNode -ModuleName ClusterLab -Times 1 -Exactly -ParameterFilter { $Name -eq 'CON-NODE01' -and $Failback -eq 'NoFailback' }
    }
    It 'does nothing with -WhatIf' {
        Invoke-ClfDrain -Cluster 'CON-CL01' -Role 'CON-WEB' -NodeName @('CON-NODE01', 'CON-NODE02') -WhatIf | Out-Null
        Should -Invoke Suspend-ClusterNode -ModuleName ClusterLab -Times 0 -Exactly
        Should -Invoke Resume-ClusterNode -ModuleName ClusterLab -Times 0 -Exactly
    }
    It 'fails clearly when the role does not exist' {
        Mock -CommandName Get-ClusterGroup -ModuleName ClusterLab -MockWith { $null }
        { Invoke-ClfDrain -Cluster 'CON-CL01' -Role 'NOPE' -NodeName @('CON-NODE01', 'CON-NODE02') -Confirm:$false } | Should -Throw "*'NOPE' not found*"
    }
}

Describe 'Get-ClfProbeSummary' {
    It 'finds the outage in the saved drain run' {
        $s = @(Get-Content (Join-Path $script:Fixtures 'probe-drain.jsonl') | ForEach-Object { $_ | ConvertFrom-Json })
        $r = Get-ClfProbeSummary -Samples $s
        $r.Samples | Should -Be 26; $r.Failed | Should -Be 2; $r.ServerChanges | Should -Be 1
        $r.OutageCount | Should -Be 1; $r.LongestOutageSeconds | Should -Be 4; $r.TotalDowntimeSeconds | Should -Be 4
        $r.Outages[0].FailedRequests | Should -Be 2
        $r.ServedBy['CON-NODE01'] | Should -Be 12; $r.ServedBy['CON-NODE02'] | Should -Be 12
    }
    It 'reports no outage for a clean run' {
        $s = 0..5 | ForEach-Object { [pscustomobject]@{ T = ([datetime]'2026-11-25T10:00:00Z').AddSeconds($_).ToString('o'); Ok = $true; Server = 'CON-NODE01'; Ms = 5 } }
        $r = Get-ClfProbeSummary -Samples $s
        $r.OutageCount | Should -Be 0; $r.TotalDowntimeSeconds | Should -Be 0; $r.ServerChanges | Should -Be 0
    }
    It 'counts an outage that never ended' {
        $t0 = [datetime]'2026-11-25T10:00:00Z'
        $s = @([pscustomobject]@{ T = $t0.ToString('o'); Ok = $true; Server = 'A'; Ms = 5 }) + (1..3 | ForEach-Object { [pscustomobject]@{ T = $t0.AddSeconds($_ * 2).ToString('o'); Ok = $false; Server = $null; Ms = 2000 } })
        $r = Get-ClfProbeSummary -Samples $s
        $r.OutageCount | Should -Be 1; $r.Outages[0].Seconds | Should -Be 4; $r.Outages[0].FailedRequests | Should -Be 3
    }
    It 'sorts samples by time and counts two outages separately' {
        $t0 = [datetime]'2026-11-25T10:00:00Z'
        $rows = @(
            @(0, $true), @(2, $false), @(4, $true), @(6, $true), @(8, $false), @(10, $true)
        ) | ForEach-Object { [pscustomobject]@{ T = $t0.AddSeconds($_[0]).ToString('o'); Ok = $_[1]; Server = 'A'; Ms = 5 } }
        $r = Get-ClfProbeSummary -Samples @($rows[5], $rows[0], $rows[3], $rows[1], $rows[4], $rows[2])
        $r.OutageCount | Should -Be 2; $r.TotalDowntimeSeconds | Should -Be 4
    }
}

Describe 'Invoke-ClfProbe (against a throwaway local HTTP listener, tests only)' {
    BeforeAll {
        $tcp = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0); $tcp.Start()
        $script:Port = $tcp.LocalEndpoint.Port; $tcp.Stop()
        $script:Listener = [System.Net.HttpListener]::new()
        $script:Listener.Prefixes.Add("http://127.0.0.1:$($script:Port)/")
        $script:Listener.Start()
        $script:Ps = [powershell]::Create()
        [void]$script:Ps.AddScript({ param($l) while ($l.IsListening) { try { $c = $l.GetContext() } catch { break }; $b = [Text.Encoding]::ASCII.GetBytes('Served by NODE-A'); $c.Response.ContentType = 'text/plain'; $c.Response.OutputStream.Write($b, 0, $b.Length); $c.Response.Close() } }).AddArgument($script:Listener)
        $script:Handle = $script:Ps.BeginInvoke()
    }
    AfterAll {
        $script:Listener.Stop(); $script:Listener.Close()
        $script:Ps.Dispose()
    }
    It 'records who answered and writes JSON lines' {
        $out = Join-Path $TestDrive 'probe.jsonl'
        $s = @(Invoke-ClfProbe -Url "http://127.0.0.1:$($script:Port)/" -DurationSec 1 -IntervalMs 200 -OutFile $out)
        $s.Count | Should -BeGreaterThan 2
        @($s | Where-Object { -not $_.Ok }).Count | Should -Be 0
        @($s | ForEach-Object Server | Select-Object -Unique) | Should -Be @('NODE-A')
        @(Get-Content $out).Count | Should -Be $s.Count
        (Get-Content $out)[0] | ConvertFrom-Json | ForEach-Object { $_.Ok } | Should -BeTrue
    }
    It 'records failures when nothing answers' {
        $tcp = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0); $tcp.Start(); $dead = $tcp.LocalEndpoint.Port; $tcp.Stop()
        $s = @(Invoke-ClfProbe -Url "http://127.0.0.1:$dead/" -DurationSec 1 -IntervalMs 200 -TimeoutSec 1)
        $s.Count | Should -BeGreaterThan 0
        @($s | Where-Object Ok).Count | Should -Be 0
        (Get-ClfProbeSummary -Samples $s).OutageCount | Should -Be 1
    }
}

Describe 'ConvertTo-ClfMarkdown' {
    It 'writes nodes and findings' {
        $f = Get-Facts 'facts-bad'
        $md = ConvertTo-ClfMarkdown -Facts $f -Findings (Test-Facts $f)
        $md | Should -BeLike '*| CON-NODE01 | 26100.1700 |*'
        $md | Should -BeLike '*192.168.5.20/24 (DHCP)*'
        $md | Should -BeLike '*| High | CON-CL01 | ClockSkew |*'
    }
    It 'shows an unreachable node and says None without findings' {
        $md = ConvertTo-ClfMarkdown -Facts (Get-Facts 'facts-unreachable') -Findings @()
        $md | Should -BeLike '*| CON-NODE02 | unreachable |*'
        $md | Should -BeLike '*None.*'
    }
}

Describe 'Scripts and collector' {
    It 'parses every script without errors' {
        foreach ($f in Get-ChildItem (Join-Path $script:Src '*.ps1'), (Join-Path $script:Src 'ClusterLab/*.ps*1')) {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$null, [ref]$errors) | Out-Null
            @($errors).Count | Should -Be 0 -Because $f.Name
        }
    }
    It 'the collector is read-only: it only gets and tests' {
        $ast = (Get-ClfCollectorScript).Ast
        $cmds = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
        @($cmds | Where-Object { $_ -match '^(Set|Remove|Install|Add|Start|Stop|Restart|Enable|Disable|Clear|Invoke|New|Move|Suspend|Resume)-' -and $_ -ne 'New-Object' }).Count | Should -Be 0
        ($cmds | Where-Object { $_ -like 'Get-*' }).Count | Should -BeGreaterThan 5
    }
    It 'the collector takes the witness path Get-ClfFacts passes' {
        (Get-ClfCollectorScript).Ast.ParamBlock.Parameters.Name.VariablePath.UserPath | Should -Be @('WitnessPath')
    }
}
