#Requires -Version 5.1
<#
    WacLab - Windows Admin Center (Administration Mode) as a gateway for lab.contoso.com (DEVLADLOG Windows Server #6).

    Preflight    Get-WacGatewayFacts (collector, runs on the gateway) + Test-WacGateway (pure rules) + ConvertTo-WacMarkdown
    Install      Get-WacInstallerArgument + Install-WacGateway (silent, Administration Mode)
    Connections  ConvertTo-WacConnectionCsv + Test-WacConnectionCsv + Find-WacPowerShellModule + Import-WacLabConnection
    SSO          Get-WacDelegationPlan (pure) + Set-WacKerberosDelegation (resource-based constrained delegation)
    RBAC         Get-WacRbacStatus (collector) + Test-WacRbac (pure) + Add-WacRbacMember

    Windows PowerShell 5.1 compatible (it runs on the gateway); tests run in PowerShell 7 on Linux with mocks.
#>
Set-StrictMode -Version 3.0

# Learn, "Use PowerShell to manage Windows Admin Center settings": the documented connection types (case-sensitive)
$script:ConnectionTypes = @{
    server  = 'msft.sme.connection-type.server'
    cluster = 'msft.sme.connection-type.cluster'
}
$script:CsvHeader = '"name","type","tags","groupId"'
# Learn, "Configure user access control": the local groups created when RBAC is applied to a node
$script:RbacGroups = [ordered]@{
    Administrators       = 'Windows Admin Center Administrators'
    HyperVAdministrators = 'Windows Admin Center Hyper-V Administrators'
    Readers              = 'Windows Admin Center Readers'
}
$script:RbacEndpoint = 'Microsoft.Sme.PowerShell'
$script:ServerAuthEku = '1.3.6.1.5.5.7.3.1'
$script:Severity = @{ High = 0; Medium = 1; Low = 2; Info = 3 }

function New-WacFinding {
    param([string] $Target, [string] $Severity, [string] $Check, [string] $Message)
    [pscustomobject]@{ Target = $Target; Severity = $Severity; Check = $Check; Message = $Message }
}

function Get-WacProp {
    param($Object, [string] $Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] }; return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    $Default
}

function Get-WacNodeFqdn {
    param([string] $Name, [string] $Domain)
    if ($Name -like '*.*') { return $Name.ToLowerInvariant() }
    ('{0}.{1}' -f $Name, $Domain).ToLowerInvariant()
}

# ---------------------------------------------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------------------------------------------

function Read-WacLabConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    $c = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if ((Get-WacProp $c 'SchemaVersion') -ne 1) { throw "Unsupported SchemaVersion in '$Path' (expected 1)." }
    foreach ($k in 'Domain', 'Gateway', 'Nodes') { if (-not (Get-WacProp $c $k)) { throw "'$Path' is missing '$k'." } }
    $mode = [string](Get-WacProp $c.Gateway 'Mode' 'Administration')
    if (@('Administration', 'Virtualization') -notcontains $mode) { throw "Gateway.Mode must be Administration or Virtualization, not '$mode'." }
    $names = @($c.Nodes | ForEach-Object { ([string]$_.Name).ToUpperInvariant() })
    $dupes = @($names | Group-Object | Where-Object Count -gt 1 | ForEach-Object Name)
    if ($dupes.Count) { throw "Duplicate node(s): $($dupes -join ', ')." }
    $c
}

# ---------------------------------------------------------------------------------------------------------------
# Connections CSV
# ---------------------------------------------------------------------------------------------------------------

function ConvertTo-WacConnectionCsv {
    <#
    .SYNOPSIS
    The import file for Import-WACConnection: "name","type","tags","groupId", FQDN names, documented types only,
    pipe-separated tags, groupId "global" for shared connections.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] $Config)
    $lines = New-Object System.Collections.ArrayList
    [void]$lines.Add($script:CsvHeader)
    foreach ($n in $Config.Nodes) {
        $type = [string](Get-WacProp $n 'Type' 'server')
        if (-not $script:ConnectionTypes.ContainsKey($type)) {
            throw "Node '$($n.Name)': type '$type' isn't a documented connection type (use: $($script:ConnectionTypes.Keys -join ', '))."
        }
        $tags = @(Get-WacProp $n 'Tags' @())
        foreach ($t in $tags) {
            if ($t -match '[|,"]' -or -not $t.Trim()) { throw "Node '$($n.Name)': tag '$t' is empty or contains | , or a quote." }
        }
        $group = ''
        if (Get-WacProp $n 'Shared' $false) { $group = 'global' }
        $fields = @((Get-WacNodeFqdn $n.Name $Config.Domain), $script:ConnectionTypes[$type], ($tags -join '|'), $group)
        [void]$lines.Add((($fields | ForEach-Object { '"{0}"' -f $_ }) -join ','))
    }
    ($lines -join "`r`n") + "`r`n"
}

function Test-WacConnectionCsv {
    <#
    .SYNOPSIS
    Strict check of a connections CSV before Import-WACConnection: exact header, every line fully quoted with 3 or 4
    fields, a documented type (the file is case-sensitive), an FQDN name, groupId empty or "global".
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Content)
    $out = New-Object System.Collections.ArrayList
    $lines = @($Content -split "\r?\n" | Where-Object { $_.Trim() })
    if (-not $lines.Count) { return @(New-WacFinding 'file' High 'Empty' 'The file has no lines.') }
    if ($lines[0] -cne $script:CsvHeader -and $lines[0] -cne '"name","type","tags"') {
        [void]$out.Add((New-WacFinding 'line 1' High 'Header' "Header must be $($script:CsvHeader) (case-sensitive), found: $($lines[0])"))
    }
    $valid = @($script:ConnectionTypes.Values)
    for ($i = 1; $i -lt $lines.Count; $i++) {
        $ln = "line $($i + 1)"
        $line = $lines[$i]
        if ($line -notmatch '^"[^"]*"(,"[^"]*"){1,3}$') {
            [void]$out.Add((New-WacFinding $ln High 'Malformed' "Not 3-4 quoted fields: $line"))
            continue
        }
        $f = @([regex]::Matches($line, '"([^"]*)"') | ForEach-Object { $_.Groups[1].Value })
        if ($f.Count -lt 3) { [void]$out.Add((New-WacFinding $ln Medium 'NoTags' "Only $($f.Count) fields: add an empty tags field.")) }
        if ($f[0] -notmatch '^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$') { [void]$out.Add((New-WacFinding $ln Medium 'NotFqdn' "Name '$($f[0])' isn't an FQDN.")) }
        if ($valid -cnotcontains $f[1]) { [void]$out.Add((New-WacFinding $ln High 'UnknownType' "Type '$($f[1])' isn't one of: $($valid -join ', ').")) }
        if ($f.Count -eq 4 -and $f[3] -and $f[3] -cne 'global') { [void]$out.Add((New-WacFinding $ln Medium 'GroupId' "groupId '$($f[3])' should be empty or 'global'.")) }
    }
    $out | Sort-Object { $script:Severity[$_.Severity] }
}

function Find-WacPowerShellModule {
    <#
    .SYNOPSIS
    Finds a Windows Admin Center PowerShell module folder (ConnectionTools, ExtensionTools) under Program Files.
    Learn shows two different paths across pages, one of them inside "$env:'Program Files'", which doesn't expand
    to a folder; so we search instead of hard-coding.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [ValidateSet('ConnectionTools', 'ExtensionTools')] [string] $Name,
        [string[]] $Root = @($env:ProgramFiles)
    )
    $searched = New-Object System.Collections.ArrayList
    foreach ($r in $Root) {
        if (-not $r) { continue }
        foreach ($rel in 'WindowsAdminCenter\PowerShellModules', 'Windows Admin Center\PowerShell\Modules') {
            $dir = Join-Path $r ($rel -replace '\\', [IO.Path]::DirectorySeparatorChar)
            [void]$searched.Add($dir)
            if (-not (Test-Path -LiteralPath $dir)) { continue }
            $hit = @(Get-ChildItem -LiteralPath $dir -Directory | Where-Object { $_.Name -eq $Name -or $_.Name -like "*.$Name" } | Sort-Object Name)
            if ($hit.Count) { return $hit[0].FullName }
        }
    }
    throw "Windows Admin Center module '$Name' not found. Searched: $($searched -join '; '). Is Windows Admin Center installed on this machine?"
}

function Import-WacLabConnection {
    <#
    .SYNOPSIS
    Writes the CSV, checks it, and imports it with Import-WACConnection (shared connections need a gateway admin).
    .PARAMETER AccessKey
    From Windows Admin Center Settings > Advanced. Passed as a SecureString so it never sits in the history.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] $Config,
        [Parameter(Mandatory)] [securestring] $AccessKey,
        [pscredential] $Credential,
        [string] $CsvPath = (Join-Path ([IO.Path]::GetTempPath()) 'wac-lab-connections.csv'),
        [switch] $Prune
    )
    $csv = ConvertTo-WacConnectionCsv -Config $Config
    $problems = @(Test-WacConnectionCsv -Content $csv | Where-Object Severity -eq 'High')
    if ($problems.Count) { throw "Connections CSV failed validation: $($problems[0].Target) $($problems[0].Message)" }
    [IO.File]::WriteAllText($CsvPath, $csv, (New-Object System.Text.UTF8Encoding($false)))

    $endpoint = Get-WacGatewayUrl -Config $Config
    if (-not $PSCmdlet.ShouldProcess($endpoint, "Import $(@($Config.Nodes).Count) connection(s) from $CsvPath")) { return }
    Import-Module (Find-WacPowerShellModule -Name ConnectionTools) -ErrorAction Stop
    # PSCredential does the SecureString -> text conversion correctly on every platform (episode 4 lesson)
    $key = (New-Object System.Management.Automation.PSCredential('wac', $AccessKey)).GetNetworkCredential().Password
    $p = @{ Endpoint = $endpoint; FileName = $CsvPath; AccessKey = $key }
    if ($Credential) { $p.Credentials = $Credential }
    if ($Prune) { $p.Prune = $true }
    Import-WACConnection @p
}

function Get-WacGatewayUrl {
    param([Parameter(Mandatory)] $Config)
    $fqdn = Get-WacNodeFqdn $Config.Gateway.ComputerName $Config.Domain
    $port = [int](Get-WacProp $Config.Gateway 'HttpsPort' 443)
    if ($port -eq 443) { return "https://$fqdn" }
    "https://${fqdn}:$port"
}

# ---------------------------------------------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------------------------------------------

$script:Collector = {
    # Runs ON the future gateway. Windows PowerShell 5.1, self-contained (no WacLab functions).
    param([string] $CertificateThumbprint, [int] $HttpsPort, [string[]] $NodeFqdns)

    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem
    $sysDisk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $os.SystemDrive)
    $installType = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -Name InstallationType -ErrorAction SilentlyContinue).InstallationType

    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $HttpsPort -ErrorAction SilentlyContinue | ForEach-Object {
            $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
            $pname = ''
            if ($proc) { $pname = $proc.ProcessName }
            [pscustomobject]@{ Port = [int]$_.LocalPort; ProcessName = $pname }
        })

    $wac = Get-Service -Name WindowsAdminCenter -ErrorAction SilentlyContinue
    $wacStatus = $null
    if ($wac) { $wacStatus = [string]$wac.Status }

    $cert = $null
    if ($CertificateThumbprint) {
        $c = Get-Item -LiteralPath ("Cert:\LocalMachine\My\{0}" -f $CertificateThumbprint) -ErrorAction SilentlyContinue
        if ($c) {
            $cert = [pscustomobject]@{
                Thumbprint = $c.Thumbprint
                Subject    = $c.Subject
                NotAfter   = $c.NotAfter.ToUniversalTime().ToString('o')
                DnsNames   = @($c.DnsNameList | ForEach-Object { [string]$_.Unicode })
                Eku        = @($c.EnhancedKeyUsageList | ForEach-Object { [string]$_.ObjectId })
                HasPrivateKey = [bool]$c.HasPrivateKey
            }
        }
        else { $cert = [pscustomobject]@{ Thumbprint = $CertificateThumbprint; Missing = $true } }
    }

    $nodes = foreach ($fqdn in $NodeFqdns) {
        $build = 0; $role = -1; $err = ''
        try {
            $nos = Get-CimInstance -ComputerName $fqdn -ClassName Win32_OperatingSystem -OperationTimeoutSec 15 -ErrorAction Stop
            $ncs = Get-CimInstance -ComputerName $fqdn -ClassName Win32_ComputerSystem -OperationTimeoutSec 15 -ErrorAction Stop
            $build = [int]$nos.BuildNumber
            $role = [int]$ncs.DomainRole
        }
        catch { $err = $_.Exception.Message }
        [pscustomobject]@{ Fqdn = $fqdn; Reachable = ($err -eq ''); Build = $build; DomainRole = $role; Error = $err }
    }

    [pscustomobject]@{
        SchemaVersion = 1
        CollectedUtc  = (Get-Date).ToUniversalTime().ToString('o')
        Gateway       = [pscustomobject]@{
            ComputerName      = $env:COMPUTERNAME
            Caption           = $os.Caption
            Build             = [int]$os.BuildNumber
            ProductType       = [int]$os.ProductType
            InstallationType  = $installType
            DomainRole        = [int]$cs.DomainRole
            PartOfDomain      = [bool]$cs.PartOfDomain
            Domain            = [string]$cs.Domain
            LogicalProcessors = [int]$cs.NumberOfLogicalProcessors
            MemoryGB          = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
            SystemFreeGB      = [math]::Round($sysDisk.FreeSpace / 1GB, 1)
            Listeners         = $listeners
            WacService        = $wacStatus
            Certificate       = $cert
        }
        Nodes         = @($nodes)
    }
}

function Get-WacCollectorScript { $script:Collector }

function Get-WacGatewayFacts {
    <#
    .SYNOPSIS
    Runs the collector on the gateway (locally when ComputerName is the local machine) and returns the facts.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config, [pscredential] $Credential)
    $gw = [string]$Config.Gateway.ComputerName
    $collectorArgs = @([string](Get-WacProp $Config.Gateway 'CertificateThumbprint' ''), [int](Get-WacProp $Config.Gateway 'HttpsPort' 443),
        [string[]]@($Config.Nodes | ForEach-Object { Get-WacNodeFqdn $_.Name $Config.Domain }))
    if ($gw -eq $env:COMPUTERNAME) { return (& $script:Collector @collectorArgs) }
    $p = @{ ComputerName = $gw; ScriptBlock = $script:Collector; ArgumentList = $collectorArgs }
    if ($Credential) { $p.Credential = $Credential }
    Invoke-Command @p | Select-Object -Property * -ExcludeProperty PSComputerName, RunspaceId, PSShowComputerName
}

function Test-WacGateway {
    <#
    .SYNOPSIS
    Pure preflight rules for a Windows Admin Center gateway and its managed nodes.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [Parameter(Mandatory)] $Config, [datetime] $Now = (Get-Date))
    $out = New-Object System.Collections.ArrayList
    $g = $Facts.Gateway
    $name = [string]$g.ComputerName
    $mode = [string](Get-WacProp $Config.Gateway 'Mode' 'Administration')
    $port = [int](Get-WacProp $Config.Gateway 'HttpsPort' 443)

    if ($g.DomainRole -ge 4 -or $g.ProductType -eq 2) {
        [void]$out.Add((New-WacFinding $name High 'GatewayOnDomainController' "Don't install Windows Admin Center on a domain controller: that configuration isn't supported."))
    }
    if ($g.ProductType -eq 1) {
        [void]$out.Add((New-WacFinding $name Medium 'ClientOs' 'Windows 11 is a local-client topology; use Windows Server for a shared gateway.'))
    }
    elseif ($g.Build -lt 14393) {
        [void]$out.Add((New-WacFinding $name High 'UnsupportedOs' "Build $($g.Build): the gateway needs Windows Server 2016 or later."))
    }
    if (-not $g.PartOfDomain) {
        [void]$out.Add((New-WacFinding $name High 'NotDomainJoined' 'Group-based access and Kerberos delegation need a domain-joined gateway.'))
    }
    elseif ($g.Domain -and $g.Domain -ne $Config.Domain) {
        [void]$out.Add((New-WacFinding $name Medium 'OtherDomain' "Gateway is in '$($g.Domain)', config says '$($Config.Domain)'."))
    }
    $others = @($g.Listeners | Where-Object { $_.Port -eq $port })
    if ($others.Count -and -not $g.WacService) {
        [void]$out.Add((New-WacFinding $name High 'PortInUse' "Port $port is already used by $(($others | ForEach-Object ProcessName) -join ', '). Pick another HttpsPort."))
    }
    if ($g.WacService) {
        [void]$out.Add((New-WacFinding $name Info 'AlreadyInstalled' "Windows Admin Center service is $($g.WacService)."))
    }

    $cert = Get-WacProp $g 'Certificate'
    if ($null -eq $cert) {
        [void]$out.Add((New-WacFinding $name Info 'SelfSignedCertificate' 'No certificate configured: the installer generates a self-signed one that expires after 60 days (testing only).'))
    }
    elseif (Get-WacProp $cert 'Missing' $false) {
        [void]$out.Add((New-WacFinding $name High 'CertificateMissing' "Certificate $($cert.Thumbprint) isn't in LocalMachine\My."))
    }
    else {
        $notAfter = [datetime]$cert.NotAfter
        $days = [math]::Floor(($notAfter.ToUniversalTime() - $Now.ToUniversalTime()).TotalDays)
        $warn = [int](Get-WacProp $Config.Policy 'CertificateWarnDays' 30)
        if ($days -lt 0) { [void]$out.Add((New-WacFinding $name High 'CertificateExpired' "Certificate expired on $($notAfter.ToString('yyyy-MM-dd')).")) }
        elseif ($days -lt $warn) { [void]$out.Add((New-WacFinding $name Medium 'CertificateExpiring' "Certificate expires in $days day(s).")) }
        if (@($cert.Eku) -notcontains $script:ServerAuthEku) {
            [void]$out.Add((New-WacFinding $name High 'CertificateEku' "Certificate lacks Server Authentication ($($script:ServerAuthEku))."))
        }
        if (-not (Get-WacProp $cert 'HasPrivateKey' $true)) {
            [void]$out.Add((New-WacFinding $name High 'CertificateNoKey' 'Certificate has no private key on this machine.'))
        }
        $fqdn = Get-WacNodeFqdn $Config.Gateway.ComputerName $Config.Domain
        if (@($cert.DnsNames | ForEach-Object { ([string]$_).ToLowerInvariant() }) -notcontains $fqdn) {
            [void]$out.Add((New-WacFinding $name Medium 'CertificateName' "Certificate names ($(@($cert.DnsNames) -join ', ')) don't include ${fqdn}: browsers will warn."))
        }
    }

    if ($mode -eq 'Virtualization') {
        if ($g.LogicalProcessors -lt 4) { [void]$out.Add((New-WacFinding $name High 'VmModeCpu' "Virtualization Mode needs at least 4 cores ($($g.LogicalProcessors)).")) }
        if ($g.MemoryGB -lt 8) { [void]$out.Add((New-WacFinding $name High 'VmModeMemory' "Virtualization Mode needs at least 8 GB of memory ($($g.MemoryGB) GB).")) }
        if ($g.SystemFreeGB -lt 10) { [void]$out.Add((New-WacFinding $name High 'VmModeDisk' "Virtualization Mode needs at least 10 GB free ($($g.SystemFreeGB) GB).")) }
    }
    else {
        $max = [int](Get-WacProp $Config.Policy 'MaxNodesAdministrationMode' 10)
        if (@($Config.Nodes).Count -gt $max) {
            [void]$out.Add((New-WacFinding $name Medium 'ManyNodes' "$(@($Config.Nodes).Count) nodes: the installer describes Administration Mode as sized for about $max managed nodes; consider Virtualization Mode."))
        }
    }

    foreach ($n in $Config.Nodes) {
        $fqdn = Get-WacNodeFqdn $n.Name $Config.Domain
        $f = @($Facts.Nodes | Where-Object { $_.Fqdn -eq $fqdn })
        if (-not $f.Count) { [void]$out.Add((New-WacFinding $n.Name Medium 'NotChecked' 'Node missing from the facts: collect again.')); continue }
        $f = $f[0]
        if (-not $f.Reachable) {
            $sev = 'High'
            if (Get-WacProp $n 'Optional' $false) { $sev = 'Info' }
            [void]$out.Add((New-WacFinding $n.Name $sev 'NodeUnreachable' "No WinRM/CIM answer from the gateway: $($f.Error)"))
            continue
        }
        if ($f.Build -lt 14393) {
            [void]$out.Add((New-WacFinding $n.Name Medium 'NodeOldOs' "Build $($f.Build): Windows Server 2012/2012 R2 need WMF 5.1 and get limited functionality."))
        }
        if ((Get-WacProp $n 'KerberosSso' $false) -and $f.DomainRole -ge 4) {
            [void]$out.Add((New-WacFinding $n.Name Medium 'SsoToDomainController' 'KerberosSso is on for a domain controller; Set-WacKerberosDelegation skips DCs unless -IncludeDomainControllers.'))
        }
    }
    $out | Sort-Object { $script:Severity[$_.Severity] }, Target, Check
}

function ConvertTo-WacMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [Parameter(Mandatory)] $Config, [object[]] $Findings = @())
    $g = $Facts.Gateway
    $lines = New-Object System.Collections.ArrayList
    [void]$lines.Add("# Windows Admin Center preflight: $($g.ComputerName)")
    [void]$lines.Add('')
    [void]$lines.Add("Collected $($Facts.CollectedUtc) | URL $(Get-WacGatewayUrl -Config $Config) | Mode $(Get-WacProp $Config.Gateway 'Mode' 'Administration')")
    [void]$lines.Add('')
    [void]$lines.Add('| Gateway | OS | Build | Type | Domain | CPU | RAM GB | Free GB |')
    [void]$lines.Add('|---|---|---|---|---|---|---|---|')
    [void]$lines.Add("| $($g.ComputerName) | $($g.Caption) | $($g.Build) | $($g.InstallationType) | $($g.Domain) | $($g.LogicalProcessors) | $($g.MemoryGB) | $($g.SystemFreeGB) |")
    [void]$lines.Add('')
    [void]$lines.Add('| Node | Reachable | Build | SSO (RBCD) | RBAC |')
    [void]$lines.Add('|---|---|---|---|---|')
    foreach ($n in $Config.Nodes) {
        $fqdn = Get-WacNodeFqdn $n.Name $Config.Domain
        $f = @($Facts.Nodes | Where-Object { $_.Fqdn -eq $fqdn }) | Select-Object -First 1
        $reach = 'not checked'; $build = ''
        if ($f) { $reach = $(if ($f.Reachable) { 'yes' } else { 'no' }); $build = $f.Build }
        [void]$lines.Add("| $fqdn | $reach | $build | $(if (Get-WacProp $n 'KerberosSso' $false) { 'yes' } else { 'no' }) | $(if (Get-WacProp $n 'Rbac' $false) { 'yes' } else { 'no' }) |")
    }
    [void]$lines.Add('')
    [void]$lines.Add('## Findings')
    [void]$lines.Add('')
    if (-not $Findings.Count) { [void]$lines.Add('None.') }
    else {
        [void]$lines.Add('| Severity | Target | Check | Message |')
        [void]$lines.Add('|---|---|---|---|')
        foreach ($x in $Findings) { [void]$lines.Add("| $($x.Severity) | $($x.Target) | $($x.Check) | $($x.Message.Replace('|', '\|')) |") }
    }
    ($lines -join "`n") + "`n"
}

# ---------------------------------------------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------------------------------------------

function Get-WacInstallerArgument {
    <# Command-line switches documented on Learn for WindowsAdminCenter.exe. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config)
    $a = New-Object System.Collections.ArrayList
    [void]$a.Add('/VERYSILENT')
    [void]$a.Add("/Mode=$([string](Get-WacProp $Config.Gateway 'Mode' 'Administration'))")
    $port = [int](Get-WacProp $Config.Gateway 'HttpsPort' 443)
    if ($port -ne 443) { [void]$a.Add("/HTTPSPortNumber=$port") }
    $thumb = [string](Get-WacProp $Config.Gateway 'CertificateThumbprint' '')
    if ($thumb) {
        if ($thumb -notmatch '^[0-9A-Fa-f]{40}$') { throw "CertificateThumbprint must be 40 hex characters." }
        [void]$a.Add("/CertificateThumbprint=$($thumb.ToUpperInvariant())")
    }
    @($a)
}

function Install-WacGateway {
    <#
    .SYNOPSIS
    Silent install of Windows Admin Center on THIS machine (the gateway), then waits for the service.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param(
        [Parameter(Mandatory)] $Config,
        [Parameter(Mandatory)] [string] $InstallerPath,
        [int] $ServiceTimeoutSeconds = 300,
        [scriptblock] $Sleep = { param($s) Start-Sleep -Seconds $s }
    )
    if (-not (Test-Path -LiteralPath $InstallerPath)) { throw "Installer not found: $InstallerPath" }
    $argList = Get-WacInstallerArgument -Config $Config
    if (-not $PSCmdlet.ShouldProcess($env:COMPUTERNAME, "$InstallerPath $($argList -join ' ')")) { return }
    $p = Start-Process -FilePath $InstallerPath -ArgumentList $argList -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Windows Admin Center installer exited with code $($p.ExitCode)." }

    $waited = 0
    while ($true) {
        $svc = Get-Service -Name WindowsAdminCenter -ErrorAction SilentlyContinue
        if ($svc -and [string]$svc.Status -eq 'Running') { break }
        if ($svc -and [string]$svc.Status -eq 'Stopped' -and $waited -eq 0) { Start-Service -Name WindowsAdminCenter }
        if ($waited -ge $ServiceTimeoutSeconds) { throw "WindowsAdminCenter service not running after $ServiceTimeoutSeconds s." }
        & $Sleep 5
        $waited += 5
    }
    [pscustomobject]@{ Url = (Get-WacGatewayUrl -Config $Config); Arguments = $argList; Service = 'Running' }
}

# ---------------------------------------------------------------------------------------------------------------
# Single sign-on: resource-based constrained delegation
# ---------------------------------------------------------------------------------------------------------------

function Get-WacDelegationPlan {
    <#
    .SYNOPSIS
    Pure: what PrincipalsAllowedToDelegateToAccount should become on each node. The parameter SETS the attribute
    (Learn: running Set-ADComputer without the existing principals overrides them), so the plan always carries the
    full list: current principals plus (or minus) the gateway.
    .PARAMETER Current
    Hashtable node name -> array of principal DNs currently allowed.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string[]] $NodeName,
        [Parameter(Mandatory)] [string] $GatewayDn,
        [hashtable] $Current = @{},
        [switch] $Remove
    )
    foreach ($n in $NodeName) {
        $cur = @()
        if ($Current.ContainsKey($n)) { $cur = @($Current[$n] | Where-Object { $_ }) }
        $has = @($cur | Where-Object { $_ -eq $GatewayDn }).Count -gt 0
        if ($Remove) {
            $desired = @($cur | Where-Object { $_ -ne $GatewayDn })
            $action = 'NoChange'
            if ($has -and $desired.Count) { $action = 'Remove' }
            elseif ($has) { $action = 'Clear' }
        }
        else {
            $desired = @($cur)
            $action = 'NoChange'
            if (-not $has) { $desired = @($cur) + $GatewayDn; $action = 'Add' }
        }
        [pscustomobject]@{ Node = $n; Action = $action; Current = @($cur); Desired = @($desired); Kept = @($cur | Where-Object { $_ -ne $GatewayDn }) }
    }
}

function Set-WacKerberosDelegation {
    <#
    .SYNOPSIS
    Lets the gateway delegate to each node with KerberosSso = true (resource-based constrained delegation),
    keeping any principal that was already allowed. Skips domain controllers unless -IncludeDomainControllers.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] $Config,
        [switch] $Remove,
        [switch] $IncludeDomainControllers
    )
    $gateway = Get-ADComputer -Identity $Config.Gateway.ComputerName
    $nodes = @($Config.Nodes | Where-Object { (Get-WacProp $_ 'KerberosSso' $false) -and $_.Name -ne $Config.Gateway.ComputerName })
    $current = @{}
    $skip = @{}
    foreach ($n in $nodes) {
        $c = Get-ADComputer -Identity $n.Name -Properties PrincipalsAllowedToDelegateToAccount, PrimaryGroupID
        if ($c.PrimaryGroupID -eq 516 -and -not $IncludeDomainControllers) { $skip[$n.Name] = $true; continue }   # 516 = Domain Controllers
        $current[$n.Name] = @($c.PrincipalsAllowedToDelegateToAccount | ForEach-Object { [string]$_ })
    }
    $names = @($nodes | Where-Object { -not $skip.ContainsKey($_.Name) } | ForEach-Object { [string]$_.Name })
    foreach ($s in $skip.Keys) {
        [pscustomobject]@{ Node = $s; Action = 'Skipped'; Current = @(); Desired = @(); Kept = @(); Result = 'Domain controller (use -IncludeDomainControllers)' }
    }
    if (-not $names.Count) { return }
    foreach ($row in (Get-WacDelegationPlan -NodeName $names -GatewayDn ([string]$gateway.DistinguishedName) -Current $current -Remove:$Remove)) {
        $result = 'NoChange'
        if ($row.Action -ne 'NoChange' -and $PSCmdlet.ShouldProcess($row.Node, "$($row.Action) $($gateway.Name) in PrincipalsAllowedToDelegateToAccount (keeps $(@($row.Kept).Count) other)")) {
            if ($row.Action -eq 'Clear') {
                Set-ADComputer -Identity $row.Node -PrincipalsAllowedToDelegateToAccount $null
            }
            else {
                Set-ADComputer -Identity $row.Node -PrincipalsAllowedToDelegateToAccount ([string[]]$row.Desired)
            }
            $result = 'Done'
        }
        elseif ($row.Action -ne 'NoChange') { $result = 'WhatIf' }
        $row | Add-Member -NotePropertyName Result -NotePropertyValue $result -PassThru
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Role-based access control (a JEA endpoint named Microsoft.Sme.PowerShell on each node)
# ---------------------------------------------------------------------------------------------------------------

$script:RbacCollector = {
    param([string] $EndpointName, [string[]] $GroupNames)
    $ep = Get-PSSessionConfiguration -Name $EndpointName -ErrorAction SilentlyContinue
    $groups = foreach ($g in $GroupNames) {
        $exists = [bool](Get-LocalGroup -Name $g -ErrorAction SilentlyContinue)
        $members = @()
        if ($exists) { $members = @(Get-LocalGroupMember -Group $g -ErrorAction SilentlyContinue | ForEach-Object { [string]$_.Name }) }
        [pscustomobject]@{ Name = $g; Exists = $exists; Members = $members }
    }
    [pscustomobject]@{
        ComputerName    = $env:COMPUTERNAME
        EndpointPresent = [bool]$ep
        Groups          = @($groups)
    }
}

function Get-WacRbacCollectorScript { $script:RbacCollector }

function Get-WacRbacStatus {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config, [pscredential] $Credential)
    $targets = @($Config.Nodes | Where-Object { Get-WacProp $_ 'Rbac' $false } | ForEach-Object { [string]$_.Name })
    if (-not $targets.Count) { return }
    $p = @{ ComputerName = $targets; ScriptBlock = $script:RbacCollector; ArgumentList = @($script:RbacEndpoint, [string[]]@($script:RbacGroups.Values)) }
    if ($Credential) { $p.Credential = $Credential }
    Invoke-Command @p | Select-Object -Property * -ExcludeProperty PSComputerName, RunspaceId, PSShowComputerName
}

function Test-WacRbac {
    <# Pure: compares each node's RBAC endpoint and role groups with the config. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [object[]] $Status, [Parameter(Mandatory)] $Config)
    $out = New-Object System.Collections.ArrayList
    $rbacCfg = Get-WacProp $Config 'Rbac'
    foreach ($s in $Status) {
        $node = [string]$s.ComputerName
        if (-not $s.EndpointPresent) {
            [void]$out.Add((New-WacFinding $node High 'RbacNotApplied' "No '$($script:RbacEndpoint)' endpoint: apply role-based access control on this node first."))
            continue
        }
        foreach ($role in $script:RbacGroups.Keys) {
            $gname = $script:RbacGroups[$role]
            $g = @($s.Groups | Where-Object Name -eq $gname) | Select-Object -First 1
            if (-not $g -or -not $g.Exists) { [void]$out.Add((New-WacFinding $node High 'RbacGroupMissing' "Local group '$gname' is missing.")); continue }
            $want = @(Get-WacProp $rbacCfg $role @() | ForEach-Object { ([string]$_).ToUpperInvariant() })
            $have = @($g.Members | ForEach-Object { ([string]$_).ToUpperInvariant() })
            foreach ($m in $want) { if ($have -notcontains $m) { [void]$out.Add((New-WacFinding $node Medium 'RbacMemberMissing' "$m isn't in '$gname'.")) } }
            foreach ($m in $have) { if ($want -notcontains $m) { [void]$out.Add((New-WacFinding $node Medium 'RbacUnexpectedMember' "$m is in '$gname' but not in the config.")) } }
        }
    }
    $out | Sort-Object { $script:Severity[$_.Severity] }, Target, Check
}

function Add-WacRbacMember {
    <# Adds the configured members to the RBAC role groups on each node (after RBAC has been applied there). #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] $Config, [pscredential] $Credential)
    $findings = @(Test-WacRbac -Status @(Get-WacRbacStatus -Config $Config -Credential $Credential) -Config $Config)
    foreach ($f in ($findings | Where-Object Check -eq 'RbacMemberMissing')) {
        if ($f.Message -notmatch "^(?<m>.+) isn't in '(?<g>.+)'\.$") { continue }
        $member = $Matches.m; $group = $Matches.g
        if ($PSCmdlet.ShouldProcess("$($f.Target): $group", "Add $member")) {
            $p = @{ ComputerName = $f.Target; ScriptBlock = { param($g, $m) Add-LocalGroupMember -Group $g -Member $m }; ArgumentList = @($group, $member) }
            if ($Credential) { $p.Credential = $Credential }
            Invoke-Command @p
            [pscustomobject]@{ Node = $f.Target; Group = $group; Member = $member; Result = 'Added' }
        }
    }
}

Export-ModuleMember -Function Read-WacLabConfig, ConvertTo-WacConnectionCsv, Test-WacConnectionCsv, Find-WacPowerShellModule,
Import-WacLabConnection, Get-WacGatewayUrl, Get-WacCollectorScript, Get-WacGatewayFacts, Test-WacGateway, ConvertTo-WacMarkdown,
Get-WacInstallerArgument, Install-WacGateway, Get-WacDelegationPlan, Set-WacKerberosDelegation, Get-WacRbacCollectorScript,
Get-WacRbacStatus, Test-WacRbac, Add-WacRbacMember
