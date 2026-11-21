Set-StrictMode -Version Latest

# ---------------------------------------------------------------------------------------------------------------
# ClusterLab: a read-only readiness check for the nodes of a failover cluster, quorum arithmetic, a build PLAN you can
# read first (and a remove plan), a failover (drain) drill, and a probe that measures how long clients really lose a
# clustered role. Windows PowerShell 5.1 and PowerShell 7.
# Facts from Microsoft Learn are constants here; OUR policy lives in cluster-lab.json.
# ---------------------------------------------------------------------------------------------------------------

$script:Severity = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
$script:AllowedCmdlets = @('Install-WindowsFeature', 'Test-Cluster', 'New-Cluster', 'Set-ClusterQuorum', 'Add-ClusterGenericServiceRole', 'Remove-Cluster')
$script:LocalOnlyCmdlets = @('New-Cluster', 'Add-ClusterGenericServiceRole', 'Remove-Cluster')   # Learn: "cannot be run remotely without CredSSP"

function New-ClfFinding {
    param([string] $Target, [string] $Severity, [string] $Check, [string] $Message, [string] $Fix = '')
    [pscustomobject]@{ Severity = $Severity; Target = $Target; Check = $Check; Message = $Message; Fix = $Fix }
}

function Get-ClfProp {
    param($Object, [string] $Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] }; return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    $Default
}

function ConvertTo-ClfIpBytes {
    param([string] $Address)
    $ip = $null
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$ip) -or $ip.AddressFamily -ne 'InterNetwork') { throw "'$Address' is not an IPv4 address." }
    , $ip.GetAddressBytes()
}

function Test-ClfSameSubnet {
    <# Pure. Is $Address inside the network of $NodeAddress/$PrefixLength? #>
    param([string] $Address, [string] $NodeAddress, [int] $PrefixLength)
    $a = ConvertTo-ClfIpBytes $Address
    $b = ConvertTo-ClfIpBytes $NodeAddress
    for ($i = 0; $i -lt 4; $i++) {
        $bits = [math]::Max(0, [math]::Min(8, $PrefixLength - 8 * $i))
        $mask = if ($bits -eq 0) { 0 } else { (0xFF -shl (8 - $bits)) -band 0xFF }
        if (($a[$i] -band $mask) -ne ($b[$i] -band $mask)) { return $false }
    }
    $true
}

function Read-ClfLabConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    $c = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if ((Get-ClfProp $c 'SchemaVersion') -ne 1) { throw "Unsupported SchemaVersion in '$Path' (expected 1)." }
    foreach ($k in 'Cluster', 'Witness', 'Role', 'Policy') { if (-not (Get-ClfProp $c $k)) { throw "'$Path' is missing '$k'." } }
    $nodes = @($c.Cluster.Nodes | ForEach-Object { ([string]$_).ToUpperInvariant() })
    if ($nodes.Count -lt 2) { throw 'Cluster.Nodes needs at least two nodes.' }
    if (@($nodes | Select-Object -Unique).Count -ne $nodes.Count) { throw 'Cluster.Nodes has a duplicate name.' }
    if (-not [string](Get-ClfProp $c.Cluster 'Name' '')) { throw 'Cluster.Name is required.' }
    if ($nodes -contains ([string]$c.Cluster.Name).ToUpperInvariant()) { throw 'Cluster.Name must differ from every node name.' }
    [void](ConvertTo-ClfIpBytes ([string]$c.Cluster.StaticAddress))
    [void](ConvertTo-ClfIpBytes ([string]$c.Role.StaticAddress))
    if ([string]$c.Cluster.StaticAddress -eq [string]$c.Role.StaticAddress) { throw 'Cluster.StaticAddress and Role.StaticAddress must differ.' }
    foreach ($k in 'Name', 'ServiceName') { if (-not [string](Get-ClfProp $c.Role $k '')) { throw "Role.$k is required." } }
    if ([string]$c.Role.Name -eq [string]$c.Cluster.Name) { throw 'Role.Name must differ from Cluster.Name.' }
    $wt = [string](Get-ClfProp $c.Witness 'Type' 'FileShare')
    if ($wt -notin 'FileShare', 'None') { throw "Witness.Type must be FileShare or None (disk and cloud witness need shared disks or an Azure account)." }
    if ($wt -eq 'FileShare') {
        foreach ($k in 'Host', 'ShareName', 'FolderPath') { if (-not [string](Get-ClfProp $c.Witness $k '')) { throw "Witness.$k is required for a file share witness." } }
        $wh = ([string]$c.Witness.Host).Split('.')[0].ToUpperInvariant()
        if ($nodes -contains $wh) { throw 'The witness share must not live on a cluster node (Learn: keep it physically separate from the nodes).' }
    }
    if ([int](Get-ClfProp $c.Policy 'MaxClockSkewSeconds' 300) -lt 1) { throw 'Policy.MaxClockSkewSeconds must be positive.' }
    $c
}

function Get-ClfWitnessPath {
    param($Config)
    if ([string](Get-ClfProp $Config.Witness 'Type' 'FileShare') -ne 'FileShare') { return $null }
    '\\{0}\{1}' -f $Config.Witness.Host, $Config.Witness.ShareName
}

# ---------------------------------------------------------------------------------------------------------------
# Collector (runs ON each node; read-only; self-contained)
# ---------------------------------------------------------------------------------------------------------------

$script:NodeCollector = {
    param($WitnessPath)
    $ErrorActionPreference = 'Stop'
    $errors = New-Object System.Collections.ArrayList
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem
    $cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    $feat = [ordered]@{ 'Failover-Clustering' = $false; 'RSAT-Clustering-PowerShell' = $false; 'Web-Server' = $false }
    try { foreach ($n in @($feat.Keys)) { $f = Get-WindowsFeature -Name $n; $feat[$n] = [bool]($f -and $f.Installed) } }
    catch { [void]$errors.Add("Get-WindowsFeature: $($_.Exception.Message)") }
    $pending = (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') -or
    (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') -or
    [bool](Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name PendingFileRenameOperations -ErrorAction SilentlyContinue)
    $nics = @()
    try {
        $dhcp = @{}
        foreach ($i in @(Get-NetIPInterface -AddressFamily IPv4)) { $dhcp[[int]$i.InterfaceIndex] = [string]$i.Dhcp }
        $nics = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } | ForEach-Object {
                [pscustomobject]@{ Alias = [string]$_.InterfaceAlias; IPv4 = [string]$_.IPAddress; PrefixLength = [int]$_.PrefixLength; Dhcp = ($dhcp[[int]$_.InterfaceIndex] -eq 'Enabled') } })
    }
    catch { [void]$errors.Add("Network: $($_.Exception.Message)") }
    $dns = @()
    try { $dns = @(Get-DnsClientServerAddress -AddressFamily IPv4 | ForEach-Object { $_.ServerAddresses } | Where-Object { $_ } | Select-Object -Unique) }
    catch { [void]$errors.Add("DnsClient: $($_.Exception.Message)") }
    $svc = Get-Service -Name ClusSvc -ErrorAction SilentlyContinue
    $wit = $null
    if ($WitnessPath) { try { $wit = [bool](Test-Path -LiteralPath $WitnessPath) } catch { $wit = $false } }
    [pscustomobject]@{
        ComputerName = [string]$env:COMPUTERNAME; Caption = [string]$os.Caption; Build = [int]$os.BuildNumber
        Revision = [int]$cv.UBR; Edition = [string]$cv.EditionID; InstallationType = [string]$cv.InstallationType
        PartOfDomain = [bool]$cs.PartOfDomain; Domain = [string]$cs.Domain
        Features = [pscustomobject]$feat; PendingReboot = [bool]$pending; Adapters = $nics; DnsServers = $dns
        ClusterService = $(if ($svc) { [string]$svc.Status } else { $null })
        TimeUtc = [datetime]::UtcNow.ToString('o'); WitnessShareVisible = $wit; Errors = @($errors)
    }
}

function Get-ClfCollectorScript { $script:NodeCollector }

function Get-ClfFacts {
    <# Runs the collector on each node through Invoke-Command (WinRM). Read-only. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config, [pscredential] $Credential)
    $wp = Get-ClfWitnessPath $Config
    $nodes = New-Object System.Collections.ArrayList
    foreach ($n in @($Config.Cluster.Nodes)) {
        $p = @{ ComputerName = [string]$n; ScriptBlock = $script:NodeCollector; ArgumentList = @($wp); ErrorAction = 'Stop' }
        if ($Credential) { $p.Credential = $Credential }
        try { [void]$nodes.Add((Invoke-Command @p | Select-Object -Property * -ExcludeProperty PSComputerName, RunspaceId, PSShowComputerName)) }
        catch { [void]$nodes.Add([pscustomobject]@{ ComputerName = [string]$n; Errors = @("Unreachable: $($_.Exception.Message)") }) }
    }
    [pscustomobject]@{ CapturedAt = (Get-Date).ToUniversalTime().ToString('o'); Witness = $wp; Nodes = @($nodes) }
}

# ---------------------------------------------------------------------------------------------------------------
# Quorum arithmetic (pure)
# ---------------------------------------------------------------------------------------------------------------

function Get-ClfQuorumMath {
    <#
    .SYNOPSIS
    Pure. Static vote arithmetic: every node has one vote, a witness adds one; quorum is a majority of the votes.
    Windows Server also adjusts votes on its own (Dynamic Quorum, Learn), so a real cluster can survive more than this
    shows; the numbers are the floor you can explain on a whiteboard.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [int] $Nodes, [bool] $Witness = $false)
    if ($Nodes -lt 1) { throw 'Nodes must be at least 1.' }
    $votes = $Nodes + [int]$Witness
    $need = [int][math]::Floor($votes / 2) + 1
    [pscustomobject]@{
        Nodes = $Nodes; Witness = $Witness; Votes = $votes; QuorumNeeded = $need; VoteLossesTolerated = ($votes - $need)
        SurvivesOneNodeLoss = (($votes - 1) -ge $need)
        SurvivesWitnessLoss = ($Witness -and (($votes - 1) -ge $need))
        Model = $(if ($Witness) { 'Node and File Share Majority (or another witness)' } else { 'Node Majority' })
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Rules (pure)
# ---------------------------------------------------------------------------------------------------------------

function Test-ClfReadiness {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [Parameter(Mandatory)] $Config)
    $out = New-Object System.Collections.ArrayList
    $pol = $Config.Policy
    $nodes = @(Get-ClfProp $Facts 'Nodes' @())
    $cname = [string]$Config.Cluster.Name
    function Add-F { param($Target, $Sev, $Check, $Msg, $Fix = '') [void]$out.Add((New-ClfFinding $Target $Sev $Check $Msg $Fix)) }

    if ($nodes.Count -lt 2) { Add-F $cname High 'TooFewNodes' 'A failover cluster needs at least two nodes: there is nothing to fail over to.' }
    $reached = @($nodes | Where-Object { Get-ClfProp $_ 'Build' })
    foreach ($n in $nodes) {
        $nn = [string](Get-ClfProp $n 'ComputerName' '?')
        foreach ($e in @(Get-ClfProp $n 'Errors' @())) {
            if ([string]$e -like 'Unreachable*') { Add-F $nn High 'NodeUnreachable' ([string]$e) } else { Add-F $nn Info 'CollectorError' ([string]$e) }
        }
    }
    foreach ($n in $reached) {
        $nn = [string]$n.ComputerName
        if (-not (Get-ClfProp $n 'PartOfDomain' $false)) { Add-F $nn High 'NotDomainJoined' 'The node is not domain-joined. Learn: all nodes must be in the same Active Directory domain.' }
        $f = Get-ClfProp $n 'Features'
        if (-not (Get-ClfProp $f 'Failover-Clustering' $false)) { Add-F $nn Medium 'FeatureMissing' 'The Failover Clustering feature is not installed (Learn: install it on every node).' 'InstallFeature' }
        if ($true -eq (Get-ClfProp $n 'PendingReboot' $false)) { Add-F $nn Medium 'PendingReboot' 'A restart is pending. Restart before creating the cluster.' }
        if ((Get-ClfProp $n 'ClusterService') -eq 'Running') { Add-F $nn Medium 'NodeAlreadyClustered' 'The Cluster service is already running on this node: it may already belong to a cluster.' }
        $adapters = @(Get-ClfProp $n 'Adapters' @())
        if (-not $adapters.Count) { Add-F $nn High 'NoIPv4Address' 'No IPv4 address found.' }
        if ([bool](Get-ClfProp $pol 'RequireStaticNodeAddresses' $true)) {
            foreach ($a in @($adapters | Where-Object { $true -eq (Get-ClfProp $_ 'Dhcp' $false) })) {
                Add-F $nn Low 'NodeAddressDhcp' "Adapter '$($a.Alias)' ($($a.IPv4)) uses DHCP. Our policy: static addresses on cluster nodes."
            }
        }
        if ($adapters.Count) {
            $inSubnet = @($adapters | Where-Object { Test-ClfSameSubnet -Address ([string]$Config.Cluster.StaticAddress) -NodeAddress ([string]$_.IPv4) -PrefixLength ([int]$_.PrefixLength) })
            if (-not $inSubnet.Count) { Add-F $nn High 'ClusterIpNotOnNodeNetwork' "The cluster address $($Config.Cluster.StaticAddress) is not in any network this node has: New-Cluster takes a static address per network it uses (Learn)." }
            $inSubnet = @($adapters | Where-Object { Test-ClfSameSubnet -Address ([string]$Config.Role.StaticAddress) -NodeAddress ([string]$_.IPv4) -PrefixLength ([int]$_.PrefixLength) })
            if (-not $inSubnet.Count) { Add-F $nn High 'RoleIpNotOnNodeNetwork' "The role address $($Config.Role.StaticAddress) is not in any network this node has." }
            if ($adapters.Count -eq 1) { Add-F $nn Info 'SingleNetwork' 'One network: cluster heartbeat and client traffic share it. Fine for a lab; Learn describes separate private networks for heartbeats in production.' }
        }
        if (-not @(Get-ClfProp $n 'DnsServers' @()).Count) { Add-F $nn High 'NoDnsServer' 'No DNS server configured. Learn: the servers in a cluster must use DNS for name resolution.' }
    }
    if ($reached.Count -ge 2) {
        $builds = @($reached | ForEach-Object { '{0}.{1}' -f $_.Build, (Get-ClfProp $_ 'Revision' 0) } | Select-Object -Unique)
        if (@($reached | ForEach-Object { $_.Build } | Select-Object -Unique).Count -gt 1) {
            Add-F $cname Medium 'NodeBuildMismatch' "Nodes run different Windows builds ($($builds -join ', ')). Expect this only during a rolling upgrade."
        }
        elseif ($builds.Count -gt 1) { Add-F $cname Low 'NodeUpdateLevelDiffers' "Nodes are on different update levels ($($builds -join ', ')): patch them to the same level." }
        if (@($reached | ForEach-Object { Get-ClfProp $_ 'Edition' '' } | Select-Object -Unique).Count -gt 1) { Add-F $cname Low 'NodeEditionDiffers' 'Nodes run different editions.' }
        if (@($reached | ForEach-Object { Get-ClfProp $_ 'InstallationType' '' } | Select-Object -Unique).Count -gt 1) { Add-F $cname Info 'NodeInstallTypeDiffers' 'Nodes mix Server Core and Desktop Experience.' }
        if (@($reached | ForEach-Object { Get-ClfProp $_ 'Domain' '' } | Select-Object -Unique).Count -gt 1) { Add-F $cname High 'NodesInDifferentDomains' 'The nodes are in different domains (Learn: all nodes must be in the same Active Directory domain).' }
        $times = @($reached | Where-Object { Get-ClfProp $_ 'TimeUtc' } | ForEach-Object { ([datetime]$_.TimeUtc).ToUniversalTime() })
        if ($times.Count -ge 2) {
            $spread = (($times | Measure-Object -Maximum).Maximum - ($times | Measure-Object -Minimum).Minimum).TotalSeconds
            if ($spread -gt [int](Get-ClfProp $pol 'MaxClockSkewSeconds' 300)) { Add-F $cname High 'ClockSkew' ("Node clocks differ by {0:N0} s; Kerberos tolerates 5 minutes by default (Learn). Fix time sync first." -f $spread) }
        }
    }
    $wp = Get-ClfProp $Facts 'Witness'
    $witnessWanted = ([string](Get-ClfProp $Config.Witness 'Type' 'FileShare') -eq 'FileShare')
    if ($nodes.Count) {
        if (-not $witnessWanted -and ($nodes.Count % 2 -eq 0) -and [bool](Get-ClfProp $pol 'RequireWitness' $true)) {
            Add-F $cname High 'NoWitnessEvenNodes' "$($nodes.Count) nodes and no witness: one failed node leaves half the votes, so the cluster stops. Learn: always configure a witness (Windows Server 2012 R2 and later)."
        }
        if ($witnessWanted) {
            $seen = @($reached | Where-Object { $null -ne (Get-ClfProp $_ 'WitnessShareVisible') })
            if ($seen.Count -and @($seen | Where-Object { $_.WitnessShareVisible -eq $true }).Count -eq 0) {
                Add-F $cname Medium 'WitnessShareMissing' "No node can see $wp yet (seen with the admin's rights; the cluster name object still needs its own access after New-Cluster)." 'WitnessShare'
            }
        }
        $q = Get-ClfQuorumMath -Nodes $nodes.Count -Witness $witnessWanted
        Add-F $cname Info 'QuorumMath' ("{0} node(s){1}: {2} votes, quorum needs {3}, survives losing one node: {4}. (Static count; Dynamic Quorum can do better.)" -f $q.Nodes, $(if ($witnessWanted) { ' plus a file share witness' } else { '' }), $q.Votes, $q.QuorumNeeded, $(if ($q.SurvivesOneNodeLoss) { 'yes' } else { 'NO' }))
    }
    @($out | Sort-Object { $script:Severity[$_.Severity] }, Target, Check)
}

function ConvertTo-ClfMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [object[]] $Findings = @())
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('# Failover cluster readiness')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('| Node | OS build | Installation | Domain | Failover Clustering | Addresses | Reboot pending |')
    [void]$sb.AppendLine('|---|---|---|---|---|---|---|')
    foreach ($n in @(Get-ClfProp $Facts 'Nodes' @())) {
        if (-not (Get-ClfProp $n 'Build')) { [void]$sb.AppendLine(('| {0} | unreachable | | | | | |' -f $n.ComputerName)); continue }
        $f = Get-ClfProp $n 'Features'
        $ad = (@(Get-ClfProp $n 'Adapters' @()) | ForEach-Object { '{0}/{1}{2}' -f $_.IPv4, $_.PrefixLength, $(if ($_.Dhcp) { ' (DHCP)' } else { '' }) }) -join ', '
        [void]$sb.AppendLine(('| {0} | {1}.{2} | {3} | {4} | {5} | {6} | {7} |' -f $n.ComputerName, $n.Build, (Get-ClfProp $n 'Revision' 0), (Get-ClfProp $n 'InstallationType' '?'), (Get-ClfProp $n 'Domain' '?'),
                $(if (Get-ClfProp $f 'Failover-Clustering' $false) { 'installed' } else { 'no' }), $ad, $(if (Get-ClfProp $n 'PendingReboot' $false) { 'yes' } else { 'no' })))
    }
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('## Findings')
    [void]$sb.AppendLine()
    if (-not @($Findings).Count) { [void]$sb.AppendLine('None.') }
    else {
        [void]$sb.AppendLine('| Severity | Target | Check | Message |')
        [void]$sb.AppendLine('|---|---|---|---|')
        foreach ($x in $Findings) { [void]$sb.AppendLine(('| {0} | {1} | {2} | {3} |' -f $x.Severity, $x.Target, $x.Check, ($x.Message -replace '\|', '/'))) }
    }
    $sb.ToString()
}

# ---------------------------------------------------------------------------------------------------------------
# Plans (pure), then apply
# ---------------------------------------------------------------------------------------------------------------

function Get-ClfBuildPlan {
    <#
    .SYNOPSIS
    Pure. The ordered steps that build the cluster in cluster-lab.json from the facts. Steps that are already done drop out
    (feature installed, node already clustered). New-Cluster and Add-ClusterGenericServiceRole are LocalOnly: Learn says they
    cannot be run remotely without CredSSP, so the plan must be applied on a node. The witness share can only get the
    cluster name object's permission after New-Cluster, so it comes after it.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config, $Facts = $null)
    $c = $Config.Cluster; $r = $Config.Role
    $names = @($c.Nodes | ForEach-Object { [string]$_ })
    $by = @{}
    foreach ($n in @(Get-ClfProp $Facts 'Nodes' @())) { $by[([string]$n.ComputerName).ToUpperInvariant()] = $n }
    $clustered = @($names | Where-Object { $by.ContainsKey($_.ToUpperInvariant()) -and (Get-ClfProp $by[$_.ToUpperInvariant()] 'ClusterService') -eq 'Running' }).Count -gt 0
    $steps = New-Object System.Collections.ArrayList
    function Add-S { param($Id, $Cmdlet, $Params, $Why, [bool] $LocalOnly = $false, $Kind = 'Cmdlet', [bool] $CreatesAd = $false) [void]$steps.Add([pscustomobject]@{ Order = $steps.Count + 1; Id = $Id; Kind = $Kind; Cmdlet = $Cmdlet; Parameters = $Params; LocalOnly = $LocalOnly; CreatesAdObjects = $CreatesAd; Why = $Why }) }
    $has = { param($n, $f) $x = $by[$n.ToUpperInvariant()]; $x -and (Get-ClfProp (Get-ClfProp $x 'Features') $f $false) }
    foreach ($n in $names) {
        if (-not (& $has $n 'Failover-Clustering')) { Add-S "InstallFeature:$n" 'Install-WindowsFeature' ([ordered]@{ Name = 'Failover-Clustering'; IncludeManagementTools = $true; ComputerName = $n }) "Install the Failover Clustering feature on $n (Learn: every node)." }
    }
    foreach ($n in $names) {
        if (-not (& $has $n 'Web-Server')) { Add-S "InstallIis:$n" 'Install-WindowsFeature' ([ordered]@{ Name = 'Web-Server'; ComputerName = $n }) "Install IIS on ${n}: the clustered role is the W3SVC service, with a page that names the node that serves it." }
    }
    foreach ($n in $names) {
        Add-S "IndexPage:$n" '' ([ordered]@{ ComputerName = $n; Text = "Served by $n" }) "Write the default page on ${n}: it says which node answered, so failover is visible from a browser." $false 'IndexPage'
    }
    if (-not $clustered) {
        Add-S 'TestCluster' 'Test-Cluster' ([ordered]@{ Node = $names; Ignore = 'Storage' }) 'Validate the nodes (Learn: run it before New-Cluster). Storage tests are ignored: this lab cluster has no shared disks.' $false
        Add-S 'NewCluster' 'New-Cluster' ([ordered]@{ Name = [string]$c.Name; Node = $names; StaticAddress = [string]$c.StaticAddress; NoStorage = $true }) "Create the cluster $($c.Name) at $($c.StaticAddress) with no clustered storage. Creates the cluster name object in Active Directory." $true 'Cmdlet' $true
    }
    $wp = Get-ClfWitnessPath $Config
    if ($wp) {
        Add-S 'WitnessShare' '' ([ordered]@{ ComputerName = [string]$Config.Witness.Host; ShareName = [string]$Config.Witness.ShareName; FolderPath = [string]$Config.Witness.FolderPath; Account = ('{0}\{1}$' -f $c.DomainNetbios, $c.Name) }) "Create $wp and give the cluster name object (CONTOSO\$($c.Name)`$) Change on the share and Modify on the folder (Learn: file share witness)." $false 'WitnessShare'
        Add-S 'SetQuorum' 'Set-ClusterQuorum' ([ordered]@{ Cluster = [string]$c.Name; FileShareWitness = $wp }) 'Node and File Share Majority.' $false
    }
    Add-S 'AddRole' 'Add-ClusterGenericServiceRole' ([ordered]@{ ServiceName = [string]$r.ServiceName; Name = [string]$r.Name; StaticAddress = [string]$r.StaticAddress; Cluster = [string]$c.Name }) "Make the $($r.ServiceName) service a clustered role named $($r.Name) at $($r.StaticAddress). Creates a computer object in Active Directory for the role." $true 'Cmdlet' $true
    $steps
}

function Get-ClfRemovePlan {
    <# Pure. The tear-down: destroy the cluster and its Active Directory objects (Remove-Cluster -CleanupAD), then the witness share. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config)
    $c = $Config.Cluster
    $steps = New-Object System.Collections.ArrayList
    [void]$steps.Add([pscustomobject]@{ Order = 1; Id = 'RemoveCluster'; Kind = 'Cmdlet'; Cmdlet = 'Remove-Cluster'; Parameters = [ordered]@{ Cluster = [string]$c.Name; Force = $true; CleanupAD = $true }; LocalOnly = $true; CreatesAdObjects = $false; Why = "Destroy $($c.Name): deletes the cluster configuration on all nodes and the cluster objects in Active Directory (Learn)." })
    if (Get-ClfWitnessPath $Config) {
        [void]$steps.Add([pscustomobject]@{ Order = 2; Id = 'RemoveWitnessShare'; Kind = 'WitnessShareRemove'; Cmdlet = ''; Parameters = [ordered]@{ ComputerName = [string]$Config.Witness.Host; ShareName = [string]$Config.Witness.ShareName; FolderPath = [string]$Config.Witness.FolderPath }; LocalOnly = $false; CreatesAdObjects = $false; Why = 'Remove the witness share and its folder.' })
    }
    $steps
}

$script:IndexPageScript = {
    param($Text)
    $dir = Join-Path $env:SystemDrive 'inetpub\wwwroot'
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Set-Content -LiteralPath (Join-Path $dir 'index.html') -Value $Text -Encoding ASCII
}
$script:WitnessScript = {
    param($ShareName, $FolderPath, $Account)
    if (-not (Test-Path -LiteralPath $FolderPath)) { New-Item -ItemType Directory -Path $FolderPath -Force | Out-Null }
    if (-not (Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue)) { New-SmbShare -Name $ShareName -Path $FolderPath -ChangeAccess $Account | Out-Null }
    else { Grant-SmbShareAccess -Name $ShareName -AccountName $Account -AccessRight Change -Force | Out-Null }
    $acl = Get-Acl -LiteralPath $FolderPath
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($Account, 'Modify', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $FolderPath -AclObject $acl
}
$script:WitnessRemoveScript = {
    param($ShareName, $FolderPath)
    if (Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue) { Remove-SmbShare -Name $ShareName -Force }
    if (Test-Path -LiteralPath $FolderPath) { Remove-Item -LiteralPath $FolderPath -Recurse -Force }
}

function Invoke-ClfPlan {
    <#
    Applies a build or remove plan one step at a time. Only allow-listed cmdlets run. LocalOnly steps need the command to run
    ON a cluster node (-LocalComputerName must be one of -NodeName); the check happens before anything changes. -WhatIf shows every step.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)] [object[]] $Plan, [Parameter(Mandatory)] [string[]] $NodeName, [string] $LocalComputerName = $env:COMPUTERNAME, [pscredential] $Credential)
    foreach ($s in $Plan) {
        if ($s.Kind -eq 'Cmdlet' -and $script:AllowedCmdlets -notcontains [string]$s.Cmdlet) { throw "Step '$($s.Id)' names '$($s.Cmdlet)', which is not an allowed cmdlet." }
    }
    $needsNode = @($Plan | Where-Object { $_.LocalOnly }).Count -gt 0
    if ($needsNode -and (@($NodeName | ForEach-Object { $_.ToUpperInvariant() }) -notcontains $LocalComputerName.ToUpperInvariant())) {
        throw "This plan has steps that cannot run remotely (Learn: $($script:LocalOnlyCmdlets -join ', ') need CredSSP when run remotely). Run it ON a cluster node ($($NodeName -join ', ')); this is $LocalComputerName."
    }
    foreach ($s in $Plan) {
        $p = @{}
        foreach ($k in $s.Parameters.Keys) { $p[$k] = $s.Parameters[$k] }
        if (-not $PSCmdlet.ShouldProcess("$($s.Id)", $s.Why)) { continue }
        switch ($s.Kind) {
            'Cmdlet' {
                $r = & $s.Cmdlet @p
                $restart = ''
                if ($s.Cmdlet -eq 'Install-WindowsFeature' -and $r -and (Get-ClfProp $r 'RestartNeeded')) { $restart = [string]$r.RestartNeeded }
                [pscustomobject]@{ Step = $s.Id; Result = 'Applied'; RestartNeeded = $restart }
            }
            'IndexPage' {
                $a = @{ ComputerName = $p.ComputerName; ScriptBlock = $script:IndexPageScript; ArgumentList = @($p.Text); ErrorAction = 'Stop' }
                if ($Credential) { $a.Credential = $Credential }
                Invoke-Command @a
                [pscustomobject]@{ Step = $s.Id; Result = 'Applied'; RestartNeeded = '' }
            }
            'WitnessShare' {
                $a = @{ ComputerName = $p.ComputerName; ScriptBlock = $script:WitnessScript; ArgumentList = @($p.ShareName, $p.FolderPath, $p.Account); ErrorAction = 'Stop' }
                if ($Credential) { $a.Credential = $Credential }
                Invoke-Command @a
                [pscustomobject]@{ Step = $s.Id; Result = 'Applied'; RestartNeeded = '' }
            }
            'WitnessShareRemove' {
                $a = @{ ComputerName = $p.ComputerName; ScriptBlock = $script:WitnessRemoveScript; ArgumentList = @($p.ShareName, $p.FolderPath); ErrorAction = 'Stop' }
                if ($Credential) { $a.Credential = $Credential }
                Invoke-Command @a
                [pscustomobject]@{ Step = $s.Id; Result = 'Applied'; RestartNeeded = '' }
            }
            default { throw "Unknown step kind '$($s.Kind)'." }
        }
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Failover drill and outage measurement
# ---------------------------------------------------------------------------------------------------------------

function Invoke-ClfDrain {
    <#
    .SYNOPSIS
    Planned failover: pauses the node that owns the role with -Drain (the role moves to the other node), checks where it is,
    then resumes the node without failing back. Run on a cluster node. -WhatIf shows the plan.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)] [string] $Cluster, [Parameter(Mandatory)] [string] $Role, [Parameter(Mandatory)] [string[]] $NodeName)
    $g = Get-ClusterGroup -Name $Role -Cluster $Cluster
    if (-not $g) { throw "Clustered role '$Role' not found on cluster '$Cluster'." }
    $from = [string]$g.OwnerNode.Name
    $to = @($NodeName | Where-Object { $_.ToUpperInvariant() -ne $from.ToUpperInvariant() })[0]
    if (-not $to) { throw 'No other node to move the role to.' }
    if (-not $PSCmdlet.ShouldProcess("$Role on $from", "Suspend-ClusterNode -Drain (move to $to), then Resume-ClusterNode -Failback NoFailback")) { return }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Suspend-ClusterNode -Name $from -Cluster $Cluster -Drain -TargetNode $to -Wait | Out-Null
    $after = Get-ClusterGroup -Name $Role -Cluster $Cluster
    $sw.Stop()
    Resume-ClusterNode -Name $from -Cluster $Cluster -Failback NoFailback | Out-Null
    [pscustomobject]@{ Role = $Role; From = $from; To = [string]$after.OwnerNode.Name; State = [string]$after.State; DrainSeconds = [math]::Round($sw.Elapsed.TotalSeconds, 1) }
}

function Get-ClfProbeSummary {
    <#
    .SYNOPSIS
    Pure. From probe samples (T = UTC time, Ok, Server) works out how many requests failed, which node answered, and every
    outage: from the first failed sample to the next good one.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [object[]] $Samples)
    $s = @($Samples | Sort-Object { [datetime]$_.T })
    $outages = New-Object System.Collections.ArrayList
    $start = $null; $count = 0; $last = $null; $changes = 0; $prevServer = $null
    $served = [ordered]@{}
    foreach ($x in $s) {
        $t = ([datetime]$x.T).ToUniversalTime()
        if ($x.Ok) {
            if ($null -ne $start) { [void]$outages.Add([pscustomobject]@{ Start = $start; End = $t; Seconds = [math]::Round(($t - $start).TotalSeconds, 2); FailedRequests = $count }); $start = $null; $count = 0 }
            $srv = [string](Get-ClfProp $x 'Server' '')
            if ($srv) {
                if ($served.Contains($srv)) { $served[$srv]++ } else { $served[$srv] = 1 }
                if ($prevServer -and $srv -ne $prevServer) { $changes++ }
                $prevServer = $srv
            }
        }
        else {
            if ($null -eq $start) { $start = $t }
            $count++
        }
        $last = $t
    }
    if ($null -ne $start) { [void]$outages.Add([pscustomobject]@{ Start = $start; End = $last; Seconds = [math]::Round(($last - $start).TotalSeconds, 2); FailedRequests = $count }) }
    $failed = @($s | Where-Object { -not $_.Ok }).Count
    [pscustomobject]@{
        Samples = $s.Count; Failed = $failed; ServerChanges = $changes; ServedBy = $served
        Outages = @($outages); OutageCount = $outages.Count
        LongestOutageSeconds = $(if ($outages.Count) { ($outages | Measure-Object Seconds -Maximum).Maximum } else { 0 })
        TotalDowntimeSeconds = $(if ($outages.Count) { [math]::Round(($outages | Measure-Object Seconds -Sum).Sum, 2) } else { 0 })
    }
}

function Invoke-ClfProbe {
    <# Client side: requests $Url every $IntervalMs for $DurationSec and writes one JSON line per request (T, Ok, Server, Ms). The page says "Served by <node>". #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Url, [int] $DurationSec = 60, [int] $IntervalMs = 500, [string] $OutFile, [int] $TimeoutSec = 2)
    $end = (Get-Date).AddSeconds($DurationSec)
    $all = New-Object System.Collections.ArrayList
    while ((Get-Date) -lt $end) {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $t = (Get-Date).ToUniversalTime()
        $ok = $false; $server = $null
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop
            $ok = ([int]$r.StatusCode -eq 200)
            $text = if ($r.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($r.Content) } else { "$($r.Content)" }
            if ($text -match 'Served by (\S+)') { $server = $Matches[1] }
        }
        catch { $ok = $false }
        $rec = [pscustomobject]@{ T = $t.ToString('o'); Ok = $ok; Server = $server; Ms = [int]$sw.ElapsedMilliseconds }
        [void]$all.Add($rec)
        if ($OutFile) { Add-Content -LiteralPath $OutFile -Value ($rec | ConvertTo-Json -Compress) -Encoding UTF8 }
        $left = $IntervalMs - [int]$sw.ElapsedMilliseconds
        if ($left -gt 0) { Start-Sleep -Milliseconds $left }
    }
    $all
}

Export-ModuleMember -Function Read-ClfLabConfig, Get-ClfCollectorScript, Get-ClfFacts, Test-ClfReadiness, Get-ClfQuorumMath,
    ConvertTo-ClfMarkdown, Get-ClfBuildPlan, Get-ClfRemovePlan, Invoke-ClfPlan, Invoke-ClfDrain, Invoke-ClfProbe, Get-ClfProbeSummary
