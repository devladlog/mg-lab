# Pester 5+: governance module. Invoke-PowerBIRestMethod is mocked with responses shaped like the Learn samples
# (tests/fixtures: zero GUIDs, fictional names). The tenant settings call goes through Invoke-RestMethod; one test sends it over real HTTP to a
# loopback listener (this is a test stand-in only, the demo uses the real service).
#   pwsh -NoProfile -Command "Invoke-Pester ./tests -Output Detailed"

BeforeAll {
    if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
        # Stand-in so Pester can mock the MicrosoftPowerBIMgmt cmdlet without installing it.
        function global:Invoke-PowerBIRestMethod { param($Url, $Method, $Body) throw 'not mocked' }
    }
    $script:Root = Join-Path $PSScriptRoot '..'
    $script:Src = Join-Path $script:Root 'src'
    $script:Fx = Join-Path $PSScriptRoot 'fixtures'
    Import-Module (Join-Path $script:Src 'PbiGovernance' 'PbiGovernance.psd1') -Force
    $global:Gov = @{ Calls = @(); Statuses = @(); Pages = @() }

    function global:Get-Fx([string] $name) { Get-Content -Raw (Join-Path $PSScriptRoot 'fixtures' $name) }
    function global:Get-GovRoute([string] $Url, [string] $Method, $Body) {
        $global:Gov.Calls += , @($Method, $Url, $Body)
        switch -Regex ($Url) {
            '^admin/activityevents\?startDateTime' { Get-Fx 'activity-page1.json'; break }
            "^admin/activityevents\?continuationToken='%2BRID%3Aaaa" { Get-Fx 'activity-page2.json'; break }
            "^admin/activityevents\?continuationToken='%2BRID%3Abbb" { Get-Fx 'activity-page3.json'; break }
            '^admin/groups\?' { Get-Fx 'groups-orphaned.json'; break }
            '^admin/workspaces/modified' { Get-Fx 'modified-workspaces.json'; break }
            '^admin/workspaces/getInfo' { Get-Fx 'scan-accepted.json'; break }
            '^admin/workspaces/scanStatus/' {
                $s = $global:Gov.Statuses
                $next = if ($s.Count) { $s[0] } else { 'Succeeded' }
                if ($s.Count) { $global:Gov.Statuses = @($s | Select-Object -Skip 1) }
                if ($next -eq 'Failed') { Get-Fx 'scan-failed.json' } else { (Get-Fx 'scan-succeeded.json') -replace '"status": "Succeeded"', "`"status`": `"$next`"" }
                break
            }
            '^admin/workspaces/scanResult/' { Get-Fx 'scan-result.json'; break }
            default { throw "unexpected URL $Url" }
        }
    }
    function global:Find-Finding($Findings, [string] $Rule) { @($Findings | Where-Object Rule -EQ $Rule) }
    $script:Today = [datetime]::UtcNow.Date
}

Describe 'module' {
    It 'has a valid manifest that exports eleven functions' {
        (Test-ModuleManifest (Join-Path $script:Src 'PbiGovernance' 'PbiGovernance.psd1')).ExportedFunctions.Count | Should -Be 11
    }
    It 'lists nine rules, GV001 to GV009' {
        @((Get-PbiGovernanceRule).Rule) | Should -Be @('GV001', 'GV002', 'GV003', 'GV004', 'GV005', 'GV006', 'GV007', 'GV008', 'GV009')
    }
    It 'Invoke-GovernanceAudit.ps1 parses' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $script:Src 'Invoke-GovernanceAudit.ps1'), [ref] $null, [ref] $errors) | Out-Null
        $errors | Should -BeNullOrEmpty
    }
}

Describe 'activity log' {
    BeforeEach { $global:Gov.Calls = @(); Mock Invoke-PowerBIRestMethod -ModuleName PbiGovernance { Get-GovRoute $Url $Method $Body } }

    It 'asks for one UTC day, both ends in single quotes, and follows the continuation token to the last page' {
        $e = @(Get-PbiActivityEvent -Date $script:Today.AddDays(-1))
        $e.Count | Should -Be 7
        $global:Gov.Calls.Count | Should -Be 3
        $day = $script:Today.AddDays(-1).ToString('yyyy-MM-dd')
        $global:Gov.Calls[0][1] | Should -Be "admin/activityevents?startDateTime='${day}T00:00:00.000Z'&endDateTime='${day}T23:59:59.999Z'"
        $global:Gov.Calls[1][1] | Should -Be "admin/activityevents?continuationToken='%2BRID%3Aaaa%3D%3D%23RT%3A1'"
        $global:Gov.Calls[2][1] | Should -BeLike "*bbb*"
        $global:Gov.Calls | ForEach-Object { $_[0] } | Sort-Object -Unique | Should -Be 'Get'
    }
    It 'sends the filter again with every page (the continuation URI in Learn carries it) and escapes it' {
        Get-PbiActivityEvent -Date $script:Today -Activity ViewReport -UserId "alex.demo@contoso.com" | Out-Null
        $global:Gov.Calls[0][1] | Should -BeLike '*&$filter=Activity%20eq%20%27ViewReport%27%20and%20UserId%20eq%20%27alex.demo%40contoso.com%27'
        $global:Gov.Calls[1][1] | Should -BeLike '*&$filter=Activity%20eq%20%27ViewReport%27*'
    }
    It 'rejects an activity name that is not a plain operation name (no filter injection)' {
        { Get-PbiActivityEvent -Date $script:Today -Activity "ViewReport' or 1 eq 1" } | Should -Throw
    }
    It 'refuses a day in the future and a day older than 28 days' {
        { Get-PbiActivityEvent -Date $script:Today.AddDays(1) } | Should -Throw '*future*'
        { Get-PbiActivityEvent -Date $script:Today.AddDays(-29) } | Should -Throw '*28 days*'
        $global:Gov.Calls.Count | Should -Be 0
    }
    It 'accepts exactly 28 days back' {
        { Get-PbiActivityEvent -Date $script:Today.AddDays(-28) | Out-Null } | Should -Not -Throw
    }
    It 'treats the date as a UTC calendar day whatever the time of day or kind of the value' {
        Get-PbiActivityEvent -Date ([datetime]::SpecifyKind($script:Today.AddDays(-2).AddHours(23).AddMinutes(30), 'Local')) | Out-Null
        $day = $script:Today.AddDays(-2).ToString('yyyy-MM-dd')
        $global:Gov.Calls[0][1] | Should -BeLike "*startDateTime='${day}T00:00:00.000Z'*"
    }
    It 'keeps going when a page has a token and no events, and stops at -MaxRequests' {
        Mock Invoke-PowerBIRestMethod -ModuleName PbiGovernance { '{"activityEventEntities":[],"continuationToken":"x1"}' }
        { Get-PbiActivityEvent -Date $script:Today -MaxRequests 5 } | Should -Throw '*Stopped after 5 requests*'
        Should -Invoke Invoke-PowerBIRestMethod -ModuleName PbiGovernance -Times 5 -Exactly
    }
}

Describe 'activity summary' {
    BeforeAll {
        Mock Invoke-PowerBIRestMethod -ModuleName PbiGovernance { Get-GovRoute $Url $Method $Body }
        $script:Sum = Get-PbiActivitySummary -Event @(Get-PbiActivityEvent -Date $script:Today)
    }
    It 'counts events and failures' { $script:Sum.Total | Should -Be 7; $script:Sum.Failed | Should -Be 1 }
    It 'groups per activity, largest first' {
        $script:Sum.ByActivity[0].Activity | Should -Be 'ViewReport'
        $script:Sum.ByActivity[0].Count | Should -Be 5
    }
    It 'ranks reports by views with distinct users (the failed view still counts as an event)' {
        $script:Sum.TopReports[0].Report | Should -Be 'Contoso Sales'
        $script:Sum.TopReports[0].Views | Should -Be 4
        $script:Sum.TopReports[0].Users | Should -Be 3
    }
    It 'lists the operations worth a second look, in time order, with aliases only' {
        @($script:Sum.Risky.Activity) | Should -Be @('ExportReport', 'UpdatedAdminFeatureSwitch')
        $script:Sum.Risky[0].User | Should -Be 'riley.demo'
        ($script:Sum | ConvertTo-Json -Depth 5) | Should -Not -Match '@'
    }
    It 'works on no events' {
        $e = Get-PbiActivitySummary -Event @()
        $e.Total | Should -Be 0
        @($e.Risky).Count | Should -Be 0
    }
}

Describe 'orphaned workspaces' {
    BeforeEach { $global:Gov.Calls = @(); Mock Invoke-PowerBIRestMethod -ModuleName PbiGovernance { Get-GovRoute $Url $Method $Body } }
    It "uses Learn's filter on Get Groups as Admin with users expanded and a top" {
        $o = @(Get-PbiOrphanedWorkspace)
        $o.Count | Should -Be 1
        $o[0].Name | Should -Be 'Contoso Sandbox (Lab)'
        $u = $global:Gov.Calls[0][1]
        $u | Should -BeLike 'admin/groups?$expand=users&$filter=*&$top=100'
        [uri]::UnescapeDataString($u) | Should -BeLike "*(not users/any()) or (not users/any(u: u/groupUserAccessRight eq Microsoft.PowerBI.ServiceContracts.Api.GroupUserAccessRight'Admin'))*"
    }
    It 'validates $top (1 to 5000)' { { Get-PbiOrphanedWorkspace -Top 0 } | Should -Throw; { Get-PbiOrphanedWorkspace -Top 5001 } | Should -Throw }
}

Describe 'modified workspaces' {
    BeforeEach { $global:Gov.Calls = @(); Mock Invoke-PowerBIRestMethod -ModuleName PbiGovernance { Get-GovRoute $Url $Method $Body } }
    It 'without a date returns all ids and sends no query' {
        @(Get-PbiModifiedWorkspace).Count | Should -Be 3
        $global:Gov.Calls[0][1] | Should -Be 'admin/workspaces/modified'
    }
    It 'adds the filters in the Learn spelling' {
        Get-PbiModifiedWorkspace -ExcludePersonal -ExcludeInactive | Out-Null
        $global:Gov.Calls[0][1] | Should -Be 'admin/workspaces/modified?excludePersonalWorkspaces=True&excludeInActiveWorkspaces=True'
    }
    It 'sends modifiedSince as ISO 8601 UTC' {
        Get-PbiModifiedWorkspace -ModifiedSince ([datetime]::UtcNow.AddDays(-2)) | Out-Null
        $global:Gov.Calls[0][1] | Should -Match '^admin/workspaces/modified\?modifiedSince=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{7}Z$'
    }
    It 'refuses a date older than 30 days or newer than 30 minutes (Learn)' {
        { Get-PbiModifiedWorkspace -ModifiedSince ([datetime]::UtcNow.AddDays(-31)) } | Should -Throw '*30 days*'
        { Get-PbiModifiedWorkspace -ModifiedSince ([datetime]::UtcNow.AddMinutes(-5)) } | Should -Throw '*30 minutes*'
        $global:Gov.Calls.Count | Should -Be 0
    }
}

Describe 'metadata scan' {
    BeforeEach { $global:Gov.Calls = @(); $global:Gov.Statuses = @(); Mock Invoke-PowerBIRestMethod -ModuleName PbiGovernance { Get-GovRoute $Url $Method $Body } }
    It 'splits 250 workspaces into chunks of 100, 100 and 50, one chunk at a time' {
        $ids = 1..250 | ForEach-Object { '00000000-0000-0000-0000-{0:d12}' -f $_ }
        $r = Invoke-PbiWorkspaceScan -WorkspaceId $ids -PollSeconds 0
        $posts = @($global:Gov.Calls | Where-Object { $_[0] -eq 'Post' })
        $posts.Count | Should -Be 3
        @($posts | ForEach-Object { @(($_[2] | ConvertFrom-Json).workspaces).Count }) | Should -Be @(100, 100, 50)
        # strictly sequential: post, status, result, post, ...
        @($global:Gov.Calls | ForEach-Object { ($_[1] -split '/')[2] -replace '\?.*', '' }) | Should -Be @('getInfo', 'scanStatus', 'scanResult', 'getInfo', 'scanStatus', 'scanResult', 'getInfo', 'scanStatus', 'scanResult')
        @($r.workspaces).Count | Should -Be 15   # five per chunk from the fixture
    }
    It 'sends only the switches that were asked for' {
        Invoke-PbiWorkspaceScan -WorkspaceId '00000000-0000-0000-0000-000000000001' -DatasourceDetails -DatasetSchema -GetArtifactUsers -PollSeconds 0 | Out-Null
        $global:Gov.Calls[0][1] | Should -Be 'admin/workspaces/getInfo?datasourceDetails=True&datasetSchema=True&getArtifactUsers=True'
        Invoke-PbiWorkspaceScan -WorkspaceId '00000000-0000-0000-0000-000000000001' -PollSeconds 0 | Out-Null
        $global:Gov.Calls[3][1] | Should -Be 'admin/workspaces/getInfo'
    }
    It 'polls scanStatus until Succeeded and only then reads the result' {
        $global:Gov.Statuses = @('NotStarted', 'Running', 'Running')
        Invoke-PbiWorkspaceScan -WorkspaceId '00000000-0000-0000-0000-000000000001' -PollSeconds 0 | Out-Null
        @($global:Gov.Calls | Where-Object { $_[1] -like 'admin/workspaces/scanStatus/*' }).Count | Should -Be 4
        $global:Gov.Calls[-1][1] | Should -BeLike 'admin/workspaces/scanResult/*'
    }
    It 'stops on a failed scan and does not read a result' {
        $global:Gov.Statuses = @('Running', 'Failed')
        { Invoke-PbiWorkspaceScan -WorkspaceId '00000000-0000-0000-0000-000000000001' -PollSeconds 0 } | Should -Throw '*failed*'
        @($global:Gov.Calls | Where-Object { $_[1] -like '*scanResult*' }).Count | Should -Be 0
    }
    It 'gives up after the timeout' {
        Mock Invoke-PowerBIRestMethod -ModuleName PbiGovernance { if ($Url -like '*getInfo*') { Get-Fx 'scan-accepted.json' } else { Get-Fx 'scan-running.json' } }
        { Invoke-PbiWorkspaceScan -WorkspaceId '00000000-0000-0000-0000-000000000001' -PollSeconds 0 -TimeoutSeconds 1 } | Should -Throw '*did not finish*'
    }
    It 'refuses an empty id list' { { Invoke-PbiWorkspaceScan -WorkspaceId @('') } | Should -Throw }
}

Describe 'governance rules on the fixture scan' {
    BeforeAll { $script:Scan = (Get-Content -Raw (Join-Path $script:Fx 'scan-result.json') | ConvertFrom-Json -Depth 32); $script:F = @(Test-PbiGovernance -ScanResult $script:Scan) }
    It 'GV001 finds the unlabelled items, in every item type that has them' {
        @((Find-Finding $script:F GV001).ItemName | Sort-Object) | Should -Be @('Jordan scratch', 'Sandbox Model', 'Sandbox Report')
    }
    It 'GV002 finds models that are not promoted or certified (missing or "None")' {
        @((Find-Finding $script:F GV002).ItemName | Sort-Object) | Should -Be @('Pilot Realtime', 'Sandbox Model')
    }
    It 'GV003 finds the item on the misconfigured data source' { @((Find-Finding $script:F GV003).ItemName) | Should -Be @('Sandbox Model') }
    It 'GV004 reports the schema blind spot with the reason' {
        $g = Find-Finding $script:F GV004
        $g.ItemName | Should -Be 'Pilot Realtime'
        $g.Message | Should -BeLike '*RealTime*'
    }
    It 'GV005 finds the workspace without an Admin and not the ones that have one' {
        @((Find-Finding $script:F GV005).Workspace) | Should -Be @('Contoso Sandbox (Lab)')
    }
    It 'GV006 finds the report shared with the whole organization' { @((Find-Finding $script:F GV006).ItemName) | Should -Be @('Sandbox Report') }
    It 'GV007 finds the workspace that is not Active' { @((Find-Finding $script:F GV007).Workspace) | Should -Be @('Contoso Old Pilot (Lab)') }
    It 'GV008 finds the role without members, not the role that has one' {
        $g = Find-Finding $script:F GV008
        @($g).Count | Should -Be 1
        $g.Message | Should -BeLike "*Head Office*"
    }
    It 'GV009 finds the personal workspace with a report' { @((Find-Finding $script:F GV009).Workspace) | Should -Be @('My workspace') }
    It 'says nothing about a clean workspace, and the model of episode 5 has only the role finding' {
        @($script:F | Where-Object Workspace -EQ 'Contoso Empty (Lab)').Count | Should -Be 0
        @($script:F | Where-Object Workspace -EQ 'Contoso Sales (Lab)').Rule | Should -Be @('GV008')
    }
    It 'gives every finding a severity from the rule table' {
        $sev = @{}; Get-PbiGovernanceRule | ForEach-Object { $sev[$_.Rule] = $_.Severity }
        foreach ($f in $script:F) { $f.Severity | Should -Be $sev[$f.Rule] }
    }
    It 'GV005 and GV006 stay silent when the scan had no user lists (no -GetArtifactUsers)' {
        $copy = Get-Content -Raw (Join-Path $script:Fx 'scan-result.json') | ConvertFrom-Json -Depth 32
        foreach ($w in $copy.workspaces) {
            $w.PSObject.Properties.Remove('users')
            foreach ($k in 'reports', 'datasets') { foreach ($i in @($w.$k)) { $i.PSObject.Properties.Remove('users') } }
        }
        $g = @(Test-PbiGovernance -ScanResult $copy)
        (Find-Finding $g GV005).Count | Should -Be 0
        (Find-Finding $g GV006).Count | Should -Be 0
        (Find-Finding $g GV001).Count | Should -Be 3
    }
    It 'accepts an empty scan' { @(Test-PbiGovernance -ScanResult ([pscustomobject]@{ workspaces = @() })).Count | Should -Be 0 }
}

Describe 'tenant settings' {
    BeforeEach {
        $global:Gov.Calls = @()
        Mock Invoke-RestMethod -ModuleName PbiGovernance {
            $global:Gov.Calls += , @($Method, "$Uri", $Headers['Authorization'])
            if ("$Uri" -like '*continuationToken=abc') { Get-Fx 'tenantsettings-page2.json' | ConvertFrom-Json }
            else { Get-Fx 'tenantsettings-page1.json' | ConvertFrom-Json }
        }
        $script:Tok = ConvertTo-SecureString 'fixture-token' -AsPlainText -Force
    }
    It 'reads every page through continuationUri with the bearer token' {
        $s = @(Get-PbiTenantSetting -FabricToken $script:Tok)
        $s.Count | Should -Be 3
        $global:Gov.Calls[0][1] | Should -Be 'https://api.fabric.microsoft.com/v1/admin/tenantsettings'
        $global:Gov.Calls[1][1] | Should -BeLike '*continuationToken=abc'
        $global:Gov.Calls | ForEach-Object { $_[2] } | Sort-Object -Unique | Should -Be 'Bearer fixture-token'
    }
    It 'returns group names sorted, and an empty list when there are none' {
        $s = @(Get-PbiTenantSetting -FabricToken $script:Tok)
        ($s | Where-Object SettingName -EQ 'DatamartTenant').Groups | Should -Be @('Contoso BI Team (Lab)', 'Contoso Datamart Makers (Lab)')
        @(($s | Where-Object SettingName -EQ 'AdminApisIncludeDetailedMetadata').Groups).Count | Should -Be 0
    }
    It 'takes the token from PBIGOV_FABRIC_TOKEN and says what to do when there is none' {
        $old = $env:PBIGOV_FABRIC_TOKEN
        try {
            $env:PBIGOV_FABRIC_TOKEN = $null
            { Get-PbiTenantSetting } | Should -Throw '*Get-AzAccessToken*'
            $env:PBIGOV_FABRIC_TOKEN = 'from-env'
            @(Get-PbiTenantSetting).Count | Should -Be 3
            $global:Gov.Calls[0][2] | Should -Be 'Bearer from-env'
        }
        finally { $env:PBIGOV_FABRIC_TOKEN = $old }
    }
    It 'waits for Retry-After on 429 and tries again, but not more than three times' {
        Mock Invoke-RestMethod -ModuleName PbiGovernance {
            $resp = [System.Net.Http.HttpResponseMessage]::new(429)
            $resp.Headers.Add('Retry-After', '0')
            throw [Microsoft.PowerShell.Commands.HttpResponseException]::new('429', $resp)
        }
        { Get-PbiTenantSetting -FabricToken $script:Tok } | Should -Throw
        Should -Invoke Invoke-RestMethod -ModuleName PbiGovernance -Times 4 -Exactly   # first try + three retries
    }
    It 'does not retry other errors such as 403' {
        Mock Invoke-RestMethod -ModuleName PbiGovernance { throw [Microsoft.PowerShell.Commands.HttpResponseException]::new('403', [System.Net.Http.HttpResponseMessage]::new(403)) }
        { Get-PbiTenantSetting -FabricToken $script:Tok } | Should -Throw
        Should -Invoke Invoke-RestMethod -ModuleName PbiGovernance -Times 1 -Exactly
    }
}

Describe 'tenant settings over real HTTP (loopback stand-in for the service)' {
    It 'sends Authorization, survives a 429 with Retry-After and follows continuationUri' {
        $tcp = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0); $tcp.Start(); $port = $tcp.LocalEndpoint.Port; $tcp.Stop()
        $log = Join-Path $TestDrive 'requests.log'
        $page1 = (Get-Fx 'tenantsettings-page1.json') -replace 'https://api.fabric.microsoft.com', "http://127.0.0.1:$port"
        $page2 = Get-Fx 'tenantsettings-page2.json'
        $job = Start-Job -ArgumentList $port, $log, $page1, $page2 -ScriptBlock {
            param($port, $log, $page1, $page2)
            $l = [System.Net.HttpListener]::new(); $l.Prefixes.Add("http://127.0.0.1:$port/"); $l.Start()
            Set-Content "$log.ready" 'ready'
            $served429 = $false
            for ($i = 0; $i -lt 3; $i++) {
                $c = $l.GetContext()
                Add-Content $log ("{0} {1} {2}" -f $c.Request.HttpMethod, $c.Request.Url.PathAndQuery, $c.Request.Headers['Authorization'])
                if (-not $served429) { $served429 = $true; $c.Response.StatusCode = 429; $c.Response.Headers.Add('Retry-After', '0'); $body = '{"errorCode":"RequestBlocked"}' }
                elseif ($c.Request.Url.Query -like '*continuationToken=abc*') { $body = $page2 }
                else { $body = $page1 }
                $b = [System.Text.Encoding]::UTF8.GetBytes($body); $c.Response.ContentType = 'application/json'
                $c.Response.OutputStream.Write($b, 0, $b.Length); $c.Response.Close()
            }
            $l.Stop()
        }
        try {
            $wait = [System.Diagnostics.Stopwatch]::StartNew()
            while (-not (Test-Path "$log.ready") -and $wait.Elapsed.TotalSeconds -lt 30) { Start-Sleep -Milliseconds 100 }
            Test-Path "$log.ready" | Should -BeTrue
            & (Get-Module PbiGovernance) { param($p) $script:FabricBase = "http://127.0.0.1:$p" } $port
            $s = @(Get-PbiTenantSetting -FabricToken (ConvertTo-SecureString 'loop-token' -AsPlainText -Force))
            $s.Count | Should -Be 3
            $lines = @(Get-Content $log)
            $lines.Count | Should -Be 3
            $lines[0] | Should -Be 'GET /v1/admin/tenantsettings Bearer loop-token'
            $lines[2] | Should -BeLike '*continuationToken=abc*'
        }
        finally {
            & (Get-Module PbiGovernance) { $script:FabricBase = 'https://api.fabric.microsoft.com' }
            Stop-Job $job -ErrorAction SilentlyContinue; Remove-Job $job -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe 'baseline and drift' {
    BeforeAll {
        Mock Invoke-RestMethod -ModuleName PbiGovernance { if ("$Uri" -like '*continuationToken=abc') { Get-Fx 'tenantsettings-page2.json' | ConvertFrom-Json } else { Get-Fx 'tenantsettings-page1.json' | ConvertFrom-Json } }
        $script:Now = @(Get-PbiTenantSetting -FabricToken (ConvertTo-SecureString 'x' -AsPlainText -Force))
        $script:Base = Join-Path $script:Fx 'baseline.json'
    }
    It 'exports a baseline that compares clean against the same settings' {
        $p = Join-Path $TestDrive 'sub' 'baseline.json'
        Export-PbiTenantBaseline -Setting $script:Now -Path $p | Should -Be 3
        @(Compare-PbiTenantSetting -Current $script:Now -BaselinePath $p).Count | Should -Be 0
    }
    It 'exports only the named settings' {
        $p = Join-Path $TestDrive 'one.json'
        Export-PbiTenantBaseline -Setting $script:Now -Path $p -Name CertifyDatasets | Should -Be 1
        (Get-Content -Raw $p | ConvertFrom-Json).settingName | Should -Be 'CertifyDatasets'
    }
    It 'the committed example baseline matches the fixture tenant' { @(Compare-PbiTenantSetting -Current $script:Now -BaselinePath $script:Base).Count | Should -Be 0 }
    It 'sees a setting that was switched off' {
        $cur = @($script:Now | ForEach-Object { $c = $_.PSObject.Copy(); if ($c.SettingName -eq 'CertifyDatasets') { $c.Enabled = $false }; $c })
        $d = @(Compare-PbiTenantSetting -Current $cur -BaselinePath $script:Base)
        $d.Count | Should -Be 1
        $d[0].Kind | Should -Be 'EnabledChanged'
        $d[0].Setting | Should -Be 'CertifyDatasets'
        $d[0].Was | Should -Be 'enabled=True'
        $d[0].Now | Should -Be 'enabled=False'
    }
    It 'sees a changed security group list' {
        $cur = @($script:Now | ForEach-Object { $c = $_.PSObject.Copy(); if ($c.SettingName -eq 'DatamartTenant') { $c.Groups = @('Contoso BI Team (Lab)') }; $c })
        $d = @(Compare-PbiTenantSetting -Current $cur -BaselinePath $script:Base)
        $d.Kind | Should -Be 'GroupsChanged'
        $d[0].Was | Should -Be 'Contoso BI Team (Lab), Contoso Datamart Makers (Lab)'
    }
    It 'sees a setting that is no longer returned, and a new one (unless -IgnoreNew)' {
        $cur = @($script:Now | Where-Object SettingName -NE 'CertifyDatasets') + [pscustomobject]@{ SettingName = 'BrandNewSetting'; Title = 't'; Group = 'g'; Enabled = $true; Groups = @(); Excluded = @() }
        $d = @(Compare-PbiTenantSetting -Current $cur -BaselinePath $script:Base)
        @($d.Kind | Sort-Object) | Should -Be @('Missing', 'New')
        @(Compare-PbiTenantSetting -Current $cur -BaselinePath $script:Base -IgnoreNew).Kind | Should -Be 'Missing'
    }
}

Describe 'report' {
    BeforeAll {
        $script:Scan = (Get-Content -Raw (Join-Path $script:Fx 'scan-result.json') | ConvertFrom-Json -Depth 32)
        $script:F = @(Test-PbiGovernance -ScanResult $script:Scan)
        Mock Invoke-PowerBIRestMethod -ModuleName PbiGovernance { Get-GovRoute $Url $Method $Body }
        $script:Sum = Get-PbiActivitySummary -Event @(Get-PbiActivityEvent -Date $script:Today)
        $script:Md = New-PbiGovernanceReport -Date $script:Today -Findings $script:F -ActivitySummary $script:Sum -Orphans @() -Drift @() -WorkspacesScanned 5
    }
    It 'has the five sections' {
        foreach ($h in '# Power BI governance check', '## Tenant settings drift', '## Orphaned workspaces', '## Scan findings (5 workspaces scanned)', '## Activity') { $script:Md | Should -BeLike "*$h*" }
    }
    It 'lists errors before warnings before info in the findings table' {
        $rows = @($script:Md -split "`n" | Where-Object { $_ -match '^\| GV' })
        $rows.Count | Should -Be $script:F.Count
        $sev = @($rows | ForEach-Object { ($_ -split '\|')[2].Trim() })
        $order = @{ error = 0; warning = 1; info = 2 }
        for ($i = 1; $i -lt $sev.Count; $i++) { $order[$sev[$i]] | Should -BeGreaterOrEqual $order[$sev[$i - 1]] }
    }
    It 'shows the risky operations and no e-mail address' {
        $script:Md | Should -BeLike '*ExportReport by riley.demo*'
        $script:Md | Should -Not -Match '@'
    }
    It 'says "Not run" for a section that was not run, never "all clear"' {
        $m = New-PbiGovernanceReport -Findings $script:F
        ([regex]::Matches($m, '_Not run\._')).Count | Should -Be 3
        $m | Should -Not -BeLike '*No difference*'
    }
    It 'says plainly when nothing was found' {
        $m = New-PbiGovernanceReport -Findings @() -Drift @() -Orphans @()
        $m | Should -BeLike '*No findings from rules GV001-GV009*'
        $m | Should -BeLike '*No difference from the baseline*'
        $m | Should -BeLike '*None returned*'
    }
}

Describe 'Invoke-GovernanceAudit.ps1 offline (saved scan, no activity)' {
    It 'writes the report and exits 1 on error findings, 0 with -FailOn none' {
        $out = Join-Path $TestDrive 'out'
        $script = Join-Path $script:Src 'Invoke-GovernanceAudit.ps1'
        $scan = Join-Path $script:Fx 'scan-result.json'
        & pwsh -NoProfile -File $script -ScanResultPath $scan -SkipActivity -OutDir $out -Date '2026-11-20' | Out-Null
        $LASTEXITCODE | Should -Be 1
        $md = Get-Content -Raw (Join-Path $out 'governance-2026-11-20.md')
        $md | Should -BeLike '*GV003*'
        $md | Should -BeLike '*## Activity*_Not run._*'
        @(Get-Content -Raw (Join-Path $out 'findings-2026-11-20.json') | ConvertFrom-Json).Count | Should -Be 12
        & pwsh -NoProfile -File $script -ScanResultPath $scan -SkipActivity -OutDir $out -Date '2026-11-20' -FailOn none | Out-Null
        $LASTEXITCODE | Should -Be 0
    }
}

Describe 'fixtures and sources stay fictional' {
    It 'uses only zero GUIDs, contoso and no real tenant name' {
        $text = (Get-ChildItem $script:Fx, (Join-Path $script:Src 'policy') -File -Recurse | ForEach-Object { Get-Content -Raw $_ }) -join "`n"
        $text += (Get-Content -Raw (Join-Path $script:Src 'PbiGovernance' 'PbiGovernance.psm1'))
        $guids = [regex]::Matches($text, '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}') | ForEach-Object { $_.Value } | Sort-Object -Unique
        foreach ($g in $guids) { $g | Should -BeLike '00000000-0000-0000-0000-*' }
        $text | Should -Not -Match '(?i)devladlog|onmicrosoft'
        ([regex]::Matches($text, '[\w.]+@([\w.]+)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique) | Should -Be @('contoso.com')
    }
}
