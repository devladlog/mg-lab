# Pester 5+: GatewayOps. Invoke-PowerBIRestMethod is mocked with responses shaped like the Learn samples (tests/fixtures/rest, zero GUIDs).
#   pwsh -NoProfile -Command "Invoke-Pester ./tests -Output Detailed"
# The credential encryption test runs the real gateway-credential tool when it has been built
# (dotnet build src/GatewayCredential -m:1) and is skipped otherwise.

BeforeAll {
    if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
        function global:Invoke-PowerBIRestMethod { param($Url, $Method, $Body) throw 'not mocked' }
    }
    $script:Src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $script:Src 'ps' 'GatewayOps' 'GatewayOps.psd1') -Force
    $script:Fix = Join-Path $PSScriptRoot 'fixtures' 'rest'
    $script:Query = Join-Path $script:Src 'queries' 'sales-by-store.pq'
    $script:Tool = Join-Path $script:Src 'GatewayCredential' 'bin' 'Debug' 'net8.0' 'gateway-credential.dll'
    $script:WS = '00000000-0000-0000-0000-0000000000b1'
    $script:DS = '00000000-0000-0000-0000-0000000000c1'
    $script:GW = '00000000-0000-0000-0000-0000000000a1'
    function global:Get-GwFixture([string] $Name) { Get-Content -Raw (Join-Path $script:Fix $Name) }
    $global:GwTest = @{ Calls = @(); Refreshes = @() }
    function global:Get-GwRoute([string] $Url, [string] $Method, $Body) {
        $global:GwTest.Calls += [pscustomobject]@{ Method = $Method; Url = $Url; Body = $Body }
        switch -Regex ($Url) {
            '^gateways$'                       { (Get-GwFixture 'gateways.json').Replace('__MODULUS__', $global:GwTest.Modulus); break }
            '^gateways/.*/datasources$' {
                if ($Method -eq 'Post') { '{}' } else { Get-GwFixture 'gateway-datasources.json' }; break }
            '/datasources$'                    { Get-GwFixture 'dataset-datasources-bound.json'; break }
            'Default\.BindToGateway$'          { ''; break }
            '/refreshes$'                      { ''; break }
            '/refreshes\?\$top=1$' {
                $q = $global:GwTest.Refreshes
                $next = if ($q.Count) { $q[0] } else { 'refreshes-completed.json' }
                if ($q.Count) { $global:GwTest.Refreshes = @($q | Select-Object -Skip 1) }
                Get-GwFixture $next; break }
            default                            { throw "unexpected URL: $Url" }
        }
    }
    # a real 1024-bit RSA public key in the shape Get Gateways returns (the SDK's >1024-bit path needs Windows CNG)
    $rsa = [System.Security.Cryptography.RSA]::Create(1024)
    $p = $rsa.ExportParameters($false)
    $global:GwTest.Modulus = [Convert]::ToBase64String($p.Modulus)
    $global:GwTest.Exponent = [Convert]::ToBase64String($p.Exponent)
}

Describe 'GatewayOps' {
    BeforeEach {
        $global:GwTest.Calls = @()
        $global:GwTest.Refreshes = @()
        Mock -ModuleName GatewayOps Invoke-PowerBIRestMethod { Get-GwRoute -Url $Url -Method $Method -Body $Body }
    }

    Describe 'Get-GatewayEndpoint and Test-GatewayNetwork' {
        It 'lists only endpoints that have a fixed host name, all on 443' {
            $e = Get-GatewayEndpoint
            $e.Host | Should -Contain 'login.microsoftonline.com'
            $e.Host | Should -Contain 'api.powerbi.com'
            $e.Host | Where-Object { $_ -match '\*' } | Should -BeNullOrEmpty
            $e.Port | Select-Object -Unique | Should -Be 443
        }
        It 'tests every endpoint plus the data sources, and reports the unreachable ones with the reason' {
            $c = { param($h, $p, $t) [pscustomobject]@{ Reachable = ($h -ne 'login.live.com' -and $p -ne 1433); Error = if ($h -eq 'login.live.com') { 'blocked' } else { 'refused' } } }
            $r = @(Test-GatewayNetwork -DataSource '10.50.0.30:1433' -Connector $c)
            $r.Count | Should -Be 7
            ($r | Where-Object Kind -eq 'DataSource').Host | Should -Be '10.50.0.30'
            ($r | Where-Object Host -eq 'login.live.com').Reachable | Should -BeFalse
            ($r | Where-Object Host -eq 'login.live.com').Error | Should -Be 'blocked'
            ($r | Where-Object Host -eq 'api.powerbi.com').Reachable | Should -BeTrue
        }
        It 'rejects a data source that is not host:port' {
            { Test-GatewayNetwork -DataSource 'CON-SQL01' -Connector { } } | Should -Throw '*host:port*'
        }
        It 'really connects over TCP: a listener on localhost is reachable, a closed port is not' {
            $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
            $l.Start()
            try {
                $open = ([System.Net.IPEndPoint]$l.LocalEndpoint).Port
                $r = @(Test-GatewayNetwork -DataSource "127.0.0.1:$open" -TimeoutMs 2000 -Connector { param($h, $p, $t) if ($h -eq '127.0.0.1') { & (Get-Module GatewayOps) { param($h2, $p2, $t2) Test-TcpPort -Hostname $h2 -Port $p2 -TimeoutMs $t2 } $h $p $t } else { [pscustomobject]@{ Reachable = $true } } })
                ($r | Where-Object Kind -eq 'DataSource').Reachable | Should -BeTrue
            }
            finally { $l.Stop() }
            $closed = & (Get-Module GatewayOps) { Test-TcpPort -Hostname '127.0.0.1' -Port 1 -TimeoutMs 1500 }
            $closed.Reachable | Should -BeFalse
            $closed.Error | Should -Not -BeNullOrEmpty
        }
    }

    Describe 'Get-MSqlSource and Test-DataSourceMatch' {
        It 'reads server and database from the episode query' {
            $s = @(Get-MSqlSource -Text (Get-Content -Raw $script:Query))
            $s.Count | Should -Be 1
            $s[0].Literal | Should -BeTrue
            $s[0].Server | Should -Be '10.50.0.30'
            $s[0].Database | Should -Be 'ContosoBikesDW'
        }
        It 'treats parameters as not literal and unescapes doubled quotes' {
            $s = @(Get-MSqlSource -Text 'Sql.Database(SqlServer, SqlDatabase) Sql.Database("a""b", "c")')
            ($s | Where-Object Literal).Server | Should -Be 'a"b'
            @($s | Where-Object { -not $_.Literal }).Count | Should -Be 1
        }
        It 'GW003: the query matches the data source on the gateway (from the REST fixture)' {
            $ds = Get-GatewayDataSource -GatewayId $script:GW
            $f = @(Test-DataSourceMatch -QueryPath $script:Query -GatewayDataSource $ds)
            $f.Rule | Should -Be 'GW003'
        }
        It 'GW001: server written as a name when the gateway has the IP address (Learn: names must match exactly)' {
            $q = Join-Path $TestDrive 'q.pq'
            'let Source = Sql.Database("CON-SQL01", "ContosoBikesDW") in Source' | Set-Content $q
            $f = @(Test-DataSourceMatch -QueryPath $q -GatewayDataSource (Get-GatewayDataSource -GatewayId $script:GW))
            $f.Rule | Should -Be 'GW001'
            $f.Severity | Should -Be 'Error'
            $f.Message | Should -BeLike '*another server text (10.50.0.30)*'
        }
        It 'GW001: a difference in letter case only is still a mismatch, and the message says why' {
            $q = Join-Path $TestDrive 'case.pq'
            'let Source = Sql.Database("10.50.0.30", "contosobikesdw") in Source' | Set-Content $q
            $f = @(Test-DataSourceMatch -QueryPath $q -GatewayDataSource (Get-GatewayDataSource -GatewayId $script:GW))
            $f.Rule | Should -Be 'GW001'
            $f.Message | Should -BeLike '*differs only in letter case*'
        }
        It 'GW001 when the gateway has no SQL data source at all; GW002 for a parameter' {
            $f = @(Test-DataSourceMatch -QueryPath $script:Query -GatewayDataSource @([pscustomobject]@{ Type = 'File'; Server = $null; Database = $null }))
            $f.Rule | Should -Be 'GW001'
            $f.Message | Should -BeLike '*No SQL Server data source*'
            $q = Join-Path $TestDrive 'param.pq'
            'let Source = Sql.Database(SqlServer, SqlDatabase) in Source' | Set-Content $q
            (@(Test-DataSourceMatch -QueryPath $q -GatewayDataSource @())).Rule | Should -Be 'GW002'
        }
        It 'the episode query and gateway/datasource.json describe the same source' {
            $def = Get-Content -Raw (Join-Path $script:Src 'gateway' 'datasource.json') | ConvertFrom-Json
            $ds = [pscustomobject]@{ Type = $def.type; Server = $def.server; Database = $def.database }
            (@(Test-DataSourceMatch -QueryPath $script:Query -GatewayDataSource $ds)).Rule | Should -Be 'GW003'
        }
    }

    Describe 'REST: gateways, data sources, binding' {
        It 'Get-GatewayCluster filters by name and keeps the public key' {
            $g = @(Get-GatewayCluster -Name 'contoso-lab-gw')
            $g.Count | Should -Be 1
            $g[0].Id | Should -Be $script:GW
            $g[0].PublicKey.exponent | Should -Be 'AQAB'
            @(Get-GatewayCluster).Count | Should -Be 2
        }
        It 'Get-GatewayDataSource parses the connectionDetails JSON string, including a file path with backslashes' {
            $d = @(Get-GatewayDataSource -GatewayId $script:GW)
            $d[0].Server | Should -Be '10.50.0.30'
            $d[0].Database | Should -Be 'ContosoBikesDW'
            $d[1].Type | Should -Be 'File'
            $d[1].Server | Should -BeNullOrEmpty
        }
        It 'Get-DatasetGatewayInfo says whether the model is bound' {
            $i = @(Get-DatasetGatewayInfo -WorkspaceId $script:WS -DatasetId $script:DS)
            $i[0].IsBound | Should -BeTrue
            $i[0].GatewayId | Should -Be $script:GW
            $global:GwTest.Calls[0].Url | Should -Be "groups/$($script:WS)/datasets/$($script:DS)/datasources"
            Mock -ModuleName GatewayOps Invoke-PowerBIRestMethod { Get-GwFixture 'dataset-datasources-unbound.json' }
            (Get-DatasetGatewayInfo -WorkspaceId $script:WS -DatasetId $script:DS).IsBound | Should -BeFalse
        }
        It 'Set-DatasetGateway posts Bind To Gateway with and without data source ids; -WhatIf posts nothing' {
            Set-DatasetGateway -WorkspaceId $script:WS -DatasetId $script:DS -GatewayId $script:GW -Confirm:$false
            $c = $global:GwTest.Calls[0]
            $c.Method | Should -Be 'Post'
            $c.Url | Should -Be "groups/$($script:WS)/datasets/$($script:DS)/Default.BindToGateway"
            ($c.Body | ConvertFrom-Json).gatewayObjectId | Should -Be $script:GW
            ($c.Body | ConvertFrom-Json).PSObject.Properties.Name | Should -Not -Contain 'datasourceObjectIds'
            $global:GwTest.Calls = @()
            Set-DatasetGateway -WorkspaceId $script:WS -DatasetId $script:DS -GatewayId $script:GW -DataSourceId 'x1', 'x2' -Confirm:$false
            ($global:GwTest.Calls[0].Body | ConvertFrom-Json).datasourceObjectIds | Should -Be @('x1', 'x2')
            $global:GwTest.Calls = @()
            Set-DatasetGateway -WorkspaceId $script:WS -DatasetId $script:DS -GatewayId $script:GW -WhatIf
            $global:GwTest.Calls.Count | Should -Be 0
        }
    }

    Describe 'Refresh' {
        It 'waits while the newest entry is Unknown, then reports Completed' {
            $global:GwTest.Refreshes = @('refreshes-running.json', 'refreshes-running.json', 'refreshes-completed.json')
            $r = Start-DatasetRefreshAndWait -WorkspaceId $script:WS -DatasetId $script:DS -PollSeconds 0 -Confirm:$false
            $r.Status | Should -Be 'Completed'
            $r.ErrorCode | Should -BeNullOrEmpty
            ($global:GwTest.Calls | Where-Object { $_.Method -eq 'Post' }).Count | Should -Be 1
            (($global:GwTest.Calls | Where-Object { $_.Method -eq 'Post' })[0].Body | ConvertFrom-Json).notifyOption | Should -Be 'NoNotification'
            ($global:GwTest.Calls | Where-Object { $_.Url -like '*refreshes?$top=1' }).Count | Should -Be 3
        }
        It 'returns the error code of a failed refresh (code from Learn''s failed-refresh sample)' {
            $global:GwTest.Refreshes = @('refreshes-failed.json')
            $r = Start-DatasetRefreshAndWait -WorkspaceId $script:WS -DatasetId $script:DS -PollSeconds 0 -Confirm:$false
            $r.Status | Should -Be 'Failed'
            $r.ErrorCode | Should -Be 'ModelRefreshFailed_CredentialsNotSpecified'
        }
        It 'times out instead of waiting forever' {
            $global:GwTest.Refreshes = @(1..50 | ForEach-Object { 'refreshes-running.json' })
            { Start-DatasetRefreshAndWait -WorkspaceId $script:WS -DatasetId $script:DS -PollSeconds 0 -TimeoutSeconds 0 -Confirm:$false } | Should -Throw '*did not finish*'
        }
        It '-WhatIf sends nothing' {
            Start-DatasetRefreshAndWait -WorkspaceId $script:WS -DatasetId $script:DS -WhatIf | Should -BeNullOrEmpty
            $global:GwTest.Calls.Count | Should -Be 0
        }
    }

    Describe 'New-GatewayDataSource (credentials encrypted by the Power BI SDK, tool must be built)' {
        BeforeAll { $script:HasTool = Test-Path $script:Tool }
        It 'builds a Create Datasource body whose credentials are ciphertext, and leaves no password in the environment' -Skip:(-not (Test-Path (Join-Path $PSScriptRoot '..' 'src' 'GatewayCredential' 'bin' 'Debug' 'net8.0' 'gateway-credential.dll'))) {
            $pw = ConvertTo-SecureString 'Pa55-not-a-real-one!' -AsPlainText -Force
            $gw = (Get-GatewayCluster -Name 'contoso-lab-gw')
            $json = New-GatewayDataSourceRequest -Gateway $gw -Name 'Contoso Bikes DW (lab)' -Server '10.50.0.30' -Database 'ContosoBikesDW' -Username 'pbi_gateway_reader' -Password $pw -ToolPath $script:Tool
            $b = $json | ConvertFrom-Json
            $b.dataSourceType | Should -Be 'Sql'
            $b.dataSourceName | Should -Be 'Contoso Bikes DW (lab)'
            ($b.connectionDetails | ConvertFrom-Json).server | Should -Be '10.50.0.30'
            $b.credentialDetails.encryptedConnection | Should -Be 'Encrypted'
            $b.credentialDetails.encryptionAlgorithm | Should -Be 'RSA-OAEP'
            $b.credentialDetails.credentials.Length | Should -BeGreaterThan 100
            $json | Should -Not -BeLike '*Pa55*'
            $json | Should -Not -BeLike '*pbi_gateway_reader*'
            $env:GATEWAY_DS_PASSWORD | Should -BeNullOrEmpty
        }
        It 'creates the data source on the gateway found by name; -WhatIf posts nothing' -Skip:(-not (Test-Path (Join-Path $PSScriptRoot '..' 'src' 'GatewayCredential' 'bin' 'Debug' 'net8.0' 'gateway-credential.dll'))) {
            $pw = ConvertTo-SecureString 'Pa55-not-a-real-one!' -AsPlainText -Force
            New-GatewayDataSource -GatewayName 'contoso-lab-gw' -Name 'n' -Server '10.50.0.30' -Database 'ContosoBikesDW' -Username 'u' -Password $pw -ToolPath $script:Tool -Confirm:$false | Out-Null
            $post = $global:GwTest.Calls | Where-Object { $_.Method -eq 'Post' }
            $post.Url | Should -Be "gateways/$($script:GW)/datasources"
            $global:GwTest.Calls = @()
            New-GatewayDataSource -GatewayName 'contoso-lab-gw' -Name 'n' -Server '10.50.0.30' -Database 'ContosoBikesDW' -Username 'u' -Password $pw -ToolPath $script:Tool -WhatIf | Out-Null
            ($global:GwTest.Calls | Where-Object { $_.Method -eq 'Post' }) | Should -BeNullOrEmpty
        }
        It 'refuses an unknown gateway name and a missing tool' {
            $pw = ConvertTo-SecureString 'x' -AsPlainText -Force
            { New-GatewayDataSource -GatewayName 'nope' -Name 'n' -Server 's' -Database 'd' -Username 'u' -Password $pw -ToolPath 'x' } | Should -Throw '*found 0*'
            { New-GatewayDataSourceRequest -Gateway (Get-GatewayCluster -Name 'contoso-lab-gw') -Name 'n' -Server 's' -Database 'd' -Username 'u' -Password $pw -ToolPath (Join-Path $TestDrive 'missing.dll') } | Should -Throw '*not found*'
        }
    }

    Describe 'Set-GatewaySqlTrustedServer' {
        BeforeEach {
            $script:Cfg = Join-Path $TestDrive 'gateway.config'
            Copy-Item (Join-Path $PSScriptRoot 'fixtures' 'rest' 'gateway-core.dll.config') $script:Cfg
        }
        It 'sets the comma separated list, keeps the other settings and makes a backup' {
            $r = Set-GatewaySqlTrustedServer -ConfigPath $script:Cfg -Server '10.50.0.30', 'contososql*' -Confirm:$false
            $r.New | Should -Be '10.50.0.30,contososql*'
            $xml = [xml](Get-Content -Raw $script:Cfg)
            $xml.SelectSingleNode("//setting[@name='SqlTrustedServers']/value").InnerText | Should -Be '10.50.0.30,contososql*'
            $xml.SelectSingleNode("//setting[@name='Other']/value").InnerText | Should -Be 'keep'
            Test-Path "$($script:Cfg).bak" | Should -BeTrue
            ([xml](Get-Content -Raw "$($script:Cfg).bak")).SelectSingleNode("//setting[@name='SqlTrustedServers']/value").InnerText | Should -Be ''
        }
        It '-WhatIf changes nothing; a file without the setting is an error, not an invention' {
            Set-GatewaySqlTrustedServer -ConfigPath $script:Cfg -Server 'x' -WhatIf | Out-Null
            ([xml](Get-Content -Raw $script:Cfg)).SelectSingleNode("//setting[@name='SqlTrustedServers']/value").InnerText | Should -Be ''
            $bare = Join-Path $TestDrive 'bare.config'
            '<configuration><appSettings/></configuration>' | Set-Content $bare
            { Set-GatewaySqlTrustedServer -ConfigPath $bare -Server 'x' -Confirm:$false } | Should -Throw '*No SqlTrustedServers*'
        }
    }
}
