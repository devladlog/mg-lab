Set-StrictMode -Version Latest

# ---------------------------------------------------------------------------------------------------------------
# RdsLab: a read-only health check of a Remote Desktop Services deployment, a deployment PLAN you can read before
# anything changes, and a session report. Windows PowerShell 5.1 and PowerShell 7.
# What Microsoft Learn documents (role names, the 120-day grace period, valid values) is a constant here; OUR
# policy (timeouts, licensing mode, security layer) lives in rds-lab.json.
# ---------------------------------------------------------------------------------------------------------------

$script:Severity = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
$script:EncryptionRank = @{ None = 0; Low = 1; ClientCompatible = 2; High = 3; FipsCompliant = 4 }   # Learn: RDEncryptionLevel
$script:SecurityLayerRank = @{ RDP = 0; Negotiate = 1; SSL = 2 }                                      # Learn: RDSecurityLayer
$script:LicensingModes = @('PerDevice', 'PerUser', 'NotConfigured')                                    # Learn: Set-RDLicenseConfiguration -Mode
$script:RoleBroker = 'RDS-CONNECTION-BROKER'                                                           # Learn: Add-RDServer -Role
$script:RoleSessionHost = 'RDS-RD-SERVER'
$script:RoleWebAccess = 'RDS-WEB-ACCESS'
$script:RoleLicensing = 'RDS-LICENSING'
$script:AllowedCmdlets = @('New-RDSessionDeployment', 'Add-RDServer', 'Set-RDLicenseConfiguration', 'New-RDSessionCollection', 'Set-RDSessionCollectionConfiguration')

function New-RdsFinding {
    param([string] $Target, [string] $Severity, [string] $Check, [string] $Message, [string] $Fix = '')
    [pscustomobject]@{ Severity = $Severity; Target = $Target; Check = $Check; Message = $Message; Fix = $Fix }
}

function Get-RdsProp {
    param($Object, [string] $Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] }; return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    $Default
}

function Read-RdsLabConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    $c = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if ((Get-RdsProp $c 'SchemaVersion') -ne 1) { throw "Unsupported SchemaVersion in '$Path' (expected 1)." }
    foreach ($k in 'Deployment', 'Collection', 'Policy') { if (-not (Get-RdsProp $c $k)) { throw "'$Path' is missing '$k'." } }
    foreach ($k in 'ConnectionBroker', 'WebAccess', 'LicenseServer') {
        if (-not [string](Get-RdsProp $c.Deployment $k '')) { throw "Deployment.$k is required." }
    }
    if (-not @(Get-RdsProp $c.Deployment 'SessionHosts' @()).Count) { throw 'Deployment.SessionHosts needs at least one server.' }
    foreach ($k in 'ConnectionBroker', 'WebAccess', 'LicenseServer') {
        if ([string]$c.Deployment.$k -notmatch '\.') { throw "Deployment.$k must be a fully qualified name (Learn: the RDS cmdlets take FQDNs)." }
    }
    foreach ($h in @($c.Deployment.SessionHosts)) { if ([string]$h -notmatch '\.') { throw "Session host '$h' must be a fully qualified name." } }
    if (-not [string](Get-RdsProp $c.Collection 'Name' '')) { throw 'Collection.Name is required.' }
    $mode = [string](Get-RdsProp $c.Policy 'LicensingMode' 'PerUser')
    if ($script:LicensingModes -notcontains $mode) { throw "Policy.LicensingMode must be one of $($script:LicensingModes -join ', ') (Learn)." }
    $sl = [string](Get-RdsProp $c.Policy 'SecurityLayer' 'SSL')
    if (-not $script:SecurityLayerRank.ContainsKey($sl)) { throw "Policy.SecurityLayer must be one of $($script:SecurityLayerRank.Keys -join ', ') (Learn)." }
    $el = [string](Get-RdsProp $c.Policy 'EncryptionLevel' 'High')
    if (-not $script:EncryptionRank.ContainsKey($el)) { throw "Policy.EncryptionLevel must be one of $($script:EncryptionRank.Keys -join ', ') (Learn)." }
    foreach ($k in 'IdleSessionLimitMin', 'DisconnectedSessionLimitMin', 'ActiveSessionLimitMin') {
        if ([int](Get-RdsProp $c.Policy $k 0) -lt 0) { throw "Policy.$k cannot be negative." }
    }
    $c
}

# ---------------------------------------------------------------------------------------------------------------
# Collectors (read-only; self-contained)
#  - Broker collector: runs ON the connection broker. RemoteDesktop module cmdlets: Get-RDServer, Get-RDLicenseConfiguration,
#    Get-RDCertificate, Get-RDSessionCollection(Configuration), Get-RDUserSession.
#  - Host collector: runs ON each session host (a second hop from the broker would not be delegated).
# Property names that Learn does not list for the RD* output objects are read tolerantly and any miss is reported as a
# CollectorError instead of guessed.
# ---------------------------------------------------------------------------------------------------------------

$script:BrokerCollector = {
    param($Broker, $CollectionName)
    $ErrorActionPreference = 'Stop'
    $errors = New-Object System.Collections.ArrayList
    function P($o, [string[]] $names) { foreach ($n in $names) { $p = $o.PSObject.Properties[$n]; if ($p) { return $p.Value } }; $null }
    Import-Module RemoteDesktop -ErrorAction Stop

    $servers = @()
    try { $servers = @(Get-RDServer -ConnectionBroker $Broker | ForEach-Object { [pscustomobject]@{ Server = [string](P $_ @('Server')); Roles = @((P $_ @('Roles')) | ForEach-Object { [string]$_ }) } }) }
    catch { [void]$errors.Add("Get-RDServer: $($_.Exception.Message)") }

    $lic = [ordered]@{ Mode = $null; LicenseServers = @() }
    try {
        $lc = Get-RDLicenseConfiguration -ConnectionBroker $Broker
        $lic.Mode = [string](P $lc @('Mode'))
        $lic.LicenseServers = @((P $lc @('LicenseServer')) | Where-Object { $_ } | ForEach-Object { [string]$_ })
    }
    catch { [void]$errors.Add("Get-RDLicenseConfiguration: $($_.Exception.Message)") }

    $certs = @()
    try { $certs = @(Get-RDCertificate -ConnectionBroker $Broker | ForEach-Object { [pscustomobject]@{ Role = [string]$_.Role; Level = [string]$_.Level; ExpiresOn = $(if ($_.ExpiresOn) { ([datetime]$_.ExpiresOn).ToString('o') } else { $null }); Subject = [string]$_.Subject } }) }
    catch { [void]$errors.Add("Get-RDCertificate: $($_.Exception.Message)") }

    $col = [ordered]@{ Name = $CollectionName; Exists = $false; UserGroups = @(); Connection = $null; Security = $null }
    try {
        $names = @(Get-RDSessionCollection -ConnectionBroker $Broker -ErrorAction Stop | ForEach-Object { [string](P $_ @('CollectionName')) })
        if ($names -contains $CollectionName) {
            $col.Exists = $true
            $col.UserGroups = @((Get-RDSessionCollectionConfiguration -CollectionName $CollectionName -UserGroup -ConnectionBroker $Broker | ForEach-Object { P $_ @('UserGroup') }) | Where-Object { $_ } | ForEach-Object { [string]$_ })
            $c = Get-RDSessionCollectionConfiguration -CollectionName $CollectionName -Connection -ConnectionBroker $Broker
            $col.Connection = [pscustomobject]@{
                ActiveSessionLimitMin = P $c @('ActiveSessionLimitMin'); DisconnectedSessionLimitMin = P $c @('DisconnectedSessionLimitMin')
                IdleSessionLimitMin = P $c @('IdleSessionLimitMin'); BrokenConnectionAction = [string](P $c @('BrokenConnectionAction'))
                AutomaticReconnectionEnabled = P $c @('AutomaticReconnectionEnabled'); TemporaryFoldersDeletedOnExit = P $c @('TemporaryFoldersDeletedOnExit')
            }
            $s = Get-RDSessionCollectionConfiguration -CollectionName $CollectionName -Security -ConnectionBroker $Broker
            $col.Security = [pscustomobject]@{ AuthenticateUsingNLA = P $s @('AuthenticateUsingNLA'); EncryptionLevel = [string](P $s @('EncryptionLevel')); SecurityLayer = [string](P $s @('SecurityLayer')) }
        }
    }
    catch { [void]$errors.Add("Collection '$CollectionName': $($_.Exception.Message)") }

    $sessions = @()
    try {
        $sessions = @(Get-RDUserSession -ConnectionBroker $Broker | ForEach-Object {
                [pscustomobject]@{ UserName = [string](P $_ @('UserName')); HostServer = [string](P $_ @('HostServer')); CollectionName = [string](P $_ @('CollectionName'))
                    SessionState = [string](P $_ @('SessionState')); UnifiedSessionId = P $_ @('UnifiedSessionId'); DisconnectTime = [string](P $_ @('DisconnectTime')) } })
    }
    catch { [void]$errors.Add("Get-RDUserSession: $($_.Exception.Message)") }

    [pscustomobject]@{ Broker = $Broker; Servers = $servers; License = [pscustomobject]$lic; Certificates = $certs; Collection = [pscustomobject]$col; Sessions = $sessions; Errors = @($errors) }
}

$script:HostCollector = {
    $ErrorActionPreference = 'Stop'
    $errors = New-Object System.Collections.ArrayList
    $it = $null
    try { $it = [string](Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').InstallationType } catch { [void]$errors.Add("InstallationType: $($_.Exception.Message)") }
    $grace = $null; $ltype = $null; $lservers = @()
    try {
        # Learn (RDS Licensing troubleshooting): Win32_TerminalServiceSetting, GetGracePeriodDays, GetSpecifiedLicenseServerList, LicensingType
        $o = Get-WmiObject -Namespace 'root\cimv2\terminalservices' -Class Win32_TerminalServiceSetting -Authentication PacketPrivacy
        $grace = [int]$o.GetGracePeriodDays().DaysLeft
        $ltype = $o.LicensingType
        $lservers = @($o.GetSpecifiedLicenseServerList().SpecifiedLSList | Where-Object { $_ } | ForEach-Object { [string]$_ })
    }
    catch { [void]$errors.Add("Win32_TerminalServiceSetting: $($_.Exception.Message)") }
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    [pscustomobject]@{
        ComputerName = [string]$env:COMPUTERNAME; Fqdn = ([System.Net.Dns]::GetHostEntry('localhost').HostName); Caption = [string]$os.Caption; Build = [int]$os.BuildNumber
        InstallationType = $it; GraceDays = $grace; LicensingType = $ltype; SpecifiedLicenseServers = $lservers; Errors = @($errors)
    }
}

function Get-RdsCollectorScript { $script:BrokerCollector }

function Get-RdsFacts {
    <# Runs the broker collector on the connection broker and the host collector on each session host (WinRM). Read-only. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config, [pscredential] $Credential)
    $broker = [string]$Config.Deployment.ConnectionBroker
    $p = @{ ComputerName = $broker; ScriptBlock = $script:BrokerCollector; ArgumentList = @($broker, [string]$Config.Collection.Name); ErrorAction = 'Stop' }
    if ($Credential) { $p.Credential = $Credential }
    $b = Invoke-Command @p
    $hosts = New-Object System.Collections.ArrayList
    $names = @($Config.Deployment.SessionHosts | ForEach-Object { [string]$_ })
    foreach ($s in @($b.Servers)) { if (@($s.Roles) -contains $script:RoleSessionHost -and $names -notcontains $s.Server) { $names += $s.Server } }
    foreach ($h in $names) {
        $hp = @{ ComputerName = $h; ScriptBlock = $script:HostCollector; ErrorAction = 'Stop' }
        if ($Credential) { $hp.Credential = $Credential }
        try {
            $r = Invoke-Command @hp
            [void]$hosts.Add(($r | Select-Object -Property * -ExcludeProperty PSComputerName, RunspaceId, PSShowComputerName))
        }
        catch { [void]$hosts.Add([pscustomobject]@{ ComputerName = $h; Fqdn = $h; Caption = $null; Build = $null; InstallationType = $null; GraceDays = $null; LicensingType = $null; SpecifiedLicenseServers = @(); Errors = @("Unreachable: $($_.Exception.Message)") }) }
    }
    [pscustomobject]@{
        CapturedAt = (Get-Date).ToUniversalTime().ToString('o'); Broker = $broker
        Servers = @($b.Servers); License = $b.License; Certificates = @($b.Certificates); Collection = $b.Collection
        Sessions = @($b.Sessions); Hosts = @($hosts); Errors = @($b.Errors)
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Rules (pure)
# ---------------------------------------------------------------------------------------------------------------

function Test-RdsDeployment {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [Parameter(Mandatory)] $Config, [datetime] $Now = (Get-Date).ToUniversalTime())
    $out = New-Object System.Collections.ArrayList
    $pol = $Config.Policy
    $n = [string](Get-RdsProp $Facts 'Broker' 'deployment')
    $servers = @(Get-RdsProp $Facts 'Servers' @())
    $hosts = @(Get-RdsProp $Facts 'Hosts' @())
    $lic = Get-RdsProp $Facts 'License'
    $col = Get-RdsProp $Facts 'Collection'
    $certs = @(Get-RdsProp $Facts 'Certificates' @())
    function Add-F { param($Target, $Sev, $Check, $Msg, $Fix = '') [void]$out.Add((New-RdsFinding $Target $Sev $Check $Msg $Fix)) }

    # --- roles in the deployment ----------------------------------------------------------------------------
    function Get-RoleCount([string] $Role) { @($servers | Where-Object { @($_.Roles) -contains $Role }).Count }
    if (-not $servers.Count) {
        Add-F $n High 'NoDeployment' 'Get-RDServer returned no servers: there is no Remote Desktop deployment on this connection broker (yet).' 'InstallDeployment'
    }
    else {
        if (-not (Get-RoleCount $script:RoleBroker)) { Add-F $n High 'NoConnectionBroker' 'No server has the RD Connection Broker role service.' 'InstallDeployment' }
        if (-not (Get-RoleCount $script:RoleSessionHost)) { Add-F $n High 'NoSessionHost' 'No server has the RD Session Host role service: nobody can get a desktop.' 'InstallDeployment' }
        if (-not (Get-RoleCount $script:RoleWebAccess)) { Add-F $n Medium 'NoWebAccess' 'No RD Web Access server: users must start .rdp files or the Remote Desktop client feed by hand.' 'InstallDeployment' }
        if (-not (Get-RoleCount $script:RoleLicensing)) { Add-F $n Medium 'NoLicensingServer' 'No RD Licensing server in the deployment. Learn: there is a 120 day grace period without one; after it clients need an RDS CAL from a license server.' 'AddLicensing' }
        if ((Get-RoleCount $script:RoleBroker) -eq 1) { Add-F $n Info 'SingleBroker' 'One RD Connection Broker: it keeps the session table, so it is a single point of failure for reconnects. Learn lists high availability for the broker as a supported design.' }
        if ((Get-RoleCount $script:RoleSessionHost) -eq 1) { Add-F $n Info 'SingleSessionHost' 'One RD Session Host: no load balancing and every update window is an outage.' }
    }

    # --- Server Core cannot host sessions -------------------------------------------------------------------
    foreach ($h in $hosts) {
        $hn = [string](Get-RdsProp $h 'ComputerName' '?')
        if ([string](Get-RdsProp $h 'InstallationType' '') -eq 'Server Core') {
            Add-F $hn High 'SessionHostOnServerCore' 'This server is Server Core. Learn: the RD Session Host, RD Web Access and RD Gateway role services are not in Server Core (Connection Broker, Licensing and Virtualization Host are). Use Server with Desktop Experience.'
        }
        foreach ($e in @(Get-RdsProp $h 'Errors' @())) { Add-F $hn Info 'CollectorError' ([string]$e) }
    }

    # --- licensing -------------------------------------------------------------------------------------------
    $mode = [string](Get-RdsProp $lic 'Mode' '')
    $licServers = @(Get-RdsProp $lic 'LicenseServers' @())
    $wantMode = [string](Get-RdsProp $pol 'LicensingMode' 'PerUser')
    $warnDays = [int](Get-RdsProp $pol 'GraceWarnDays' 30)
    foreach ($h in $hosts) {
        $hn = [string](Get-RdsProp $h 'ComputerName' '?')
        $g = Get-RdsProp $h 'GraceDays'
        if ($null -eq $g) { continue }
        if (-not $licServers.Count) {
            if ([int]$g -le 0) { Add-F $hn High 'GracePeriodOver' 'The licensing grace period is over (GetGracePeriodDays returned 0) and no license server is configured. Learn: clients now need an RDS CAL from a license server to sign in.' 'LicenseConfig' }
            elseif ([int]$g -le $warnDays) { Add-F $hn Medium 'GracePeriodEnding' "$g day(s) left of the licensing grace period (Learn: 120 days) and no license server is configured." 'LicenseConfig' }
            else { Add-F $hn Info 'OnGracePeriod' "Running on the licensing grace period: $g day(s) left (Learn: 120 days, no license server needed until it ends)." }
        }
    }
    if ($servers.Count) {
        if ($licServers.Count -and ($mode -eq 'NotConfigured' -or -not $mode)) {
            Add-F $n Medium 'LicensingModeNotSet' "A license server is configured ($($licServers -join ', ')) but the licensing mode is '$mode'. Learn: set Per User or Per Device; the mode must match the RDS CALs you own." 'LicenseConfig'
        }
        elseif ($mode -and $mode -ne 'NotConfigured' -and $mode -ne $wantMode) {
            Add-F $n Low 'LicensingModeDiffers' "Licensing mode is $mode, policy says $wantMode. Per User CALs are not enforced by the server (Learn): you must count them; Per Device CALs cannot be over-allocated." 'LicenseConfig'
        }
        if ($mode -eq 'NotConfigured' -and -not $licServers.Count) { Add-F $n Info 'NoLicensingConfigured' 'Neither a license server nor a mode is set: expect the "licensing mode is not configured" balloon in sessions (Learn).' }
    }

    # --- certificates ----------------------------------------------------------------------------------------
    $minDays = [int](Get-RdsProp $pol 'CertMinDays' 30)
    foreach ($c in $certs) {
        $role = [string](Get-RdsProp $c 'Role' '?')
        $level = [string](Get-RdsProp $c 'Level' '')
        if ($level -match 'Not ?Configured') { Add-F $role High 'CertNotConfigured' "The $role role service has no valid certificate (Get-RDCertificate level: Not Configured)." 'Certificate' }
        elseif ($level -eq 'Untrusted' -and [bool](Get-RdsProp $pol 'RequireTrustedCertificates' $true)) {
            Add-F $role Medium 'CertSelfSigned' "The $role certificate is self-signed (Learn: level Untrusted). Clients show a warning, and people learn to click through it. Replace it with an enterprise or public certificate (Set-RDCertificate)." 'Certificate'
        }
        $exp = Get-RdsProp $c 'ExpiresOn'
        if ($exp) {
            $left = ([datetime]$exp).ToUniversalTime() - $Now.ToUniversalTime()
            if ($left.TotalDays -lt 0) { Add-F $role High 'CertExpired' "The $role certificate expired on $(([datetime]$exp).ToString('yyyy-MM-dd'))." 'Certificate' }
            elseif ($left.TotalDays -lt $minDays) { Add-F $role Medium 'CertExpiring' "The $role certificate expires in $([int]$left.TotalDays) day(s) (policy: at least $minDays)." 'Certificate' }
        }
    }

    # --- collection ------------------------------------------------------------------------------------------
    $cn = [string]$Config.Collection.Name
    if ($servers.Count) {
        if (-not $col -or -not (Get-RdsProp $col 'Exists' $false)) {
            Add-F $cn High 'NoCollection' "Session collection '$cn' does not exist: sessions have nowhere to land." 'NewCollection'
        }
        else {
            $groups = @(Get-RdsProp $col 'UserGroups' @())
            if (-not $groups.Count) { Add-F $cn High 'CollectionNoUsers' 'The collection has no user groups: nobody is allowed to connect.' 'CollectionConfig' }
            foreach ($g in $groups) {
                if ($g -match '(^|\\)(Domain Users|Everyone|Authenticated Users)$') { Add-F $cn Medium 'CollectionOpenToEveryone' "User group '$g' lets every domain account log on to the session host. Use a dedicated group." 'CollectionConfig' }
            }
            $conn = Get-RdsProp $col 'Connection'
            $sec = Get-RdsProp $col 'Security'
            if ($null -eq $conn -or $null -eq $sec) { Add-F $cn Info 'CollectionSettingsUnreadable' 'Connection or security settings could not be read (see CollectorError).' }
            else {
                $nla = Get-RdsProp $sec 'AuthenticateUsingNLA'
                if ($false -eq $nla -and [bool](Get-RdsProp $pol 'RequireNla' $true)) { Add-F $cn High 'NlaOff' 'Network Level Authentication is off: the logon screen is offered to anyone who can reach port 3389 before they authenticate.' 'CollectionConfig' }
                $sl = [string](Get-RdsProp $sec 'SecurityLayer' '')
                $wantSl = [string](Get-RdsProp $pol 'SecurityLayer' 'SSL')
                if ($sl -and $script:SecurityLayerRank.ContainsKey($sl) -and $script:SecurityLayerRank[$sl] -lt $script:SecurityLayerRank[$wantSl]) {
                    $sev = if ($sl -eq 'RDP') { 'High' } else { 'Low' }
                    Add-F $cn $sev 'SecurityLayerBelowPolicy' "Security layer is $sl, policy wants $wantSl (Learn: RDP, Negotiate, SSL; the default is Negotiate)." 'CollectionConfig'
                }
                $el = [string](Get-RdsProp $sec 'EncryptionLevel' '')
                $wantEl = [string](Get-RdsProp $pol 'EncryptionLevel' 'High')
                if ($el -and $script:EncryptionRank.ContainsKey($el) -and $script:EncryptionRank[$el] -lt $script:EncryptionRank[$wantEl]) {
                    $sev = if ($script:EncryptionRank[$el] -le 1) { 'High' } else { 'Low' }
                    Add-F $cn $sev 'EncryptionBelowPolicy' "Encryption level is $el, policy wants $wantEl (Learn: Low, ClientCompatible (default), High, FipsCompliant)." 'CollectionConfig'
                }
                $idle = Get-RdsProp $conn 'IdleSessionLimitMin'
                $disc = Get-RdsProp $conn 'DisconnectedSessionLimitMin'
                if ($null -ne $idle -and [int]$idle -eq 0 -and [int](Get-RdsProp $pol 'IdleSessionLimitMin' 0) -gt 0) { Add-F $cn Medium 'NoIdleLimit' "No idle session limit (0). Policy: $($pol.IdleSessionLimitMin) minutes. Idle sessions keep memory and licences busy. (0 is read as no limit; confirm in the lab.)" 'CollectionConfig' }
                elseif ($null -ne $idle -and [int]$idle -gt [int](Get-RdsProp $pol 'IdleSessionLimitMin' 0) -and [int](Get-RdsProp $pol 'IdleSessionLimitMin' 0) -gt 0) { Add-F $cn Low 'IdleLimitHigh' "Idle session limit is $idle minutes, policy $($pol.IdleSessionLimitMin)." 'CollectionConfig' }
                if ($null -ne $disc -and [int]$disc -eq 0 -and [int](Get-RdsProp $pol 'DisconnectedSessionLimitMin' 0) -gt 0) { Add-F $cn Medium 'NoDisconnectLimit' "Disconnected sessions are kept forever (0). Policy: end them after $($pol.DisconnectedSessionLimitMin) minutes. Closed laptops leave running sessions behind." 'CollectionConfig' }
                elseif ($null -ne $disc -and [int]$disc -gt [int](Get-RdsProp $pol 'DisconnectedSessionLimitMin' 0) -and [int](Get-RdsProp $pol 'DisconnectedSessionLimitMin' 0) -gt 0) { Add-F $cn Low 'DisconnectLimitHigh' "Disconnected session limit is $disc minutes, policy $($pol.DisconnectedSessionLimitMin)." 'CollectionConfig' }
                if ($false -eq (Get-RdsProp $conn 'TemporaryFoldersDeletedOnExit') -and [bool](Get-RdsProp $pol 'TemporaryFoldersDeletedOnExit' $true)) { Add-F $cn Low 'TempFoldersKept' 'Temporary folders are kept after logoff.' 'CollectionConfig' }
                if ($false -eq (Get-RdsProp $conn 'AutomaticReconnectionEnabled') -and [bool](Get-RdsProp $pol 'AutomaticReconnectionEnabled' $true)) { Add-F $cn Low 'NoAutoReconnect' 'Automatic reconnection is off: a network blip ends the user''s work session view.' 'CollectionConfig' }
            }
        }
    }
    foreach ($e in @(Get-RdsProp $Facts 'Errors' @())) { Add-F $n Info 'CollectorError' ([string]$e) }
    @($out | Sort-Object { $script:Severity[$_.Severity] }, Target, Check)
}

function Get-RdsSessionSummary {
    <# Pure. Counts per host and state from the Get-RDUserSession rows. State text is matched loosely (ACTIVE / DISCONNECT). #>
    [CmdletBinding()]
    param([object[]] $Sessions = @())
    $rows = @($Sessions | Group-Object { [string](Get-RdsProp $_ 'HostServer' '?') } | ForEach-Object {
            $g = @($_.Group)
            $act = @($g | Where-Object { [string](Get-RdsProp $_ 'SessionState' '') -match 'ACTIVE' }).Count
            $dis = @($g | Where-Object { [string](Get-RdsProp $_ 'SessionState' '') -match 'DISCONNECT' }).Count
            [pscustomobject]@{ HostServer = $_.Name; Total = $g.Count; Active = $act; Disconnected = $dis; Other = ($g.Count - $act - $dis); Users = (@($g | ForEach-Object { [string](Get-RdsProp $_ 'UserName' '?') } | Sort-Object -Unique) -join ', ') }
        })
    $rows
}

function ConvertTo-RdsMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [object[]] $Findings = @())
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('# Remote Desktop Services check')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine("Connection broker: ``$([string](Get-RdsProp $Facts 'Broker' '?'))``")
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('## Servers and role services')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('| Server | Role services |')
    [void]$sb.AppendLine('|---|---|')
    foreach ($s in @(Get-RdsProp $Facts 'Servers' @())) { [void]$sb.AppendLine(('| {0} | {1} |' -f $s.Server, (@($s.Roles) -join ', '))) }
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('## Session hosts')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('| Host | OS | Installation | Grace days left |')
    [void]$sb.AppendLine('|---|---|---|---|')
    foreach ($h in @(Get-RdsProp $Facts 'Hosts' @())) {
        $g = Get-RdsProp $h 'GraceDays'
        [void]$sb.AppendLine(('| {0} | {1} | {2} | {3} |' -f $h.ComputerName, (Get-RdsProp $h 'Caption' '?'), (Get-RdsProp $h 'InstallationType' '?'), $(if ($null -eq $g) { '?' } else { $g })))
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
    $sum = @(Get-RdsSessionSummary -Sessions @(Get-RdsProp $Facts 'Sessions' @()))
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('## Sessions')
    [void]$sb.AppendLine()
    if (-not $sum.Count) { [void]$sb.AppendLine('No user sessions.') }
    else {
        [void]$sb.AppendLine('| Host | Total | Active | Disconnected | Users |')
        [void]$sb.AppendLine('|---|---|---|---|---|')
        foreach ($r in $sum) { [void]$sb.AppendLine(('| {0} | {1} | {2} | {3} | {4} |' -f $r.HostServer, $r.Total, $r.Active, $r.Disconnected, $r.Users)) }
    }
    $sb.ToString()
}

# ---------------------------------------------------------------------------------------------------------------
# Plan, then apply
# ---------------------------------------------------------------------------------------------------------------

function Get-RdsDeploymentPlan {
    <#
    .SYNOPSIS
    Pure. The steps that bring the deployment to rds-lab.json, from the facts (or from nothing, with -Facts $null).
    Only differences become steps, and each carries the value it found (Before). New-RDSessionDeployment is marked Disruptive:
    it installs role services and is only applied with -AllowDeployment. Certificates are a Manual step: we never pick one.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config, $Facts = $null)
    $d = $Config.Deployment; $pol = $Config.Policy; $cn = [string]$Config.Collection.Name
    $broker = [string]$d.ConnectionBroker
    $servers = @(Get-RdsProp $Facts 'Servers' @())
    $has = { param($role) @($servers | Where-Object { @($_.Roles) -contains $role }).Count -gt 0 }
    $steps = New-Object System.Collections.ArrayList
    function Add-S { param($Id, $Cmdlet, $Params, $Why, $Before = $null, [bool] $Disruptive = $false) [void]$steps.Add([pscustomobject]@{ Order = $steps.Count + 1; Id = $Id; Cmdlet = $Cmdlet; Parameters = $Params; Before = $Before; Disruptive = $Disruptive; Why = $Why }) }

    if (-not (& $has $script:RoleBroker)) {
        Add-S 'InstallDeployment' 'New-RDSessionDeployment' ([ordered]@{ ConnectionBroker = $broker; WebAccessServer = [string]$d.WebAccess; SessionHost = @($d.SessionHosts | ForEach-Object { [string]$_ }) }) 'Installs the RD Connection Broker, RD Web Access and RD Session Host role services (Learn). Roles are installed on the servers: plan a maintenance window.' $null $true
    }
    if (-not (& $has $script:RoleLicensing)) {
        Add-S 'AddLicensing' 'Add-RDServer' ([ordered]@{ Server = [string]$d.LicenseServer; Role = $script:RoleLicensing; ConnectionBroker = $broker }) 'Adds the RD Licensing role service to the deployment (Learn: Add-RDServer -Role RDS-LICENSING).'
    }
    $lic = Get-RdsProp $Facts 'License'
    $mode = [string](Get-RdsProp $lic 'Mode' '')
    $ls = @(Get-RdsProp $lic 'LicenseServers' @())
    $wantMode = [string](Get-RdsProp $pol 'LicensingMode' 'PerUser')
    $wantLs = [string]$d.LicenseServer
    if ($mode -ne $wantMode -or ($ls -notcontains $wantLs)) {
        Add-S 'LicenseConfig' 'Set-RDLicenseConfiguration' ([ordered]@{ LicenseServer = @($wantLs); Mode = $wantMode; ConnectionBroker = $broker; Force = $true }) "Point the deployment at the license server and set the licensing mode ($wantMode). The mode does not buy a licence: RDS CALs are installed on the license server separately (Learn)." ([ordered]@{ Mode = $mode; LicenseServer = ($ls -join ',') })
    }
    $col = Get-RdsProp $Facts 'Collection'
    $exists = [bool](Get-RdsProp $col 'Exists' $false)
    if (-not $exists) {
        Add-S 'NewCollection' 'New-RDSessionCollection' ([ordered]@{ CollectionName = $cn; SessionHost = @($d.SessionHosts | ForEach-Object { [string]$_ }); CollectionDescription = [string](Get-RdsProp $Config.Collection 'Description' ''); ConnectionBroker = $broker }) 'Creates the session collection on the session host(s).'
    }
    $conn = Get-RdsProp $col 'Connection'
    $sec = Get-RdsProp $col 'Security'
    $want = [ordered]@{}; $before = [ordered]@{}
    $chk = {
        param($key, $wantVal, $haveVal)
        if ($null -eq $haveVal -or [string]$haveVal -ne [string]$wantVal) { $want[$key] = $wantVal; $before[$key] = $haveVal }
    }
    & $chk 'AuthenticateUsingNLA' ([bool](Get-RdsProp $pol 'RequireNla' $true)) (Get-RdsProp $sec 'AuthenticateUsingNLA')
    & $chk 'SecurityLayer' ([string]$pol.SecurityLayer) (Get-RdsProp $sec 'SecurityLayer')
    & $chk 'EncryptionLevel' ([string]$pol.EncryptionLevel) (Get-RdsProp $sec 'EncryptionLevel')
    & $chk 'IdleSessionLimitMin' ([int]$pol.IdleSessionLimitMin) (Get-RdsProp $conn 'IdleSessionLimitMin')
    & $chk 'DisconnectedSessionLimitMin' ([int]$pol.DisconnectedSessionLimitMin) (Get-RdsProp $conn 'DisconnectedSessionLimitMin')
    & $chk 'ActiveSessionLimitMin' ([int]$pol.ActiveSessionLimitMin) (Get-RdsProp $conn 'ActiveSessionLimitMin')
    & $chk 'AutomaticReconnectionEnabled' ([bool]$pol.AutomaticReconnectionEnabled) (Get-RdsProp $conn 'AutomaticReconnectionEnabled')
    & $chk 'TemporaryFoldersDeletedOnExit' ([bool]$pol.TemporaryFoldersDeletedOnExit) (Get-RdsProp $conn 'TemporaryFoldersDeletedOnExit')
    $have = @(Get-RdsProp $col 'UserGroups' @())
    $wantGroups = @($Config.Collection.UserGroup | ForEach-Object { [string]$_ })
    if ($wantGroups.Count -and (@($wantGroups | Where-Object { $have -notcontains $_ }).Count -or @($have | Where-Object { $_ -match '(^|\\)(Domain Users|Everyone|Authenticated Users)$' }).Count)) {
        $want['UserGroup'] = $wantGroups; $before['UserGroup'] = ($have -join ',')
    }
    if ($want.Count) {
        $p = [ordered]@{ CollectionName = $cn; ConnectionBroker = $broker }
        foreach ($k in $want.Keys) { $p[$k] = $want[$k] }
        Add-S 'CollectionConfig' 'Set-RDSessionCollectionConfiguration' $p ('Set ' + ($want.Keys -join ', ') + ' on the collection (our policy, rds-lab.json).') $before
    }
    $badCerts = @(Get-RdsProp $Facts 'Certificates' @() | Where-Object { [string]$_.Level -ne 'Trusted' })
    if ($badCerts.Count) {
        Add-S 'Certificate' 'Set-RDCertificate' ([ordered]@{ Role = (@($badCerts | ForEach-Object { [string]$_.Role }) -join ','); Thumbprint = '<your trusted certificate>' }) 'Manual: Set-RDCertificate -Role <role> -Thumbprint <thumbprint> per role (RDGateway, RDWebAccess, RDRedirector, RDPublishing). The script never chooses a certificate for you.'
        $steps[$steps.Count - 1] | Add-Member -NotePropertyName Manual -NotePropertyValue $true
    }
    $steps
}

function Invoke-RdsDeploymentPlan {
    <# Applies Get-RdsDeploymentPlan one step at a time. Only the five allow-listed RD cmdlets can run. The disruptive step needs -AllowDeployment. -WhatIf shows each step. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)] [object[]] $Plan, [switch] $AllowDeployment)
    foreach ($s in $Plan) {
        if (Get-RdsProp $s 'Manual' $false) { Write-Warning "$($s.Id): manual step. $($s.Why)"; continue }
        if ($script:AllowedCmdlets -notcontains [string]$s.Cmdlet) { throw "Step '$($s.Id)' names '$($s.Cmdlet)', which is not an allowed cmdlet." }
        if ($s.Disruptive -and -not $AllowDeployment) { Write-Warning "Skipping $($s.Id) ($($s.Cmdlet)): it installs role services. Re-run with -AllowDeployment."; continue }
        $p = @{}
        foreach ($k in $s.Parameters.Keys) { $p[$k] = $s.Parameters[$k] }
        if (-not $PSCmdlet.ShouldProcess("$($s.Id): $($s.Cmdlet)", $s.Why)) { continue }
        & $s.Cmdlet @p | Out-Null
        [pscustomobject]@{ Step = $s.Id; Cmdlet = $s.Cmdlet; Result = 'Applied' }
    }
}

function Invoke-RdsDisconnectedLogoff {
    <# Logs off DISCONNECTED sessions of the users matching -UserName (a -like pattern, mandatory on purpose). Invoke-RDUserLogoff closes the user's applications (Learn). -WhatIf first. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)] [string] $UserName, [string] $ConnectionBroker, [string] $CollectionName)
    $a = @{}
    if ($ConnectionBroker) { $a.ConnectionBroker = $ConnectionBroker }
    if ($CollectionName) { $a.CollectionName = $CollectionName }
    foreach ($s in @(Get-RDUserSession @a)) {
        if ([string]$s.SessionState -notmatch 'DISCONNECT') { continue }
        if ([string]$s.UserName -notlike $UserName) { continue }
        if ($PSCmdlet.ShouldProcess("$($s.UserName) on $($s.HostServer) (session $($s.UnifiedSessionId))", 'Log off the disconnected session')) {
            Invoke-RDUserLogoff -HostServer ([string]$s.HostServer) -UnifiedSessionID ([int]$s.UnifiedSessionId) -Force
            [pscustomobject]@{ UserName = [string]$s.UserName; HostServer = [string]$s.HostServer; SessionId = [int]$s.UnifiedSessionId; Result = 'LoggedOff' }
        }
    }
}

Export-ModuleMember -Function Read-RdsLabConfig, Get-RdsCollectorScript, Get-RdsFacts, Test-RdsDeployment, Get-RdsSessionSummary,
    ConvertTo-RdsMarkdown, Get-RdsDeploymentPlan, Invoke-RdsDeploymentPlan, Invoke-RdsDisconnectedLogoff
