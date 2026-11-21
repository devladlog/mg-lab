<#
    GatewayOps: what to check and automate around an on-premises data gateway (standard mode).

    REST functions call Invoke-PowerBIRestMethod (module MicrosoftPowerBIMgmt, after Connect-PowerBIServiceAccount); the URL is
    relative to https://api.powerbi.com/v1.0/myorg. The tests mock that cmdlet with responses shaped like Learn's samples.
    Findings are objects { Rule, Severity, Message }:
      GW001 error    a data source in the query has no gateway data source with exactly the same server and database
      GW002 info     a data source is not a text literal in the query (a parameter), so it can't be checked from the file
      GW003 info     the query and a gateway data source match
#>
Set-StrictMode -Version 3.0

function New-Finding([string] $Rule, [string] $Severity, [string] $Message, [string] $Source = '') {
    [pscustomobject]@{ Rule = $Rule; Severity = $Severity; Source = $Source; Message = $Message }
}

# ---------------------------------------------------------------- network

# Outbound ports from Learn "Adjust communication settings for the on-premises data gateway". The gateway needs no inbound ports.
$script:RequiredOutboundPorts = '80, 443, 1433, 5671, 5672 and 9350-9354'

function Get-GatewayEndpoint {
<#
.SYNOPSIS
    The endpoints of the Learn table that have a fixed host name, so they can be tested with a TCP connection.
.DESCRIPTION
    Wildcard entries (*.servicebus.windows.net on 5671-5672, 443 and 9350-9354, *.analysis.windows.net, *.download.microsoft.com ...)
    have no host name to test: Learn says to use the gateway app's Diagnostics > Network ports test, which gets the list from Azure Relay.
    api.powerbi.com stands for *.powerbi.com.
#>
    [CmdletBinding()] param()
    @(
        [pscustomobject]@{ Host = 'login.microsoftonline.com';   Port = 443; Purpose = 'Microsoft Entra ID sign in' }
        [pscustomobject]@{ Host = 'login.live.com';              Port = 443; Purpose = 'Microsoft Entra ID sign in' }
        [pscustomobject]@{ Host = 'aadcdn.msauth.net';           Port = 443; Purpose = 'Microsoft Entra ID sign in' }
        [pscustomobject]@{ Host = 'api.powerbi.com';             Port = 443; Purpose = 'Power BI cluster discovery (*.powerbi.com)' }
        [pscustomobject]@{ Host = 'ecs.office.com';              Port = 443; Purpose = 'ECS configuration for Mashup features' }
        [pscustomobject]@{ Host = 'gatewayadminportal.azure.com'; Port = 443; Purpose = 'Gateway management in the portal' }
    )
}

function Test-TcpPort {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Hostname, [Parameter(Mandatory)][int] $Port, [int] $TimeoutMs = 3000)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($Hostname, $Port)
        if (-not $task.Wait($TimeoutMs)) { return [pscustomobject]@{ Reachable = $false; Error = "timeout after $TimeoutMs ms" } }
        [pscustomobject]@{ Reachable = $client.Connected; Error = $null }
    }
    catch {
        $e = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
        [pscustomobject]@{ Reachable = $false; Error = $e }
    }
    finally { $client.Dispose() }
}

function Test-GatewayNetwork {
<#
.SYNOPSIS
    Run on the gateway machine: can it open outbound TCP to the fixed-name endpoints, and to the data sources it will read?
.PARAMETER DataSource
    'host:port' strings (for example 10.50.0.30:1433). The gateway must reach the sources too.
.PARAMETER Connector
    Replaces the real TCP test (tests only): { param($Hostname, $Port, $TimeoutMs) } returning an object with Reachable and Error.
.OUTPUTS
    One object per endpoint: Host, Port, Kind (Cloud or DataSource), Reachable, Ms, Error. The caller decides on the exit code.
#>
    [CmdletBinding()]
    param(
        [string[]] $DataSource = @(),
        [int] $TimeoutMs = 3000,
        [scriptblock] $Connector
    )
    $targets = foreach ($e in Get-GatewayEndpoint) { [pscustomobject]@{ Host = $e.Host; Port = $e.Port; Kind = 'Cloud' } }
    $targets = @($targets) + @(foreach ($d in $DataSource) {
        if ($d -notmatch '^(?<h>[^:\s]+):(?<p>\d{1,5})$') { throw "DataSource '$d' must be host:port" }
        [pscustomobject]@{ Host = $Matches.h; Port = [int]$Matches.p; Kind = 'DataSource' }
    })
    foreach ($t in $targets) {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $r = if ($Connector) { & $Connector $t.Host $t.Port $TimeoutMs } else { Test-TcpPort -Hostname $t.Host -Port $t.Port -TimeoutMs $TimeoutMs }
        $sw.Stop()
        [pscustomobject]@{ Host = $t.Host; Port = $t.Port; Kind = $t.Kind; Reachable = [bool]$r.Reachable; Ms = [int]$sw.ElapsedMilliseconds; Error = (Get-Prop $r 'Error') }
    }
}

# ---------------------------------------------------------------- REST

function Invoke-GatewayApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Get', 'Post')][string] $Method,
        [Parameter(Mandatory)][string] $Url,
        $Body
    )
    $params = @{ Method = $Method; Url = $Url }
    if ($null -ne $Body) { $params.Body = if ($Body -is [string]) { $Body } else { $Body | ConvertTo-Json -Depth 6 -Compress } }
    $json = Invoke-PowerBIRestMethod @params
    if ([string]::IsNullOrWhiteSpace($json)) { return $null }
    $json | ConvertFrom-Json
}

function Get-Prop($Object, [string] $Name) {
    if ($null -ne $Object -and $Object.PSObject.Properties[$Name]) { $Object.$Name } else { $null }
}

function Get-GatewayCluster {
<#
.SYNOPSIS
    Gateways - Get Gateways: the gateways the caller is an admin of. For a cluster the id is the primary gateway's.
#>
    [CmdletBinding()] param([string] $Name)
    $r = Invoke-GatewayApi -Method Get -Url 'gateways'
    foreach ($g in @($r.value)) {
        if ($Name -and $g.name -ne $Name) { continue }
        [pscustomobject]@{ Id = $g.id; Name = $g.name; Type = $g.type; Status = Get-Prop $g 'gatewayStatus'; PublicKey = $g.publicKey }
    }
}

function Get-GatewayDataSource {
<#
.SYNOPSIS
    The data sources defined on a gateway (connectionDetails is a JSON string: server and database are parsed out of it).
#>
    [CmdletBinding()] param([Parameter(Mandatory)][string] $GatewayId)
    $r = Invoke-GatewayApi -Method Get -Url "gateways/$GatewayId/datasources"
    foreach ($d in @($r.value)) {
        $conn = $null
        try { $conn = $d.connectionDetails | ConvertFrom-Json -ErrorAction Stop } catch { $conn = $null }
        [pscustomobject]@{
            Id             = $d.id
            Name           = Get-Prop $d 'datasourceName'
            Type           = Get-Prop $d 'datasourceType'
            Server         = Get-Prop $conn 'server'
            Database       = Get-Prop $conn 'database'
            CredentialType = Get-Prop $d 'credentialType'
        }
    }
}

# ---------------------------------------------------------------- the link between a query and a gateway data source

function Get-MSqlSource {
<#
.SYNOPSIS
    The Sql.Database(...) calls of an M query. Text literals give Server and Database; anything else is Literal = $false.
#>
    [CmdletBinding()] param([Parameter(Mandatory)][string] $Text)
    $unquote = { param($s) $s.Replace('""', '"') }
    $literal = [regex]::new('Sql\.Database\s*\(\s*"(?<s>(?:[^"]|"")*)"\s*,\s*"(?<d>(?:[^"]|"")*)"')
    $any = [regex]::new('Sql\.Database\s*\(')
    $found = @($literal.Matches($Text))
    foreach ($m in $found) {
        [pscustomobject]@{ Literal = $true; Server = (& $unquote $m.Groups['s'].Value); Database = (& $unquote $m.Groups['d'].Value) }
    }
    $others = $any.Matches($Text).Count - $found.Count
    for ($i = 0; $i -lt $others; $i++) { [pscustomobject]@{ Literal = $false; Server = $null; Database = $null } }
}

function Test-DataSourceMatch {
<#
.SYNOPSIS
    Does every SQL Server source in the query have a gateway data source with exactly the same server and database?
.DESCRIPTION
    Learn ("Manage a SQL Server data source"): the link between the semantic model and the gateway data source is the server name and the
    database name; they must match exactly, matching is case-sensitive, an IP address in Desktop needs the IP address on the gateway.
    Returns findings: GW001 (error), GW002 (info), GW003 (info, a match).
.PARAMETER GatewayDataSource
    Objects with Type, Server, Database (Get-GatewayDataSource), or a JSON file shaped like src/gateway/datasource.json via -Definition.
#>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $QueryPath,
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]] $GatewayDataSource
    )
    $sql = @($GatewayDataSource | Where-Object { $_.Type -in 'Sql', 'SQL' })
    foreach ($s in @(Get-MSqlSource -Text (Get-Content -Raw -LiteralPath $QueryPath))) {
        if (-not $s.Literal) {
            New-Finding 'GW002' 'Info' 'Sql.Database is called with a parameter or an expression: the server and database can only be checked in the service.' $QueryPath
            continue
        }
        $label = "$($s.Server) / $($s.Database)"
        if ($sql | Where-Object { $_.Server -ceq $s.Server -and $_.Database -ceq $s.Database }) {
            New-Finding 'GW003' 'Info' "$label matches a gateway data source." $QueryPath
            continue
        }
        $hint = if ($sql | Where-Object { $_.Server -ieq $s.Server -and $_.Database -ieq $s.Database }) {
            'A data source exists that differs only in letter case: matching is case-sensitive.'
        } elseif ($sql | Where-Object { $_.Database -ceq $s.Database }) {
            ('A data source for this database exists with another server text ({0}): the server must be written the same way (an IP address in Desktop needs the IP address on the gateway).' -f (($sql | Where-Object { $_.Database -ceq $s.Database } | ForEach-Object Server) -join ', '))
        } else {
            'No SQL Server data source on this gateway for this server and database.'
        }
        New-Finding 'GW001' 'Error' "${label}: no gateway data source with exactly this server and database. $hint" $QueryPath
    }
}

# ---------------------------------------------------------------- create the data source, with encrypted credentials

function New-GatewayDataSourceRequest {
<#
.SYNOPSIS
    The JSON body of Gateways - Create Datasource, with the credentials encrypted for this gateway by tools gateway-credential
    (Microsoft's AsymmetricKeyEncryptor from the Power BI .NET SDK). The password goes to the tool in an environment variable of the child process only.
#>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object] $Gateway,
        [Parameter(Mandatory)][string] $Name,
        [Parameter(Mandatory)][string] $Server,
        [Parameter(Mandatory)][string] $Database,
        [Parameter(Mandatory)][string] $Username,
        [Parameter(Mandatory)][securestring] $Password,
        [ValidateSet('Organizational', 'Private', 'Public', 'None')][string] $PrivacyLevel = 'Organizational',
        [Parameter(Mandatory)][string] $ToolPath
    )
    if (-not $Gateway.PublicKey) { throw 'The gateway has no public key in the response: cannot encrypt credentials.' }
    if (-not (Test-Path -LiteralPath $ToolPath)) { throw "gateway-credential not found at $ToolPath (dotnet build src/GatewayCredential)." }
    $keyFile = Join-Path ([System.IO.Path]::GetTempPath()) ('gwkey-' + [guid]::NewGuid().ToString('N') + '.json')
    $previous = $env:GATEWAY_DS_PASSWORD
    try {
        $Gateway.PublicKey | ConvertTo-Json -Compress | Set-Content -LiteralPath $keyFile -Encoding utf8 -WhatIf:$false
        $env:GATEWAY_DS_PASSWORD = ConvertFrom-SecureString -SecureString $Password -AsPlainText
        $out = & dotnet $ToolPath --public-key-file $keyFile --server $Server --database $Database --name $Name --username $Username --privacy $PrivacyLevel 2>&1
        if ($LASTEXITCODE -ne 0) { throw "gateway-credential failed: $($out -join ' ')" }
        ($out -join "`n")
    }
    finally {
        $env:GATEWAY_DS_PASSWORD = $previous
        Remove-Item -LiteralPath $keyFile -Force -ErrorAction SilentlyContinue -WhatIf:$false
    }
}

function New-GatewayDataSource {
<#
.SYNOPSIS
    Creates a SQL Server data source on the named gateway (needs gateway admin permission). -WhatIf sends nothing.
#>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string] $GatewayName,
        [Parameter(Mandatory)][string] $Name,
        [Parameter(Mandatory)][string] $Server,
        [Parameter(Mandatory)][string] $Database,
        [Parameter(Mandatory)][string] $Username,
        [Parameter(Mandatory)][securestring] $Password,
        [ValidateSet('Organizational', 'Private', 'Public', 'None')][string] $PrivacyLevel = 'Organizational',
        [Parameter(Mandatory)][string] $ToolPath
    )
    $gw = @(Get-GatewayCluster -Name $GatewayName)
    if ($gw.Count -ne 1) { throw "Expected one gateway named '$GatewayName', found $($gw.Count)." }
    $body = New-GatewayDataSourceRequest -Gateway $gw[0] -Name $Name -Server $Server -Database $Database -Username $Username `
        -Password $Password -PrivacyLevel $PrivacyLevel -ToolPath $ToolPath
    if ($PSCmdlet.ShouldProcess("gateway '$GatewayName'", "Create data source '$Name' ($Server / $Database)")) {
        Invoke-GatewayApi -Method Post -Url "gateways/$($gw[0].Id)/datasources" -Body $body
    }
    else { Write-Verbose $body }
}

# ---------------------------------------------------------------- the semantic model side

function Get-DatasetGatewayInfo {
<#
.SYNOPSIS
    Datasets - Get Datasources In Group: each data source of the model, and the gateway it is bound to (empty when it isn't).
#>
    [CmdletBinding()] param([Parameter(Mandatory)][string] $WorkspaceId, [Parameter(Mandatory)][string] $DatasetId)
    $r = Invoke-GatewayApi -Method Get -Url "groups/$WorkspaceId/datasets/$DatasetId/datasources"
    foreach ($d in @($r.value)) {
        $gw = Get-Prop $d 'gatewayId'
        [pscustomobject]@{
            Type         = $d.datasourceType
            Server       = Get-Prop $d.connectionDetails 'server'
            Database     = Get-Prop $d.connectionDetails 'database'
            DatasourceId = Get-Prop $d 'datasourceId'
            GatewayId    = $gw
            IsBound      = -not [string]::IsNullOrWhiteSpace($gw)
        }
    }
}

function Set-DatasetGateway {
<#
.SYNOPSIS
    Datasets - Bind To Gateway In Group. Learn: add the caller as a data source user on the gateway first; without data source ids the
    model is bound to the first matching data source. Republishing the model removes the association, so run this after every publish.
#>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $DatasetId,
        [Parameter(Mandatory)][string] $GatewayId,
        [string[]] $DataSourceId
    )
    $body = [ordered]@{ gatewayObjectId = $GatewayId }
    if ($DataSourceId) { $body.datasourceObjectIds = @($DataSourceId) }
    if ($PSCmdlet.ShouldProcess("model $DatasetId", "Bind to gateway $GatewayId")) {
        Invoke-GatewayApi -Method Post -Url "groups/$WorkspaceId/datasets/$DatasetId/Default.BindToGateway" -Body $body | Out-Null
    }
}

function Get-RefreshErrorCode {
<#
.SYNOPSIS
    errorCode from a refresh history entry's serviceExceptionJson (empty when there is no error).
#>
    [CmdletBinding()] param($Refresh)
    $json = Get-Prop $Refresh 'serviceExceptionJson'
    if ([string]::IsNullOrWhiteSpace($json)) { return $null }
    try { (Get-Prop ($json | ConvertFrom-Json) 'errorCode') } catch { $json }
}

function Start-DatasetRefreshAndWait {
<#
.SYNOPSIS
    Refresh Dataset In Group, then poll Get Refresh History until the newest entry is no longer 'Unknown' (in progress).
    Learn: status is Unknown while running, Completed, Failed (serviceExceptionJson holds the error code), or Disabled.
#>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $DatasetId,
        [int] $PollSeconds = 10,
        [int] $TimeoutSeconds = 600
    )
    if (-not $PSCmdlet.ShouldProcess("model $DatasetId", 'Refresh')) { return }
    Invoke-GatewayApi -Method Post -Url "groups/$WorkspaceId/datasets/$DatasetId/refreshes" -Body @{ notifyOption = 'NoNotification' } | Out-Null
    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ($PollSeconds -gt 0) { Start-Sleep -Seconds $PollSeconds }
        $r = Invoke-GatewayApi -Method Get -Url "groups/$WorkspaceId/datasets/$DatasetId/refreshes?`$top=1"
        $latest = @($r.value) | Select-Object -First 1
        if ($latest -and $latest.status -ne 'Unknown') {
            return [pscustomobject]@{ Status = $latest.status; ErrorCode = Get-RefreshErrorCode $latest; StartTime = $latest.startTime; EndTime = Get-Prop $latest 'endTime' }
        }
    } while ([datetime]::UtcNow -lt $deadline)
    throw "The refresh did not finish within $TimeoutSeconds seconds."
}

# ---------------------------------------------------------------- the self-signed certificate gotcha

function Set-GatewaySqlTrustedServer {
<#
.SYNOPSIS
    Sets SqlTrustedServers in the gateway's Microsoft.PowerBI.DataMovement.Pipeline.GatewayCore.dll.config (run on the gateway machine, elevated).
.DESCRIPTION
    Learn (SQL Server connector, troubleshooting): when the SQL Server uses a self-signed certificate, a refresh can fail with
    'The certificate chain was issued by an authority that is not trusted'. The fix on the gateway is the SqlTrustedServers setting: a
    comma separated list of server names, '*' allowed as a wild card, matched against the server name as written (contososql* matches
    contososql6 but not mysvr.microsoft.com). A backup of the file is made first. The setting has to exist: the function never invents the XML.
#>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [string] $ConfigPath = 'C:\Program Files\On-premises data gateway\Microsoft.PowerBI.DataMovement.Pipeline.GatewayCore.dll.config',
        [Parameter(Mandatory)][string[]] $Server
    )
    if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "Config file not found: $ConfigPath" }
    $xml = [xml](Get-Content -Raw -LiteralPath $ConfigPath)
    $node = $xml.SelectSingleNode("//setting[@name='SqlTrustedServers']/value")
    if (-not $node) { throw "No SqlTrustedServers setting in $ConfigPath. Update the gateway, or see Learn (SQL Server connector, troubleshooting)." }
    $old = $node.InnerText
    $new = ($Server | ForEach-Object { $_.Trim() } | Where-Object { $_ }) -join ','
    if ($PSCmdlet.ShouldProcess($ConfigPath, "SqlTrustedServers '$old' -> '$new'")) {
        Copy-Item -LiteralPath $ConfigPath -Destination "$ConfigPath.bak" -Force
        $node.InnerText = $new
        $xml.Save($ConfigPath)
    }
    [pscustomobject]@{ Path = $ConfigPath; Old = $old; New = $new }
}

Export-ModuleMember -Function Get-GatewayEndpoint, Test-GatewayNetwork, Get-GatewayCluster, Get-GatewayDataSource, Get-MSqlSource,
    Test-DataSourceMatch, New-GatewayDataSourceRequest, New-GatewayDataSource, Get-DatasetGatewayInfo, Set-DatasetGateway,
    Start-DatasetRefreshAndWait, Get-RefreshErrorCode, Set-GatewaySqlTrustedServer
